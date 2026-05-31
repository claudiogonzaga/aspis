"""youtube.py — leitura das inscrições e dos vídeos novos via YouTube Data API v3.

Default: OAuth (escopo youtube.readonly) para ler as inscrições do usuário
automaticamente. No primeiro uso abre o navegador para consentimento e salva o
token em token.json; depois reaproveita/atualiza.

Modo alternativo (sem OAuth): se config youtube.channels_manuais estiver
preenchido, usamos uma API key e essa lista fixa de canais.

Quota: subscriptions/channels/playlistItems/videos custam 1 unidade/chamada.
Nunca usamos search.list (100 unidades).
"""
import re
from datetime import datetime, timezone

from config import expand, load

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


# --- duração ISO 8601 → "mm min" -------------------------------------------
_ISO_DUR = re.compile(
    r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
)


def iso_duration_to_human(iso):
    if not iso:
        return ""
    m = _ISO_DUR.match(iso)
    if not m:
        return ""
    days, hours, minutes, seconds = (int(x) if x else 0 for x in m.groups())
    total_min = days * 24 * 60 + hours * 60 + minutes + (1 if seconds >= 30 else 0)
    if total_min >= 60:
        h, mm = divmod(total_min, 60)
        return f"{h} h {mm:02d} min" if mm else f"{h} h"
    return f"{total_min} min"


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# --- construção do client ---------------------------------------------------
def _oauth_service(cfg):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_path = expand(cfg["youtube"]["token_path"])
    secret_path = expand(cfg["youtube"]["client_secret_path"])

    creds = None
    import os

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(secret_path):
                raise RuntimeError(
                    f"client_secret.json não encontrado em {secret_path}. "
                    "Crie a credencial OAuth (Desktop) no Google Cloud e salve aí."
                )
            flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _apikey_service(cfg):
    import os

    from googleapiclient.discovery import build

    key = os.environ.get(cfg["youtube"].get("api_key_env", "YOUTUBE_API_KEY"))
    if not key:
        raise RuntimeError(
            "Modo manual exige YOUTUBE_API_KEY no ambiente (ou use OAuth)."
        )
    return build("youtube", "v3", developerKey=key, cache_discovery=False)


def get_service(cfg=None):
    cfg = cfg or load()
    if cfg["youtube"].get("channels_manuais"):
        return _apikey_service(cfg)
    return _oauth_service(cfg)


# --- API calls --------------------------------------------------------------
def get_subscriptions(service):
    """Retorna lista de channel_id das inscrições do usuário (paginado)."""
    channel_ids = []
    page_token = None
    while True:
        resp = (
            service.subscriptions()
            .list(part="snippet", mine=True, maxResults=50, pageToken=page_token)
            .execute()
        )
        for item in resp.get("items", []):
            cid = item["snippet"]["resourceId"]["channelId"]
            channel_ids.append(cid)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return channel_ids


def get_uploads_playlists(service, channel_ids):
    """channel_id → uploads playlist id. Lotes de 50."""
    out = {}
    for batch in _chunks(channel_ids, 50):
        resp = (
            service.channels()
            .list(part="contentDetails", id=",".join(batch), maxResults=50)
            .execute()
        )
        for item in resp.get("items", []):
            uploads = (
                item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            if uploads:
                out[item["id"]] = uploads
    return out


def get_new_video_ids(service, playlist_id, since_dt, max_videos):
    """IDs de vídeos publicados depois de `since_dt` numa uploads playlist."""
    ids = []
    page_token = None
    while True:
        resp = (
            service.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=min(50, max_videos) if max_videos else 50,
                pageToken=page_token,
            )
            .execute()
        )
        stop = False
        for item in resp.get("items", []):
            published = item["snippet"].get("publishedAt")
            vid = item["contentDetails"].get("videoId")
            if not published or not vid:
                continue
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if pub_dt > since_dt:
                ids.append(vid)
            else:
                # uploads vêm em ordem decrescente de data → pode parar
                stop = True
            if max_videos and len(ids) >= max_videos:
                stop = True
                break
        page_token = resp.get("nextPageToken")
        if stop or not page_token:
            break
    return ids


def hydrate(service, video_ids):
    """videos.list em lotes de 50. Retorna lista de dicts com metadados."""
    out = []
    for batch in _chunks(list(video_ids), 50):
        resp = (
            service.videos()
            .list(part="snippet,contentDetails,statistics", id=",".join(batch))
            .execute()
        )
        for item in resp.get("items", []):
            sn = item.get("snippet", {})
            cd = item.get("contentDetails", {})
            st = item.get("statistics", {})
            out.append(
                {
                    "video_id": item["id"],
                    "title": sn.get("title", ""),
                    "channel": sn.get("channelTitle", ""),
                    "channel_id": sn.get("channelId", ""),
                    "description": sn.get("description", ""),
                    "published_at": sn.get("publishedAt", ""),
                    "duration": iso_duration_to_human(cd.get("duration", "")),
                    "views": int(st.get("viewCount", 0)) if st.get("viewCount") else 0,
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                }
            )
    return out


def fetch_new_videos(since_dt, cfg=None):
    """Pipeline de leitura: inscrições → uploads → novos → hidrata.
    Retorna lista de dicts de vídeo (metadados), prontos para o brain."""
    cfg = cfg or load()
    service = get_service(cfg)
    max_per = cfg.get("max_videos_per_channel", 8)

    manual = cfg["youtube"].get("channels_manuais")
    channel_ids = manual if manual else get_subscriptions(service)

    uploads = get_uploads_playlists(service, channel_ids)
    new_ids = []
    for _cid, playlist_id in uploads.items():
        new_ids.extend(get_new_video_ids(service, playlist_id, since_dt, max_per))

    # dedup preservando ordem
    seen = set()
    new_ids = [v for v in new_ids if not (v in seen or seen.add(v))]
    return hydrate(service, new_ids)


if __name__ == "__main__":
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(hours=36)
    vids = fetch_new_videos(since)
    print(f"{len(vids)} vídeos novos desde {since.isoformat()}")
    for v in vids[:10]:
        print(f"  [{v['duration']}] {v['channel']} — {v['title']}")
