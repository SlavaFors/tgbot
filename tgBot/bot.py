from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fondtale-bot")

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

HASHTAG_RE = re.compile(r"#(\w+)")


def extract_tag(text: str | None) -> str:
    if not text:
        return "без_тега"
    match = HASHTAG_RE.search(text)
    return match.group(1) if match else "без_тега"


@dp.message.outer_middleware()
async def allowed_user_only(handler, event: Message, data):
    if event.from_user is None or event.from_user.id != config.ALLOWED_USER_ID:
        return None
    return await handler(event, data)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Пишите текст, фото, голосовые, аудио, видео или видео-кружочки с хэштегом "
        "(например #фраза, #спор, #смешное) — сохраню в дневник. "
        "Без хэштега тоже сохраню, под #без_тега.\n\n"
        "/recent — последние записи за 7 дней\n"
        "/retag <номер> <новый_тег> — исправить тег записи из списка /recent"
    )


RECENT_DAYS = 7


@dp.message(Command("recent"))
async def cmd_recent(message: Message):
    entries = await asyncio.to_thread(storage.list_entries, days=RECENT_DAYS)
    if not entries:
        await message.answer(f"За последние {RECENT_DAYS} дней записей нет.")
        return

    lines = [f"Записи за последние {RECENT_DAYS} дней:"]
    for i, entry in enumerate(entries, start=1):
        date = datetime.fromisoformat(entry["date"])
        preview = entry.get("preview") or f"[{entry['type']}]"
        lines.append(f"{i}. #{entry['tag']} — {preview} ({date.strftime('%d.%m %H:%M')})")
    lines.append("\nЧтобы исправить тег: /retag <номер> <новый_тег>")
    await message.answer("\n".join(lines))


@dp.message(Command("retag"))
async def cmd_retag(message: Message):
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "Формат: /retag <номер> <новый_тег>\n"
            "Номер — из списка /recent, тег — без решётки, одно слово."
        )
        return

    _, number_raw, new_tag_raw = args
    if not number_raw.isdigit():
        await message.answer("Номер должен быть числом. Формат: /retag <номер> <новый_тег>")
        return

    new_tag = new_tag_raw.strip().lstrip("#")
    if not HASHTAG_RE.fullmatch("#" + new_tag):
        await message.answer("Тег может содержать только буквы, цифры и подчёркивание.")
        return

    try:
        result = await asyncio.to_thread(
            storage.retag_entry, number=int(number_raw), new_tag=new_tag, days=RECENT_DAYS
        )
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    await message.answer(f"✅ Тег изменён: #{result['old_tag']} → #{result['new_tag']}")


@dp.message(F.text)
async def handle_text(message: Message):
    tag = extract_tag(message.text)
    tag_used = await asyncio.to_thread(
        storage.save_entry, tag=tag, msg_type="text", text=message.text
    )
    await message.answer(f"✅ Сохранено под #{tag_used}")


@dp.message(F.photo)
async def handle_photo(message: Message):
    tag = extract_tag(message.caption)
    file = await bot.get_file(message.photo[-1].file_id)
    buffer = await bot.download_file(file.file_path)
    tag_used = await asyncio.to_thread(
        storage.save_entry,
        tag=tag,
        msg_type="photo",
        text=message.caption,
        media_bytes=buffer.read(),
        media_extension="jpg",
        media_mime="image/jpeg",
    )
    await message.answer(f"✅ Сохранено под #{tag_used}")


@dp.message(F.voice)
async def handle_voice(message: Message):
    tag = extract_tag(message.caption)
    file = await bot.get_file(message.voice.file_id)
    buffer = await bot.download_file(file.file_path)
    tag_used = await asyncio.to_thread(
        storage.save_entry,
        tag=tag,
        msg_type="voice",
        media_bytes=buffer.read(),
        media_extension="ogg",
        media_mime="audio/ogg",
    )
    await message.answer(f"✅ Сохранено под #{tag_used}")


@dp.message(F.audio)
async def handle_audio(message: Message):
    tag = extract_tag(message.caption)
    file = await bot.get_file(message.audio.file_id)
    buffer = await bot.download_file(file.file_path)
    extension = Path(file.file_path).suffix.lstrip(".") or "bin"
    mime_type = message.audio.mime_type or "application/octet-stream"
    tag_used = await asyncio.to_thread(
        storage.save_entry,
        tag=tag,
        msg_type="audio",
        media_bytes=buffer.read(),
        media_extension=extension,
        media_mime=mime_type,
    )
    await message.answer(f"✅ Сохранено под #{tag_used}")


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    tag = extract_tag(message.caption)
    file = await bot.get_file(message.video_note.file_id)
    buffer = await bot.download_file(file.file_path)
    tag_used = await asyncio.to_thread(
        storage.save_entry,
        tag=tag,
        msg_type="video_note",
        media_bytes=buffer.read(),
        media_extension="mp4",
        media_mime="video/mp4",
    )
    await message.answer(f"✅ Сохранено под #{tag_used}")


@dp.message(F.video)
async def handle_video(message: Message):
    tag = extract_tag(message.caption)
    file = await bot.get_file(message.video.file_id)
    buffer = await bot.download_file(file.file_path)
    extension = Path(file.file_path).suffix.lstrip(".") or "mp4"
    mime_type = message.video.mime_type or "video/mp4"
    tag_used = await asyncio.to_thread(
        storage.save_entry,
        tag=tag,
        msg_type="video",
        text=message.caption,
        media_bytes=buffer.read(),
        media_extension=extension,
        media_mime=mime_type,
    )
    await message.answer(f"✅ Сохранено под #{tag_used}")


@dp.message()
async def handle_unsupported(message: Message):
    await message.answer("⚠️ Этот тип сообщения не поддерживается")


async def on_startup(app: web.Application) -> None:
    webhook_url = f"{config.RENDER_EXTERNAL_URL}{config.WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=config.WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    logger.info("Webhook set to %s", webhook_url)


async def on_shutdown(app: web.Application) -> None:
    # Не трогаем вебхук здесь: на Render старый инстанс завершается уже
    # после того, как новый успел его переустановить (редеплой), а на free
    # tier это же событие происходит и при штатном "засыпании" — удаление
    # вебхука в обоих случаях оставило бы бота без единственного способа
    # получать сообщения.
    await bot.session.close()


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="Fondtale memory bot is running")


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_health)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path=config.WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=config.PORT)
