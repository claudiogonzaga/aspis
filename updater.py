"""updater.py — verifica e instala atualizações do Clípeo a partir do GitHub.

Segurança: o updater só consulta e baixa do repositório OFICIAL (definido em
version.py), sempre por HTTPS. Nunca segue URLs vindas de outro lugar.

Fluxo:
  check()   → consulta a última release (GitHub API), compara com a versão local
  install() → baixa o .dmg do asset, monta, copia o .app para /Applications,
              desmonta e reabre o app novo.
"""
import json
import os
import plistlib
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.request

import version

API_URL = (
    f"https://api.github.com/repos/{version.GITHUB_OWNER}/"
    f"{version.GITHUB_REPO}/releases/latest"
)
_DMG_HOST_RE = re.compile(
    r"^https://github\.com/|^https://objects\.githubusercontent\.com/|"
    r"^https://release-assets\.githubusercontent\.com/"
)


def _parse_ver(s):
    """'v1.2.3' / '1.2.3' → (1,2,3) para comparação numérica."""
    s = (s or "").lstrip("vV")
    parts = re.findall(r"\d+", s)
    return tuple(int(p) for p in parts[:3]) + (0,) * (3 - len(parts[:3]))


def _http_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Clipeo/{version.__version__}",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check():
    """Consulta a última release. Retorna dict para a UI:
    {ok, current, latest, update_available, notes, dmg_url, name} ou {ok:False,error}."""
    try:
        data = _http_json(API_URL)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Não foi possível consultar atualizações: {e}"}

    tag = data.get("tag_name") or ""
    latest = _parse_ver(tag)
    current = _parse_ver(version.__version__)

    dmg_url = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if name.lower().endswith(".dmg") and _DMG_HOST_RE.match(url):
            dmg_url = url
            break

    return {
        "ok": True,
        "current": version.__version__,
        "latest": tag.lstrip("vV"),
        "update_available": latest > current and dmg_url is not None,
        "notes": (data.get("body") or "").strip()[:1500],
        "dmg_url": dmg_url,
        "name": data.get("name") or tag,
    }


def _download(url, dest):
    if not _DMG_HOST_RE.match(url):
        raise ValueError("URL de download não confiável (fora do GitHub).")
    req = urllib.request.Request(url, headers={"User-Agent": f"Clipeo/{version.__version__}"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def _current_app_path():
    """Caminho do .app em execução (…/Clipeo.app)."""
    # RESOURCEPATH = …/Clipeo.app/Contents/Resources
    res = os.environ.get("RESOURCEPATH")
    if res:
        app = os.path.dirname(os.path.dirname(res))
        if app.endswith(".app"):
            return app
    return None


def install(dmg_url):
    """Baixa o .dmg, monta, copia o .app para /Applications, desmonta e reabre.
    Retorna {ok, installed_path} ou {ok:False, error}.

    Observação: instalar em /Applications pode exigir senha de admin se a pasta
    não for gravável pelo usuário — nesse caso, devolvemos uma mensagem clara
    pedindo a instalação manual (arrastar do dmg)."""
    if not dmg_url or not _DMG_HOST_RE.match(dmg_url):
        return {"ok": False, "error": "URL de atualização inválida."}

    tmp = tempfile.mkdtemp(prefix="clipeo_upd_")
    dmg = os.path.join(tmp, "update.dmg")
    mount = os.path.join(tmp, "mnt")
    os.makedirs(mount, exist_ok=True)
    try:
        _download(dmg_url, dmg)

        # monta sem registrar no Finder
        subprocess.run(
            ["hdiutil", "attach", dmg, "-nobrowse", "-mountpoint", mount],
            check=True, capture_output=True, text=True,
        )
        try:
            src = None
            for name in os.listdir(mount):
                if name.endswith(".app"):
                    src = os.path.join(mount, name)
                    break
            if not src:
                return {"ok": False, "error": "O .dmg não contém um app."}

            app_name = os.path.basename(src)
            dest = os.path.join("/Applications", app_name)

            # se /Applications não for gravável, instrui instalação manual
            if not os.access("/Applications", os.W_OK):
                return {
                    "ok": False,
                    "needs_manual": True,
                    "error": "Não foi possível escrever em /Aplicativos automaticamente. "
                             "Abra o .dmg e arraste o Clípeo para Aplicativos.",
                }

            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src, dest, symlinks=True)
        finally:
            subprocess.run(["hdiutil", "detach", mount, "-force"],
                           capture_output=True, text=True)

        # reabre o app novo (substitui o em execução) e agenda fechamento do atual
        subprocess.Popen(["open", "-n", dest])
        return {"ok": True, "installed_path": dest, "relaunch": True}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"Falha ao montar o .dmg: {e.stderr or e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
