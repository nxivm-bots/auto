import aiohttp
import aiofiles
from time import time, sleep
from traceback import format_exc
from math import floor
from os import path as ospath, remove as osremove
from aiofiles.os import remove as aioremove
from pyrogram.errors import FloodWait
from bot.core.database import db
from bot import bot, Var
from .func_utils import editMessage, sendMessage, convertBytes, convertTime
from .reporter import rep
import os
import re

# Quality formatting mapping
btn_formatter = {
    'HDRi': '𝗛𝗗𝗥𝗶𝗣',
    '1080': '𝟭𝟬𝟴𝟬𝗽',
    '720': '𝟳𝟮𝟬𝗽',
    '480': '𝟰𝟴𝟬𝗽',
}

class TgUploader:
    def __init__(self, message):
        self.cancelled = False
        self.message = message
        self.__name = ""
        self.__qual = ""
        self.__client = bot
        self.__start = time()
        self.__updater = time()

    async def download_thumbnail(self, url):
        """Download the thumbnail if it's a URL and return the local file path."""
        temp_path = "temp_thumb.jpg"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open(temp_path, "wb") as f:
                        await f.write(await resp.read())

                    if os.path.getsize(temp_path) > 0:
                        return temp_path
        return None

    def rename_file(self, old_name, qual):
        # Extract season and episode
        match = re.search(r"S(\d{2})E(\d{2})", old_name, re.IGNORECASE)
        season = match.group(1) if match else "01"
        episode = match.group(2) if match else "01"

        # Get formatted quality from mapping
        quality_label = btn_formatter.get(qual, qual)

        # Determine audio type
        audio_type = "Sub"
        if re.search(r"DUAL", old_name, re.IGNORECASE):
            audio_type = "Dual"
        elif re.search(r"DUB", old_name, re.IGNORECASE):
            audio_type = "Dub"

        # Build consistent file name & caption
        new_name = (
            f"[NA] Private Tutor to the Duke's Daughter - "
            f"[S{season}- E{episode}] [{quality_label} - {audio_type}]@ongoing_nxivm.mkv"
        )

        return new_name

    async def upload(self, path, qual):
        old_name = os.path.basename(path)
        new_name = self.rename_file(old_name, qual)
        self.__name = new_name
        self.__qual = qual

        # Rename the actual file before upload
        new_path = ospath.join(ospath.dirname(path), new_name)
        os.rename(path, new_path)
        path = new_path

        # Fetch custom thumbnail
        thumbnail = await db.get_thumbnail()
        if isinstance(thumbnail, str) and thumbnail.startswith(("http://", "https://")):
            thumbnail = await self.download_thumbnail(thumbnail)

        if not thumbnail or not os.path.exists(thumbnail) or os.path.getsize(thumbnail) == 0:
            thumbnail = "thumb.jpg" if os.path.exists("thumb.jpg") and os.path.getsize("thumb.jpg") > 0 else None

        try:
            caption_text = f"<i>{self.__name}</i>"
            if Var.AS_DOC:
                return await self.__client.send_document(
                    chat_id=Var.FILE_STORE,
                    document=path,
                    thumb=thumbnail,
                    caption=caption_text,
                    force_document=True,
                    progress=self.progress_status
                )
            else:
                return await self.__client.send_video(
                    chat_id=Var.FILE_STORE,
                    video=path,
                    thumb=thumbnail,
                    caption=caption_text,
                    progress=self.progress_status
                )
        except FloodWait as e:
            sleep(e.value * 1.5)
            return await self.upload(path, qual)
        except Exception as e:
            await rep.report(format_exc(), "error")
            raise e
        finally:
            await aioremove(path)
            if thumbnail == "temp_thumb.jpg":
                os.remove(thumbnail)

    async def progress_status(self, current, total):
        if self.cancelled:
            self.__client.stop_transmission()
        now = time()
        diff = now - self.__start
        if (now - self.__updater) >= 7 or current == total:
            self.__updater = now
            percent = round(current / total * 100, 2)
            speed = current / diff
            eta = round((total - current) / speed)
            bar = floor(percent / 8) * "■" + (12 - floor(percent / 8)) * "□"
            progress_str = f"""‣ <b>Anime Name :</b> <b><i>{self.__name}</i></b>

‣ <b>Status :</b> <i>Uploading</i>
<code>[{bar}]</code> {percent}%

‣ <b>Size :</b> {convertBytes(current)} out of ~ {convertBytes(total)}
‣ <b>Speed :</b> {convertBytes(speed)}/s
‣ <b>Time Took :</b> {convertTime(diff)}
‣ <b>Time Left :</b> {convertTime(eta)}

‣ <b>File(s) Uploaded:</b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code>

<b>Powered by @Codeflix_bots</b>"""
            await editMessage(self.message, progress_str)


# Fix for the `thumbnail_command` function where the error occurred
async def thumbnail_command(client, message):
    """Handles fetching and displaying the current thumbnail."""
    current_thumbnail = await db.get_thumbnail()

    if isinstance(current_thumbnail, str) and current_thumbnail.startswith(("http://", "https://")):
        thumbnail_link = f"<a href='{current_thumbnail}'>🔗 View Thumbnail</a>"
    else:
        thumbnail_link = "No thumbnail available"

    await message.reply_text(
        f"📌 Current Thumbnail:\n{thumbnail_link}",
        disable_web_page_preview=True
    )



class TgUploaders:
    def __init__(self, message):
        self.cancelled = False
        self.message = message
        self.__name = ""
        self.__qual = ""
        self.__client: Client = bot
        self.__start = time()
        self.__updater = time()

    async def download_thumbnail(self, url: str) -> str | None:
        """Download the thumbnail if it's a URL and return the local file path."""
        temp_path = "temp_thumb.jpg"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open(temp_path, "wb") as f:
                        await f.write(await resp.read())

                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        return temp_path  # Valid thumbnail

        return None  # Failed to download

    async def upload(self, path: str, qual: str):
        """Upload encoded anime to Telegram file store."""
        self.__name = os.path.basename(path)  # Extract clean filename
        self.__qual = qual

        # Sanitize filename to remove unwanted characters
        filename = self.sanitize_filename(self.__name)

        # Fetch custom thumbnail from DB
        thumbnail = await db.get_thumbnail()

        # If thumbnail is a URL, download it
        if isinstance(thumbnail, str) and thumbnail.startswith(("http://", "https://")):
            thumbnail = await self.download_thumbnail(thumbnail)

        # Use default local thumbnail if the fetched one is invalid
        if not thumbnail or not os.path.exists(thumbnail) or os.path.getsize(thumbnail) == 0:
            thumbnail = "thumb.jpg" if os.path.exists("thumb.jpg") and os.path.getsize("thumb.jpg") > 0 else None

        try:
            if Var.AS_DOC:
                return await self.__client.send_document(
                    chat_id=Var.FILE_STORE,
                    document=path,
                    thumb=thumbnail,
                    caption=f"<i>{filename}</i>",
                    file_name=filename,  # Ensure correct filename
                    force_document=True,
                    progress=self.progress_status
                )
            else:
                return await self.__client.send_video(
                    chat_id=Var.FILE_STORE,
                    video=path,
                    thumb=thumbnail,
                    caption=f"<i>{filename}</i>",
                    file_name=filename,
                    progress=self.progress_status
                )
        except FloodWait as e:
            await sleep(e.value * 1.5)
            return await self.upload(path, qual)
        except Exception as e:
            await rep.report(format_exc(), "error")
            raise e
        finally:
            await aioremove(path)
            if thumbnail == "temp_thumb.jpg":
                os.remove(thumbnail)

    async def progress_status(self, current: int, total: int):
        """Updates upload progress status message."""
        if self.cancelled:
            return await self.__client.stop_transmission()

        now = time()
        diff = now - self.__start

        if (now - self.__updater) >= 7 or current == total:
            self.__updater = now
            percent = round(current / total * 100, 2)
            speed = current / diff if diff > 0 else 0
            eta = round((total - current) / speed) if speed > 0 else 0
            bar = floor(percent / 8) * "■" + (12 - floor(percent / 8)) * "□"

            # Extract resolution (360p, 720p, etc.) from `self.__qual`
            resolution = re.search(r"\b\d{3,4}p\b", self.__qual)
            self.__qual = resolution.group() if resolution else "Unknown"

            # Avoid index error
            qual_index = Var.QUALS.index(self.__qual) if self.__qual in Var.QUALS else 0

            progress_str = f"""‣ <b>Anime Name :</b> <b><i>{self.__name}</i></b>

‣ <b>Status :</b> <i>Uploading</i>
    <code>[{bar}]</code> {percent}%
    
    ‣ <b>Size :</b> {convertBytes(current)} out of ~ {convertBytes(total)}
    ‣ <b>Speed :</b> {convertBytes(speed)}/s
    ‣ <b>Time Took :</b> {convertTime(diff)}
    ‣ <b>Time Left :</b> {convertTime(eta)}

‣ <b>File(s) Encoded:</b> <code>{qual_index} / {len(Var.QUALS)}</code>"""

            await editMessage(self.message, progress_str)



    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to remove 'encoded', unwanted characters, and move 'sub' or 'dub' after episode number or quality."""
        filename = filename.replace("_", " ")  # Replace underscores with spaces
        filename = re.sub(r"(?i)\bencoded\b", "", filename)  # Remove "encoded" (case-insensitive)
        filename = re.sub(r"[^\w\s\.-]", "", filename)  # Remove special characters except dots and dashes
        filename = filename.strip()  # Remove leading/trailing spaces

    # Match "sub" or "dub" (case-insensitive) and extract the rest of the filename
        match = re.search(r"(?i)\b(sub|dub)\b", filename)
        if match:
            tag = match.group().capitalize()  # Get "Sub" or "Dub"
            filename = re.sub(r"(?i)\bsub\b|\bdub\b", "", filename).strip()  # Remove from original position

        # Find episode number or resolution to place "Sub" or "Dub" after it
            match_ep = re.search(r"EP\s*\d+", filename, re.IGNORECASE)
            match_res = re.search(r"\b\d{3,4}p\b", filename)  # Match resolution (360p, 720p, etc.)

            if match_res:
                filename = filename.replace(match_res.group(), f"[{match_res.group()}] [{tag}]")  # After resolution
            elif match_ep:
                filename = filename.replace(match_ep.group(), f"[{match_ep.group()}] [{tag}]")  # After episode number
            else:
                filename += f" {tag}"  # If no match, append at the end

        return filename
