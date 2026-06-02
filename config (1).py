"""Carregador de configuração compartilhado.

Lê config.yaml (ao lado deste arquivo), expande ~ em caminhos e expõe um
dicionário simples. Mantido minúsculo de propósito — é só cola entre módulos.
"""
import os
from functools import lru_cache

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.yaml")


def expand(path):
    """Expande ~ e variáveis de ambiente num caminho."""
    if not path:
        return path
    return os.path.expanduser(os.path.expandvars(path))


@lru_cache(maxsize=1)
def load():
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg


def db_path():
    """SQLite mora ao lado do código, em escudo.db."""
    return os.path.join(HERE, "escudo.db")
