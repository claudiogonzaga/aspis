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
        self._refreshing = False
        store.init()

    @property
    def threshold(self):
        # lido dinamicamente: reflete ajustes feitos nas Configurações
        import config

        return config.get_threshold()

    def get_threshold(self):
        import config

        return {"threshold": config.get_threshold()}

    def set_threshold(self, value):
        import config

        return {"ok": True, "threshold": config.set_threshold(value)}

    # --- leitura ---
    def get_videos(self, pillar=None, include_read=False):
        return store.get_videos(
            filter_pillar=pillar, min_score=self.threshold, include_read=include_read
        )

    def get_synthesis(self, video_id):
        return store.get_video(video_id)

    def new_count(self):
        # "novos" = acima do limiar e ainda não lidos
        return len(store.get_videos(min_score=self.threshold, include_read=False))

    def read_count(self):
        return store.count_read(self.threshold)

    def set_read(self, video_id, value=1):
        store.set_flag(video_id, "read", int(value))
        return {"ok": True}

    def refresh(self, max_total=25):
        """Botão Atualizar: roda o pipeline na hora (busca novos → sintetiza →
        grava) e devolve um resumo. Exige um canal do YouTube conectado e a
        chave do Gemini. Limita a `max_total` vídeos novos por clique."""
        if self._refreshing:
            return {"ok": False, "error": "Atualização já em andamento."}
        # pré-checagens amigáveis
        try:
            import accounts

            if not accounts.status().get("active"):
                return {"ok": False, "error": "Conecte um canal do YouTube primeiro."}
        except Exception:
            pass
        import keystore

        env, _ = self._llm_env()
        if not keystore.has(env):
            return {"ok": False, "error": "Configure a chave do Gemini primeiro."}

        self._refreshing = True
        try:
            import routine

            summary = routine.run(self.cfg, max_total=max_total)
            return {"ok": True, **summary}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        finally:
            self._refreshing = False

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

    # --- chave do LLM (Gemini) ---
    def _llm_env(self):
        """Nome da variável de ambiente da chave do provedor ativo."""
        llm = self.cfg.get("llm", {})
        prov = llm.get("provider", "gemini")
        pcfg = llm.get("providers", {}).get(prov, {})
        return pcfg.get("api_key_env", "GEMINI_API_KEY"), prov

    def gemini_status(self):
        import keystore

        env, prov = self._llm_env()
        return {"provider": prov, "env": env,
                "configured": keystore.has(env), "masked": keystore.masked(env)}

    def save_gemini_key(self, value):
        import keystore

        env, _ = self._llm_env()
        if not (value or "").strip():
            return {"ok": False, "error": "Cole a chave."}
        return keystore.set_key(env, value)

    def clear_gemini_key(self):
        import keystore

        env, _ = self._llm_env()
        keystore.set_key(env, "")
        return {"ok": True}

    # --- atualizações (GitHub) ---
    def check_update(self):
        import updater

        return updater.check()

    def install_update(self, dmg_url):
        import updater

        r = updater.install(dmg_url)
        if r.get("ok") and r.get("relaunch"):
            # fecha o app atual logo após disparar a abertura do novo
            def _quit():
                import time

                time.sleep(1.5)
                try:
                    webview.windows[0].destroy()
                except Exception:
                    pass
                os._exit(0)

            import threading

            threading.Thread(target=_quit, daemon=True).start()
        return r

    # --- Whisper (fallback de transcrição) ---
    def whisper_status(self):
        import config

        w = config.get_whisper()
        # marca quais modelos já estão baixados em cache local
        downloaded = set()
        try:
            import os

            hub = os.path.expanduser("~/.cache/huggingface/hub")
            if os.path.isdir(hub):
                for name in os.listdir(hub):
                    for m in config.WHISPER_MODELS:
                        tag = "large-v3" if m == "large-v3" else m
                        if f"faster-whisper-{tag}" in name:
                            downloaded.add(m)
        except Exception:
            pass
        return {
            "model": w.get("model", "base"),
            "enabled": w.get("enabled", False),
            "auto_on_block": w.get("auto_on_block", True),
            "models": config.WHISPER_MODELS,
            "downloaded": sorted(downloaded),
        }

    def save_whisper(self, model=None, enabled=None, auto_on_block=None):
        import config

        cfg = config.save_whisper(model=model, enabled=enabled, auto_on_block=auto_on_block)
        return {"ok": True, **cfg}

    # --- objetivos (pilares) editáveis, com peso ---
    def get_pilares(self):
        import config

        return [
            {"id": k, "nome": p.get("nome", k),
             "descricao": p.get("descricao", ""), "peso": p.get("peso", 3)}
            for k, p in config.get_pilares().items()
        ]

    def save_pilares(self, items):
        import re
        import unicodedata

        import config

        def slug(s):
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
            s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
            return s[:24] or "obj"

        prev = config.get_pilares()
        out = {}
        for it in (items or []):
            nome = (it.get("nome") or "").strip()
            if not nome:
                continue
            key = (it.get("id") or "").strip().lower() or slug(nome)
            base, n = key, 2
            while key in out:
                key = f"{base}-{n}"
                n += 1
            try:
                peso = int(it.get("peso", 3))
            except (TypeError, ValueError):
                peso = 3
            old = prev.get(it.get("id", ""), {})
            out[key] = {
                "nome": nome,
                "descricao": (it.get("descricao") or "").strip(),
                "quero": old.get("quero", []),
                "nao_quero": old.get("nao_quero", []),
                "peso": max(1, min(5, peso)),
            }
        if not out:
            return {"ok": False, "error": "Defina ao menos um objetivo."}
        config.save_pilares(out)
        return {"ok": True, "pilares": self.get_pilares()}


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
