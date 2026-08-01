from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
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
    date: datetime | None = None,
) -> str:
    date = date if date is not None else now_moscow()
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

    preview = text.strip()[:80] if text else None

    append_index_entry(
        {
            "date": date.isoformat(),
            "tag": tag,
            "type": msg_type,
            "entry_path": f"entries/{entry_filename}",
            "media_path": media_path,
            "preview": preview,
        }
    )

    return tag


def list_entries(days: int = 7) -> list[dict]:
    service = get_drive_service()
    structure = ensure_structure()

    raw = service.files().get_media(fileId=structure["index_file_id"]).execute()
    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        entries = []

    cutoff = now_moscow() - timedelta(days=days)
    recent = [e for e in entries if datetime.fromisoformat(e["date"]) >= cutoff]
    recent.sort(key=lambda e: e["date"], reverse=True)
    return recent


def _lookup_recent(service, structure, number: int, days: int) -> tuple[list[dict], dict]:
    raw = service.files().get_media(fileId=structure["index_file_id"]).execute()
    entries = json.loads(raw)

    cutoff = now_moscow() - timedelta(days=days)
    recent = [e for e in entries if datetime.fromisoformat(e["date"]) >= cutoff]
    recent.sort(key=lambda e: e["date"], reverse=True)

    if number < 1 or number > len(recent):
        raise ValueError(f"Нет записи №{number} за последние {days} дней")

    return entries, recent[number - 1]  # target is the same dict object as inside `entries`


def _apply_entry_update(service, structure, target: dict, new_tag: str, new_date: datetime) -> None:
    old_tag = target["tag"]
    old_date_iso = target["date"]
    new_date_iso = new_date.isoformat()
    new_stamp = new_date.strftime("%Y-%m-%d_%H%M%S")

    old_entry_name = target["entry_path"].split("/")[-1]
    entry_file_id = _find_child(service, old_entry_name, structure["entries_folder_id"])
    if entry_file_id is None:
        raise ValueError("Не найден markdown-файл записи в Google Drive")

    content = service.files().get_media(fileId=entry_file_id).execute().decode("utf-8")
    content = content.replace(f"tag: {old_tag}\n", f"tag: {new_tag}\n", 1)
    content = content.replace(f"date: {old_date_iso}\n", f"date: {new_date_iso}\n", 1)
    new_entry_name = f"{new_stamp}_{new_tag}.md"
    updated_media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/markdown")
    service.files().update(
        fileId=entry_file_id, body={"name": new_entry_name}, media_body=updated_media
    ).execute()

    if target.get("media_path"):
        old_media_name = target["media_path"].split("/")[-1]
        extension = old_media_name.rsplit(".", 1)[-1]
        media_file_id = _find_child(service, old_media_name, structure["media_folder_id"])
        if media_file_id:
            new_media_name = f"{new_stamp}_{new_tag}.{extension}"
            service.files().update(fileId=media_file_id, body={"name": new_media_name}).execute()
            target["media_path"] = f"media/{new_media_name}"

    target["tag"] = new_tag
    target["date"] = new_date_iso
    target["entry_path"] = f"entries/{new_entry_name}"


def _save_index(service, structure, entries: list[dict]) -> None:
    media = MediaIoBaseUpload(
        io.BytesIO(json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")),
        mimetype="application/json",
    )
    service.files().update(fileId=structure["index_file_id"], media_body=media).execute()


def retag_entry(number: int, new_tag: str, days: int = 7) -> dict:
    service = get_drive_service()
    structure = ensure_structure()
    entries, target = _lookup_recent(service, structure, number, days)

    old_tag = target["tag"]
    unchanged_date = datetime.fromisoformat(target["date"])
    _apply_entry_update(service, structure, target, new_tag=new_tag, new_date=unchanged_date)
    _save_index(service, structure, entries)

    return {
        "old_tag": old_tag,
        "new_tag": new_tag,
        "date": target["date"],
        "preview": target.get("preview"),
    }


def set_entry_date(number: int, new_date: datetime, days: int = 7) -> dict:
    service = get_drive_service()
    structure = ensure_structure()
    entries, target = _lookup_recent(service, structure, number, days)

    old_date = target["date"]
    unchanged_tag = target["tag"]
    _apply_entry_update(service, structure, target, new_tag=unchanged_tag, new_date=new_date)
    _save_index(service, structure, entries)

    return {
        "old_date": old_date,
        "new_date": target["date"],
        "tag": unchanged_tag,
        "preview": target.get("preview"),
    }
