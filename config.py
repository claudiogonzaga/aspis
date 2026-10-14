"""Carregador de configuração compartilhado.

Lê config.yaml e expõe um dicionário simples, expandindo ~ em caminhos.

Locais (procurados nesta ordem):
  1. ~/.aspis/config.yaml      → config "de produção", compartilhada entre o
                                   app empacotado (.app) e a rotina do launchd.
  2. config.yaml ao lado deste arquivo → template versionado no repositório.

O banco SQLite e o estado ficam SEMPRE em ~/.aspis/aspis.db, para que o .app
(que só lê) e a rotina (que escreve) enxerguem o mesmo dado, não importa de onde
cada um seja executado.
"""
import json
import os
import shutil
from functools import lru_cache

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED_CONFIG = os.path.join(HERE, "config.yaml")

USER_DIR = os.path.expanduser("~/.aspis")
USER_CONFIG = os.path.join(USER_DIR, "config.yaml")
USER_DB = os.path.join(USER_DIR, "aspis.db")


def expand(path):
    """Expande ~ e variáveis de ambiente num caminho."""
    if not path:
        return path
    return os.path.expanduser(os.path.expandvars(path))


def _template_candidates():
    """Locais possíveis do config.yaml de template, em ordem de preferência.

    Dentro de um .app empacotado pelo py2app, os data_files vão para
    Contents/Resources, cujo caminho é exposto na env var RESOURCEPATH; o
    BUNDLED_CONFIG (ao lado deste .py) fica dentro do zip de libs e NÃO é um
    arquivo real, então precisamos olhar o RESOURCEPATH primeiro.
    """
    cands = []
    res = os.environ.get("RESOURCEPATH")
    if res:
        cands.append(os.path.join(res, "config.yaml"))
    cands.append(BUNDLED_CONFIG)
    return cands


def config_path():
    """Caminho efetivo da config. Se não houver uma em ~/.aspis, semeia a
    partir de um template (sem sobrescrever nada)."""
    if os.path.exists(USER_CONFIG):
        return USER_CONFIG
    for template in _template_candidates():
        if os.path.exists(template):
            try:
                os.makedirs(USER_DIR, exist_ok=True)
                shutil.copy2(template, USER_CONFIG)
                return USER_CONFIG
            except OSError:
                return template  # fallback: usa o template diretamente
    raise FileNotFoundError("config.yaml não encontrado (nem em ~/.aspis nem no projeto)")


@lru_cache(maxsize=1)
def load():
    with open(config_path(), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def db_path():
    """SQLite compartilhado em ~/.aspis/aspis.db."""
    os.makedirs(USER_DIR, exist_ok=True)
    return USER_DB


# --- fonte X (Twitter) ------------------------------------------------------
def get_x_config():
    """Bloco `x:` do config.yaml, com defaults garantidos. As contas a seguir,
    o teto de posts por execução e o piso de curtidas (filtro de ruído)."""
    x = (load().get("x", {}) or {})
    accounts = x.get("accounts") or []
    if isinstance(accounts, str):
        accounts = [a.strip() for a in accounts.split(",") if a.strip()]
    try:
        max_posts = int(x.get("max_posts_per_account", 20))
    except (TypeError, ValueError):
        max_posts = 20
    try:
        min_likes = int(x.get("min_likes", 0))
    except (TypeError, ValueError):
        min_likes = 0
    return {
        "accounts": [str(a).lstrip("@").strip() for a in accounts if str(a).strip()],
        "max_posts_per_account": max(1, max_posts),
        "min_likes": max(0, min_likes),
    }


# --- objetivos (pilares) editáveis pelo usuário -----------------------------
USER_PILARES = os.path.join(USER_DIR, "pilares.json")
DEFAULT_PESO = 3


def _with_peso(pilares):
    """Garante peso inteiro 1..5 (neutro=3) em cada pilar."""
    out = {}
    for k, p in (pilares or {}).items():
        p = dict(p or {})
        try:
            peso = int(p.get("peso", DEFAULT_PESO))
        except (TypeError, ValueError):
            peso = DEFAULT_PESO
        p["peso"] = max(1, min(5, peso))
        out[k] = p
    return out


# Pilar amplo (igual ao Aspis Android): conteúdo que ensina de verdade mas não
# cabe nos outros pilares deixa de cair em "nenhum" com nota baixa.
PILAR_APRENDIZADO = {
    "nome": "Curiosidade e aprendizado",
    "descricao": (
        "Aprender algo de verdade fora dos outros pilares: ciência, história, "
        "tecnologia, como as coisas funcionam, ideias bem argumentadas."
    ),
    "quero": ["explicações claras", "especialistas", "conteúdo com fontes",
              "ensaios bem argumentados"],
    "nao_quero": ["listas de curiosidades rasas", "react sem conteúdo", "polêmica vazia"],
    "peso": 2,
}


def _read_pilares():
    if os.path.exists(USER_PILARES):
        try:
            with open(USER_PILARES, "r", encoding="utf-8") as fh:
                return _with_peso(json.load(fh))
        except (json.JSONDecodeError, OSError):
            pass
    return _with_peso(load().get("pilares", {}))


def get_pilares():
    """Pilares efetivos: ~/.aspis/pilares.json se existir; senão os do
    config.yaml. Sempre com 'peso' normalizado.

    Migração única: os pilares ganham o pilar amplo 'aprendizado' (se o usuário
    apagá-lo depois, não volta)."""
    pilares = _read_pilares()
    prefs = _load_prefs()
    if not prefs.get("pillars_v2"):
        if "aprendizado" not in pilares:
            pilares["aprendizado"] = dict(PILAR_APRENDIZADO)
            save_pilares(pilares)
        prefs["pillars_v2"] = True
        _save_prefs(prefs)
    return pilares


def save_pilares(pilares):
    """Persiste os objetivos editados pelo usuário em ~/.aspis/pilares.json."""
    os.makedirs(USER_DIR, exist_ok=True)
    with open(USER_PILARES, "w", encoding="utf-8") as fh:
        json.dump(_with_peso(pilares), fh, ensure_ascii=False, indent=2)


# --- limiar de score, editável pelo usuário ---------------------------------
USER_PREFS = os.path.join(USER_DIR, "prefs.json")


def _load_prefs():
    p = {}
    if os.path.exists(USER_PREFS):
        try:
            with open(USER_PREFS, "r", encoding="utf-8") as fh:
                p = json.load(fh)
        except (json.JSONDecodeError, OSError):
            p = {}
    if not p.get("defaults_v2"):
        _migrate_defaults_v2(p)
    return p


def _migrate_defaults_v2(p):
    """Migração única (igual ao Android): quem ainda estava nos defaults antigos
    (Dia + nível 2), que deixavam o feed quase vazio, passa para os novos
    (Semana + nível 1); regras default antigas (nunca editadas) → as novas."""
    if p.get("period") == "day" and p.get("min_stars") == 2:
        p["period"] = DEFAULT_PERIOD
        p["min_stars"] = DEFAULT_MIN_STARS
    if p.get("rules") == LEGACY_DEFAULT_RULES:
        del p["rules"]
    p["defaults_v2"] = True
    try:
        _save_prefs(p)
    except OSError:
        pass


def _save_prefs(p):
    os.makedirs(USER_DIR, exist_ok=True)
    with open(USER_PREFS, "w", encoding="utf-8") as fh:
        json.dump(p, fh, ensure_ascii=False, indent=2)


# --- alinhamento (escala Likert 0–4) -----------------------------------------
# Faixas de score → nível de alinhamento. Limiares simétricos (passo 25), com o
# centro (nível 2) = score ≥ 50.
STAR_MIN_SCORE = {0: 0, 1: 25, 2: 50, 3: 75, 4: 90}

# Defaults de exibição (iguais ao Android). Alinhamento mínimo = nível 1 (25%):
# o feed mostra bastante e a régua aperta se o usuário quiser — começar no
# centro (50%) combinado com o período "Dia" deixava o feed quase vazio.
DEFAULT_MIN_STARS = 1
DEFAULT_PERIOD = "week"


def score_to_stars(score):
    """Converte score 0–100 no nível de alinhamento Likert 0–4."""
    s = max(0, min(100, int(score or 0)))
    stars = 0
    for k in (1, 2, 3, 4):
        if s >= STAR_MIN_SCORE[k]:
            stars = k
    return stars


def get_min_stars():
    """Nível mínimo de alinhamento para um vídeo aparecer (0–4)."""
    p = _load_prefs()
    if "min_stars" in p:
        try:
            return max(0, min(4, int(p["min_stars"])))
        except (TypeError, ValueError):
            pass
    return DEFAULT_MIN_STARS


def set_min_stars(value):
    p = _load_prefs()
    p["min_stars"] = max(0, min(4, int(value)))
    _save_prefs(p)
    return p["min_stars"]


def get_threshold():
    """Limiar de SCORE efetivo (derivado das estrelas mínimas)."""
    return STAR_MIN_SCORE[get_min_stars()]


# --- período (exibição + janela de busca) -----------------------------------
PERIODS = {"day": 36, "week": 24 * 7, "month": 24 * 30}  # horas de lookback
MAX_LOOKBACK_HOURS = 24 * 30  # busca cobre o tempo sem rodar, até 1 mês
AUTO_REFRESH_AFTER_HOURS = 2  # abrir o app → busca se a última foi há 2h+


def get_period():
    p = _load_prefs().get("period", DEFAULT_PERIOD)
    return p if p in PERIODS else DEFAULT_PERIOD


def set_period(value):
    p = _load_prefs()
    p["period"] = value if value in PERIODS else DEFAULT_PERIOD
    _save_prefs(p)
    return p["period"]


def period_lookback_hours():
    return PERIODS[get_period()]


# --- regras gerais da IA (texto livre, editável) ----------------------------
# Iguais ao Android: descontos GRADUAIS (a embalagem não condena um conteúdo
# bom — dá para "resgatar") e opinião não é defeito por si só.
DEFAULT_RULES = (
    "Sensacionalismo (rage bait, isca de engajamento, promessas vazias, FOMO, CAPS, "
    "emojis de alarme): marque is_clickbait e desconte aos poucos, conforme a "
    "intensidade (em geral 5 a 15 pontos). A embalagem não decide a nota: se o "
    "conteúdo entrega substância, a nota reflete a substância.\n"
    "Priorize densidade de informação acionável e evidência sobre popularidade.\n"
    "Opinião não é defeito: opinião qualificada (de quem entende do assunto, bem "
    "argumentada ou baseada em evidências) vale como conteúdo. Desconte só o achismo "
    "sem fundamento, e também aos poucos.\n"
    "Entretenimento sem relação com os pilares vai para 'nenhum' com nota baixa, "
    "mas sem zerar (em geral 10 a 20)."
)

# Regras default ANTERIORES — quem nunca as editou migra para as novas.
LEGACY_DEFAULT_RULES = (
    "Penalize sensacionalismo: rage bait, isca de engajamento, promessas vazias, "
    "FOMO, CAPS, emojis de alarme — marque is_clickbait e reduza o score.\n"
    "Priorize densidade de informação acionável e evidência sobre popularidade.\n"
    "Vídeos de pura opinião/entretenimento, sem valor para os objetivos, vão para "
    "'nenhum' com score baixo."
)


def get_rules():
    p = _load_prefs()
    return p.get("rules", DEFAULT_RULES)


def set_rules(text):
    p = _load_prefs()
    p["rules"] = (text or "").strip() or DEFAULT_RULES
    _save_prefs(p)
    return p["rules"]


# --- modelo do Whisper (fallback de transcrição), editável pelo usuário -----
USER_WHISPER = os.path.join(USER_DIR, "whisper.json")
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]


def get_whisper():
    """Config efetiva do Whisper: ~/.aspis/whisper.json se existir; senão a do
    config.yaml (transcript.whisper). Garante chaves model/enabled/auto_on_block."""
    base = (load().get("transcript", {}) or {}).get("whisper", {}) or {}
    cfg = {
        "enabled": bool(base.get("enabled", False)),
        "auto_on_block": bool(base.get("auto_on_block", True)),
        "model": base.get("model", "base"),
    }
    if os.path.exists(USER_WHISPER):
        try:
            with open(USER_WHISPER, "r", encoding="utf-8") as fh:
                cfg.update(json.load(fh))
        except (json.JSONDecodeError, OSError):
            pass
    if cfg.get("model") not in WHISPER_MODELS:
        cfg["model"] = "base"
    return cfg


def save_whisper(model=None, enabled=None, auto_on_block=None):
    """Persiste a config do Whisper escolhida pelo usuário."""
    cfg = get_whisper()
    if model is not None and model in WHISPER_MODELS:
        cfg["model"] = model
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if auto_on_block is not None:
        cfg["auto_on_block"] = bool(auto_on_block)
    os.makedirs(USER_DIR, exist_ok=True)
    with open(USER_WHISPER, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return cfg
