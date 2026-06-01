"""transcript.py — obtém a transcrição de um vídeo do YouTube.

Estratégia (em ordem):
  1. yt-dlp: baixa a FAIXA DE LEGENDAS oficial do YouTube (manual ou
     autogerada), em formato json3 (tem timestamps). É o caminho mais robusto
     — não depende do endpoint que a youtube-transcript-api raspa (e que o
     YouTube vem bloqueando por IP/rate-limit).
  2. youtube-transcript-api: fallback, caso o yt-dlp não ache legenda.
  3. Whisper (opcional, desligado por padrão): se NÃO houver legenda nenhuma e
     o usuário tiver habilitado, baixa o áudio e transcreve localmente. Não vem
     embutido (modelo + ffmpeg são pesados); ativa só se disponível.

Se nada funcionar, retorna {available: False} — o brain cai para
título+descrição. Zona cinzenta dos ToS do YouTube; uso pessoal apenas.
"""
import json
import urllib.request

# pt primeiro (inclui variantes/orig), depois en
PREFERRED_LANGS = [
    "pt", "pt-BR", "pt-PT", "pt-orig",
    "en", "en-US", "en-GB", "en-orig",
]


def _fmt_ts(seconds):
    seconds = int(seconds or 0)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


# --- 1) yt-dlp (faixa de legendas oficial) ---------------------------------
def _pick_json3_url(track_list):
    """De uma lista de formatos de uma legenda, devolve a URL do json3."""
    if not track_list:
        return None
    for fmt in track_list:
        if fmt.get("ext") == "json3" and fmt.get("url"):
            return fmt["url"]
    return None


def _choose_track(subtitles, automatic):
    """Escolhe a melhor legenda: manual nos idiomas preferidos, depois
    autogerada nos preferidos, depois qualquer pt/en."""
    for source in (subtitles, automatic):
        if not source:
            continue
        for lang in PREFERRED_LANGS:
            if lang in source:
                url = _pick_json3_url(source[lang])
                if url:
                    return url
        for lang, tracks in source.items():
            if any(lang.startswith(p) for p in ("pt", "en")):
                url = _pick_json3_url(tracks)
                if url:
                    return url
    return None


def _parse_json3(data):
    """json3 do YouTube → lista de segments {text, start, ts}."""
    segments = []
    for ev in data.get("events", []):
        segs = ev.get("segs") or []
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text:
            continue
        start = (ev.get("tStartMs", 0) or 0) / 1000.0
        segments.append({"text": text, "start": start, "ts": _fmt_ts(start)})
    return segments


def _via_ytdlp(video_id):
    """Deixa o PRÓPRIO yt-dlp baixar o arquivo de legenda (json3) para uma pasta
    temporária e então lê. Baixar a URL na mão falha: o YouTube agora exige um
    token (po_token) nessas URLs, que o yt-dlp resolve internamente."""
    import glob
    import os
    import tempfile

    try:
        from yt_dlp import YoutubeDL
    except Exception:
        return None

    tmp = tempfile.mkdtemp(prefix="clipeo_sub_")
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": PREFERRED_LANGS + ["pt.*", "en.*"],
        "subtitlesformat": "json3",
        "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception:
        pass  # mesmo com erro parcial, pode ter escrito um arquivo

    try:
        files = sorted(glob.glob(os.path.join(tmp, "*.json3")))
        # prioriza idioma preferido pela ordem do nome do arquivo
        def rank(path):
            base = os.path.basename(path)
            for i, lang in enumerate(PREFERRED_LANGS):
                if f".{lang}." in base:
                    return i
            return len(PREFERRED_LANGS)
        for path in sorted(files, key=rank):
            if os.path.getsize(path) < 10:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
            segments = _parse_json3(data)
            if segments:
                return segments
        return None
    except Exception:
        return None
    finally:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


# --- 2) youtube-transcript-api (fallback) ----------------------------------
def _via_api(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return None
    try:
        if hasattr(YouTubeTranscriptApi, "fetch") or not hasattr(
            YouTubeTranscriptApi, "get_transcript"
        ):
            raw = YouTubeTranscriptApi().fetch(video_id, languages=PREFERRED_LANGS)
        else:
            raw = YouTubeTranscriptApi.get_transcript(video_id, languages=PREFERRED_LANGS)
    except Exception:
        return None

    segments = []
    for item in raw:
        if isinstance(item, dict):
            text, start = item.get("text", ""), item.get("start", 0)
        else:
            text, start = getattr(item, "text", ""), getattr(item, "start", 0)
        if text:
            segments.append({"text": text, "start": start, "ts": _fmt_ts(start)})
    return segments or None


# --- 3) Whisper (opcional, desligado por padrão) ----------------------------
def _via_whisper(video_id, cfg):
    """Reserva: baixa o áudio e transcreve com Whisper local. Só roda se o
    usuário habilitar (config transcript.whisper.enabled) e as libs existirem.
    Não vem embutido no .app (modelo + ffmpeg são pesados)."""
    tcfg = (cfg or {}).get("transcript", {}).get("whisper", {})
    if not tcfg.get("enabled"):
        return None
    try:
        import os
        import tempfile

        from yt_dlp import YoutubeDL

        try:
            from faster_whisper import WhisperModel  # mais leve/rápido
            backend = "faster"
        except Exception:
            import whisper  # openai-whisper
            backend = "openai"

        tmp = tempfile.mkdtemp(prefix="clipeo_wh_")
        out = os.path.join(tmp, "%(id)s.%(ext)s")
        opts = {
            "skip_download": False,
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": out,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            ],
        }
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        audio = os.path.join(tmp, f"{video_id}.mp3")
        if not os.path.exists(audio):
            return None

        model_name = tcfg.get("model", "base")
        segments = []
        if backend == "faster":
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segs, _ = model.transcribe(audio)
            for s in segs:
                segments.append(
                    {"text": s.text.strip(), "start": s.start, "ts": _fmt_ts(s.start)}
                )
        else:
            model = whisper.load_model(model_name)
            res = model.transcribe(audio)
            for s in res.get("segments", []):
                segments.append(
                    {"text": s["text"].strip(), "start": s["start"], "ts": _fmt_ts(s["start"])}
                )
        return segments or None
    except Exception:
        return None


# --- API pública ------------------------------------------------------------
def get_transcript(video_id, cfg=None):
    """Retorna {available, text, segments, source}. segments é lista de
    {text, start, ts}. Em ausência total de legenda: {available: False, ...}."""
    source = None
    segments = _via_ytdlp(video_id)
    if segments:
        source = "yt-dlp"
    if not segments:
        segments = _via_api(video_id)
        if segments:
            source = "youtube-transcript-api"
    if not segments:
        segments = _via_whisper(video_id, cfg)
        if segments:
            source = "whisper"

    if not segments:
        return {"available": False, "text": None, "segments": [], "source": None}

    full_text = " ".join(s["text"] for s in segments).strip()
    return {
        "available": bool(full_text),
        "text": full_text or None,
        "segments": segments,
        "source": source,
    }


if __name__ == "__main__":
    import sys

    vid = sys.argv[1] if len(sys.argv) > 1 else "dQw4w9WgXcQ"
    r = get_transcript(vid)
    print(f"available={r['available']} source={r.get('source')} segments={len(r['segments'])}")
    if r["text"]:
        print(r["text"][:300], "…")
