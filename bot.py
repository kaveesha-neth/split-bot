"""
Telegram Large File Splitter Bot
Uses Telethon (MTProto) for large file downloads/uploads, bypassing Bot API limits.
"""

import os
import asyncio
import logging
import glob
import time
import shutil
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename

# ── Config ────────────────────────────────────────────────────────────────────
API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/tmp/tgbot/downloads"))
OUTPUT_DIR   = Path(os.environ.get("OUTPUT_DIR",   "/tmp/tgbot/output"))
SPLIT_SIZE_MB = int(os.environ.get("SPLIT_SIZE_MB", "1000"))   # ~1 GB
MIN_SIZE_MB   = int(os.environ.get("MIN_SIZE_MB",   "1000"))   # only process files >= this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tgbot")

# ── Telethon client (bot session) ─────────────────────────────────────────────
client = TelegramClient("bot_session", API_ID, API_HASH)


# ── Helpers ───────────────────────────────────────────────────────────────────

def human_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"


async def safe_edit(msg, text: str):
    """Edit a message, ignoring 'not modified' errors."""
    try:
        await msg.edit(text)
    except Exception:
        pass


async def compress_and_split(input_path: Path, output_dir: Path, base_name: str,
                             split_mb: int, status_msg) -> list[Path]:
    """
    Run rar to compress + split the file.
    Returns list of .rar part paths sorted alphabetically.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_base = output_dir / base_name

    await safe_edit(status_msg, f"⚙️ Compressing and splitting `{input_path.name}`…\n"
                                 f"Split size: {split_mb} MB")

    cmd = [
        "rar", "a",
        "-m0",                          # store only (fastest), change to -m5 for max compression
        f"-v{split_mb}m",               # split volume size
        "-ep",                          # strip path from archived files
        str(archive_base),
        str(input_path),
    ]

    log.info("Running: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"rar failed (rc={proc.returncode}):\n{stderr.decode()}")

    # Collect parts: base_name.rar, base_name.r00, base_name.r01 … OR
    # base_name.part1.rar, base_name.part2.rar … (depends on rar version)
    parts = sorted(output_dir.glob(f"{base_name}*.rar")) + \
            sorted(output_dir.glob(f"{base_name}*.r[0-9][0-9]"))

    if not parts:
        # Fallback glob
        parts = sorted(output_dir.glob(f"{base_name}*"))

    parts = sorted(set(parts))  # deduplicate & sort
    return parts


# ── Event handler ─────────────────────────────────────────────────────────────

@client.on(events.NewMessage(pattern="/start"))
async def handle_start(event):
    await event.reply(
        "👋 **Large File Splitter Bot**\n\n"
        f"Send me any file **≥ {MIN_SIZE_MB} MB** and I will:\n"
        f"1. Download it to the server\n"
        f"2. Compress & split it into **{SPLIT_SIZE_MB} MB** RAR parts\n"
        f"3. Send all parts back to you\n\n"
        "Just drop the file here!"
    )


@client.on(events.NewMessage(pattern="/help"))
async def handle_help(event):
    await handle_start(event)


@client.on(events.NewMessage())
async def handle_file(event):
    msg = event.message

    # Must have a document
    if not msg.document:
        return

    file_size = msg.document.size
    file_size_mb = file_size / (1024 * 1024)

    # Only handle files >= MIN_SIZE_MB
    if file_size_mb < MIN_SIZE_MB:
        await event.reply(
            f"⚠️ File is {human_size(file_size)} — smaller than the "
            f"{MIN_SIZE_MB} MB threshold.\nJust use Telegram normally for small files 😊"
        )
        return

    # Try to get original filename
    original_name = "file"
    for attr in msg.document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            original_name = attr.file_name
            break

    stem = Path(original_name).stem
    status = await event.reply(
        f"📥 Received **{original_name}** ({human_size(file_size)})\n"
        "Starting download…"
    )

    # ── Directories ──────────────────────────────────────────────────────────
    job_id = f"{int(time.time())}_{msg.id}"
    dl_dir  = DOWNLOAD_DIR / job_id
    out_dir = OUTPUT_DIR   / job_id
    dl_dir.mkdir(parents=True, exist_ok=True)
    input_path = dl_dir / original_name

    try:
        # ── 1. Download ───────────────────────────────────────────────────────
        downloaded_bytes = 0
        last_edit = 0

        async def progress(current, total):
            nonlocal downloaded_bytes, last_edit
            downloaded_bytes = current
            now = time.time()
            if now - last_edit > 3:          # throttle edits to every 3 s
                pct = current / total * 100
                await safe_edit(status,
                    f"📥 Downloading **{original_name}**…\n"
                    f"{human_size(current)} / {human_size(total)} ({pct:.1f}%)"
                )
                last_edit = now

        await client.download_media(msg, file=str(input_path), progress_callback=progress)
        await safe_edit(status, f"✅ Download complete ({human_size(file_size)})\n"
                                 "⚙️ Compressing…")

        # ── 2. Compress & split ───────────────────────────────────────────────
        parts = await compress_and_split(input_path, out_dir, stem, SPLIT_SIZE_MB, status)

        if not parts:
            raise RuntimeError("No RAR parts were produced — check rar installation.")

        total_parts = len(parts)
        await safe_edit(status,
            f"✅ Split into **{total_parts}** part(s)\n"
            f"📤 Uploading…"
        )

        # ── 3. Upload parts ───────────────────────────────────────────────────
        for idx, part_path in enumerate(parts, 1):
            part_size = part_path.stat().st_size
            upload_status = await event.reply(
                f"📤 Uploading part {idx}/{total_parts}: "
                f"`{part_path.name}` ({human_size(part_size)})…"
            )

            last_up_edit = 0

            async def up_progress(current, total, _up_status=upload_status,
                                  _name=part_path.name, _idx=idx, _total=total_parts):
                nonlocal last_up_edit
                now = time.time()
                if now - last_up_edit > 3:
                    pct = current / total * 100
                    await safe_edit(_up_status,
                        f"📤 Uploading part {_idx}/{_total}: `{_name}`\n"
                        f"{human_size(current)} / {human_size(total)} ({pct:.1f}%)"
                    )
                    last_up_edit = now

            await client.send_file(
                event.chat_id,
                str(part_path),
                caption=f"📦 Part {idx}/{total_parts} — `{part_path.name}`",
                progress_callback=up_progress,
                attributes=[DocumentAttributeFilename(part_path.name)],
                reply_to=msg.id,
            )

            await upload_status.delete()

        await safe_edit(status,
            f"🎉 Done! Sent **{total_parts}** RAR part(s) for `{original_name}`.\n"
            f"Original size: {human_size(file_size)}"
        )

    except Exception as e:
        log.exception("Job failed")
        await safe_edit(status, f"❌ Error: {e}")

    finally:
        # Clean up temp files
        shutil.rmtree(dl_dir,  ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    await client.start(bot_token=BOT_TOKEN)
    log.info("Bot started. Waiting for files…")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
