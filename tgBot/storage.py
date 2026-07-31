from __future__ import annotations

import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

import config

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
INDEX_FILENAME = "index.json"

_drive_service = None
_structure_cache = None  # {"entries_folder_id": ..., "media_folder_id": ..., "index_file_id": ...}


def now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        credentials = Credentials(
            token=None,
            refresh_token=config.GOOGLE_REFRESH_TOKEN,
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
        )
        _drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return _drive_service


def _find_child(service, name: str, parent_id: str, mime_type: str | None = None) -> str | None:
    query = f"name = '{name}' and '{parent_id}' in parents and trashed = false"
    if mime_type:
        query += f" and mimeType = '{mime_type}'"
    response = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
    )
    files = response.get("files", [])
    return files[0]["id"] if files else None


def _find_or_create_folder(service, name: str, parent_id: str) -> str:
    folder_id = _find_child(service, name, parent_id, mime_type=FOLDER_MIME_TYPE)
    if folder_id:
        return folder_id
    metadata = {"name": name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]}
    created = service.files().create(body=metadata, fields="id").execute()
    return created["id"]


def _find_or_create_index_file(service, parent_id: str) -> str:
    file_id = _find_child(service, INDEX_FILENAME, parent_id)
    if file_id:
        return file_id
    media = MediaIoBaseUpload(io.BytesIO(b"[]"), mimetype="application/json")
    metadata = {"name": INDEX_FILENAME, "parents": [parent_id]}
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"]


def ensure_structure() -> dict:
    global _structure_cache
    if _structure_cache is not None:
        return _structure_cache

    service = get_drive_service()
    root_id = config.GDRIVE_ROOT_FOLDER_ID
    entries_folder_id = _find_or_create_folder(service, "entries", root_id)
    media_folder_id = _find_or_create_folder(service, "media", root_id)
    index_file_id = _find_or_create_index_file(service, root_id)

    _structure_cache = {
        "entries_folder_id": entries_folder_id,
        "media_folder_id": media_folder_id,
        "index_file_id": index_file_id,
    }
    return _structure_cache


def upload_media(data: bytes, filename: str, mime_type: str) -> tuple[str, str]:
    service = get_drive_service()
    structure = ensure_structure()
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type)
    metadata = {"name": filename, "parents": [structure["media_folder_id"]]}
    created = (
        service.files()
        .create(body=metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    return created["id"], created.get("webViewLink", "")


def upload_markdown(content: str, filename: str) -> str:
    service = get_drive_service()
    structure = ensure_structure()
    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/markdown")
    metadata = {"name": filename, "parents": [structure["entries_folder_id"]]}
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"]


def append_index_entry(entry: dict) -> None:
    service = get_drive_service()
    structure = ensure_structure()
    index_file_id = structure["index_file_id"]

    raw = service.files().get_media(fileId=index_file_id).execute()
    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        entries = []

    entries.append(entry)

    media = MediaIoBaseUpload(
        io.BytesIO(json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")),
        mimetype="application/json",
    )
    service.files().update(fileId=index_file_id, media_body=media).execute()


def _build_markdown(date: datetime, tag: str, msg_type: str, body: str) -> str:
    frontmatter = (
        "---\n"
        f"date: {date.isoformat()}\n"
        f"tag: {tag}\n"
        f"type: {msg_type}\n"
        "---\n\n"
    )
    return frontmatter + body.strip() + "\n"


def save_entry(
    tag: str,
    msg_type: str,
    text: str | None = None,
    media_bytes: bytes | None = None,
    media_extension: str | None = None,
    media_mime: str | None = None,
) -> str:
    date = now_moscow()
    stamp = date.strftime("%Y-%m-%d_%H%M%S")
    entry_filename = f"{stamp}_{tag}.md"

    media_path = None
    body_parts = []

    if text:
        body_parts.append(text.strip())

    if media_bytes is not None:
        media_filename = f"{stamp}_{tag}.{media_extension}"
        _media_file_id, web_view_link = upload_media(media_bytes, media_filename, media_mime)
        media_path = f"media/{media_filename}"
        body_parts.append(f"[Медиафайл]({web_view_link})")

    body = "\n\n".join(body_parts) if body_parts else "_(нет текста)_"
    markdown_content = _build_markdown(date, tag, msg_type, body)

    upload_markdown(markdown_content, entry_filename)

    append_index_entry(
        {
            "date": date.isoformat(),
            "tag": tag,
            "type": msg_type,
            "entry_path": f"entries/{entry_filename}",
            "media_path": media_path,
        }
    )

    return tag
