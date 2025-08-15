import re, os
import asyncio
from asyncio import gather, create_task, sleep as asleep, Event
from asyncio.subprocess import PIPE
from os import path as ospath, system
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove
from traceback import format_exc
from base64 import urlsafe_b64encode
from time import time
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot, bot_loop, Var, ani_cache, ffQueue, ffLock, ff_queued
from .tordownload import TorDownloader
from .database import db
from .func_utils import getfeed, encode, editMessage, sendMessage, convertBytes
from .text_utils import TextEditor
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .reporter import rep
from .text_utils import stylize_quote
from monitor import live_status_updater


async def log_unmapped_anime(anime_name: str):
    anime_name = anime_name.strip()
    try:
        if not ospath.exists("unmapped.log"):
            async with aiopen("unmapped.log", "w") as f:
                await f.write(anime_name + "\n")
            return

        async with aiopen("unmapped.log", "r+") as f:
            lines = await f.readlines()
            if anime_name + "\n" in lines:
                return  # Already logged

            lines.append(anime_name + "\n")
            if len(lines) > 50:
                lines = lines[-50:]

            await f.seek(0)
            await f.truncate()
            await f.writelines(lines)

    except Exception as e:
        await rep.report(f"Unmapped log error: {e}", "error")


btn_formatter = {
    'HDRi': '𝗛𝗗𝗥𝗶𝗣',
    '1080': '𝟭𝟬𝟴𝟬𝗽',
    '720': '𝟳𝟮𝟬𝗽',
    '480': '𝟰𝟴𝟬𝗽',
}

ani_cache.setdefault('reported_ids', set())


async def fetch_animes():
    await rep.report("Fetch Animes Started !!", "info")
    while False:
        await asleep(60)
        if ani_cache['fetch_animes']:
            for idx, rss_list in enumerate([Var.RSS_ITEMS_1, Var.RSS_ITEMS_2], start=1):
                for link in rss_list:
                    info = await getfeed(link, 0)
                    if info:
                        bot_loop.create_task(get_animes(info.title, info.link))
                    else:
                        await rep.report(f"No info from link: {link}", "warning")


def clean_torrent_title(raw_name: str) -> str:
    """
    Cleans up messy torrent names for better AniList matching.
    """
    name = re.sub(r'.S\d+E\d+.', '', raw_name, flags=re.IGNORECASE)
    name = re.sub(r'.E\d+.', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(480p|720p|1080p|2160p|4K|WEB-DL|WEBRip|BluRay|BRRip|HDRip|x264|x265|H.264|H.265|HEVC)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[._]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


async def get_animes(name, torrent, force=False):
    try:
        aniInfo = TextEditor(name)
        await aniInfo.load_anilist()
        ani_id, ep_no = aniInfo.adata.get('id'), aniInfo.pdata.get("episode_number")

        titles = aniInfo.adata.get("title", {})
        anime_title = (titles.get("english") or titles.get("romaji") or titles.get("native")).lower().strip()

        channel_id = await db.get_anime_channel(anime_title)

        if not channel_id:
            channel_id = Var.MAIN_CHANNEL
            #await rep.report(f"❌ No channel set for anime: `{anime_title}`", "warning")
            ani_cache.setdefault("unmapped", set())
            if anime_title not in ani_cache["unmapped"]:
                await log_unmapped_anime(anime_title)
                ani_cache["unmapped"].add(anime_title)
            channel_id = await db.get_main_channel() or Var.MAIN_CHANNEL

        if ani_id not in ani_cache['ongoing']:
            ani_cache['ongoing'].add(ani_id)
        elif not force:
            return
        if not force and ani_id in ani_cache['completed']:
            return

        ani_data = await db.getAnime(ani_id)
        qual_data = ani_data.get(ep_no) if ani_data else None

        if force or not ani_data or not qual_data or not all(qual for qual in qual_data.values()):
            if "[BATCH]" in name:
                await rep.report(f"Torrent Skipped!\n\n{name}", "warning")
                return

            if ani_id not in ani_cache["reported_ids"]:
                await rep.report(f"New Anime Torrent Found!\n\n{name}", "info")
                ani_cache["reported_ids"].add(ani_id)

            post_msg = await bot.send_photo(
                channel_id,
                photo=await aniInfo.get_poster(),
                caption=await aniInfo.get_caption()
            )

            bot_loop.create_task(post_channel_info_delayed(anime_title, post_msg.id))

            await bot.send_sticker(channel_id, "CAACAgUAAxkBAAEBaQZoaFz-20hjKjdRx0Q67wKhJa7H9wACOxkAAqNcQFfHOLnxo8XllR4E")
            await asleep(1.5)
            stat_msg = await sendMessage(channel_id, f"‣ <b>Anime Name :</b> <b><i>{name}</i></b>\n\n<i>Downloading...</i>\n\nPowered by @KGN_BOTZ ,Owner @ExE_AQUIB Anime Index- @KGN_ANIME_INDEX")

            stop_event = asyncio.Event()
            monitor_task = asyncio.create_task(live_status_updater(stat_msg, name, "📥 Downloading", stop_event))
            dl = await TorDownloader("./downloads").download(torrent, name)
            stop_event.set()
            await monitor_task

            if not dl or not ospath.exists(dl):
                await rep.report("File Download Incomplete, Try Again", "error")
                await stat_msg.delete()
                return

            post_id = post_msg.id
            ffEvent = Event()
            ff_queued[post_id] = ffEvent

            if ffLock.locked():
                await editMessage(stat_msg, f"‣ <b>Anime Name :</b> <b><i>{name}</i></b>\n\n<i>Queued to Encode...</i>\n\nPowered by @KGN_BOTZ ,Owner @ExE_AQUIB Anime Index- @KGN_ANIME_INDEX")
                await rep.report("Added Task to Queue...", "info")

            await ffQueue.put(post_id)
            await ffEvent.wait()
            await ffLock.acquire()

            btns = []
            for qual in Var.QUALS:
                filename = await aniInfo.get_upname(qual)
                await editMessage(stat_msg, f"‣ <b>Anime Name :</b> <b><i>{name}</i></b>\n\n<i>Ready to Encode...</i>\n\nPowered by @KGN_BOTZ ,Owner @ExE_AQUIB Anime Index- @KGN_ANIME_INDEX")
                await asleep(1.5)
                await rep.report("Starting Encode...", "info")

                try:
                    encoder = FFEncoder(stat_msg, dl, filename, qual)
                    out_path = await encoder.start_encode()
                except Exception as e:
                    await rep.report(f"Encoding Error: {e}", "error")
                    await stat_msg.delete()
                    if ffLock.locked():
                        ffLock.release()
                    return

                await rep.report("Successfully Compressed. Now Uploading...", "info")
                await editMessage(stat_msg, f"‣ <b>Anime Name :</b> <b><i>{filename}</i></b>\n\n<i>Ready to Upload...</i>\n\nPowered by @KGN_BOTZ ,Owner @ExE_AQUIB Anime Index- @KGN_ANIME_INDEX")
                await asleep(1.5)

                try:
                    msg = await TgUploader(stat_msg).upload(out_path, qual)
                except Exception as e:
                    await rep.report(f"Upload Error: {e}", "error")
                    await stat_msg.delete()
                    if ffLock.locked():
                        ffLock.release()
                    return

                await rep.report("Successfully Uploaded to Telegram.", "info")
                msg_id = msg.id
                link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(msg_id * abs(Var.FILE_STORE)))}"

                if post_msg:
                    if btns and len(btns[-1]) == 1:
                        btns[-1].insert(1, InlineKeyboardButton(f"{btn_formatter[qual]}", url=link))
                    else:
                        btns.append([InlineKeyboardButton(f"{btn_formatter[qual]}", url=link)])
                    await editMessage(post_msg, post_msg.caption.html if post_msg.caption else "", InlineKeyboardMarkup(btns))

                await db.saveAnime(ani_id, ep_no, qual, post_id)
                bot_loop.create_task(extra_utils(msg_id, out_path))

            if ffLock.locked():
                ffLock.release()
            await stat_msg.delete()
            await aioremove(dl)

        ani_cache['completed'].add(ani_id)

    except Exception:
        await rep.report(format_exc(), "error")
        if ffLock.locked():
            ffLock.release()

async def post_channel_info_delayed(anime_name: str, post_id: int):
    anime_name = anime_name.lower().strip()

    channel_id1 = await db.get_main_channel()
    if not channel_id1:
        channel_id1 = Var.MAIN_CHANNEL
    channel_id = await db.get_anime_channel(anime_name)
    if channel_id == Var.MAIN_CHANNEL:
        return

    if not channel_id:
        print(f"[INFO] No specific channel found for anime: {anime_name}")
        return

    try:
        chat = await bot.get_chat(channel_id)
    except Exception as e:
        print(f"[ERROR] Get Chat Error: {e}")
        return

    # Always get a valid invite link
    try:
        if chat.username:
            invite_link = f"https://t.me/{chat.username}/{post_id}"
        else:
            invite_obj = await bot.create_chat_invite_link(channel_id)
            invite_link = invite_obj.invite_link
    except Exception as e:
        print(f"[ERROR] Failed to create invite link: {e}")
        invite_link = await db.get_anime_invite(anime_name)

    # === Load AniList Metadata ===
    ani = TextEditor(anime_name)
    await ani.load_anilist()
    await ani.extract_metadata(anime_name)

    # Pull metadata
    adata = ani.adata
    pdata = ani.pdata
    caption = await ani.get_caption()

    # Extract season and episode numbers
    season_match = re.search(r"Season[:\s]+(\d+)", caption, re.IGNORECASE)
    episode_match = re.search(r"Episode[:\s]+(\d+)", caption, re.IGNORECASE)

    season = season_match.group(1) if season_match else "01"
    episode = episode_match.group(1) if episode_match else "01"

    audio = pdata.get("audio", "SUB")
    if channel_id1:
        audio = "DUAL"  # This will trigger "English Japanese" below
    quality = pdata.get("quality", "720p")

    title_data = adata.get("title", {})
    title = title_data.get("english") or title_data.get("romaji") or title_data.get("native", "Unknown Title")
    season_tag = adata.get("season", "Season").title()
    year_tag = str(adata.get("seasonYear", "2025"))
    seasonal_hashtag = f"#{season_tag}Ongoing{year_tag}"
    duration = adata.get("duration", 24)

    langinfo = {
        "DUAL": "English Japanese",
        "MULTI": "Multi Audio",
        "SUB": "Japanese"
    }.get(audio.upper(), "Japanese [E-Sub]")

    desc = adata.get("description", "").replace("<br>", "").replace("\n", " ").strip()
    desc = re.sub(r"Source:.*?", "", desc).strip()
    desc_parts = re.split(r'[.!?]\s+', desc, maxsplit=1)

    if len(desc_parts) >= 2:
        quote = stylize_quote(desc_parts[0])
        summary = desc_parts[1]
    else:
        quote = stylize_quote(desc)
        summary = ""

    quote_text = f"“{quote}.”"
    summary_words = summary.split()

    header = f"""<b>《 {title} 》  •  {year_tag}</b>

━━━━━━━━━━━━━━━━━━━━━
<b>⧫ Season: {str(season).zfill(2)}</b> {seasonal_hashtag}
<b>⧫ Episode: {str(episode).zfill(2)}</b>
<b>⧫ Language: {langinfo}</b>
<b>⧫ Quality: All Qualities with E-Subs</b>
<b>⧫ Runtime: {duration} mins</b>

<blockquote expandable>"""
    footer = "</blockquote>\n\nᴘʀᴇsᴇɴᴛᴇᴅ ʙʏ : <a href=\"https://t.me/chrunchyrool\">ᴄ ʀ ᴜ ɴ ᴄ ʜ ʏ ʀ σ σ ʟ</a>"
    max_caption_len = 1024

    base_len = len(header + footer + quote_text + "\n\n")
    caption = None
    success = False

    # Try trimming until caption fits
    for i in range(len(summary_words), -1, -1):
        trimmed_summary = " ".join(summary_words[:i])
        if i < len(summary_words):
            trimmed_summary += "..."
        full_desc = f"{quote_text}\n\n{trimmed_summary}"
        temp_caption = header + full_desc + footer
        if len(temp_caption) <= max_caption_len:
            caption = temp_caption
            try:
                poster = await ani.get_poster()
                if not poster:
                    poster = "https://i.ibb.co/20pSh9H0/photo-2025-07-22-12-24-19-7533280454300925960.jpg"
                await bot.send_photo(
                    channel_id1,
                    photo=poster,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "⛩️ 𝐂𝐋𝐈𝐂𝐊 𝐇𝐄𝐑𝐄 𝐓𝐎 𝐖𝐀𝐓𝐂𝐇 𝐈𝐓 ⛩️",
                            url=invite_link
                        )
                    ]])
                )
                print(f"[INFO] Successfully posted anime info for {anime_name}")
                success = True
                break
            except Exception as e:
                if "MEDIA_CAPTION_TOO_LONG" not in str(e):
                    print(f"[ERROR] Post Failed: {e}")
                    return

    # Fallback if nothing worked
    if not success:
        print("[WARN] Using minimal fallback caption")
        caption = header + quote_text + footer
        try:
            poster = await ani.get_poster()
            if not poster:
                poster = "https://i.ibb.co/20pSh9H0/photo-2025-07-22-12-24-19-7533280454300925960.jpg"
            await bot.send_photo(
                channel_id1,
                photo=poster,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⛩️ 𝐂𝐋𝐈𝐂𝐊 𝐇𝐄𝐑𝐄 𝐓𝐎 𝐖𝐀𝐓𝐂𝐇 𝐈𝐓 ⛩️",
                        url=invite_link
                    )
                ]])
            )
            print(f"[INFO] Successfully posted fallback info for {anime_name}")
        except Exception as e:
            print(f"[ERROR] Final Post Failed: {e}")

async def extra_utils(msg_id, out_path):
    msg = await bot.get_messages(Var.FILE_STORE, message_ids=msg_id)
    if Var.BACKUP_CHANNEL:
        for chat_id in Var.BACKUP_CHANNEL.split():
            await msg.copy(int(chat_id))