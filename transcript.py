"""transcript.py — obtém a transcrição de um vídeo do YouTube.

Usa youtube-transcript-api (legendas manuais ou autogeradas). Se não houver
legenda, retorna {available: False} com elegância — o brain cai para
título+descrição. Zona cinzenta dos ToS do YouTube; uso pessoal apenas.

Suporta tanto a API nova (1.x, baseada em instância: fetch/list) quanto a
antiga (0.6.x, métodos estáticos), escolhendo automaticamente.
"""
from youtube_transcript_api import YouTubeTranscriptApi

try:  # nomes/posições mudam entre versões — degrade com elegância
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
except ImportError:
    class TranscriptsDisabled(Exception):
        pass

    class NoTranscriptFound(Exception):
        pass

PREFERRED_LANGS = ["pt", "pt-BR", "en"]


def _fmt_ts(seconds):
    seconds = int(seconds or 0)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def _snippet_fields(item):
    """Extrai (text, start) de um item, seja dict (0.6.x) ou objeto (1.x)."""
    if isinstance(item, dict):
        return item.get("text", ""), item.get("start", 0)
    return getattr(item, "text", ""), getattr(item, "start", 0)


def _fetch_raw(video_id):
    """Devolve um iterável de snippets, tentando a API nova e depois a antiga."""
    # API 1.x: instância com .fetch()
    if hasattr(YouTubeTranscriptApi, "fetch") or not hasattr(
        YouTubeTranscriptApi, "get_transcript"
    ):
        ytt = YouTubeTranscriptApi()
        return ytt.fetch(video_id, languages=PREFERRED_LANGS)
    # API 0.6.x: método estático
    return YouTubeTranscriptApi.get_transcript(video_id, languages=PREFERRED_LANGS)


def get_transcript(video_id):
    """Retorna {available, text, segments} onde segments é lista de
    {text, start, ts}. Em ausência de legenda: {available: False, ...}."""
    try:
        raw = _fetch_raw(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        return {"available": False, "text": None, "segments": []}
    except Exception:
        # qualquer outra falha (rede, idioma indisponível, parsing): não quebre.
        return {"available": False, "text": None, "segments": []}

    segments = []
    for item in raw:
        text, start = _snippet_fields(item)
        segments.append({"text": text, "start": start, "ts": _fmt_ts(start)})

    full_text = " ".join(s["text"] for s in segments).strip()
    return {"available": bool(full_text), "text": full_text or None, "segments": segments}


if __name__ == "__main__":
    import sys

    vid = sys.argv[1] if len(sys.argv) > 1 else "dQw4w9WgXcQ"
    r = get_transcript(vid)
    print(f"available={r['available']} segments={len(r['segments'])}")
    if r["text"]:
        print(r["text"][:300], "…")
