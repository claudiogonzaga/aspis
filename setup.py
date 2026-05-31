"""Empacotamento do Clípeo como app de macOS (.app) via py2app.

Build:
    ./.venv/bin/python setup.py py2app          # build completo (distribuível)
    ./.venv/bin/python setup.py py2app -A       # alias mode (rápido, p/ teste)

O .app resultante (em dist/) é a INTERFACE: lê o SQLite em ~/.clipeo/clipeo.db e
executa as ações dos botões (Obsidian, Anki, Baixar, Assistir). O pipeline diário
(routine.py: YouTube + LLM) roda separado, pelo launchd usando o venv — por isso
não embrulhamos google-genai/anthropic/googleapiclient aqui (bundle enxuto).
"""
from setuptools import setup

APP = ["app.py"]

DATA_FILES = [
    ("ui", ["ui/index.html"]),
    ("", ["config.yaml"]),
]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Clípeo",
        "CFBundleDisplayName": "Clípeo",
        "CFBundleIdentifier": "com.clipeo.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        # app de janela normal (não agente de menu-bar)
        "LSUIElement": False,
    },
    # dependências de runtime do APP (não do pipeline)
    "packages": ["webview", "yaml", "yt_dlp"],
    "includes": ["config", "store", "obsidian", "anki", "download"],
    # o pipeline (e suas libs pesadas) roda fora do .app, pelo launchd
    "excludes": [
        "brain", "youtube", "transcript", "routine",
        "google", "googleapiclient", "google_auth_oauthlib",
        "anthropic", "youtube_transcript_api",
        "tkinter", "test", "tests",
    ],
}

setup(
    app=APP,
    name="Clípeo",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
