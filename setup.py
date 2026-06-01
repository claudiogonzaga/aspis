"""Empacotamento do Clípeo como app de macOS (.app) via py2app.

Build:
    ./.venv/bin/python setup.py py2app          # build completo (distribuível)
    ./.venv/bin/python setup.py py2app -A       # alias mode (rápido, p/ teste)

O .app resultante (em dist/) é a INTERFACE: lê o SQLite em ~/.clipeo/clipeo.db e
executa as ações dos botões (Obsidian, Anki, Baixar, Assistir). O pipeline diário
(routine.py: YouTube + LLM) roda separado, pelo launchd usando o venv — por isso
não embrulhamos google-genai/anthropic/googleapiclient aqui (bundle enxuto).
"""
import os

from setuptools import setup

APP = ["app.py"]

DATA_FILES = [
    ("ui", ["ui/index.html"]),
    ("", ["config.yaml"]),
]

# Credencial OAuth do app (não versionada): se presente, embute no bundle
# para que o usuário final apenas clique "Conectar com o Google".
if os.path.exists("assets/oauth_client.json"):
    DATA_FILES.append(("", ["assets/oauth_client.json"]))

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "clipeo.icns",
    "plist": {
        # CFBundleName em ASCII define o nome do bundle/executável (py2app usa
        # este campo) — acento aqui quebraria o codesign. O nome bonito com
        # acento aparece no Finder/janela via CFBundleDisplayName.
        "CFBundleName": "Clipeo",
        "CFBundleDisplayName": "Clípeo",
        "CFBundleIdentifier": "com.clipeo.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleIconFile": "clipeo.icns",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        # app de janela normal (não agente de menu-bar)
        "LSUIElement": False,
    },
    # dependências de runtime do APP. Agora o LOGIN do YouTube acontece dentro
    # do app (accounts.py), então as libs do Google OAuth precisam ir no bundle.
    # OBS: NÃO forçar "google" aqui — é namespace package (sem __init__.py) e
    # o py2app quebra ao tentar resolvê-lo. O modulegraph puxa google.auth /
    # google.oauth2 sozinho ao rastrear os imports de accounts.py.
    "packages": [
        "webview", "yaml", "yt_dlp",
        # Google OAuth + YouTube Data API (login multi-canal no app)
        "googleapiclient", "google_auth_oauthlib",
        "httplib2", "oauthlib", "requests_oauthlib", "uritemplate",
        "requests", "certifi", "charset_normalizer", "idna", "urllib3",
        "pyasn1", "pyasn1_modules",
        # botão Atualizar (pipeline embarcado): transcrições + LLM (google-genai)
        "youtube_transcript_api", "defusedxml",
        "curl_cffi",  # impersonation de navegador → reduz HTTP 429 nas legendas
        "websockets", "pydantic", "pydantic_core",
        "httpx", "httpcore", "anyio", "sniffio", "h11",
        # Whisper local (fallback quando o YouTube bloqueia as legendas por IP)
        "faster_whisper", "ctranslate2", "av", "tokenizers",
        "huggingface_hub", "tqdm",
    ],
    "includes": [
        "config", "store", "accounts", "keystore", "obsidian", "anki", "download",
        # pipeline embarcado para o botão Atualizar rodar dentro do app
        "youtube", "transcript", "brain", "routine",
        # módulos pontuais (dotted/soltos) — namespace google NÃO entra em packages
        "google.auth.transport.requests", "google.oauth2.credentials",
        "google.genai", "google_auth_oauthlib.flow", "google_auth_httplib2",
        "googleapiclient.discovery",
    ],
    "excludes": [
        # provedor desligado (brain importa anthropic de forma tardia só se ativado)
        "anthropic",
        "tkinter", "test", "tests",
    ],
}

# IMPORTANTE: o nome do bundle/executável é ASCII ("Clipeo") de propósito.
# Um nome com acento ("Clípeo") quebra o codesign (divergência de
# normalização Unicode NFC/NFD no nome do executável), deixando o selo
# inválido — o que o Gatekeeper, sob quarentena, reporta como "danificado".
# O nome bonito com acento aparece via CFBundleName/CFBundleDisplayName.
setup(
    app=APP,
    name="Clipeo",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
