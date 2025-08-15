import random
import re
import aiohttp, asyncio
from bot import *
from pyrogram import filters, Client
from pyrogram import __version__
from bot.FORMATS import *
from bot.core.func_utils import *
#from pyrogram.errors import TimeoutError
from pyrogram.enums import ChatAction
from bot.autoDelete import *
from bot.core.database import db
from bot.core.database import *
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, ReplyKeyboardMarkup, ReplyKeyboardRemove    
import requests
from bs4 import BeautifulSoup
from bot.queue import add_to_queue, remove_from_queue
from bot.kwik import extract_kwik_link
from bot.direct_link import get_dl_link
from bot.headers import *
from bot.file import *
from bot.core.text_utils import *
from bot.core.man_text import *
from bot.core.ffencoder import *
from bot.core.tguploader import *
from bot.core.reporter import rep
from re import findall
from math import floor
from time import time
from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, rename as aiorename
#from bot.modules.cmds import user_queries
import requests
from bs4 import BeautifulSoup
from shlex import split as ssplit
from asyncio import sleep as asleep, gather, create_subprocess_shell, create_task
from asyncio.subprocess import PIPE



DOWNLOAD_DIR = "./downloads"

async def download_thumbnail(url):
    """Download the thumbnail if it's a URL and return the local file path."""
    temp_path = "temp_thumb.jpg"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                content = await resp.read()
                if not content:  # Check if the response is empty
                    return None
                async with aiofiles.open(temp_path, "wb") as f:
                    await f.write(content)
                return temp_path  # Return the file path
    return None  # Return None if the request fails

# Function to extract kwik link
def extract_kwik_link(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Ensure we got a valid response

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all <script> tags
        script_tags = soup.find_all('script', type="text/javascript")
        for script in script_tags:            
            match = re.search(r'https://kwik\.si/f/[\w\d]+', script.text)
            if match:
                return match.group(0)

        return "No kwik.si link found in the page."

    except Exception as e:
        return f"Error extracting kwik link: {str(e)}"




# Initialize session with headers
session = requests.Session()
session.headers.update({
    'authority': 'animepahe.ru',
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'accept-language': 'en-US,en;q=0.9',
    'cookie': '__ddg2_=;',  # You may need a valid cookie
    'dnt': '1',
    'sec-ch-ua': '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'x-requested-with': 'XMLHttpRequest',
    'referer': 'https://animepahe.ru',
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
})

user_queries = {}
episode_data = {}
episode_urls = {}


async def download_watermark(url, save_path):
    """Downloads watermark image if it's a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                async with aiopen(save_path, 'wb') as f:
                    await f.write(await resp.read())
                return save_path
    return None


async def progress_monitor(stat_msg, prog_file, file_name, proc):
    while proc.returncode is None:
        async with aiopen(prog_file, 'r+') as p:
            text = await p.read()
        
        if text:
            time_done = floor(int(t[-1]) / 1000000) if (t := findall("out_time_ms=(\d+)", text)) else 1
            ensize = int(s[-1]) if (s := findall(r"total_size=(\d+)", text)) else 0

            diff = time() - proc.start_time
            speed = ensize / max(diff, 1)
            percent = round((time_done / 1) * 100, 2)  # Approximate
            eta = (1 - time_done) / max(speed, 1)  # Approximate

            bar = floor(percent / 8) * "■" + (12 - floor(percent / 8)) * "□"

            progress_str = f"""<b>Encoding: {file_name}</b>
<code>[{bar}]</code> {percent}%  
<b>Size:</b> {convertBytes(ensize)}  
<b>Speed:</b> {convertBytes(speed)}/s  
<b>ETA:</b> {convertTime(eta)}"""

            await stat_msg.edit(progress_str)

            if "progress=end" in text:
                break
        
        await asyncio.sleep(8)


#File setting function for retriveing modes and state of file related setting
async def fileSettings(getfunc, setfunc=None, delfunc=False) :
    btn_mode, txt_mode, pic_mode = '❌', off_txt, off_pic
    del_btn_mode = 'Eɴᴀʙʟᴇ Mᴏᴅᴇ ✅'
    try:
        if not setfunc:
            if await getfunc():
                txt_mode = on_txt    
                btn_mode = '✅'
                del_btn_mode = 'Dɪsᴀʙʟᴇ Mᴏᴅᴇ ❌'

            return txt_mode, (del_btn_mode if delfunc else btn_mode)

        else:
            if await getfunc():
                await setfunc(False)
            else:
                await setfunc(True)
                pic_mode, txt_mode = on_pic, on_txt
                btn_mode = '✅'
                del_btn_mode = 'Dɪsᴀʙʟᴇ Mᴏᴅᴇ ❌'

            return pic_mode, txt_mode, (del_btn_mode if delfunc else btn_mode)

    except Exception as e:
        print(f"Error occured at [fileSettings(getfunc, setfunc=None, delfunc=False)] : {e}")

#Provide or Make Button by takiing required modes and data
def buttonStatus(pc_data: str, hc_data: str, cb_data: str) -> list:
    button = [
        [
            InlineKeyboardButton(f'• ᴘᴄ : {pc_data}', callback_data='pc'),
            InlineKeyboardButton(f'• ʜᴄ : {hc_data}', callback_data='hc')
        ],
        [
            InlineKeyboardButton(f'• ᴄʙ : {cb_data}', callback_data='cb'), 
            InlineKeyboardButton(f'sʙ •', callback_data='setcb')
        ],
        [
            InlineKeyboardButton('• ʀᴇғʀᴇsʜ', callback_data='files_cmd'), 
            InlineKeyboardButton('Cʟᴏsᴇ', callback_data='close')
        ],
    ]
    return button

# Verify user, if he/she is admin or owner before processing the query...

    
async def authoUser(query, id, owner_only=False):
    if not owner_only:
        if not any([id in Var.ADMINS]):
            await query.answer("ʙʀᴜʜ! ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴍʏ sᴇɴᴘᴀɪ", show_alert=True)
            return False
        return True
    else:
        if id not in Var.ADMINS:
            await query.answer("ʙʀᴜʜ! ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴍʏ sᴇɴᴘᴀɪ", show_alert=True)
            return False
        return True


# Texts for watermark states
WATERMARK_ENABLED = "🟢 Watermark is enabled."
WATERMARK_DISABLED = "🔴 Watermark is disabled."


#from bot.modules.cmds import user_queries

@bot.on_callback_query()
async def cb_handler(client: bot, query: CallbackQuery):
    data = query.data        
    if data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass

    elif data == "about":
        await query.message.edit_text(
            text=(
                f"<b>○ Updates : <a href='https://t.me/animes_cruise'>Anime Cruise</a>\n"
                f"○ Language : <code>Python3</code>\n"
                f"○ Library : <a href='https://docs.pyrogram.org/'>Pyrogram asyncio {__version__}</a>"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('• ʙᴀᴄᴋ', callback_data='start'), InlineKeyboardButton('ᴄʟᴏsᴇ •', callback_data='close')]
            ]),
        )


    elif data == "setting":
        await query.edit_message_media(InputMediaPhoto(random.choice(PICS), "<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b"))
        try:
            total_fsub = len(await db.get_all_channels())
            autodel_mode = 'Eɴᴀʙʟᴇᴅ' if await db.get_auto_delete() else 'Dɪsᴀʙʟᴇᴅ'
            protect_content = 'Eɴᴀʙʟᴇᴅ' if await db.get_protect_content() else 'Dɪsᴀʙʟᴇᴅ'
            hide_caption = 'Eɴᴀʙʟᴇᴅ' if await db.get_hide_caption() else 'Dɪsᴀʙʟᴇᴅ'
            chnl_butn = 'Eɴᴀʙʟᴇᴅ' if await db.get_channel_button() else 'Dɪsᴀʙʟᴇᴅ'
            reqfsub = 'Eɴᴀʙʟᴇᴅ' if await db.get_request_forcesub() else 'Dɪsᴀʙʟᴇᴅ'

            await query.edit_message_media(
                InputMediaPhoto(random.choice(PICS),
                                SETTING_TXT.format(
                                    total_fsub = total_fsub,
                                    autodel_mode = autodel_mode,
                                    protect_content = protect_content,
                                    hide_caption = hide_caption,
                                    chnl_butn = chnl_butn,
                                    reqfsub = reqfsub
                                )
                ),
                reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('• ʙᴀᴄᴋ', callback_data='start'), InlineKeyboardButton('ᴄʟᴏsᴇ •', callback_data='close')]
                ]),
            )
        except Exception as e:
            print(f"! Error Occured on callback data = 'setting' : {e}")

    elif data == "channel":
        await query.edit_message_media(
            InputMediaPhoto("https://envs.sh/Wdj.jpg", 
                            CHANNELS_TXT.format(
                            )
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('• ʙᴀᴄᴋ', callback_data='start'), InlineKeyboardButton('sᴛᴀᴛs •', callback_data='setting')]
            ]),
        )

    elif data == "start":
        await query.edit_message_media(
            InputMediaPhoto(random.choice(PICS), 
                            START_MSG.format(
                                first = query.from_user.first_name,
                                last = query.from_user.last_name,
                                username = None if not query.from_user.username else '@' + query.from_user.username,
                                mention = query.from_user.mention,
                                id = query.from_user.id
                            )
            ),
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('• ᴀʙᴏᴜᴛ ᴍᴇ', callback_data='about'), InlineKeyboardButton('sᴇᴛᴛɪɴɢs •', callback_data='setting')]
            ]),
        )

    elif data == "files_cmd":
        if await authoUser(query, query.from_user.id) : 
            await query.answer("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b>") 

            try:
                protect_content, pcd = await fileSettings(db.get_protect_content)
                hide_caption, hcd = await fileSettings(db.get_hide_caption)
                channel_button, cbd = await fileSettings(db.get_channel_button)
                name, link = await kingdb.get_channel_button_link()

                await query.edit_message_media(
                    InputMediaPhoto(files_cmd_pic,
                                    FILES_CMD_TXT.format(
                                        protect_content = protect_content,
                                        hide_caption = hide_caption,
                                        channel_button = channel_button,
                                        name = name,
                                        link = link
                                    )
                    ),
                    reply_markup = InlineKeyboardMarkup(buttonStatus(pcd, hcd, cbd)),
                )                   
            except Exception as e:
                print(f"! Error Occured on callback data = 'files_cmd' : {e}")

    elif data == "pc":
        if await authoUser(query, query.from_user.id) :
            await query.answer("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b>") 

            try:
                pic, protect_content, pcd = await fileSettings(db.get_protect_content, db.set_protect_content)
                hide_caption, hcd = await fileSettings(db.get_hide_caption)   
                channel_button, cbd = await fileSettings(db.get_channel_button) 
                name, link = await db.get_channel_button_link()

                await query.edit_message_media(
                    InputMediaPhoto(pic,
                                    FILES_CMD_TXT.format(
                                        protect_content = protect_content,
                                        hide_caption = hide_caption,
                                        channel_button = channel_button,
                                        name = name,
                                        link = link
                                    )
                    ),
                    reply_markup = InlineKeyboardMarkup(buttonStatus(pcd, hcd, cbd))
                )                   
            except Exception as e:
                print(f"! Error Occured on callback data = 'pc' : {e}")

    elif data == "hc":
        if await authoUser(query, query.from_user.id) :
            await query.answer("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b>") 

            try:
                protect_content, pcd = await fileSettings(db.get_protect_content)
                pic, hide_caption, hcd = await fileSettings(db.get_hide_caption, db.set_hide_caption)   
                channel_button, cbd = await fileSettings(db.get_channel_button) 
                name, link = await db.get_channel_button_link()

                await query.edit_message_media(
                    InputMediaPhoto(pic,
                                    FILES_CMD_TXT.format(
                                        protect_content = protect_content,
                                        hide_caption = hide_caption,
                                        channel_button = channel_button,
                                        name = name,
                                        link = link
                                    )
                    ),
                    reply_markup = InlineKeyboardMarkup(buttonStatus(pcd, hcd, cbd))
                )                   
            except Exception as e:
                print(f"! Error Occured on callback data = 'hc' : {e}")

    elif data == "cb":
        if await authoUser(query, query.from_user.id) :
            await query.answer("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b>") 

            try:
                protect_content, pcd = await fileSettings(db.get_protect_content)
                hide_caption, hcd = await fileSettings(db.get_hide_caption)   
                pic, channel_button, cbd = await fileSettings(db.get_channel_button, db.set_channel_button) 
                name, link = await db.get_channel_button_link()

                await query.edit_message_media(
                    InputMediaPhoto(pic,
                                    FILES_CMD_TXT.format(
                                        protect_content = protect_content,
                                        hide_caption = hide_caption,
                                        channel_button = channel_button,
                                        name = name,
                                        link = link
                                    )
                    ),
                    reply_markup = InlineKeyboardMarkup(buttonStatus(pcd, hcd, cbd))
                )                   
            except Exception as e:
                print(f"! Error Occured on callback data = 'cb' : {e}")

    elif data == "setcb":
        id = query.from_user.id
        if await authoUser(query, id) :
            await query.answer("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b>") 

            try:
                button_name, button_link = await db.get_channel_button_link()

                button_preview = [[InlineKeyboardButton(text=button_name, url=button_link)]]  
                set_msg = await bot.ask(chat_id = id, text=f'<b>Tᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴ, Pʟᴇᴀsᴇ sᴇɴᴅ ᴠᴀʟɪᴅ ᴀʀɢᴜᴍᴇɴᴛs ᴡɪᴛʜɪɴ 1 ᴍɪɴᴜᴛᴇ.\nFᴏʀ ᴇxᴀᴍᴘʟᴇ:\n<blockquote><code>Join Channel - https://t.me/nova_flix</code></blockquote>\n\n<i>Bᴇʟᴏᴡ ɪs ʙᴜᴛᴛᴏɴ Pʀᴇᴠɪᴇᴡ ⬇️</i></b>', timeout=60, reply_markup=InlineKeyboardMarkup(button_preview), disable_web_page_preview = True)
                button = set_msg.text.split(' - ')

                if len(button) != 2:
                    markup = [[InlineKeyboardButton(f'◈ Sᴇᴛ Cʜᴀɴɴᴇʟ Bᴜᴛᴛᴏɴ ➪', callback_data='setcb')]]
                    return await set_msg.reply("<b>Pʟᴇᴀsᴇ sᴇɴᴅ ᴠᴀʟɪᴅ ᴀʀɢᴜᴍᴇɴᴛs.\nFᴏʀ ᴇxᴀᴍᴘʟᴇ:\n<blockquote><code>Join Channel - https://t.me/nova_flix</code></blockquote>\n\n<i>Tʀʏ ᴀɢᴀɪɴ ʙʏ ᴄʟɪᴄᴋɪɴɢ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ..</i></b>", reply_markup=InlineKeyboardMarkup(markup), disable_web_page_preview = True)

                button_name = button[0].strip(); button_link = button[1].strip()
                button_preview = [[InlineKeyboardButton(text=button_name, url=button_link)]]

                await set_msg.reply("<b><i>Aᴅᴅᴇᴅ Sᴜᴄcᴇssғᴜʟʟʏ ✅</i>\n<blockquote>Sᴇᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ ᴀs Pʀᴇᴠɪᴇᴡ ⬇️</blockquote></b>", reply_markup=InlineKeyboardMarkup(button_preview))
                await db.set_channel_button_link(button_name, button_link)
                return

            except TimeoutError:
                await client.send_message(
                    id, 
                    text="<b>⚠️ Tɪᴍᴇ Oᴜᴛ!</b>\n<blockquote><i>You didn't respond within 60 seconds. "
                         "Please try again by clicking the button below.</i></blockquote>", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('◈ Rᴇᴛʀʏ ⏱', callback_data='setcb')]]),
                    disable_notification=True
                )
            except Exception as e:
                await client.send_message(id, text=f"<b>❌ Eʀʀᴏʀ:</b>\n<blockquote>{e}</blockquote>")
                print(f"! Error Occurred on callback data = 'set_timer': {e}")
  

    elif data == 'autodel_cmd':
        if await authoUser(query, query.from_user.id) :
            await query.answer("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</i></b>") 

            try:
                timer = convert_time(await db.get_del_timer())
                autodel_mode, mode = await fileSettings(db.get_auto_delete, delfunc=True)

                await query.edit_message_media(
                    InputMediaPhoto(autodel_cmd_pic,
                                    AUTODEL_CMD_TXT.format(
                                        autodel_mode = autodel_mode,
                                        timer = timer
                                    )
                    ),
                    reply_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton(mode, callback_data='chng_autodel'), InlineKeyboardButton('sᴇᴛ ᴛɪᴍᴇʀ •', callback_data='set_timer')],
                        [InlineKeyboardButton('• ʀᴇғʀᴇsʜ', callback_data='autodel_cmd'), InlineKeyboardButton('ᴄʟᴏsᴇ •', callback_data='close')]
                    ])
                )
            except Exception as e:
                print(f"! Error Occured on callback data = 'autodel_cmd' : {e}")

    elif data == 'chng_autodel':
        if await authoUser(query, query.from_user.id) :
            await query.answer("› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...")

            try:
                timer = convert_time(await db.get_del_timer())
                pic, autodel_mode, mode = await fileSettings(db.get_auto_delete, db.set_auto_delete, delfunc=True)

                await query.edit_message_media(
                    InputMediaPhoto(pic,
                                    AUTODEL_CMD_TXT.format(
                                        autodel_mode = autodel_mode,
                                        timer = timer
                                    )
                    ),
                    reply_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton(mode, callback_data='chng_autodel'), InlineKeyboardButton('sᴇᴛ ᴛɪᴍᴇʀ •', callback_data='set_timer')],
                        [InlineKeyboardButton('• ʀᴇғʀᴇsʜ', callback_data='autodel_cmd'), InlineKeyboardButton('ᴄʟᴏsᴇ •', callback_data='close')]
                    ])
                )
            except Exception as e:
                print(f"! Error Occured on callback data = 'chng_autodel' : {e}")

    
    elif data == 'set_timer':
        id = query.from_user.id
        if await authoUser(query, id, owner_only=True) :
            try:

                timer = convert_time(await db.get_del_timer())
                set_msg = await bot.ask(chat_id=id, text=f'<b><blockquote>⏱ Cᴜʀʀᴇɴᴛ Tɪᴍᴇʀ: {timer}</blockquote>\n\nTᴏ ᴄʜᴀɴɢᴇ ᴛɪᴍᴇʀ, Pʟᴇᴀsᴇ sᴇɴᴅ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ɪɴ sᴇᴄᴏɴᴅs ᴡɪᴛʜɪɴ 1 ᴍɪɴᴜᴛᴇ.\n<blockquote>Fᴏʀ ᴇxᴀᴍᴘʟᴇ: <code>300</code>, <code>600</code>, <code>900</code></b></blockquote>', timeout=60)
                del_timer = set_msg.text.split()

                if len(del_timer) == 1 and del_timer[0].isdigit():
                    DEL_TIMER = int(del_timer[0])
                    await db.set_del_timer(DEL_TIMER)
                    timer = convert_time(DEL_TIMER)
                    await set_msg.reply(f"<b><i>Aᴅᴅᴇᴅ Sᴜᴄcᴇssғᴜʟʟʏ ✅</i>\n<blockquote>⏱ Cᴜʀʀᴇɴᴛ Tɪᴍᴇʀ: {timer}</blockquote></b>")
                else:
                    markup = [[InlineKeyboardButton('◈ Sᴇᴛ Dᴇʟᴇᴛᴇ Tɪᴍᴇʀ ⏱', callback_data='set_timer')]]
                    return await set_msg.reply("<b>Pʟᴇᴀsᴇ sᴇɴᴅ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ɪɴ sᴇᴄᴏɴᴅs.\n<blockquote>Fᴏʀ ᴇxᴀᴍᴘʟᴇ: <code>300</code>, <code>600</code>, <code>900</code></blockquote>\n\n<i>Tʀʏ ᴀɢᴀɪɴ ʙʏ ᴄʟɪᴄᴋɪɴɢ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ..</i></b>", reply_markup=InlineKeyboardMarkup(markup))
            except TimeoutError:
                await client.send_message(
                    id, 
                    text="<b>⚠️ Tɪᴍᴇ Oᴜᴛ!</b>\n<blockquote><i>You didn't respond within 60 seconds. "
                         "Please try again by clicking the button below.</i></blockquote>", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('◈ Rᴇᴛʀʏ ⏱', callback_data='set_timer')]]),
                    disable_notification=True
                )
            except Exception as e:
                await client.send_message(id, text=f"<b>❌ Eʀʀᴏʀ:</b>\n<blockquote>{e}</blockquote>")
                print(f"! Error Occurred on callback data = 'set_timer': {e}")


    elif data == 'chng_req':
        if await authoUser(query, query.from_user.id) :
            await query.answer("› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...")

            try:
                on = off = ""
                if await db.get_request_forcesub():
                    await db.set_request_forcesub(False)
                    off = "🔴"
                    texting = off_txt
                else:
                    await db.set_request_forcesub(True)
                    on = "🟢"
                    texting = on_txt

                button = [
                    [InlineKeyboardButton(f"{on} ON", "chng_req"), InlineKeyboardButton(f"{off} OFF", "chng_req")],
                    [InlineKeyboardButton("⚙️ Mᴏʀᴇ Sᴇᴛᴛɪɴɢs ⚙️", "more_settings")]
                ]
                await query.message.edit_text(text=RFSUB_CMD_TXT.format(req_mode=texting), reply_markup=InlineKeyboardMarkup(button)) #🎉)

            except Exception as e:
                print(f"! Error Occured on callback data = 'chng_req' : {e}")


    elif data == 'more_settings':
        #if await authoUser(query, query.from_user.id) :
            #await query.answer("› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ..."")
            try:
                await query.message.edit_text("<b>› › ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ...</b>")
                LISTS = "Eᴍᴘᴛʏ Rᴇǫᴜᴇsᴛ FᴏʀᴄᴇSᴜʙ Cʜᴀɴɴᴇʟ Lɪsᴛ !?"

                REQFSUB_CHNLS = await db.get_reqChannel()
                if REQFSUB_CHNLS:
                    LISTS = ""
                    channel_name = "<i>Uɴᴀʙʟᴇ Lᴏᴀᴅ Nᴀᴍᴇ..</i>"
                    for CHNL in REQFSUB_CHNLS:
                        await query.message.reply_chat_action(ChatAction.TYPING)
                        try:
                            name = (await client.get_chat(CHNL)).title
                        except:
                            name = None
                        channel_name = name if name else channel_name

                        user = await db.get_reqSent_user(CHNL)
                        channel_users = len(user) if user else 0

                        link = await db.get_stored_reqLink(CHNL)
                        if link:
                            channel_name = f"<a href={link}>{channel_name}</a>"
    
                        LISTS += f"NAME: {channel_name}\n(ID: <code>{CHNL}</code>)\nUSERS: {channel_users}\n\n"
                        
                buttons = [
                    [InlineKeyboardButton("ᴄʟᴇᴀʀ ᴜsᴇʀs", "clear_users"), InlineKeyboardButton("cʟᴇᴀʀ cʜᴀɴɴᴇʟs", "clear_chnls")],
                    [InlineKeyboardButton("♻️  Rᴇғʀᴇsʜ Sᴛᴀᴛᴜs  ♻️", "more_settings")],
                    [InlineKeyboardButton("⬅️ Bᴀᴄᴋ", "req_fsub"), InlineKeyboardButton("Cʟᴏsᴇ ✖️", "close")]
                ]
                await query.message.reply_chat_action(ChatAction.CANCEL)
                await query.message.edit_text(text=RFSUB_MS_TXT.format(reqfsub_list=LISTS.strip()), reply_markup=InlineKeyboardMarkup(buttons))
                        
            except Exception as e:
                print(f"! Error Occured on callback data = 'more_settings' : {e}")


    elif data == 'clear_users':
        #if await authoUser(query, query.from_user.id) :
        #await query.answer("♻️ Qᴜᴇʀʏ Pʀᴏᴄᴇssɪɴɢ....")    
        try:
            REQFSUB_CHNLS = await db.get_reqChannel()
            if not REQFSUB_CHNLS:
                return await query.answer("Eᴍᴘᴛʏ Rᴇǫᴜᴇsᴛ FᴏʀᴄᴇSᴜʙ Cʜᴀɴɴᴇʟ !?", show_alert=True)

            await query.answer("♻️ Qᴜᴇʀʏ Pʀᴏᴄᴇssɪɴɢ....")
                
            REQFSUB_CHNLS = list(map(str, REQFSUB_CHNLS))    
            buttons = [REQFSUB_CHNLS[i:i+2] for i in range(0, len(REQFSUB_CHNLS), 2)]
            buttons.insert(0, ['CANCEL'])
            buttons.append(['DELETE ALL CHANNELS USER'])

            user_reply = await client.ask(query.from_user.id, text=CLEAR_USERS_TXT, reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
            
            if user_reply.text == 'CANCEL':
                return await user_reply.reply("<b><i>🆑 Cᴀɴᴄᴇʟʟᴇᴅ...</i></b>", reply_markup=ReplyKeyboardRemove())
                
            elif user_reply.text in REQFSUB_CHNLS:
                try:
                    await db.clear_reqSent_user(int(user_reply.text))
                    return await user_reply.reply(f"<b><blockquote>✅ Usᴇʀ Dᴀᴛᴀ Sᴜᴄᴄᴇssғᴜʟʟʏ Cʟᴇᴀʀᴇᴅ ғʀᴏᴍ Cʜᴀɴɴᴇʟ ɪᴅ: <code>{user_reply.text}</code></blockquote></b>", reply_markup=ReplyKeyboardRemove())
                except Exception as e:
                    return await user_reply.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ...\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote>", reply_markup=ReplyKeyboardRemove())
                    
            elif user_reply.text == 'DELETE ALL CHANNELS USER':
                try:
                    for CHNL in REQFSUB_CHNLS:
                        await db.clear_reqSent_user(int(CHNL))
                    return await user_reply.reply(f"<b><blockquote>✅ Usᴇʀ Dᴀᴛᴀ Sᴜᴄᴄᴇssғᴜʟʟʏ Cʟᴇᴀʀᴇᴅ ғʀᴏᴍ Aʟʟ Cʜᴀɴɴᴇʟ ɪᴅs</blockquote></b>", reply_markup=ReplyKeyboardRemove())
                except Exception as e:
                    return await user_reply.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ...\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote>", reply_markup=ReplyKeyboardRemove())
                    
            else:
                return await user_reply.reply(f"<b><blockquote>INVALID SELECTIONS</blockquote></b>", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            print(f"! Error Occured on callback data = 'clear_users' : {e}")


    elif data == 'clear_chnls':
        #if await authoUser(query, query.from_user.id, owner_only=True) 
            
        try:
            REQFSUB_CHNLS = await db.get_reqChannel()
            if not REQFSUB_CHNLS:
                return await query.answer("Eᴍᴘᴛʏ Rᴇǫᴜᴇsᴛ FᴏʀᴄᴇSᴜʙ Cʜᴀɴɴᴇʟ !?", show_alert=True)
            
            await query.answer("♻️ Qᴜᴇʀʏ Pʀᴏᴄᴇssɪɴɢ....")
                
            REQFSUB_CHNLS = list(map(str, REQFSUB_CHNLS))    
            buttons = [REQFSUB_CHNLS[i:i+2] for i in range(0, len(REQFSUB_CHNLS), 2)]
            buttons.insert(0, ['CANCEL'])
            buttons.append(['DELETE ALL CHANNEL IDS'])

            user_reply = await client.ask(query.from_user.id, text=CLEAR_CHNLS_TXT, reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
            
            if user_reply.text == 'CANCEL':
                return await user_reply.reply("<b><i>🆑 Cᴀɴᴄᴇʟʟᴇᴅ...</i></b>", reply_markup=ReplyKeyboardRemove())
                
            elif user_reply.text in REQFSUB_CHNLS:
                try:
                    chnl_id = int(user_reply.text)

                    await db.del_reqChannel(chnl_id)

                    try: await client.revoke_chat_invite_link(chnl_id, await db.get_stored_reqLink(chnl_id))
                    except: pass

                    await db.del_stored_reqLink(chnl_id)

                    return await user_reply.reply(f"<b><blockquote><code>{user_reply.text}</code> Cʜᴀɴɴᴇʟ ɪᴅ ᴀʟᴏɴɢ ᴡɪᴛʜ ɪᴛs ᴅᴀᴛᴀ sᴜᴄᴄᴇssғᴜʟʟʏ Dᴇʟᴇᴛᴇᴅ ✅</blockquote></b>", reply_markup=ReplyKeyboardRemove())
                except Exception as e:
                    return await user_reply.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ...\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote>", reply_markup=ReplyKeyboardRemove())
                    
            elif user_reply.text == 'DELETE ALL CHANNEL IDS':
                try:
                    for CHNL in REQFSUB_CHNLS:
                        chnl = int(CHNL)

                        await db.del_reqChannel(chnl)

                        try: await client.revoke_chat_invite_link(chnl, await db.get_stored_reqLink(chnl))
                        except: pass

                        await db.del_stored_reqLink(chnl)

                    return await user_reply.reply(f"<b><blockquote>Aʟʟ Cʜᴀɴɴᴇʟ ɪᴅs ᴀʟᴏɴɢ ᴡɪᴛʜ ɪᴛs ᴅᴀᴛᴀ sᴜᴄᴄᴇssғᴜʟʟʏ Dᴇʟᴇᴛᴇᴅ ✅</blockquote></b>", reply_markup=ReplyKeyboardRemove())
                
                except Exception as e:
                    return await user_reply.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ...\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote>", reply_markup=ReplyKeyboardRemove())
                    
            else:
                return await user_reply.reply(f"<b><blockquote>INVALID SELECTIONS</blockquote></b>", reply_markup=ReplyKeyboardRemove())
        
        except Exception as e:
            print(f"! Error Occured on callback data = 'more_settings' : {e}")


    elif data == 'clear_links':
        #if await authoUser(query, query.from_user.id) :
        #await query.answer("♻️ Qᴜᴇʀʏ Pʀᴏᴄᴇssɪɴɢ....")
            
        try:
            REQFSUB_CHNLS = await db.get_reqLink_channels()
            if not REQFSUB_CHNLS:
                return await query.answer("Nᴏ Sᴛᴏʀᴇᴅ Rᴇǫᴜᴇsᴛ Lɪɴᴋ Aᴠᴀɪʟᴀʙʟᴇ !?", show_alert=True)

            await query.answer("♻️ Qᴜᴇʀʏ Pʀᴏᴄᴇssɪɴɢ....")
                
            REQFSUB_CHNLS = list(map(str, REQFSUB_CHNLS))    
            buttons = [REQFSUB_CHNLS[i:i+2] for i in range(0, len(REQFSUB_CHNLS), 2)]
            buttons.insert(0, ['CANCEL'])
            buttons.append(['DELETE ALL REQUEST LINKS'])

            user_reply = await client.ask(query.from_user.id, text=CLEAR_LINKS_TXT, reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
            
            if user_reply.text == 'CANCEL':
                return await user_reply.reply("<b><i>🆑 Cᴀɴᴄᴇʟʟᴇᴅ...</i></b>", reply_markup=ReplyKeyboardRemove())
                
            elif user_reply.text in REQFSUB_CHNLS:
                channel_id = int(user_reply.text)
                try:
                    try:
                        await client.revoke_chat_invite_link(channel_id, await db.get_stored_reqLink(channel_id))
                    except:
                        text = """<b>❌ Uɴᴀʙʟᴇ ᴛᴏ Rᴇᴠᴏᴋᴇ ʟɪɴᴋ !
<blockquote expandable>ɪᴅ: <code>{}</code></b>
<i>Eɪᴛʜᴇʀ ᴛʜᴇ ʙᴏᴛ ɪs ɴᴏᴛ ɪɴ ᴀʙᴏᴠᴇ ᴄʜᴀɴɴᴇʟ Oʀ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘʀᴏᴘᴇʀ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs</i></blockquote>"""
                        return await user_reply.reply(text=text.format(channel_id), reply_markup=ReplyKeyboardRemove())
                        
                    await db.del_stored_reqLink(channel_id)
                    return await user_reply.reply(f"<b><blockquote><code>{channel_id}</code> Cʜᴀɴɴᴇʟs Lɪɴᴋ Sᴜᴄᴄᴇssғᴜʟʟʏ Dᴇʟᴇᴛᴇᴅ ✅</blockquote></b>", reply_markup=ReplyKeyboardRemove())
                
                except Exception as e:
                    return await user_reply.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ...\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote>", reply_markup=ReplyKeyboardRemove())
                    
            elif user_reply.text == 'DELETE ALL REQUEST LINKS':
                try:
                    result = ""
                    for CHNL in REQFSUB_CHNLS:
                        channel_id = int(CHNL)
                        try:
                            await client.revoke_chat_invite_link(channel_id, await db.get_stored_reqLink(channel_id))
                        except:
                            result += f"<blockquote expandable><b><code>{channel_id}</code> Uɴᴀʙʟᴇ ᴛᴏ Rᴇᴠᴏᴋᴇ ❌</b>\n<i>Eɪᴛʜᴇʀ ᴛʜᴇ ʙᴏᴛ ɪs ɴᴏᴛ ɪɴ ᴀʙᴏᴠᴇ ᴄʜᴀɴɴᴇʟ Oʀ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘʀᴏᴘᴇʀ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.</i></blockquote>\n"
                            continue
                        await db.del_stored_reqLink(channel_id)
                        result += f"<blockquote><b><code>{channel_id}</code> IDs Lɪɴᴋ Dᴇʟᴇᴛᴇᴅ ✅</b></blockquote>\n"
                        
                    return await user_reply.reply(f"<b>⁉️ Oᴘᴇʀᴀᴛɪᴏɴ Rᴇsᴜʟᴛ:</b>\n{result.strip()}", reply_markup=ReplyKeyboardRemove())
 
                except Exception as e:
                    return await user_reply.reply(f"<b>! Eʀʀᴏʀ Oᴄᴄᴜʀᴇᴅ...\n<blockquote>Rᴇᴀsᴏɴ:</b> {e}</blockquote>", reply_markup=ReplyKeyboardRemove())
                    
            else:
                return await user_reply.reply(f"<b><blockquote>INVALID SELECTIONS</blockquote></b>", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            print(f"! Error Occured on callback data = 'more_settings' : {e}")
            

    elif data == 'req_fsub':
        #if await authoUser(query, query.from_user.id) :
        #await query.answer("♻️ Qᴜᴇʀʏ Pʀᴏᴄᴇssɪɴɢ....")
    
        try:
            on = off = ""
            if await db.get_request_forcesub():
                on = "🟢"
                texting = on_txt
            else:
                off = "🔴"
                texting = off_txt
    
            button = [
                [InlineKeyboardButton(f"{on} ON", "chng_req"), InlineKeyboardButton(f"{off} OFF", "chng_req")],
                [InlineKeyboardButton("⚙️ Mᴏʀᴇ Sᴇᴛᴛɪɴɢs ⚙️", "more_settings")]
            ]
            await query.message.edit_text(text=RFSUB_CMD_TXT.format(req_mode=texting), reply_markup=InlineKeyboardMarkup(button)) #🎉)
    
        except Exception as e:
            print(f"! Error Occured on callback data = 'chng_req' : {e}")

    
    elif data == 'chng_watermark':
        if await authoUser(query, query.from_user.id):
            await query.answer("♻️ Processing...")

            try:
            # Toggle watermark state
                current_watermark = await db.get_watermark()
                new_state = not current_watermark  # Toggle between True/False
                await db.set_watermark(new_state)

                status_text = "🟢 Watermark is enabled."     if new_state else "🔴 Watermark is disabled."

            # Buttons
                button = [
                    [InlineKeyboardButton("🟢 ON" if new_state else "OFF 🔴", callback_data="chng_watermark")],
                    [InlineKeyboardButton("⚙️ Set Watermark", callback_data="set_watermark")],
                    [InlineKeyboardButton("✖ Close", callback_data="close")]
                ]

                await query.message.edit_text(
                    text=f"<b>Watermark Settings</b>\n\n{status_text}",
                    reply_markup=InlineKeyboardMarkup(button)
            )

            except Exception as e:
                print(f"! Error in 'chng_watermark': {e}")



    elif data == 'set_watermark':
        id = query.from_user.id
        if await authoUser(query, id):
            try:
                set_msg = await bot.ask(
                    chat_id=id, 
                    text=(
                        "📌 Please send the new watermark (URL).\n\n"
                        "To remove the watermark, send <code>remove</code>.\n\n"
                        "⚠️ You have 30 seconds to send the watermark."
                    ),
                    timeout=30
                )

            # Handle user response
                if set_msg.photo:
                    file_id = set_msg.photo[-1].file_id
                    file_path = await bot.get_file(file_id)
                    new_watermark = file_path.file_path  # Local path
                elif set_msg.text:
                    if set_msg.text.lower() == "remove":
                        new_watermark = False  # Disable watermark
                    elif set_msg.text.startswith(("http://", "https://")):
                        new_watermark = set_msg.text  # URL
                    else:
                        return await set_msg.reply(
                            "❌ Invalid input! Please send a valid URL.\n"
                            "Try again by clicking below.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔄 Retry", callback_data="set_watermark")],
                                [InlineKeyboardButton("✖ Close", callback_data="close")]
                            ])
                        )
                else:
                    return await set_msg.reply(
                        "❌ Invalid input! Please send a valid URL.\n"
                        "Try again by clicking below.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Retry", callback_data="set_watermark")],
                            [InlineKeyboardButton("✖ Close", callback_data="close")]
                        ])
                    )

            # Update watermark in the database
                await db.set_watermark(new_watermark)

            # Confirmation message
                status_text = "✅ Watermark has been updated successfully!" if new_watermark else "❌ Watermark has been removed."
                await set_msg.reply(status_text)

            except TimeoutError:
                await bot.send_message(
                    id, 
                    text=(
                        "<b>⚠️ Timeout!</b>\n"
                        "<blockquote>You didn’t send a watermark in 30 seconds.</blockquote>\n"
                        "<i>Try again by clicking the button below.</i>"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Retry", callback_data="set_watermark")],
                        [InlineKeyboardButton("✖ Close", callback_data="close")]
                    ])
                )
            except Exception as e:
                print(f"! Error in 'set_watermark': {e}")
                await bot.send_message(id, f"<b>❌ Error:</b>\n<blockquote>{e}</blockquote>")

# Handle changing thumbnail
    
    elif data == 'chng_thumbnail':
        if await authoUser(query, query.from_user.id):
            await query.answer("♻️ Processing...")

            try:
            # Toggle watermark state
                current_thumbnail = await db.get_thumbnail()
                new_state = not current_thumbnail  # Toggle between True/False
                await db.set_thumbnail(new_state)

                status_text = "🟢 Thumbnail is enabled."     if new_state else "🔴 Thumbnail is disabled."

            # Buttons
                button = [
                    [InlineKeyboardButton("🟢 ON" if new_state else "OFF 🔴", callback_data="chng_thumbnail")],
                    [InlineKeyboardButton("⚙️ Set Watermark", callback_data="set_thumbnail")],
                    [InlineKeyboardButton("✖ Close", callback_data="close")]
                ]

                await query.message.edit_text(
                    text=f"<b>Thumbnail Settings</b>\n\n{status_text}",
                    reply_markup=InlineKeyboardMarkup(button)
            )

            except Exception as e:
                print(f"! Error in 'chng_thumbnail': {e}")



    elif data == 'set_thumbnail':
        id = query.from_user.id
        if await authoUser(query, id):
            try:
                set_msg = await bot.ask(
                    chat_id=id, 
                    text=(
                        "📌 Please send the new thumbnail (URL).\n\n"
                        "To remove the thumbnail, send <code>remove</code>.\n\n"
                        "⚠️ You have 30 seconds to send the thumbnail."
                    ),
                    timeout=30
                )

            # Handle user response
                if set_msg.photo:
                    file_id = set_msg.photo[-1].file_id
                    file_path = await bot.get_file(file_id)
                    new_thumbnail = file_path.file_path  # Local path
                elif set_msg.text:
                    if set_msg.text.lower() == "remove":
                        new_thumbnail = False  # Disable watermark
                    elif set_msg.text.startswith(("http://", "https://")):
                        new_thumbnail = set_msg.text  # URL
                    else:
                        return await set_msg.reply(
                            "❌ Invalid input! Please send a valid  URL.\n"
                            "Try again by clicking below.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔄 Retry", callback_data="set_thumbnail")],
                                [InlineKeyboardButton("✖ Close", callback_data="close")]
                            ])
                        )
                else:
                    return await set_msg.reply(
                        "❌ Invalid input! Please send a valid URL.\n"
                        "Try again by clicking below.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Retry", callback_data="set_thumbnail")],
                            [InlineKeyboardButton("✖ Close", callback_data="close")]
                        ])
                    )

            # Update watermark in the database
                await db.set_thumbnail(new_thumbnail)

            # Confirmation message
                status_text = "✅ Thumbnail has been updated successfully!" if new_thumbnail else "❌ Watermark has been removed."
                await set_msg.reply(status_text)

            except TimeoutError:
                await bot.send_message(
                    id, 
                    text=(
                        "<b>⚠️ Timeout!</b>\n"
                        "<blockquote>You didn’t send a Thumbnail in 30 seconds.</blockquote>\n"
                        "<i>Try again by clicking the button below.</i>"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Retry", callback_data="set_thumbnail")],
                        [InlineKeyboardButton("✖ Close", callback_data="close")]
                    ])
                )
            except Exception as e:
                print(f"! Error in 'set_thumbnail': {e}")
                await bot.send_message(id, f"<b>❌ Error:</b>\n<blockquote>{e}</blockquote>")



    elif data == 'chng_banner':
        if await authoUser(query, query.from_user.id):
            await query.answer("♻️ Processing...")

            try:
            # Toggle banner state
                current_banner = await db.get_banner()
                new_state = not current_banner  # Toggle between True/False
                await db.set_banner(new_state)

                status_text = "🟢 Banner is enabled."     if new_state else "🔴 Banner is disabled."

            # Buttons
                button = [
                    [InlineKeyboardButton("🟢 ON" if new_state else "OFF 🔴", callback_data="chng_banner")],
                    [InlineKeyboardButton("⚙️ Set Banner", callback_data="set_banner")],
                    [InlineKeyboardButton("✖ Close", callback_data="close")]
                ]

                await query.message.edit_text(
                    text=f"<b>Banner Settings</b>\n\n{status_text}",
                    reply_markup=InlineKeyboardMarkup(button)
            )

            except Exception as e:
                print(f"! Error in 'chng_banner': {e}")



    elif data == 'set_banner':
        id = query.from_user.id
        if await authoUser(query, id):
            try:
                set_msg = await bot.ask(
                    chat_id=id, 
                    text=(
                        "📌 Please send the new banner (URL).\n\n"
                        "To remove the banner, send <code>remove</code>.\n\n"
                        "⚠️ You have 30 seconds to send the banner."
                    ),
                    timeout=30
                )

            # Handle user response
                if set_msg.photo:
                    file_id = set_msg.photo[-1].file_id
                    file_path = await bot.get_file(file_id)
                    new_banner = file_path.file_path  # Local path
                elif set_msg.text:
                    if set_msg.text.lower() == "remove":
                        new_banner = False  # Disable watermark
                    elif set_msg.text.startswith(("http://", "https://")):
                        new_banner = set_msg.text  # URL
                    else:
                        return await set_msg.reply(
                            "❌ Invalid input! Please send a valid  URL.\n"
                            "Try again by clicking below.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔄 Retry", callback_data="set_banner")],
                                [InlineKeyboardButton("✖ Close", callback_data="close")]
                            ])
                        )
                else:
                    return await set_msg.reply(
                        "❌ Invalid input! Please send a valid URL.\n"
                        "Try again by clicking below.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Retry", callback_data="set_banner")],
                            [InlineKeyboardButton("✖ Close", callback_data="close")]
                        ])
                    )

            # Update watermark in the database
                await db.set_banner(new_banner)

            # Confirmation message
                status_text = "✅ Banner has been updated successfully!" if new_banner else "❌ Banner has been removed."
                await set_msg.reply(status_text)

            except TimeoutError:
                await bot.send_message(
                    id, 
                    text=(
                        "<b>⚠️ Timeout!</b>\n"
                        "<blockquote>You didn’t send a Banner in 30 seconds.</blockquote>\n"
                        "<i>Try again by clicking the button below.</i>"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Retry", callback_data="set_banner")],
                        [InlineKeyboardButton("✖ Close", callback_data="close")]
                    ])
                )
            except Exception as e:
                print(f"! Error in 'set_banner': {e}")
                await bot.send_message(id, f"<b>❌ Error:</b>\n<blockquote>{e}</blockquote>")


    elif data.startswith("anime_"):
        session_id = data.split("anime_")[1]

    # Retrieve the query stored earlier
        query_text = user_queries.get(query.message.chat.id, "")
        search_url = f"https://animepahe.ru/api?m=search&q={query_text.replace(' ', '+')}"

    # Use the session with headers
        response = session.get(search_url)

        if response.status_code != 200:
            await query.message.reply_text(f"API request failed. Status: {response.status_code}")
            return

        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError:
            await query.message.reply_text("Invalid response from API. Please try again later.")
            return

        anime = next((anime for anime in response_data['data'] if anime['session'] == session_id), None)

        if not anime:
            await query.message.reply_text("Anime not found.")
            return

        title = anime['title']
        anime_type = anime['type']
        episodes = anime['episodes']
        status = anime['status']
        season = anime['season']
        year = anime['year']
        score = anime['score']
        poster_url = anime['poster']
        anime_link = f"https://animepahe.ru/anime/{session_id}"

        message_text = (
            f"Title: {title}\n"
            f"Type: {anime_type}\n"
            f"Episodes: {episodes}\n"
            f"Status: {status}\n"
            f"Season: {season}\n"
            f"Year: {year}\n"
            f"Score: {score}\n"
            f"[Anime Link]({anime_link})"
        )

    # Store session ID for episodes
        episode_data[query.message.chat.id] = {
            "session_id": session_id,
            "poster": poster_url,
            "title": title
        }

        episode_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("Episodes", callback_data="episodes")]
        ])

        await client.send_photo(
            chat_id=query.message.chat.id,
            photo=poster_url,
            caption=message_text,
            reply_markup=episode_button
        )

    elif data == "episodes":
        session_data = episode_data.get(query.message.chat.id)

        if not session_data:
            await query.message.reply_text("Session ID not found.")
            return

        session_id = session_data['session_id']
        episodes_url = f"https://animepahe.ru/api?m=release&id={session_id}&sort=episode_asc&page=1"

        response = session.get(episodes_url)

        if response.status_code != 200:
            await query.message.reply_text(f"API request failed. Status: {response.status_code}")
            return

        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError:
            await query.message.reply_text("Invalid response from API. Please try again later.")
            return

        last_page = int(response_data["last_page"])
        episodes = response_data['data']

        episode_data[query.message.chat.id]['current_page'] = 1
        episode_data[query.message.chat.id]['last_page'] = last_page
        episode_data[query.message.chat.id]['episodes'] = {ep['episode']: ep['session'] for ep in episodes}

        episode_buttons = [
            [InlineKeyboardButton(f"Episode {ep['episode']}", callback_data=f"ep_{ep['episode']}")]
            for ep in episodes
        ]

        nav_buttons = []
        if last_page > 1:
            nav_buttons.append(InlineKeyboardButton(">", callback_data="page_2"))

        if nav_buttons:
            episode_buttons.append(nav_buttons)

        reply_markup = InlineKeyboardMarkup(episode_buttons)

        await query.message.reply_text("Select an episode:", reply_markup=reply_markup)


    elif data.startswith("page_"):
        new_page = int(data.split("_")[1])
        session_data = episode_data.get(query.message.chat.id)

        if not session_data:
            await query.message.reply_text("Session ID not found.")
            return

        current_page = session_data.get('current_page', 1)
        last_page = session_data.get('last_page', 1)

        if new_page < 1:
            await query.answer("You're already on the first page.", show_alert=True)
        elif new_page > last_page:
            await query.answer("You're already on the last page.", show_alert=True)
        else:
            session_id = session_data['session_id']
            episodes_url = f"https://animepahe.ru/api?m=release&id={session_id}&sort=episode_asc&page={new_page}"
            response = session.get(episodes_url).json()

            episodes = response['data']
            episode_data[query.message.chat.id]['current_page'] = new_page
            episode_data[query.message.chat.id]['episodes'] = {ep['episode']: ep['session'] for ep in episodes}

            episode_buttons = [
                [InlineKeyboardButton(f"Episode {ep['episode']}", callback_data=f"ep_{ep['episode']}")]
                for ep in episodes
            ]

            nav_buttons = []
            if new_page > 1:
                nav_buttons.append(InlineKeyboardButton("<", callback_data=f"page_{new_page - 1}"))
            if new_page < last_page:
                nav_buttons.append(InlineKeyboardButton(">", callback_data=f"page_{new_page + 1}"))

            if nav_buttons:
                episode_buttons.append(nav_buttons)

            reply_markup = InlineKeyboardMarkup(episode_buttons)

            await query.message.edit_reply_markup(reply_markup)

    elif data.startswith("ep_"):
        episode_number = int(data.split("_")[1])
        user_id = query.message.chat.id

        session_data = episode_data.get(user_id)

        if not session_data or 'episodes' not in session_data:
            await query.message.reply_text("Episode not found.")
            return

        session_id = session_data['session_id']
        episodes = session_data['episodes']

        if episode_number not in episodes:
            await query.message.reply_text("Episode not found.")
            return

        episode_data[user_id]['current_episode'] = episode_number
        episode_session = episodes[episode_number]
        episode_url = f"https://animepahe.ru/play/{session_id}/{episode_session}"

        response = session.get(episode_url)
        soup = BeautifulSoup(response.content, "html.parser")
        download_links = soup.select("#pickDownload a.dropdown-item")

        if not download_links:
            await query.message.reply_text("No download links found.")
            return

        download_buttons = [
            [InlineKeyboardButton(link.get_text(strip=True), callback_data=f"dl_{link['href']}")]
            for link in download_links
        ]
        reply_markup = InlineKeyboardMarkup(download_buttons)

        await query.message.reply_text("Select a download link:", reply_markup=reply_markup)


    elif data.startswith("set_method_"):
        user_id = query.from_user.id
        upload_method = data.split("_")[2]  # 'document' or 'video'

    # Update the selected method in the database
        save_upload_method(user_id, upload_method)

    # Acknowledge the change
        await query.answer(f"Upload method set to {upload_method.capitalize()}")

    # Update buttons
        document_status = "✅" if upload_method == "document" else "❌"
        video_status = "✅" if upload_method == "video" else "❌"

        buttons = [
            [
                InlineKeyboardButton(f"Document ({document_status})", callback_data="set_method_document"),
                InlineKeyboardButton(f"Video ({video_status})", callback_data="set_method_video")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_reply_markup(reply_markup)


    elif data.startswith("dl_"):
        user_id = query.from_user.id
        download_url = data.split("dl_")[1]
        kwik_link = extract_kwik_link(download_url)

        try:
            direct_link = get_dl_link(kwik_link)
        except Exception as e:
            await query.message.reply_text(f"Error generating download link: {str(e)}")
            return

        username = query.from_user.username or "Unknown User"
        add_to_queue(user_id, username, direct_link)

        session_data = episode_data.get(user_id, {})
        episode_number = session_data.get("current_episode", "Unknown")
        title = session_data.get("title", "Unknown Title")

        download_button_title = next(
            (button.text for row in query.message.reply_markup.inline_keyboard
             for button in row if button.callback_data == f"dl_{download_url}"),
            "Unknown Source"
        )

        resolution = re.search(r"\b\d{3,4}p\b", download_button_title)
        resolution = resolution.group() if resolution else download_button_title
        file_type = "Dub" if 'eng' in download_button_title else "Sub"

        short_name = create_short_name(title)
        file_name = sanitize_filename(f"[{file_type}] [{short_name}] [EP {episode_number}] [{resolution}].mp4")

        random_str = random_string(5)
        user_download_dir = os.path.join(DOWNLOAD_DIR, str(user_id), random_str)
        os.makedirs(user_download_dir, exist_ok=True)
        download_path = os.path.join(user_download_dir, file_name)

        dl_msg = await query.message.reply_text(f"<b>Added to queue:</b>\n <pre>{file_name}</pre>\n<b>Downloading now...</b>")

        try:
            # Download file
            download_file(direct_link, download_path)
            await dl_msg.edit("<b>Download complete. Uploading...</b>")

            # Upload
            caption = f"{title} - EP {episode_number} - {resolution}"
            msg = await TgUploaders(dl_msg).upload(download_path, caption)
            msg_id = msg.id
            link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(msg_id * abs(Var.FILE_STORE)))}"
            btns = [[InlineKeyboardButton(f"{resolution} - {convertBytes(msg.document.file_size)}", url=link)]]

            # Update inline buttons
            if query.message.reply_markup:
                post_msg = query.message
                await post_msg.edit_reply_markup(reply_markup=InlineKeyboardMarkup(btns))

            # Backup
            if Var.BACKUP_CHANNEL:
                for chat_id in Var.BACKUP_CHANNEL.split():
                    await msg.copy(int(chat_id))

            await dl_msg.edit("<b>Successfully Uploaded 🎉</b>")

            # Cleanup
            remove_from_queue(user_id, direct_link)
            if os.path.exists(user_download_dir):
                shutil.rmtree(user_download_dir)

        except Exception as e:
            await query.message.reply_text(f"Error: {str(e)}")



