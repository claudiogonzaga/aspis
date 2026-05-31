"""routine.py — job agendado (launchd). Orquestra, idempotente:

  1. lê last_run (default: lookback_hours atrás)
  2. youtube: inscrições → uploads → vídeos novos → hidrata
  3. para cada vídeo ainda não no banco: transcript → brain → store.upsert
  4. (M3) escreve/atualiza a nota-digest do dia no Obsidian
  5. atualiza last_run = agora

Rodar duas vezes no mesmo dia NÃO reprocessa vídeos já no banco (cache por
video_id) nem refaz chamadas de LLM.
"""
import sys
import traceback
from datetime import datetime, timedelta, timezone

import store
from config import load


def _since(cfg):
    last = store.get_meta("last_run")
    if last:
        try:
            return datetime.fromisoformat(last)
        except ValueError:
            pass
    hours = cfg.get("lookback_hours", 36)
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def run(cfg=None):
    cfg = cfg or load()
    store.init()
    started = datetime.now(timezone.utc)
    since = _since(cfg)
    print(f"[routine] início {started.isoformat()} | buscando desde {since.isoformat()}")

    # imports tardios para não exigir as libs quando só se usa o app/seed
    import youtube
    import transcript as transcript_mod
    import brain

    videos = youtube.fetch_new_videos(since, cfg)
    print(f"[routine] {len(videos)} vídeos novos retornados pela API")

    processed = filtered = skipped = errors = 0
    threshold = cfg.get("score_threshold", 60)

    for v in videos:
        vid = v["video_id"]
        if store.has_video(vid):
            skipped += 1
            continue
        try:
            tr = transcript_mod.get_transcript(vid)
            analysis = brain.analyze(v, tr, cfg)
            row = {
                "video_id": vid,
                "channel": v.get("channel", ""),
                "channel_id": v.get("channel_id", ""),
                "original_title": v.get("title", ""),
                "neutral_title": analysis["neutral_title"],
                "url": v.get("url", ""),
                "published_at": v.get("published_at", ""),
                "duration": v.get("duration", ""),
                "pillar": analysis["pillar"],
                "score": analysis["score"],
                "is_clickbait": analysis["is_clickbait"],
                "resumo": analysis["resumo"],
                "pontos_chave": analysis["pontos_chave"],
                "fatos": analysis["fatos"],
                "citacoes": analysis["citacoes"],
                "transcript_available": 1 if tr.get("available") else 0,
            }
            store.upsert_video(row)
            processed += 1
            if analysis["score"] < threshold:
                filtered += 1
        except Exception as e:  # nunca derrube a rotina inteira por 1 vídeo
            errors += 1
            print(f"[routine] erro no vídeo {vid}: {e}", file=sys.stderr)
            traceback.print_exc()

    # passo 4 (M3): nota-digest do dia no Obsidian, se o módulo existir
    try:
        import obsidian

        if hasattr(obsidian, "write_daily_digest"):
            obsidian.write_daily_digest(cfg)
            print("[routine] digest diário do Obsidian atualizado")
    except ImportError:
        pass  # obsidian.py chega no Milestone 3
    except Exception as e:
        print(f"[routine] aviso: digest do Obsidian falhou: {e}", file=sys.stderr)

    store.set_meta("last_run", started.isoformat())
    print(
        f"[routine] fim | novos={processed} já_no_banco={skipped} "
        f"abaixo_do_limiar={filtered} erros={errors}"
    )


if __name__ == "__main__":
    run()
