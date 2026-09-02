# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import signal
import string
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from telethon import TelegramClient, events


BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
MEDIA_DIR = Path(os.getenv("TSDMD_MEDIA_DIR", BASE_DIR / "Media")).resolve()
SESSION_NAME = os.getenv("TSDMD_SESSION_NAME", "tsdmd")
LOG_FILE = os.getenv("TSDMD_LOG_FILE")
MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".mp4", ".avi", ".mkv")
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv")

client = None
admin_id = None
shutdown_event = asyncio.Event()
letters = iter(string.ascii_uppercase)


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    admin_id: int


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(os.getenv("TSDMD_LOG_LEVEL", "INFO").upper())
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if LOG_FILE:
        log_path = Path(LOG_FILE).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logging()


def read_settings_file():
    if not SETTINGS_FILE.exists():
        return {}

    with SETTINGS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def prompt_if_allowed(name):
    allow_prompts = os.getenv("TSDMD_ALLOW_PROMPTS", "false").lower() == "true"
    if allow_prompts and sys.stdin.isatty():
        return input(f"Enter {name}: ").strip()
    return None


def load_config():
    settings = read_settings_file()

    api_id = os.getenv("TSDMD_API_ID") or settings.get("api_id")
    api_hash = os.getenv("TSDMD_API_HASH") or settings.get("api_hash")
    loaded_admin_id = os.getenv("TSDMD_ADMIN_ID") or settings.get("admin_id")

    api_id = api_id or prompt_if_allowed("your API_ID")
    api_hash = api_hash or prompt_if_allowed("your API_HASH")
    loaded_admin_id = loaded_admin_id or prompt_if_allowed("the Admin ID")

    missing = [
        name
        for name, value in (
            ("TSDMD_API_ID", api_id),
            ("TSDMD_API_HASH", api_hash),
            ("TSDMD_ADMIN_ID", loaded_admin_id),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Set environment variables or create settings.json."
        )

    return Config(api_id=int(api_id), api_hash=api_hash, admin_id=int(loaded_admin_id))


def ensure_directories():
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def get_next_letter():
    global letters
    try:
        return next(letters)
    except StopIteration:
        letters = iter(string.ascii_uppercase)
        return next(letters)


def safe_name(value):
    value = str(value or "None")
    return "".join(char if char.isalnum() or char in "@._- " else "_" for char in value)


def is_within(path, parent):
    return path == parent or parent in path.parents


def display_path(path):
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def resolve_managed_path(user_path):
    requested = (BASE_DIR / user_path).resolve()
    if is_within(requested, BASE_DIR) or is_within(requested, MEDIA_DIR):
        return requested
    raise ValueError("Path is outside the project/media directories.")


async def is_admin(event):
    return event.sender_id == admin_id


async def show_welcome(event):
    if not await is_admin(event):
        return

    welcome_message = (
        "Self-Destructing-Media-Downloader Helper Menu\n\n"
        "/ping - Check if the service is alive and measure ping time.\n"
        "/status - Show downloaded photo/video counts.\n"
        "/files - List files in the project folder.\n"
        "/check - List files in the media folder.\n"
        "/download [file_path] - Send a project file to Telegram.\n"
        "/delete [file_path] - Delete a project file.\n"
        "/all - Send all media files from the media folder.\n"
        "/zip - Create and send a zip archive of the media folder."
    )
    await event.respond(welcome_message)


async def handle_ping(event):
    if not await is_admin(event):
        return

    url = "https://www.google.com"
    try:
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                await response.read()
        ping_time = round((time.time() - start_time) * 1000)
        await event.respond(f"The service is alive. Ping: {ping_time} ms.")
    except Exception as exc:
        logger.exception("Error in /ping command")
        await event.respond(f"Failed to measure ping time: {exc}")


async def handle_status(event):
    if not await is_admin(event):
        return

    count_photos = 0
    count_videos = 0
    for path in MEDIA_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in PHOTO_EXTENSIONS:
            count_photos += 1
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            count_videos += 1

    await event.respond(
        f"Service status:\nTotal Photos: {count_photos}\nTotal Videos: {count_videos}"
    )


async def handle_files(event):
    if not await is_admin(event):
        return

    rows = []
    for path in sorted(BASE_DIR.rglob("*")):
        if any(part.startswith(".") for part in path.relative_to(BASE_DIR).parts):
            continue
        if path.is_file():
            rows.append(str(path.relative_to(BASE_DIR)))

    message = "Files:\n" + "\n".join(rows) if rows else "No files found."
    await event.respond(message[:4000])


async def handle_check(event):
    if not await is_admin(event):
        return

    current_files = [
        display_path(path)
        for path in sorted(MEDIA_DIR.rglob("*"))
        if path.is_file()
    ]
    if current_files:
        await event.respond(("Current media files:\n" + "\n".join(current_files))[:4000])
    else:
        await event.respond("No files found in the media folder.")


async def handle_download(event):
    if not await is_admin(event):
        return

    file_path = event.pattern_match.group(1).strip()
    try:
        resolved_path = resolve_managed_path(file_path)
        if resolved_path.is_file():
            await client.send_file(event.sender_id, str(resolved_path))
            await event.respond(f"File {file_path} sent successfully.")
        else:
            await event.respond(f"File {file_path} does not exist.")
    except ValueError as exc:
        await event.respond(str(exc))
    except Exception as exc:
        logger.exception("Error in /download command")
        await event.respond(f"Error in downloading file: {exc}")


async def handle_delete(event):
    if not await is_admin(event):
        return

    file_path = event.pattern_match.group(1).strip()
    try:
        resolved_path = resolve_managed_path(file_path)
        if resolved_path.is_file():
            resolved_path.unlink()
            await event.respond(f"File {file_path} deleted successfully.")
        else:
            await event.respond(f"File {file_path} does not exist.")
    except ValueError as exc:
        await event.respond(str(exc))
    except Exception as exc:
        logger.exception("Error in /delete command")
        await event.respond(f"Error in deleting file: {exc}")


async def handle_all(event):
    if not await is_admin(event):
        return

    media_files = [
        path for path in sorted(MEDIA_DIR.rglob("*"))
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
    ]
    if not media_files:
        await event.respond("No media files found in the media folder.")
        return

    try:
        for media_file in media_files:
            await client.send_file(event.sender_id, str(media_file))
        await event.respond("All media files sent successfully.")
    except Exception as exc:
        logger.exception("Error in /all command")
        await event.respond(f"Error in sending all media files: {exc}")


async def handle_zip(event):
    if not await is_admin(event):
        return

    zip_filename = BASE_DIR / "media_files.zip"
    try:
        with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for path in sorted(MEDIA_DIR.rglob("*")):
                if path.is_file():
                    archive_name = Path(MEDIA_DIR.name) / path.relative_to(MEDIA_DIR)
                    zip_file.write(path, archive_name)

        await client.send_file(event.sender_id, str(zip_filename))
        await event.respond("ZIP file created and sent successfully.")
    except Exception as exc:
        logger.exception("Error in /zip command")
        await event.respond(f"Error in creating zip file: {exc}")
    finally:
        if zip_filename.exists():
            zip_filename.unlink()


def get_user_folder_name(username, user_id):
    user_marker = f"@{username} - {user_id}"
    for folder in MEDIA_DIR.iterdir():
        if folder.is_dir() and user_marker in folder.name:
            return folder.name

    return f"{get_next_letter()} - @{username} - {user_id}"


async def downloader(event):
    me = await client.get_me()
    if event.sender_id == me.id:
        return

    sender = await event.get_sender()
    username = safe_name(sender.username if sender.username else "None")
    user_id = safe_name(sender.id if sender.id else "None")
    user_folder_name = get_user_folder_name(username, user_id)
    user_folder_path = MEDIA_DIR / user_folder_name
    user_folder_path.mkdir(parents=True, exist_ok=True)

    logger.info("Received media from %s (ID: %s). Starting download...", username, user_id)

    try:
        result = await event.download_media(file=str(user_folder_path))
        media_type = "photo" if event.photo else "video"
        logger.info(
            "%s downloaded successfully from %s (ID: %s)",
            media_type.capitalize(),
            username,
            user_id,
        )
        if result:
            await client.send_file(
                "me",
                result,
                caption=f"Downloaded by TSDMD from {username}",
            )
    except Exception as exc:
        logger.exception("Failed to download media from %s (ID: %s)", username, user_id)
        await event.respond(f"Error in downloading media: {exc}")


def register_handlers():
    client.add_event_handler(
        show_welcome,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/help"),
    )
    client.add_event_handler(
        handle_ping,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/ping"),
    )
    client.add_event_handler(
        handle_status,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/status"),
    )
    client.add_event_handler(
        handle_files,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/files"),
    )
    client.add_event_handler(
        handle_check,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/check"),
    )
    client.add_event_handler(
        handle_download,
        events.NewMessage(pattern=r"/download (.+)", func=lambda event: event.is_private),
    )
    client.add_event_handler(
        handle_delete,
        events.NewMessage(pattern=r"/delete (.+)", func=lambda event: event.is_private),
    )
    client.add_event_handler(
        handle_all,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/all"),
    )
    client.add_event_handler(
        handle_zip,
        events.NewMessage(func=lambda event: event.is_private and event.text == "/zip"),
    )
    client.add_event_handler(
        downloader,
        events.NewMessage(
            func=lambda event: event.is_private
            and (event.photo or event.video)
            and event.media_unread
        ),
    )


def install_signal_handlers():
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)


async def run_client():
    global client, admin_id

    config = load_config()
    admin_id = config.admin_id
    session_path = str(BASE_DIR / SESSION_NAME)
    client = TelegramClient(session_path, config.api_id, config.api_hash)
    register_handlers()

    await client.start()
    logger.info("Telegram client started. Media directory: %s", MEDIA_DIR)

    disconnect_task = asyncio.ensure_future(client.disconnected)
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    done, pending = await asyncio.wait(
        {disconnect_task, shutdown_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()

    if shutdown_task in done:
        logger.info("Shutdown signal received.")
    else:
        logger.warning("Telegram client disconnected.")


async def main():
    ensure_directories()
    install_signal_handlers()

    while not shutdown_event.is_set():
        try:
            await run_client()
        except RuntimeError:
            raise
        except Exception:
            logger.exception("Unexpected service error")
        finally:
            if client and client.is_connected():
                await client.disconnect()

        if not shutdown_event.is_set():
            logger.info("Restarting Telegram client in 10 seconds...")
            await asyncio.sleep(10)

    logger.info("Service stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        logger.critical("Service failed: %s", exc)
        sys.exit(1)
