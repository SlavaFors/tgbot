from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BotCommand, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fondtale-bot")

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

HASHTAG_RE = re.compile(r"#(\w+)")
DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b(?:[ T](\d{2}):(\d{2}))?")
DATE_RU_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b(?:[ ,](\d{2}):(\d{2}))?")


class InvalidDateError(ValueError):
    pass


def extract_tag(text: str | None) -> str:
    if not text:
        return "без_тега"
    match = HASHTAG_RE.search(text)
    return match.group(1) if match else "без_тега"


def extract_date_override(text: str | None, now: datetime) -> datetime | None:
    """Ищет в тексте дату (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ, время опционально) —
    для добавления старых воспоминаний задним числом. Час/минута/секунда,
    если не указаны явно, берутся из `now` (чтобы несколько сообщений за
    один и тот же день не давали одинаковое имя файла)."""
    if not text:
        return None

    match = DATE_ISO_RE.search(text)
    if match:
        year, month, day, hour, minute = match.groups()
    else:
        match = DATE_RU_RE.search(text)
        if not match:
            return None
        day, month, year, hour, minute = match.groups()

    try:
        return now.replace(
            year=int(year),
            month=int(month),
            day=int(day),
            hour=int(hour) if hour else now.hour,
            minute=int(minute) if minute else now.minute,
        )
    except ValueError as error:
        raise InvalidDateError(
            f"Не получилось разобрать дату «{match.group(0)}» — проверьте, что она существует."
        ) from error


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
        "Чтобы добавить старое воспоминание, укажите дату прямо в тексте/подписи: "
        "«#слова_Криса 10.05.2023 сказал первое слово „мама“» — сохранится именно этим числом, "
        "а не сегодняшним.\n\n"
        "/recent — записи, добавленные за последние 7 дней (не по дате события, "
        "а по тому, когда реально отправили боту)\n"
        "/retag <номер> <новый_тег> — исправить тег записи из списка /recent\n"
        "/setdate <номер> <ГГГГ-ММ-ДД> [ЧЧ:ММ] — исправить дату записи из списка /recent\n"
        "/delete <номер> — удалить запись из списка /recent (файлы уходят в корзину Drive)\n\n"
        "Если отправить /retag, /setdate или /delete без аргументов (например через меню команд) — "
        "бот спросит нужные данные отдельным сообщением, на которое нужно ответить (reply)."
    )


RECENT_DAYS = 7


@dp.message(Command("recent"))
async def cmd_recent(message: Message):
    entries = await asyncio.to_thread(storage.list_entries, days=RECENT_DAYS)
    if not entries:
        await message.answer(f"За последние {RECENT_DAYS} дней ничего не добавляли.")
        return

    lines = [f"Добавлено за последние {RECENT_DAYS} дней (дата в скобках — дата события):"]
    for i, entry in enumerate(entries, start=1):
        date = datetime.fromisoformat(entry["date"])
        preview = entry.get("preview") or f"[{entry['type']}]"
        lines.append(f"{i}. #{entry['tag']} — {preview} ({date.strftime('%d.%m.%Y %H:%M')})")
    lines.append(
        "\nИсправить: /retag <номер> <тег> · /setdate <номер> <дата> · /delete <номер>"
    )
    await message.answer("\n".join(lines))


RETAG_PROMPT = "Ответьте на это сообщение в формате: <номер> <новый_тег>"
SETDATE_PROMPT = "Ответьте на это сообщение в формате: <номер> <ГГГГ-ММ-ДД> [ЧЧ:ММ]"
DELETE_PROMPT = "Ответьте на это сообщение номером записи для удаления"


async def _do_retag(message: Message, number_raw: str, new_tag_raw: str) -> None:
    if not number_raw.isdigit():
        await message.answer(f"Номер должен быть числом.\n{RETAG_PROMPT}")
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


async def _do_setdate(message: Message, number_raw: str, date_raw: str) -> None:
    if not number_raw.isdigit():
        await message.answer(f"Номер должен быть числом.\n{SETDATE_PROMPT}")
        return

    now = storage.now_moscow()
    try:
        new_date = extract_date_override(date_raw, now)
    except InvalidDateError as error:
        await message.answer(f"⚠️ {error}")
        return
    if new_date is None:
        await message.answer(
            "Не нашёл дату в формате ГГГГ-ММ-ДД или ДД.ММ.ГГГГ (время — опционально, ЧЧ:ММ)."
        )
        return

    try:
        result = await asyncio.to_thread(
            storage.set_entry_date, number=int(number_raw), new_date=new_date, days=RECENT_DAYS
        )
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    old_date = datetime.fromisoformat(result["old_date"])
    new_date_result = datetime.fromisoformat(result["new_date"])
    await message.answer(
        f"✅ Дата записи #{result['tag']} изменена: "
        f"{old_date.strftime('%d.%m.%Y %H:%M')} → {new_date_result.strftime('%d.%m.%Y %H:%M')}"
    )


async def _do_delete(message: Message, number_raw: str) -> None:
    number_raw = number_raw.strip()
    if not number_raw.isdigit():
        await message.answer(f"Номер должен быть числом.\n{DELETE_PROMPT}")
        return

    try:
        result = await asyncio.to_thread(
            storage.delete_entry, number=int(number_raw), days=RECENT_DAYS
        )
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    date = datetime.fromisoformat(result["date"])
    preview = result.get("preview") or f"[{result['tag']}]"
    await message.answer(
        f"🗑 Удалено: #{result['tag']} — {preview} ({date.strftime('%d.%m.%Y %H:%M')})\n"
        "Файлы перемещены в корзину Google Drive — можно восстановить в течение 30 дней."
    )


@dp.message(Command("retag"))
async def cmd_retag(message: Message):
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        # Отправлено через меню/автодополнение без аргументов — Telegram шлёт
        # такие команды сразу, без возможности дописать текст. Просим ответить
        # (reply) на этот же вопрос отдельным сообщением.
        await message.answer(RETAG_PROMPT)
        return
    await _do_retag(message, args[1], args[2])


@dp.message(Command("setdate"))
async def cmd_setdate(message: Message):
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        await message.answer(SETDATE_PROMPT)
        return
    await _do_setdate(message, args[1], args[2])


@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(DELETE_PROMPT)
        return
    await _do_delete(message, args[1])


def _is_reply_to_correction_prompt(message: Message) -> bool:
    parent = message.reply_to_message
    return bool(parent and parent.text in (RETAG_PROMPT, SETDATE_PROMPT, DELETE_PROMPT))


@dp.message(_is_reply_to_correction_prompt)
async def handle_correction_reply(message: Message):
    prompt = message.reply_to_message.text
    text = (message.text or "").strip()

    if prompt == DELETE_PROMPT:
        await _do_delete(message, text)
        return

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно два значения: номер и новое значение через пробел.")
        return

    if prompt == RETAG_PROMPT:
        await _do_retag(message, parts[0], parts[1])
    else:
        await _do_setdate(message, parts[0], parts[1])


async def _save_and_reply(message: Message, source_text: str | None, **save_kwargs) -> None:
    tag = extract_tag(source_text)
    now = storage.now_moscow()
    try:
        date_override = extract_date_override(source_text, now)
    except InvalidDateError as error:
        await message.answer(f"⚠️ {error}")
        return

    tag_used = await asyncio.to_thread(
        storage.save_entry, tag=tag, date=date_override, **save_kwargs
    )
    reply = f"✅ Сохранено под #{tag_used}"
    if date_override is not None:
        reply += f" ({date_override.strftime('%d.%m.%Y')})"
    await message.answer(reply)


@dp.message(F.text)
async def handle_text(message: Message):
    await _save_and_reply(message, message.text, msg_type="text", text=message.text)


@dp.message(F.photo)
async def handle_photo(message: Message):
    file = await bot.get_file(message.photo[-1].file_id)
    buffer = await bot.download_file(file.file_path)
    await _save_and_reply(
        message,
        message.caption,
        msg_type="photo",
        text=message.caption,
        media_bytes=buffer.read(),
        media_extension="jpg",
        media_mime="image/jpeg",
    )


@dp.message(F.voice)
async def handle_voice(message: Message):
    file = await bot.get_file(message.voice.file_id)
    buffer = await bot.download_file(file.file_path)
    await _save_and_reply(
        message,
        message.caption,
        msg_type="voice",
        media_bytes=buffer.read(),
        media_extension="ogg",
        media_mime="audio/ogg",
    )


@dp.message(F.audio)
async def handle_audio(message: Message):
    file = await bot.get_file(message.audio.file_id)
    buffer = await bot.download_file(file.file_path)
    extension = Path(file.file_path).suffix.lstrip(".") or "bin"
    mime_type = message.audio.mime_type or "application/octet-stream"
    await _save_and_reply(
        message,
        message.caption,
        msg_type="audio",
        media_bytes=buffer.read(),
        media_extension=extension,
        media_mime=mime_type,
    )


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    file = await bot.get_file(message.video_note.file_id)
    buffer = await bot.download_file(file.file_path)
    await _save_and_reply(
        message,
        message.caption,
        msg_type="video_note",
        media_bytes=buffer.read(),
        media_extension="mp4",
        media_mime="video/mp4",
    )


@dp.message(F.video)
async def handle_video(message: Message):
    file = await bot.get_file(message.video.file_id)
    buffer = await bot.download_file(file.file_path)
    extension = Path(file.file_path).suffix.lstrip(".") or "mp4"
    mime_type = message.video.mime_type or "video/mp4"
    await _save_and_reply(
        message,
        message.caption,
        msg_type="video",
        text=message.caption,
        media_bytes=buffer.read(),
        media_extension=extension,
        media_mime=mime_type,
    )


@dp.message()
async def handle_unsupported(message: Message):
    await message.answer("⚠️ Этот тип сообщения не поддерживается")


BOT_COMMANDS = [
    BotCommand(command="start", description="Как пользоваться ботом"),
    BotCommand(command="recent", description="Записи, добавленные за 7 дней"),
    BotCommand(command="retag", description="Исправить тег записи"),
    BotCommand(command="setdate", description="Исправить дату записи"),
    BotCommand(command="delete", description="Удалить запись"),
]


async def on_startup(app: web.Application) -> None:
    await bot.set_my_commands(BOT_COMMANDS)

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
