"""keystore.py — chaves de API coladas no app, compartilhadas com a rotina.

As chaves ficam em ~/.aspis/secrets.json (permissão 0600), indexadas pelo nome
da variável de ambiente correspondente (ex.: "GEMINI_API_KEY"). Tanto o app
(onde o usuário cola a chave) quanto a rotina do launchd (que chama o LLM) leem
daqui.

Resolução: secrets.json tem prioridade; se não houver, cai na variável de
ambiente de mesmo nome (continua funcionando para quem prefere exportar).

NB: o nome do módulo NÃO é "secrets" de propósito — isso sombrearia o módulo
`secrets` da biblioteca padrão (usado pelo oauthlib no fluxo OAuth).
"""
import json
import os

import config

SECRETS_PATH = os.path.join(config.USER_DIR, "secrets.json")


def _load():
    if not os.path.exists(SECRETS_PATH):
        return {}
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data):
    os.makedirs(config.USER_DIR, exist_ok=True)
    with open(SECRETS_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def get(name):
    """Valor da chave: secrets.json tem prioridade; senão variável de ambiente."""
    val = _load().get(name)
    return val if val else os.environ.get(name)


def set_key(name, value):
    """Salva (ou remove, se vazio) a chave. Retorna {'ok':bool}."""
    value = (value or "").strip()
    data = _load()
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    _save(data)
    return {"ok": True}


def has(name):
    return bool(get(name))


def masked(name):
    """Versão mascarada (só os 4 últimos) para exibir na UI, nunca a chave inteira."""
    v = get(name) or ""
    if not v:
        return ""
    return ("••••" + v[-4:]) if len(v) > 4 else "••••"
