"""Clípeo — janela pywebview + ponte Python<->JS.

Milestone 2: a UI passa a ler do SQLite (store.py), preenchido pela rotina
(routine.py). As ações de leitura são reais; as ações de escrita do segundo
cérebro (Obsidian/Anki/download) marcam flags no banco e ganham execução de
verdade no Milestone 3.

Para demonstrar sem rodar o pipeline real:
    ./.venv/bin/python store.py --seed   # popula vídeos de exemplo
    ./.venv/bin/python app.py
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

import webview

import store
from config import load

UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")


class Api:
    """Ponte exposta ao JS como pywebview.api.*"""

    def __init__(self):
        self.cfg = load()
        self.threshold = self.cfg.get("score_threshold", 60)
        store.init()

    # --- leitura ---
    def get_videos(self, pillar=None):
        return store.get_videos(filter_pillar=pillar, min_score=self.threshold)

    def get_synthesis(self, video_id):
        return store.get_video(video_id)

    def new_count(self):
        return store.count_at_or_above(self.threshold)

    def filtered_count(self, day=None):
        return store.count_below(self.threshold, day=day)

    # --- ações ---
    def save_obsidian(self, video_id):
        # Execução real chega no Milestone 3 (obsidian.py). Por ora, registra o estado.
        try:
            import obsidian

            obsidian.save(video_id, self.cfg)
        except ImportError:
            print(f"[m2] save_obsidian({video_id}) — obsidian.py chega no M3")
        store.set_flag(video_id, "saved_obsidian", 1)
        return {"ok": True}

    def save_anki(self, video_id):
        try:
            import anki

            anki.save(video_id, self.cfg)
        except ImportError:
            print(f"[m2] save_anki({video_id}) — anki.py chega no M3")
        store.set_flag(video_id, "saved_anki", 1)
        return {"ok": True}

    def download(self, video_id):
        try:
            import download as dl

            dl.download(video_id, self.cfg)
        except ImportError:
            print(f"[m2] download({video_id}) — download.py chega no M3")
        store.set_flag(video_id, "downloaded", 1)
        return {"ok": True}

    def watch(self, video_id):
        """Abre o arquivo LOCAL no player do sistema — nunca o YouTube."""
        v = store.get_video(video_id)
        try:
            import download as dl

            path = dl.local_path(video_id, self.cfg) if hasattr(dl, "local_path") else None
            if not v or not v.get("downloaded") or not path or not os.path.exists(path):
                dl.download(video_id, self.cfg)
                path = dl.local_path(video_id, self.cfg)
            store.set_flag(video_id, "downloaded", 1)
            subprocess.run(["open", path], check=False)
            return {"ok": True, "path": path}
        except ImportError:
            print(f"[m2] watch({video_id}) — download/player chega no M3")
            return {"ok": False, "reason": "m3"}

    def set_feedback(self, video_id, value):
        store.set_flag(video_id, "feedback", int(value))
        return {"ok": True}

    # --- conta do YouTube (login multi-canal dentro do app) ---
    def yt_status(self):
        import accounts

        return accounts.status()

    def yt_save_client(self, text):
        """Salva a credencial OAuth colada pelo usuário."""
        import accounts

        return accounts.save_client(text)

    def yt_connect(self):
        """Abre o navegador para o usuário logar e escolher a conta/canal.
        Bloqueia até concluir; devolve o canal conectado ou erro."""
        import accounts

        return accounts.connect()

    def yt_set_active(self, channel_id):
        import accounts

        return accounts.set_active(channel_id)

    def yt_remove(self, channel_id):
        import accounts

        return accounts.remove(channel_id)

    def yt_reset_client(self):
        import accounts

        return accounts.clear_client()


def main():
    if not os.path.exists(UI_PATH):
        print(f"UI não encontrada em {UI_PATH}", file=sys.stderr)
        sys.exit(1)
    webview.create_window(
        "Clípeo",
        UI_PATH,
        js_api=Api(),
        width=720,
        height=820,
        min_size=(560, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
