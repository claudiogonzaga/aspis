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


# sinaliza, via atributo de módulo, se a última tentativa do yt-dlp bateu em
# bloqueio de IP (HTTP 429) — usado pela cascata para decidir cair no Whisper.
_last_blocked = False


def _ydl_opts_base():
    """Opções comuns: impersonar um navegador real (curl_cffi) reduz muito o
    429 nas URLs de legenda/mídia do YouTube. O yt-dlp exige um objeto
    ImpersonateTarget (não uma string)."""
    opts = {"quiet": True, "no_warnings": True}
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        opts["impersonate"] = ImpersonateTarget("chrome")
    except Exception:
        pass
    return opts


def _via_ytdlp(video_id):
    """Deixa o PRÓPRIO yt-dlp baixar o arquivo de legenda (json3/vtt) para uma
    pasta temporária e então lê. Baixar a URL na mão falha (po_token); o yt-dlp
    resolve internamente. Usa impersonation (curl_cffi) e pausa entre legendas
    para evitar o 429. Marca _last_blocked=True se o YouTube rate-limitar."""
    global _last_blocked
    _last_blocked = False
    import glob
    import os
    import shutil
    import tempfile

    try:
        from yt_dlp import YoutubeDL
    except Exception:
        return None

    tmp = tempfile.mkdtemp(prefix="aspis_sub_")
    opts = {
        **_ydl_opts_base(),
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": PREFERRED_LANGS + ["pt.*", "en.*"],
        "subtitlesformat": "json3/vtt/best",
        "sleep_interval_subtitles": 1,
        "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:
        if "429" in str(e) or "Too Many Requests" in str(e):
            _last_blocked = True
        # mesmo com erro parcial, pode ter escrito um arquivo

    try:
        files = glob.glob(os.path.join(tmp, "*.json3")) + glob.glob(
            os.path.join(tmp, "*.vtt")
        )

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
                raw = fh.read()
            if path.endswith(".json3"):
                segments = _parse_json3(json.loads(raw))
            else:
                segments = _parse_vtt(raw)
            if segments:
                return segments
        return None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_vtt(text):
    """WebVTT → lista de segments {text, start, ts}, deduplicando linhas
    repetidas (comum em legenda autogerada com rolagem)."""
    import re

    segments = []
    last = None
    cur_start = 0.0
    ts_re = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{3})\s*-->")
    for line in text.splitlines():
        m = ts_re.search(line)
        if m:
            h, mn, s, ms = (int(x) for x in m.groups())
            cur_start = h * 3600 + mn * 60 + s + ms / 1000.0
            continue
        if "-->" in line or line.strip() in ("WEBVTT", "") or line.startswith(
            ("Kind:", "Language:", "NOTE")
        ):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean != last:
            segments.append(
                {"text": clean, "start": cur_start, "ts": _fmt_ts(cur_start)}
            )
            last = clean
    return segments


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
    # Lê a config efetiva do Whisper (overlay do usuário em ~/.aspis/whisper.json
    # tem prioridade sobre o config.yaml).
    try:
        import config
        tcfg = config.get_whisper()
    except Exception:
        tcfg = (cfg or {}).get("transcript", {}).get("whisper", {})
    # Liga se: sempre (enabled) OU só quando o YouTube bloqueou as legendas por
    # IP (auto_on_block + _last_blocked). É o caminho de fallback automático.
    allow = tcfg.get("enabled") or (tcfg.get("auto_on_block", True) and _last_blocked)
    if not allow:
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

        tmp = tempfile.mkdtemp(prefix="aspis_wh_")
        out = os.path.join(tmp, "%(id)s.%(ext)s")
        opts = {
            **_ydl_opts_base(),
            "skip_download": False,
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
    {text, start, ts}. Em ausência total de legenda: {available: False, ...}.

    Cascata: 1) yt-dlp (legenda oficial, com impersonation); 2) se NÃO bloqueado
    por IP, tenta youtube-transcript-api; 3) Whisper local (se habilitado) — que
    é o caminho quando o YouTube rate-limita as legendas (429), pois baixa o
    áudio por um endpoint diferente e transcreve offline."""
    source = None
    segments = _via_ytdlp(video_id)
    if segments:
        source = "yt-dlp"

    # A youtube-transcript-api usa o MESMO endpoint de legenda; se o yt-dlp
    # tomou 429, ela também tomaria — pula direto pro Whisper.
    if not segments and not _last_blocked:
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
