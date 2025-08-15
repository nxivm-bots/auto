
import binascii
import base64
import re, os, sys
import asyncio
import subprocess
import hashlib
from pyrogram import filters, Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserIsBlocked, InputUserDeactivated, FloodWait, PeerIdInvalid, RPCError
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from shortzy import Shortzy
import requests
import time
from datetime import datetime, timedelta
import random
import string
from pyrogram.enums import ParseMode, ChatAction
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatMemberUpdated
from asyncio import sleep as asleep, gather
from pyrogram import filters, Client
from pyrogram.filters import command, private, user, regex
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified

from bot import bot, bot_loop, Var, ani_cache
from bot.core.database import db
from bot.core.func_utils import *
from bot.core.auto_animes import get_animes
from bot.core.reporter import rep
from bot.modules.up_posts import upcoming_animes
from bot.func import *
from bot.autoDelete import *
from bot.query import *
import logging
import feedparser
from bs4 import BeautifulSoup
from bot.headers import *
from bot.queue import *
from bot.utils.cache import custom_filename_wait
from bot.core.torrent_info import get_torrent_info


pending_invites = {}  # Global dictionary
rename_task_wait = {}
custom_filename_wait = {}
edit_cache = {}
FSUB_LINK_EXPIRY = Var.FSUB_LINK_EXPIRY

#=====================================================================================##

WAIT_MSG = "<b>Working....</b>"

REPLY_ERROR = "<code>Use this command as a reply to any telegram message without any spaces.</code>"

#=====================================================================================##


def non_command():
    return filters.text & filters.user(Var.ADMINS) & ~filters.regex(r"^/")



#=====================================================================================##

@bot.on_message(command('leech') & private & user(Var.ADMINS))
@new_task
async def add_task(client, message):
    args = message.text.split(maxsplit=1)
    replied = message.reply_to_message
    input_text = None

    # Case 1: Command includes URL/link
    if len(args) > 1:
        input_text = args[1].strip()
    # Case 2: Replied message has link
    elif replied and (replied.text or replied.caption):
        input_text = (replied.text or replied.caption).strip()

    if not input_text:
        return await sendMessage(message, "<b>❌ No link or task found!</b>")

    # Case A: Magnet link
    if input_text.startswith("magnet:?"):
        title = extract_title_from_magnet(input_text)
        bot_loop.create_task(get_animes(title, input_text, True))
        return await sendMessage(message, f"<b>✅ Magnet Task Added:</b>\n• <b>Title:</b> {title}\n• <b>Link:</b> {input_text}")

    # Case B: .torrent URL
    if input_text.endswith(".torrent") and input_text.startswith("http"):
        title = await extract_title_from_torrent(input_text)
        bot_loop.create_task(get_animes(title, input_text, True))
        return await sendMessage(message, f"<b>✅ Torrent Task Added:</b>\n• <b>Title:</b> {title}\n• <b>Link:</b> {input_text}")

    # Case C: RSS Feed
    if "rss" in input_text and "://" in input_text:
        # Optional: handle index
        url_parts = input_text.split()
        feed_url = url_parts[0]
        index = int(url_parts[1]) if len(url_parts) > 1 and url_parts[1].isdigit() else 0
        taskInfo = await getfeed(feed_url, index)
        if not taskInfo:
            return await sendMessage(message, "<b>❌ No RSS Task found.</b>")
        bot_loop.create_task(get_animes(taskInfo.title, taskInfo.link, True))
        return await sendMessage(
            message,
            f"<b>✅ RSS Task Added:</b>\n• <b>Title:</b> {taskInfo.title}\n• <b>Link:</b> {taskInfo.link}"
        )

    # Unknown/invalid input
    return await sendMessage(message, "<b>❌ Unsupported or Invalid Link Format!</b>")

#=====================================================================================##



@bot.on_message(filters.command('update') & filters.private)
async def update_bot(client, message: Message):
    if message.from_user.id in Var.ADMINS:
        sent = await message.reply("🔄 Pᴜʟʟɪɴɢ ʟᴀᴛᴇsᴛ ᴜᴘᴅᴀᴛᴇs ғʀᴏᴍ Gɪᴛ...")

        # Run git pull
        process = await asyncio.create_subprocess_shell(
            "git pull",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if process.returncode != 0:
            return await sent.edit(f"❌ Git pull failed:\n<code>{error}</code>")

        await sent.edit(f"✅ Uᴘᴅᴀᴛᴇᴅ:\n<code>{output}</code>\n\n♻️ Rᴇsᴛᴀʀᴛɪɴɢ ʙᴏᴛ...")

        # Restart the bot using exec
        await asyncio.sleep(2)
        os.execvp(sys.executable, [sys.executable, "-m", "bot"])

    else:
        await message.reply_text("<blockquote><b>Aᴅᴍɪɴ Oɴʟʏ</b> 💀</blockquote>", parse_mode=ParseMode.HTML)




@bot.on_message(filters.command('anime') & filters.private & filters.user(Var.ADMINS))
async def search_anime(client, message):
    user_id = message.from_user.id
    if not await db.present_user(user_id):
        try:
            await db.add_user(user_id)
        except Exception as e:
            await client.send_message(-1001868871195, f"{e}")

    try:
        query = message.text.split("/anime ", maxsplit=1)[1]
    except IndexError:
        await message.reply_text("<b>Usage:</b> <code>/anime anime_name</code>")
        return

    search_url = f"https://animepahe.ru/api?m=search&q={query.replace(' ', '+')}"
    response = session.get(search_url).json()

    if response['total'] == 0:
        await message.reply_text("Anime not found.")
        return

    user_queries[user_id] = query
    anime_buttons = [
        [InlineKeyboardButton(anime['title'], callback_data=f"anime_{anime['session']}")]
        for anime in response['data']
    ]
    reply_markup = InlineKeyboardMarkup(anime_buttons)

    gif_url = "https://telegra.ph/file/33067bb12f7165f8654f9.mp4"
    await message.reply_video(
        video=gif_url,
        caption=f"Search Result for <code>{query}</code>",
        reply_markup=reply_markup,
        quote=True
    )


@bot.on_message(filters.command('queue') & filters.private & filters.user(Var.ADMINS))
async def view_queue(client, message):
    with download_lock:
        if not global_queue:
            await message.reply_text("No active downloads.")
            return

        user_task_counts = {}
        for username, link in global_queue:
            user_task_counts[username] = user_task_counts.get(username, 0) + 1

        queue_text = "Active Downloads:\n"
        for i, (username, task_count) in enumerate(user_task_counts.items(), start=1):
            user_profile_link = f"[{username}](https://t.me/{username})"
            queue_text += f"{i}. {user_profile_link} (Active Task = {task_count})\n"

        await message.reply_text(queue_text, disable_web_page_preview=True)

#=====================================================================================##

@bot.on_message(filters.command('latest') & filters.private)
async def send_latest_anime(client, message):
    try:
        # Fetch the latest airing anime from AnimePahe
        API_URL = "https://animepahe.ru/api?m=airing&page=1"
        response = session.get(API_URL)
        if response.status_code == 200:
            data = response.json()
            anime_list = data.get('data', [])

            # Check if any anime is available
            if not anime_list:
                await message.reply_text("No latest anime available at the moment.")
                return

            # Prepare the message content with titles and links
            latest_anime_text = "<b>📺 Latest Airing Anime:</b>\n\n"
            for idx, anime in enumerate(anime_list, start=1):
                title = anime.get('anime_title')
                anime_session = anime.get('anime_session')
                episode = anime.get('episode')
                link = f"https://animepahe.ru/anime/{anime_session}"
                latest_anime_text += f"<b>{idx}) <a href='{link}'>{title}</a> [E{episode}]</b>\n"

            # Send the formatted anime list with clickable links
            await message.reply_text(latest_anime_text, disable_web_page_preview=True)
        else:
            await message.reply_text(f"Failed to fetch data from the API. Status code: {response.status_code}")

    except Exception as e:
        await client.send_message(-1001868871195, f"Error: {e}")
        await message.reply_text("Something went wrong. Please try again later.")


#=====================================================================================##

@bot.on_message(filters.command('airing') & filters.private)
async def send_airing_anime(client, message):
    try:
        # Fetch the latest airing anime from AnimePahe
        API_URL = "https://animepahe.ru/anime/airing"
        response = session.get(API_URL)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            # Find all anime links
            anime_list = soup.select(".index-wrapper .index a")

            # Check if any anime is available
            if not anime_list:
                await message.reply_text("No airing anime available at the moment.")
                return

            # Prepare the message content with titles and links
            airing_anime_text = "<b>🎬 Currently Airing Anime:</b>\n\n"
            for idx, anime in enumerate(anime_list, start=1):
                title = anime.get("title", "Unknown Title")
                link = "https://animepahe.ru" + anime["href"]
                airing_anime_text += f"<b>{idx}) {title}</b>\n"

            # Send the formatted anime list with clickable links
            await message.reply_text(airing_anime_text, disable_web_page_preview=True)
        else:
            await message.reply_text(f"Failed to fetch data. Status Code: {response.status_code}")

    except Exception as e:
        await message.reply_text("Something went wrong. Please try again later.")


#=====================================================================================##

# This handler captures membership updates (like when a user leaves, banned)
@bot.on_chat_member_updated()
async def handle_Chatmembers(client, chat_member_updated: ChatMemberUpdated):    
    chat_id = chat_member_updated.chat.id

    if await db.reqChannel_exist(chat_id):
        old_member = chat_member_updated.old_chat_member

        if not old_member:
            return

        if old_member.status == ChatMemberStatus.MEMBER:
            user_id = old_member.user.id

            if await db.reqSent_user_exist(chat_id, user_id):
                await db.del_reqSent_user(chat_id, user_id)


# This handler will capture any join request to the channel/group where the bot is an admin
@bot.on_chat_join_request()
async def handle_join_request(client, chat_join_request):
    chat_id = chat_join_request.chat.id  

    if await db.reqChannel_exist(chat_id):
        user_id = chat_join_request.from_user.id 

        if not await db.reqSent_user_exist(chat_id, user_id):
            await db.reqSent_user(chat_id, user_id)



# Global cache for chat data to reduce API calls
chat_data_cache = {}

async def not_joined(client: Client, message: Message):
    temp = await message.reply("<b>Checking Subscription...</b>")
    user_id = message.from_user.id
    bot_info = await client.get_me()
    bot_username = bot_info.username  
    REQFSUB = await db.get_request_forcesub()
    buttons = []
    count = 0

    try:
        for total, chat_id in enumerate(await db.get_all_channels(), start=1):
            await message.reply_chat_action(ChatAction.PLAYING)

            # Show the join button of non-subscribed Channels.....
            if not await is_userJoin(client, user_id, chat_id):
                try:
                    # Check if chat data is in cache
                    if chat_id in chat_data_cache:
                        data = chat_data_cache[chat_id]  # Get data from cache
                    else:
                        data = await client.get_chat(chat_id)  # Fetch from API
                        chat_data_cache[chat_id] = data  # Store in cache

                    cname = data.title

                    # Handle private channels and links
                    if REQFSUB and not data.username: 
                        link = await db.get_stored_reqLink(chat_id)
                        await db.add_reqChannel(chat_id)

                        if not link:
                            link = (await client.create_chat_invite_link(chat_id=chat_id, creates_join_request=True)).invite_link
                            await db.store_reqLink(chat_id, link)
                    else:
                        link = data.invite_link

                    # Add button for the chat
                    buttons.append([InlineKeyboardButton(text=cname, url=link)])
                    count += 1
                    await temp.edit(f"<b>{'! ' * count}</b>")

                except Exception as e:
                    print(f"Can't Export Channel Name and Link..., Please Check If the Bot is admin in the FORCE SUB CHANNELS:\nProvided Force sub Channel:- {chat_id}")
                    return await temp.edit(f"<b><i>! Eʀʀᴏʀ, </i></b>\n<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>")

        try:
            buttons.append([InlineKeyboardButton(text='♻️ Tʀʏ Aɢᴀɪɴ', url=f"https://t.me/{bot_username}?start={message.command[1]}")])
        except IndexError:
            pass

        await message.reply_photo(
            photo=FORCE_PIC,
            caption=FORCE_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=InlineKeyboardMarkup(buttons))#,
    #message_effect_id=5104841245755180586  #🔥 Add the effect ID here
        #)
    except Exception as e:
        print(f"Error: {e}")  # Print the error message for debugging
        # Optionally, send an error message to the user or handle further actions here
        await temp.edit(f"<b><i>! Eʀʀᴏʀ, </i></b>\n<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>")

@bot.on_message(command('start') & private)
@new_task
async def start_msg(client, message):
    uid = message.from_user.id
    user_id = message.from_user.id
    from_user = message.from_user
    bot_info = await client.get_me()
    bot_username = bot_info.username  
    txtargs = message.text.split()
    temp = await sendMessage(message, "<i>ᴜᴘʟᴏᴀᴅɪɴɢ..</i>")
    # ✅ Add user to DB if not already present
    if not await db.present_user(uid):
        await db.add_user(uid)
    # ✅ Check Force Subscription
    if not await is_subscribed(client, message):
        await temp.delete()
        return await not_joined(client, message)
    # ✅ If user is subscribed, continue with normal start message
    if len(txtargs) <= 1:
        await temp.delete()
        btns = []
        for elem in Var.START_BUTTONS.split():
            try:
                bt, link = elem.split('|', maxsplit=1)
            except:
                continue
            if len(btns) != 0 and len(btns[-1]) == 1:
                btns[-1].insert(1, InlineKeyboardButton(bt, url=link))
            else:
                btns.append([InlineKeyboardButton(bt, url=link)])
        smsg = Var.START_MSG.format(
            first_name=from_user.first_name,
            last_name=from_user.last_name,
            mention=from_user.mention, 
            user_id=from_user.id
        )
        if Var.START_PHOTO:
            await message.reply_photo(
                photo=Var.START_PHOTO, 
                caption=smsg,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("• ғɪɴɪsʜᴇᴅ •", url='https://t.me/KGN_BOTZ')],
                    [InlineKeyboardButton("• ᴄʜᴀɴɴᴇʟs", callback_data='channel'),
                     InlineKeyboardButton("• ᴄʜᴀᴛ •", url='https://t.me/KGN_SUPPORTZ')],
                    [InlineKeyboardButton("• ᴏᴜʀ ᴄᴏᴍᴍᴜɴɪᴛʏ •", url='https://t.me/chrunchyrool')],
                ])
            )
        else:
            await sendMessage(message, smsg, InlineKeyboardMarkup(btns) if len(btns) != 0 else None)
        return
    # ✅ Handle Movie Fetching from Stored Database
    try:
        arg = (await decode(txtargs[1])).split('-')
    except Exception as e:
        await rep.report(f"User : {uid} | Error : {str(e)}", "error")
        await editMessage(temp, "<b>Input Link Code Decode Failed !</b>")
        return
    if len(arg) == 2 and arg[0] == 'get':
        try:
            fid = int(int(arg[1]) / abs(int(Var.FILE_STORE)))
        except Exception as e:
            await rep.report(f"User : {uid} | Error : {str(e)}", "error")
            await editMessage(temp, "<b>Input Link Code is Invalid !</b>")
            return
        try:
            msg = await client.get_messages(Var.FILE_STORE, message_ids=fid)
            if msg.empty:
                return await editMessage(temp, "<b>File Not Found !</b>")
            # ✅ Fetch Auto-Delete, Channel Button & Protection Settings
            AUTO_DEL, DEL_TIMER, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
                db.get_auto_delete(),
                db.get_del_timer(),
                db.get_channel_button(),
                db.get_protect_content()
            )
            if CHNL_BTN:
                button_name, button_link = await db.get_channel_button_link()
            # ✅ Use the original caption only (no modification)
            original_caption = getattr(msg, 'caption', '')
            # ✅ Preserve original buttons unless CHNL_BTN is enabled
            reply_markup = (
                InlineKeyboardMarkup([[InlineKeyboardButton(text=button_name, url=button_link)]])
                if CHNL_BTN and (msg.document or msg.photo or msg.video or msg.audio)
                else msg.reply_markup
            )
            # ✅ Send the file to user
            try:
                copied_msg = await msg.copy(
                    message.chat.id,
                    caption=original_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    protect_content=PROTECT_MODE
                )
                await temp.delete()
                # ⏳ Auto-Delete after Timer
                if AUTO_DEL:
                    asyncio.create_task(delete_message(copied_msg, DEL_TIMER))
                    asyncio.create_task(auto_del_notification(bot_username, copied_msg, DEL_TIMER, txtargs[1]))
            except FloodWait as e:
                await asyncio.sleep(e.x)
                copied_msg = await msg.copy(
                    message.chat.id,
                    caption=original_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    protect_content=PROTECT_MODE
                )
                if AUTO_DEL:
                    asyncio.create_task(delete_message(copied_msg, DEL_TIMER))
                    asyncio.create_task(auto_del_notification(bot_username, copied_msg, DEL_TIMER, txtargs[1]))
        except Exception as e:
            await rep.report(f"User : {uid} | Error : {str(e)}", "error")
            await editMessage(temp, "<b>File Not Found !</b>")
    else:
        await editMessage(temp, "<b>Input Link is Invalid for Usage !</b>")


@bot.on_message(command('pause') & private & user(Var.ADMINS))
async def pause_fetch(client, message):
    ani_cache['fetch_animes'] = False
    await sendMessage(message, "`Successfully Paused Fetching Animes...`")

@bot.on_message(command('resume') & private & user(Var.ADMINS))
async def pause_fetch(client, message):
    ani_cache['fetch_animes'] = True
    await sendMessage(message, "`Successfully Resumed Fetching Animes...`")

@bot.on_message(command('log') & private & user(Var.ADMINS))
@new_task
async def _log(client, message):
    await message.reply_document("log.txt", quote=True)

@bot.on_message(command('addlink') & private & user(Var.ADMINS))
@new_task
async def add_task(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Link Found to Add</b>")

    Var.RSS_ITEMS.append(args[0])
    req_msg = await sendMessage(message, f"`Global Link Added Successfully!`\n\n    • **All Link(s) :** {', '.join(Var.RSS_ITEMS)[:-2]}")

@bot.on_message(command('addtask') & private & user(Var.ADMINS))
@new_task
async def add_task(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Task Found to Add</b>")

    index = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
    if not (taskInfo := await getfeed(args[1], index)):
        return await sendMessage(message, "<b>No Task Found to Add for the Provided Link</b>")

    ani_task = bot_loop.create_task(get_animes(taskInfo.title, taskInfo.link, True))
    await sendMessage(message, f"<i><b>Task Added Successfully!</b></i>\n\n    • <b>Task Name :</b> {taskInfo.title}\n    • <b>Task Link :</b> {args[1]}")

@bot.on_message(command(['addtask1']) & private & user(Var.ADMINS))
@new_task
async def add_task_direct(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Torrent Link Provided</b>")

    torrent_link = args[1]

    # Get torrent metadata
    try:
        torrent_info = await get_torrent_info(torrent_link)  # You must define this function
    except Exception as e:
        return await sendMessage(message, f"<b>Failed to fetch torrent info:</b> {e}")

    title = torrent_info.get("name", "Unknown")
    size = torrent_info.get("size", "Unknown")

    ani_task = bot_loop.create_task(get_animes(title, torrent_link, True))

    await sendMessage(
        message,
        f"<i><b>Task Added Successfully!</b></i>\n\n"
        f"    • <b>Task Name :</b> {title}\n"
        f"    • <b>Size :</b> {size}\n"
        f"    • <b>Torrent Link :</b> {torrent_link}"
    )





@bot.on_message(filters.command('addfsub') & filters.private & filters.user(Var.ADMINS))
async def add_forcesub(client: Client, message: Message):
    pro = await message.reply("<b><i>Processing....</i></b>", quote=True)
    check = 0
    channel_ids = await db.get_all_channels()
    fsubs = message.text.split()[1:]

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]])

    if not fsubs:
        await pro.edit("<b>You need to add channel IDs\n<blockquote><u>EXAMPLE</u>:\n/addfsub [channel_ids] :</b> You can add one or multiple channel IDs at a time.</blockquote>", reply_markup=reply_markup)
        return

    channel_list = ""
    for id in fsubs:
        try:
            id = int(id)
        except:
            channel_list += f"<b><blockquote>Invalid ID: <code>{id}</code></blockquote></b>\n\n"
            continue

        if id in channel_ids:
            channel_list += f"<blockquote><b>ID: <code>{id}</code>, already exists..</b></blockquote>\n\n"
            continue

        id = str(id)
        if id.startswith('-') and id[1:].isdigit() and len(id) == 14:
            try:
                data = await client.get_chat(id)
                link = data.invite_link
                cname = data.title

                if not link:
                    link = await client.export_chat_invite_link(id)

                channel_list += f"<b><blockquote>NAME: <a href={link}>{cname}</a> (ID: <code>{id}</code>)</blockquote></b>\n\n"
                check += 1

            except:
                channel_list += f"<b><blockquote>ID: <code>{id}</code>\n<i>Unable to add force-sub, check the channel ID or bot permissions properly..</i></blockquote></b>\n\n"

        else:
            channel_list += f"<b><blockquote>Invalid ID: <code>{id}</code></blockquote></b>\n\n"
            continue

    if check == len(fsubs):
        for id in fsubs:
            await db.add_channel(int(id))
        await pro.edit(f'<b>Force-sub channel added ✅</b>\n\n{channel_list}', reply_markup=reply_markup, disable_web_page_preview=True)

    else:
        await pro.edit(f'<b>❌ Error occurred while adding force-sub channels</b>\n\n{channel_list.strip()}\n\n<b><i>Please try again...</i></b>', reply_markup=reply_markup, disable_web_page_preview=True)


@bot.on_message(filters.command('delfsub') & filters.private & filters.user(Var.ADMINS))
async def delete_all_forcesub(client: Client, message: Message):
    pro = await message.reply("<b><i>Processing....</i></b>", quote=True)
    channels = await db.get_all_channels()
    fsubs = message.text.split()[1:]

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]])

    if not fsubs:
        return await pro.edit("<b>⁉️ Please, provide valid IDs or arguments\n<blockquote><u>EXAMPLES</u>:\n/delfsub [channel_ids] :</b> To delete one or multiple specified IDs\n<code>/del_fsub all</code>: To delete all available force-sub IDs</blockquote>", reply_markup=reply_markup)

    if len(fsubs) == 1 and fsubs[0].lower() == "all":
        if channels:
            for id in channels:
                await db.del_channel(id)

            ids = "\n".join(f"<blockquote><code>{channel}</code> ✅</blockquote>" for channel in channels)
            return await pro.edit(f"<b>⛔️ All available channel IDs are deleted:\n{ids}</b>", reply_markup=reply_markup)
        else:
            return await pro.edit("<b><blockquote>⁉️ No channel IDs available to delete</blockquote></b>", reply_markup=reply_markup)

    if len(channels) >= 1:
        passed = ''
        for sub_id in fsubs:
            try:
                id = int(sub_id)
            except:
                passed += f"<b><blockquote><i>Invalid ID: <code>{sub_id}</code></i></blockquote></b>\n"
                continue
            if id in channels:
                await db.del_channel(id)

                passed += f"<blockquote><code>{id}</code> ✅</blockquote>\n"
            else:
                passed += f"<b><blockquote><code>{id}</code> not in force-sub channels</blockquote></b>\n"

        await pro.edit(f"<b>⛔️ Provided channel IDs are deleted:\n\n{passed}</b>", reply_markup=reply_markup)

    else:
        await pro.edit("<b><blockquote>⁉️ No channel IDs available to delete</blockquote></b>", reply_markup=reply_markup)


@bot.on_message(filters.command('channels') & filters.private & filters.user(Var.ADMINS))
async def get_forcesub(client: Client, message: Message):
    pro = await message.reply("<b><i>Processing....</i></b>", quote=True)
    channels = await db.get_all_channels()
    channel_list = "<b><blockquote>❌ No force sub channel found!</b></blockquote>"
    if channels:
        channel_list = ""
        for id in channels:
            await message.reply_chat_action(ChatAction.TYPING)
            try:
                data = await client.get_chat(id)
                link = data.invite_link
                cname = data.title

                if not link:
                    link = await client.export_chat_invite_link(id)

                channel_list += f"<b><blockquote>NAME: <a href={link}>{cname}</a>\n(ID: <code>{id}</code>)</blockquote></b>\n\n"

            except:
                channel_list += f"<b><blockquote>ID: <code>{id}</code>\n<i>Unable to load other details..</i></blockquote></b>\n\n"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]])
    await message.reply_chat_action(ChatAction.CANCEL)
    await pro.edit(f"<b>⚡ Force-sub channel list:</b>\n\n{channel_list}", reply_markup=reply_markup, disable_web_page_preview=True)

#=====================================================================================##
#.........Extra Functions.......#
#=====================================================================================##

# Auto Delete Setting Commands
@bot.on_message(filters.command('autodel') & filters.private & filters.user(Var.ADMINS))
async def autoDelete_settings(client, message):
    await message.reply_chat_action(ChatAction.TYPING)

    try:
            timer = convert_time(await db.get_del_timer())
            if await db.get_auto_delete():
                autodel_mode = on_txt
                mode = 'Dɪsᴀʙʟᴇ Mᴏᴅᴇ ❌'
            else:
                autodel_mode = off_txt
                mode = 'Eɴᴀʙʟᴇ Mᴏᴅᴇ ✅'

            await message.reply_photo(
                photo = autodel_cmd_pic,
                caption = AUTODEL_CMD_TXT.format(autodel_mode=autodel_mode, timer=timer),
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton(mode, callback_data='chng_autodel'), InlineKeyboardButton('sᴇᴛ ᴛɪᴍᴇʀ •', callback_data='set_timer')],
                    [InlineKeyboardButton('• ʀᴇғʀᴇsʜ', callback_data='autodel_cmd'), InlineKeyboardButton('ᴄʟᴏsᴇ •', callback_data='close')]
                ])#,
                #message_effect_id = 5107584321108051014 #👍
            )
    except Exception as e:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cʟᴏsᴇ ✖️", callback_data = "close")]])
            await message.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ..\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote><b><i>Cᴏɴᴛᴀɴᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ: @ExE_AQUIB</i></b>", reply_markup=reply_markup)
#edit post 
@bot.on_message(filters.command("edit") & filters.user(Var.ADMINS))
async def edit_start(client, message):
    print("DEBUG: /edit triggered")
    await message.reply("Please forward the message from the channel you want to edit.")
    edit_cache[message.from_user.id] = {"state": "await_forward"}


@bot.on_message(filters.forwarded & filters.user(Var.ADMINS))
async def handle_forwarded(client, message):
    user_id = message.from_user.id
    if user_id not in edit_cache or edit_cache[user_id]["state"] != "await_forward":
        return

    if not message.forward_from_chat or not message.forward_from_message_id:
        return await message.reply("❌ Invalid forwarded message.")

    buttons = message.reply_markup.inline_keyboard if message.reply_markup else []

    edit_cache[user_id].update({
        "state": "await_button",
        "chat_id": message.forward_from_chat.id,
        "msg_id": message.forward_from_message_id,
        "buttons": buttons
    })

    await message.reply("Now send the new quality button like:\n`1080p - https://link.com`", quote=True)


@bot.on_message(non_command() & filters.user(Var.ADMINS))
async def add_new_button(client, message):
    print("DEBUG: /edit non")
    user_id = message.from_user.id
    if user_id not in edit_cache or edit_cache[user_id]["state"] != "await_button":
        return

    if " - " not in message.text:
        return await message.reply("❌ Invalid format. Use: `QUALITY - LINK`")

    label, link = map(str.strip, message.text.split(" - ", 1))
    buttons = edit_cache[user_id]["buttons"]

    if not buttons or len(buttons[-1]) >= 2:
        buttons.append([InlineKeyboardButton(label, url=link)])
    else:
        buttons[-1].append(InlineKeyboardButton(label, url=link))

    edit_cache[user_id]["buttons"] = buttons
    edit_cache[user_id]["state"] = "await_post"

    await message.reply("Preview of updated buttons:", reply_markup=InlineKeyboardMarkup(buttons))
    await message.reply("Send `/post` to apply this to the original message.")


@bot.on_message(filters.command("post") & filters.user(Var.ADMINS))
async def finalize_edit(client, message):
    user_id = message.from_user.id
    if user_id not in edit_cache or edit_cache[user_id]["state"] != "await_post":
        return await message.reply("Nothing to post. Use `/edit` first.")

    data = edit_cache.pop(user_id)

    try:
        await client.edit_message_reply_markup(
            chat_id=data["chat_id"],
            message_id=data["msg_id"],
            reply_markup=InlineKeyboardMarkup(data["buttons"])
        )
        await message.reply("✅ Inline buttons updated successfully.")
    except Exception as e:
        await message.reply(f"❌ Failed to update message:\n<code>{e}</code>")


#Files related settings command
@bot.on_message(filters.command('fsettings') & filters.private & filters.user(Var.ADMINS))
async def files_commands(client: Client, message: Message):
    await message.reply_chat_action(ChatAction.TYPING)

    try:
        protect_content = hide_caption = channel_button = off_txt
        pcd = hcd = cbd = '❌'
        if await db.get_protect_content():
            protect_content = on_txt
            pcd = '✅'
        if await db.get_hide_caption():
            hide_caption = on_txt
            hcd = '✅'
        if await db.get_channel_button():
            channel_button = on_txt
            cbd = '✅'
        name, link = await db.get_channel_button_link()

        await message.reply_photo(
            photo = files_cmd_pic,
            caption = FILES_CMD_TXT.format(
                protect_content = protect_content,
                hide_caption = hide_caption,
                channel_button = channel_button,
                name = name,
                link = link
            ),
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f'• ᴘᴄ: {pcd}', callback_data='pc'), InlineKeyboardButton(f'• ʜᴄ : {hcd}', callback_data='hc')],
                [InlineKeyboardButton(f'• ᴄʙ: {cbd}', callback_data='cb'), InlineKeyboardButton(f'• sʙ •', callback_data='setcb')],
                [InlineKeyboardButton('• ʀᴇғʀᴇsʜ', callback_data='files_cmd'), InlineKeyboardButton('cʟᴏsᴇ', callback_data='close')]
            ])#,
            #message_effect_id = 5107584321108051014 #👍
        )
    except Exception as e:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("cʟᴏsᴇ", callback_data = "close")]])
        await message.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ..\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote><b><i>Cᴏɴᴛᴀɴᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ: @ExE_AQUIB</i></b>", reply_markup=reply_markup)

#Request force sub mode commad,,,,,,
@bot.on_message(filters.command('req') & filters.private & filters.user(Var.ADMINS))
async def handle_reqFsub(client: Client, message: Message):
    await message.reply_chat_action(ChatAction.TYPING)
    try:
        on = off = ""
        if await db.get_request_forcesub():
            on = "🟢"
            texting = on_txt
        else:
            off = "🔴"
            texting = off_txt

        button = [
            [InlineKeyboardButton(f"{on} ᴏɴ", "chng_req"), InlineKeyboardButton(f"{off} ᴏғғ", "chng_req")],
            [InlineKeyboardButton("• ᴍᴏʀᴇ sᴇᴛᴛɪɴɢs •", "more_settings")]
        ]
        await message.reply(text=RFSUB_CMD_TXT.format(req_mode=texting), reply_markup=InlineKeyboardMarkup(button))#, #message_effect_id=5046509860389126442)

    except Exception as e:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cʟᴏsᴇ ✖️", callback_data = "close")]])
        await message.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ..\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote><b><i>Cᴏɴᴛᴀɴᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ: @ExE_AQUIB</i></b>", reply_markup=reply_markup)




@bot.on_message(filters.command('users') & filters.private & filters.user(Var.ADMINS))
async def get_users(client: bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await db.full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@bot.on_message(filters.private & filters.command('broadcast') & filters.user(Var.ADMINS))
async def send_text(client: bot, message: Message):
    if message.reply_to_message:
        query = await db.full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0

        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await db.del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await db.del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1

        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""

        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()



@bot.on_message(filters.command("watermark") & filters.private & filters.user(Var.ADMINS))
async def watermark_command(client: Client, message: Message):
    current_watermark = await db.get_watermark()

    if current_watermark:
        status_text = "🟢 Watermark is enabled."
        watermark_display = (
            f"<a href='{current_watermark}'>🔗 View Watermark</a>" if current_watermark.startswith(("http://", "https://")) 
            else "🖼 Watermark is an image."
        )
    else:
        status_text = "🔴 Watermark is disabled."
        watermark_display = "No watermark set."

    buttons = [
        [InlineKeyboardButton("ᴏɴ" if current_watermark else "ᴏғғ", callback_data="chng_watermark"),
        InlineKeyboardButton("• ᴄʟᴏsᴇ •", callback_data="close")],
        [InlineKeyboardButton("sᴇᴛ ᴡᴀᴛᴇʀᴍᴀʀᴋ", callback_data="set_watermark")]
    ]

    if current_watermark and not current_watermark.startswith(("http://", "https://")):
        # If watermark is an image, send it before replying with buttons
        await message.reply_photo(
            photo=current_watermark,
            caption=f"<b>Watermark Settings</b>\n\n{status_text}\n\n{watermark_display}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await message.reply_text(
            text=f"<b>Watermark Settings</b>\n\n{status_text}\n\n{watermark_display}",
            reply_markup=InlineKeyboardMarkup(buttons))


@bot.on_message(filters.command("thumbnail") & filters.private & filters.user(Var.ADMINS))
async def thumbnail_command(client: Client, message: Message):
    current_thumbnail = await db.get_thumbnail()

    # Ensure `current_thumbnail` is a valid string before using `startswith()`
    if isinstance(current_thumbnail, str):
        if current_thumbnail.startswith(("http://", "https://")):
            status_text = "🟢 Thumbnail is enabled."
            thumbnail_display = f"<a href='{current_thumbnail}'>🔗 View Thumbnail</a>"
        else:
            status_text = "🟢 Thumbnail is enabled."
            thumbnail_display = "🖼 Thumbnail is an image."
    else:
        current_thumbnail = None  # Reset to None if invalid
        status_text = "🔴 Thumbnail is disabled."
        thumbnail_display = "No Thumbnail set."

    buttons = [
        [InlineKeyboardButton("ᴏɴ" if current_thumbnail else "ᴏғғ", callback_data="chng_thumbnail"),
        InlineKeyboardButton("close", callback_data="close")],
        [InlineKeyboardButton("sᴇᴛ ᴛʜᴜᴍʙɴᴀɪʟ", callback_data="set_thumbnail")]
    ]

    if current_thumbnail and not current_thumbnail.startswith(("http://", "https://")):
        # If thumbnail is a local image, send it before replying with buttons
        await message.reply_photo(
            photo=current_thumbnail,
            caption=f"<b>Thumbnail Settings</b>\n\n{status_text}\n\n{thumbnail_display}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await message.reply_text(
            text=f"<b>Thumbnail Settings</b>\n\n{status_text}\n\n{thumbnail_display}",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        

@bot.on_message(filters.command("banner") & filters.private & filters.user(Var.ADMINS))
async def banner_command(client: Client, message: Message):
    current_banner = await db.get_banner()

    is_valid_str = isinstance(current_banner, str)
    is_banner_url = is_valid_str and current_banner.startswith(("http://", "https://"))
    is_banner_image = is_valid_str and not is_banner_url

    if current_banner:
        status_text = "🟢 Banner is enabled."
        banner_display = (
            f"<a href='{current_banner}'>🔗 View Banner</a>" if is_banner_url 
            else "🖼 Banner is an image."
        )
    else:
        status_text = "🔴 Banner is disabled."
        banner_display = "No Banner set."

    buttons = [
        [
            InlineKeyboardButton("ᴏɴ" if current_banner else "ᴏғғ", callback_data="chng_banner"),
            InlineKeyboardButton("close", callback_data="close")
        ],
        [InlineKeyboardButton("sᴇᴛ ʙᴀɴɴᴇʀ", callback_data="set_banner")]
    ]

    if is_banner_image:
        await message.reply_photo(
            photo=current_banner,
            caption=f"<b>Banner Settings</b>\n\n{status_text}\n\n{banner_display}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await message.reply_text(
            text=f"<b>Banner Settings</b>\n\n{status_text}\n\n{banner_display}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        
@bot.on_message(filters.command("set_main") & filters.user(Var.ADMINS))
async def set_main_channel_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply(
            "⚠️ Please provide a valid channel ID.\n\nExample:\n<code>/set_main -1001234567890</code>"
        )

    try:
        new_channel_id = int(message.command[1])
        old_channel_id = await db.get_main_channel()
        await db.set_main_channel(new_channel_id)

        if old_channel_id:
            await message.reply(
                f"🔁 Main channel updated:\n"
                f"• Old: <code>{old_channel_id}</code>\n"
                f"• New: <code>{new_channel_id}</code>"
            )
        else:
            await message.reply(f"✅ Main channel set to: <code>{new_channel_id}</code>")

    except Exception as e:
        await message.reply(f"❌ Error:\n<code>{e}</code>")

@bot.on_message(filters.command("get_main") & filters.user(Var.ADMINS))
async def get_main_channel_cmd(client: Client, message: Message):
    channel_id = await db.get_main_channel()
    if channel_id:
        await message.reply(f"📢 Current main channel ID:\n<code>{channel_id}</code>")
    else:
        await message.reply("⚠️ Main channel is not set.")

@bot.on_message(filters.command("remove_main") & filters.user(Var.ADMINS))
async def remove_main_channel_cmd(client: Client, message: Message):
    channel_id = await db.get_main_channel()
    if not channel_id:
        return await message.reply("⚠️ No main channel is currently set.")

    await db.remove_main_channel()
    await message.reply(f"🗑️ Main channel removed.\n(WAS: <code>{channel_id}</code>)")

@bot.on_message(filters.command("schedule") & filters.user(Var.OWNER_ID))
async def manual_schedule(_, message):
    await message.reply_text("📡 Generating schedule...")
    await upcoming_animes()
    await message.reply_text("✅ Schedule posted!")



@bot.on_message(filters.command("setchannel") & filters.user(Var.OWNER_ID))
async def set_anime_channel_handler(client, message):
    try:
        print("✅ /setchannel triggered")

        if not message.reply_to_message or not message.reply_to_message.forward_from_chat:
            print("❌ Invalid usage — must reply to a forwarded message.")
            return await message.reply_text("❌ Usage:\nReply to a forwarded channel message with:\n`/setchannel <anime name>`")

        args = message.text.split(None, 1)
        if len(args) < 2:
            return await message.reply_text("❌ Please provide the anime name: `/setchannel <anime name>`")

        anime_name = args[1].strip()
        chat = message.reply_to_message.forward_from_chat
        channel_id = chat.id

        print(f"✅ Setting channel for: {anime_name} → ID: {channel_id}")
        await db.set_anime_channel(anime_name, channel_id)

        chat_info = await bot.get_chat(channel_id)
        if chat_info.username:
            invite = f"https://t.me/{chat_info.username}"
            await db.set_anime_invite(anime_name, invite)
            return await message.reply_text(
                f"✅ Channel set for **{anime_name}** → `{channel_id}`\n🔓 [t.me/{chat_info.username}]({invite})"
            )
        else:
            pending_invites[message.from_user.id] = anime_name
            return await message.reply_text(
                f"✅ Channel set for **{anime_name}** → `{channel_id}`\n🔐 Now send the **invite link** for this private channel.Eg: /invite https://t.me/+ahshs0"
            )

    except Exception as e:
        print(f"❌ Error in /setchannel: {e}")
        await message.reply_text(f"❌ Error: {e}")


@bot.on_message(filters.command("invite") & filters.private & filters.user(Var.OWNER_ID))
async def handle_invite_command(client, message):
    user_id = message.from_user.id

    if user_id not in pending_invites:
        return await message.reply_text("❌ No anime is waiting for an invite link. Use `/setchannel` first.")

    if len(message.command) < 2:
        return await message.reply_text("❌ Please send the invite link like:\n`/invite https://t.me/xxxxxxx`")

    invite_link = message.command[1].strip()
    anime_name = pending_invites.pop(user_id)

    if not invite_link.startswith("https://t.me/"):
        return await message.reply_text("❌ Invalid invite link. Please send a valid Telegram invite link.")

    try:
        await db.set_anime_invite(anime_name, invite_link)
        await message.reply_text(f"✅ Invite link saved for **{anime_name}**!")
    except Exception as e:
        await message.reply_text(f"❌ Failed to save invite link: {e}")




# List all anime-channel mappings
@bot.on_message(filters.command("listchannels") & filters.user(Var.OWNER_ID))
async def list_all_channels(client, message):
    print("✅ Command triggered: /listchannels")
    mapping = await db.list_all_anime_channels()
    if not mapping:
        return await message.reply("📭 No anime-channel mappings found.")
    text = "\n".join([f"• `{k}` → `{v}`" for k, v in mapping.items()])
    await message.reply(f"📚 <b>Anime → Channel Mappings:</b>\n\n{text}", quote=True)

# Delete an anime-channel mapping
@bot.on_message(filters.command("delchannel") & filters.user(Var.OWNER_ID))
async def delete_anime_channel_handler(client, message):
    print("✅ Command triggered: /delte")
    try:
        args = message.text.split(None, 1)
        if len(args) < 2:
            return await message.reply_text("❌ Usage:\n/delchannel <anime name>")

        anime_name = args[1].strip().lower()

        # Attempt to delete channel mapping and invite
        await db.delete_anime_channel(anime_name)
        await db.delete_anime_invite(anime_name)

        await message.reply_text(f"✅ Removed channel mapping for **{anime_name}**")

    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")



@bot.on_message(filters.command("unmapped") & filters.user(Var.OWNER_ID))
async def show_unmapped(_, message):
    try:
        async with aiopen("unmapped.log", "r") as f:
            content = await f.read()
        if not content.strip():
            return await message.reply("✅ No unmapped anime titles found.")
        await message.reply(f"📜 Unmapped Titles:\n\n`{content.strip()}`")
    except FileNotFoundError:
        await message.reply("❌ Log file not found.")

@bot.on_message(filters.command("clearunmapped") & filters.user(Var.OWNER_ID))
async def clear_unmapped(_, message):
    try:
        async with aiopen("unmapped.log", "w") as f:
            await f.write("")
        await message.reply("✅ `unmapped.log` has been cleared.")
    except Exception as e:
        await message.reply(f"❌ Failed: `{e}`")




@bot.on_message(filters.all, group=99)
async def debug_all(client, message):
    text = message.text or message.caption or ""
    command = text.split()[0] if text.startswith("/") else None

    print("🧪 Debug | Text:", text)
    print("🧪 Debug | Command:", command)
    return










