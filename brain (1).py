"""brain.py — o coração. UMA chamada de LLM por vídeo produz um objeto
estruturado: pilar, score, título neutro, resumo, pontos-chave, fatos para o
Anki e citações. Isolado aqui para ser trocável.

Custo: o system prompt (regras + perfis dos pilares) é estável entre vídeos, então
usamos prompt caching da Anthropic para pagá-lo uma vez por janela de cache.
"""
import json
import os

import anthropic

from config import load

# ----------------------------------------------------------------------------
SYSTEM_RULES = """Você é um curador a serviço dos objetivos de vida do usuário (os "pilares" \
descritos abaixo). Sua tarefa é avaliar UM vídeo do YouTube e devolver um JSON \
estrito, em português, com a análise.

Regras:
- Classifique o vídeo no pilar mais alinhado, ou "nenhum" se não servir a nenhum.
- Dê um score 0–100 de alinhamento aos objetivos do usuário (quanto realmente \
entrega de valor para os pilares, não quão popular é).
- Penalize sensacionalismo: rage bait, isca de engajamento, promessas vazias, \
FOMO, CAPS, emojis de alarme. Nesses casos marque is_clickbait=true e reduza o score.
- neutral_title: reescreva o título para algo neutro e informativo (o que o vídeo \
realmente entrega), SEM CAPS, SEM emoji, SEM isca. Sentence case.
- resumo: 2 a 4 frases.
- pontos_chave: pontos acionáveis (pode ser lista vazia se não houver).
- fatos_para_memorizar: SÓ inclua conhecimento atômico e testável (fatos, \
definições, princípios). Se o vídeo for opinião/narrativa, devolva lista vazia — \
não polua o Anki. Pode ser vazio mesmo em vídeos bons. Use {"tipo":"basic","frente":..,"verso":..} \
ou {"tipo":"cloze","texto":"... {{c1::lacuna}} ..."}.
- citacoes: trechos curtos com timestamp "mm:ss" (use os timestamps da transcrição \
quando houver). Lista vazia se não houver transcrição.
- Se NÃO houver transcrição, ranqueie e reescreva o título usando título+descrição, \
e deixe claro no resumo que ele é baseado só em metadados.

Responda APENAS com o JSON, sem texto antes ou depois, neste formato exato:
{
  "pillar": "saude | investimento | paternidade | nenhum",
  "score": 0,
  "is_clickbait": false,
  "neutral_title": "",
  "resumo": "",
  "pontos_chave": [],
  "fatos_para_memorizar": [],
  "citacoes": [{"texto": "", "timestamp": "mm:ss"}]
}"""


def _pillars_block(pilares):
    linhas = ["Pilares do usuário:"]
    for key, p in pilares.items():
        linhas.append(
            f"- {key} ({p.get('nome','')}): {p.get('descricao','')}\n"
            f"    quero: {', '.join(p.get('quero', []))}\n"
            f"    não quero: {', '.join(p.get('nao_quero', []))}"
        )
    return "\n".join(linhas)


def _client(cfg):
    key = os.environ.get(cfg["llm"].get("api_key_env", "ANTHROPIC_API_KEY"))
    if not key:
        raise RuntimeError(
            f"Variável de ambiente {cfg['llm'].get('api_key_env')} não definida. "
            "Exporte a chave da Anthropic antes de rodar a rotina."
        )
    return anthropic.Anthropic(api_key=key)


def _build_user_message(video, transcript, cfg):
    parts = [
        f"Título original: {video.get('title','')}",
        f"Canal: {video.get('channel','')}",
        f"Duração: {video.get('duration','')}",
        f"Descrição:\n{(video.get('description') or '')[:2000]}",
    ]
    if transcript and transcript.get("available") and transcript.get("text"):
        limit = cfg["llm"].get("max_transcript_chars", 14000)
        # incluímos alguns timestamps de referência para ancorar citações
        text = transcript["text"][:limit]
        parts.append(f"\nTranscrição (pode estar truncada):\n{text}")
        # amostra de marcações de tempo para o modelo citar mm:ss
        marks = [f'{s["ts"]}: {s["text"]}' for s in transcript["segments"][:40]]
        if marks:
            parts.append("\nReferências de timestamp (início da transcrição):\n" + "\n".join(marks))
    else:
        parts.append("\n[Sem transcrição disponível — avalie por título e descrição.]")
    return "\n".join(parts)


def _coerce(obj, video):
    """Normaliza o JSON do modelo para o formato que o store espera."""
    pillar = obj.get("pillar", "nenhum")
    if pillar not in ("saude", "investimento", "paternidade", "nenhum"):
        pillar = "nenhum"
    try:
        score = int(round(float(obj.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    return {
        "pillar": pillar,
        "score": score,
        "is_clickbait": 1 if obj.get("is_clickbait") else 0,
        "neutral_title": (obj.get("neutral_title") or video.get("title") or "").strip(),
        "resumo": (obj.get("resumo") or "").strip(),
        "pontos_chave": obj.get("pontos_chave") or [],
        "fatos": obj.get("fatos_para_memorizar") or [],
        "citacoes": obj.get("citacoes") or [],
    }


def _parse_json(text):
    """Parse tolerante: tenta direto, depois recorta do primeiro { ao último }."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j != -1 and j > i:
        return json.loads(text[i : j + 1])
    raise ValueError("resposta do LLM não continha JSON válido")


def analyze(video, transcript, cfg=None, max_retries=2):
    """Analisa um único vídeo. `video` é dict com title/channel/description/
    duration. `transcript` é o dict de transcript.get_transcript (ou None).
    Retorna o dict normalizado pronto para store.upsert_video."""
    cfg = cfg or load()
    client = _client(cfg)
    model = cfg["llm"]["model"]
    pillars_block = _pillars_block(cfg["pilares"])
    user_msg = _build_user_message(video, transcript, cfg)

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1500,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_RULES + "\n\n" + pillars_block,
                        # cache do bloco estável (regras + pilares) entre vídeos
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
            )
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            )
            obj = _parse_json(text)
            return _coerce(obj, video)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e  # JSON inválido → tenta de novo
            continue
    raise RuntimeError(f"brain.analyze falhou após {max_retries+1} tentativas: {last_err}")
