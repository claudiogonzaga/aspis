"""download.py — baixa o vídeo (yt-dlp) para a pasta sincronizada.

Só sob ação explícita do usuário, nunca em lote automático. Zona cinzenta dos
ToS do YouTube; uso pessoal. O arquivo vai para download.folder (sincronizada
via Syncthing/Drive com o Android). watch() no app abre esse arquivo LOCAL no
player do sistema — jamais o YouTube, para não reintroduzir o feed.
"""
import os
import re

import store
from config import expand, load


def _sanitize(name, max_len=80):
    name = re.sub(r"[\\/:*?\"<>|]", "", name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name[:max_len].strip() or "video"


def _folder(cfg):
    folder = expand(cfg["download"]["folder"])
    os.makedirs(folder, exist_ok=True)
    return folder


def _basename(cfg, v):
    return f"{_sanitize(v['neutral_title'])} [{v['video_id']}]"


def local_path(video_id, cfg=None):
    """Caminho .mp4 esperado para o vídeo (exista ou não ainda)."""
    cfg = cfg or load()
    v = store.get_video(video_id)
    if not v:
        raise ValueError(f"vídeo {video_id} não está no banco")
    return os.path.join(_folder(cfg), _basename(cfg, v) + ".mp4")


def is_downloaded(video_id, cfg=None):
    try:
        return os.path.exists(local_path(video_id, cfg))
    except ValueError:
        return False


def _ffmpeg_path():
    """Acha o ffmpeg mesmo quando o app é aberto pelo Finder/Dock (PATH mínimo,
    sem /opt/homebrew/bin). Retorna o caminho do binário ou None."""
    import shutil

    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (
        "/opt/homebrew/bin/ffmpeg",   # Apple Silicon (Homebrew)
        "/usr/local/bin/ffmpeg",      # Intel (Homebrew)
        "/opt/local/bin/ffmpeg",      # MacPorts
    ):
        if os.path.exists(cand):
            return cand
    return None


def _impersonate():
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget("chrome")
    except Exception:
        return None


def download(video_id, cfg=None):
    """Baixa o melhor mp4 para a pasta sincronizada. Retorna o caminho final.
    Idempotente: se o arquivo já existe, não rebaixa.

    Se houver ffmpeg, baixa a melhor faixa de vídeo+áudio e junta (qualidade
    máxima). Sem ffmpeg, cai para um arquivo MP4 progressivo único (não precisa
    de merge) — pior qualidade, mas funciona em qualquer máquina."""
    import yt_dlp

    cfg = cfg or load()
    v = store.get_video(video_id)
    if not v:
        raise ValueError(f"vídeo {video_id} não está no banco")

    out_base = os.path.join(_folder(cfg), _basename(cfg, v))
    final_path = out_base + ".mp4"
    if os.path.exists(final_path):
        store.set_flag(video_id, "downloaded", 1)
        return final_path

    url = v.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    ffmpeg = _ffmpeg_path()

    ydl_opts = {
        "outtmpl": out_base + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    imp = _impersonate()
    if imp is not None:
        ydl_opts["impersonate"] = imp

    if ffmpeg:
        ydl_opts["ffmpeg_location"] = ffmpeg
        ydl_opts["format"] = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        )
        ydl_opts["merge_output_format"] = "mp4"
    else:
        # progressivo: já vem com vídeo+áudio num único arquivo (sem merge)
        ydl_opts["format"] = (
            "best[ext=mp4][acodec!=none][vcodec!=none]/"
            "best[acodec!=none][vcodec!=none]/best"
        )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # o arquivo final pode ter outra extensão se não houve merge
    if not os.path.exists(final_path):
        guess = ydl.prepare_filename(info)
        if os.path.exists(guess):
            final_path = guess

    store.set_flag(video_id, "downloaded", 1)
    return final_path


if __name__ == "__main__":
    import sys

    store.init()
    vid = sys.argv[1] if len(sys.argv) > 1 else None
    if not vid:
        print("uso: python download.py <video_id>")
    else:
        print("baixado em:", download(vid))
