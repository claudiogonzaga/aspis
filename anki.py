"""anki.py — cria cards no Anki a partir de fatos_para_memorizar.

Usa o add-on AnkiConnect (HTTP em http://localhost:8765). O Anki desktop precisa
estar aberto com o add-on instalado. Se não houver fatos, não faz nada. Se o
Anki estiver fechado, levanta erro com mensagem clara.

Tipos de fato:
  {"tipo":"basic","frente":..,"verso":..}  -> modelo "Basic" (Front/Back)
  {"tipo":"cloze","texto":"... {{c1::x}}"} -> modelo "Cloze" (Text)
"""
import json
import urllib.error
import urllib.request

import store
from config import load

ANKICONNECT_URL = "http://localhost:8765"


def _invoke(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        ANKICONNECT_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Não consegui falar com o Anki (AnkiConnect em localhost:8765). "
            "Abra o Anki desktop com o add-on AnkiConnect instalado e tente de novo. "
            f"Detalhe: {e}"
        )
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect: {data['error']}")
    return data.get("result")


def _note_for(fato, deck, tags):
    tipo = (fato.get("tipo") or "basic").lower()
    base = {"deckName": deck, "tags": tags, "options": {"allowDuplicate": False}}
    if tipo == "cloze":
        base["modelName"] = "Cloze"
        base["fields"] = {"Text": fato.get("texto", ""), "Back Extra": ""}
    else:
        base["modelName"] = "Basic"
        base["fields"] = {"Front": fato.get("frente", ""), "Back": fato.get("verso", "")}
    return base


def save(video_id, cfg=None):
    """Cria os cards do vídeo no deck configurado. Retorna nº de cards criados.
    Não faz nada (0) se o vídeo não tiver fatos memorizáveis."""
    cfg = cfg or load()
    if not cfg.get("anki", {}).get("enabled", True):
        print("[anki] desativado em config.yaml — pulando.")
        return 0

    v = store.get_video(video_id)
    if not v:
        raise ValueError(f"vídeo {video_id} não está no banco")
    fatos = v.get("fatos") or []
    if not fatos:
        print(f"[anki] {video_id} não tem fatos memorizáveis — nada a fazer.")
        store.set_flag(video_id, "saved_anki", 1)  # marcado: avaliado, sem cards
        return 0

    deck = cfg["anki"].get("deck", "Aspis")
    tags = ["aspis", v.get("pillar", "nenhum"), video_id]

    _invoke("createDeck", deck=deck)  # idempotente
    notes = [_note_for(f, deck, tags) for f in fatos]
    # addNotes devolve uma lista: id do card, ou None se duplicado/inválido
    results = _invoke("addNotes", notes=notes)
    created = sum(1 for r in results if r)
    store.set_flag(video_id, "saved_anki", 1)
    print(f"[anki] {created}/{len(notes)} card(s) criado(s) no deck '{deck}'.")
    return created


if __name__ == "__main__":
    import sys

    store.init()
    vid = sys.argv[1] if len(sys.argv) > 1 else "m1"
    try:
        n = save(vid)
        print(f"OK — {n} card(s).")
    except RuntimeError as e:
        print("ERRO:", e)
