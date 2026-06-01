"""Carregador de configuração compartilhado.

Lê config.yaml e expõe um dicionário simples, expandindo ~ em caminhos.

Locais (procurados nesta ordem):
  1. ~/.clipeo/config.yaml      → config "de produção", compartilhada entre o
                                   app empacotado (.app) e a rotina do launchd.
  2. config.yaml ao lado deste arquivo → template versionado no repositório.

O banco SQLite e o estado ficam SEMPRE em ~/.clipeo/clipeo.db, para que o .app
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

USER_DIR = os.path.expanduser("~/.clipeo")
USER_CONFIG = os.path.join(USER_DIR, "config.yaml")
USER_DB = os.path.join(USER_DIR, "clipeo.db")


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
    """Caminho efetivo da config. Se não houver uma em ~/.clipeo, semeia a
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
    raise FileNotFoundError("config.yaml não encontrado (nem em ~/.clipeo nem no projeto)")


@lru_cache(maxsize=1)
def load():
    with open(config_path(), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def db_path():
    """SQLite compartilhado em ~/.clipeo/clipeo.db."""
    os.makedirs(USER_DIR, exist_ok=True)
    return USER_DB


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


def get_pilares():
    """Pilares efetivos: ~/.clipeo/pilares.json se existir; senão os do
    config.yaml. Sempre com 'peso' normalizado."""
    if os.path.exists(USER_PILARES):
        try:
            with open(USER_PILARES, "r", encoding="utf-8") as fh:
                return _with_peso(json.load(fh))
        except (json.JSONDecodeError, OSError):
            pass
    return _with_peso(load().get("pilares", {}))


def save_pilares(pilares):
    """Persiste os objetivos editados pelo usuário em ~/.clipeo/pilares.json."""
    os.makedirs(USER_DIR, exist_ok=True)
    with open(USER_PILARES, "w", encoding="utf-8") as fh:
        json.dump(_with_peso(pilares), fh, ensure_ascii=False, indent=2)
