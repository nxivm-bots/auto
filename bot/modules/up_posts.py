from json import loads as jloads
from os import execl
from sys import executable
from bot.core.database import db

from aiohttp import ClientSession
from bot import Var, bot, ffQueue
from bot.core.text_utils import TextEditor
from bot.core.reporter import rep
from datetime import datetime, timezone, timedelta

TD_SCHR = None  # Global reference to schedule message

async def upcoming_animes():
    global TD_SCHR

    if Var.SEND_SCHEDULE:
        try:
            async with ClientSession() as ses:
                res = await ses.get("https://subsplease.org/api/?f=schedule&h=true&tz=Asia/Kolkata")
                aniContent = jloads(await res.text())["schedule"]

                # Set IST timezone and get today's date
                IST = timezone(timedelta(hours=5, minutes=30))
                today = datetime.now(IST).date()

                # Sort by time
                def get_time_key(item):
                    try:
                        return datetime.strptime(item["time"], "%H:%M")
                    except:
                        return datetime.min

                aniContent.sort(key=get_time_key)

                # Build message
                text = "<b>╔═《 𝗧𝗢𝗗𝗔𝗬'𝗦 𝗔𝗡𝗜𝗠𝗘 𝗦𝗖𝗛𝗘𝗗𝗨𝗟𝗘 》═╗</b>\n\n"

                for i in aniContent:
                    aname = TextEditor(i["title"])
                    await aname.load_anilist()
                    title = aname.adata.get('title', {}).get('english') or i['title']

                    # AniList airing info
                    next_ep = aname.adata.get("nextAiringEpisode")
                    if not next_ep:
                        continue

                    airing_at = datetime.fromtimestamp(next_ep["airingAt"], IST).date()
                    if airing_at != today:
                        continue

                    # Episode number
                    episode = next_ep["episode"]
                    episode_text = f"Ep {episode}"

                    # Convert SubsPlease time to 12-hour format
                    try:
                        time_24 = i["time"]
                        time_12 = datetime.strptime(time_24, "%H:%M").strftime("%I:%M %p")
                    except:
                        time_12 = i["time"]

                    # Add to text
                    text += (
                        f"╟─ ❖ <b>{title}</b>\n"
                        f"╟─ ✎ <i>{episode_text}</i>\n"
                        f"╙─ ✦  <i>{time_12}</i>\n\n"
                    )

                # Footer
                if text.strip() == "<b>╔═《 𝗧𝗢𝗗𝗔𝗬'𝗦 𝗔𝗡𝗜𝗠𝗘 𝗦𝗖𝗛𝗘𝗗𝗨𝗟𝗘 》═╗</b>":
                    text += "No episodes releasing today.\n"
                else:
                    text += "<b>╚═《✦𝗘𝗡𝗗 𝗢𝗙 𝗧𝗢𝗗𝗔𝗬'𝗦 𝗟𝗜𝗦𝗧✦》═╝</b>"

                # Get optional banner
                banner = await db.get_banner()

                # Send message
                if banner:
                    TD_SCHR = await bot.send_photo(Var.MAIN_CHANNEL, banner, caption=text)
                else:
                    TD_SCHR = await bot.send_message(Var.MAIN_CHANNEL, text)

                await (await TD_SCHR.pin())  # pin the message

        except Exception as err:
            await rep.report(str(err), "error")

    if not ffQueue.empty():
        await ffQueue.join()


async def update_shdr(name, link):
    global TD_SCHR
    if TD_SCHR:
        TD_lines = TD_SCHR.caption.split('\n') if TD_SCHR.photo else TD_SCHR.text.split('\n')
        
        for i, line in enumerate(TD_lines):
            if line.startswith(f"📌 {name}"):
                TD_lines[i+2] = f"    • Status : ✅ __Uploaded__\n    • Link : {link}"

        if TD_SCHR.photo:
            await TD_SCHR.edit_caption("\n".join(TD_lines))
        else:
            await TD_SCHR.edit_text("\n".join(TD_lines))
