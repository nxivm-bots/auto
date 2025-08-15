from re import findall
from math import floor
from time import time
from os import path as ospath, makedirs
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, rename as aiorename
from asyncio import sleep as asleep, gather, create_subprocess_shell, create_task
from asyncio.subprocess import PIPE
from urllib.parse import urlparse, unquote
import aiohttp
import pathlib
import json
import subprocess

from bot import Var, ffpids_cache, LOGS
from bot.core.database import db
from .func_utils import mediainfo, convertBytes, convertTime, editMessage
from .reporter import rep

# Encoding args
ffargs = {
    '1080': (
        "-c:v libx264 -preset veryfast -crf 27 -tune animation "
        "-threads 0 -pix_fmt yuv420p -movflags +faststart "
        "-c:a libopus -b:a 70k -c:s copy"
    ),
    '720': (
        "-c:v libx264 -preset veryfast -crf 29 -tune animation "
        "-threads 0 -pix_fmt yuv420p -movflags +faststart "
        "-c:a libopus -b:a 55k -c:s copy"
    ),
    '480': (
        "-c:v libx264 -preset veryfast -crf 30 -tune animation "
        "-threads 0 -pix_fmt yuv420p -movflags +faststart "
        "-c:a libopus -b:a 40k -c:s copy"
    ),
    'HDRi': "-c copy"  # For HDRi/HDRip copy mode
}

# Scaling values
scale_values = {
    '1080': "scale=1920:1080",
    '720': "scale=1280:720",
    '480': "scale=854:480",
    'HDRi': None  # No scaling for HDRi/HDRip
}

if not ospath.exists("encode"):
    makedirs("encode", exist_ok=True)


class FFEncoder:
    def __init__(self, message, path, name, qual):
        self.__proc = None
        self.is_cancelled = False
        self.message = message
        self.__name = name
        self.__qual = qual
        self.dl_path = path
        self.__total_time = None
        self.out_path = ospath.join("encode", name)
        self.__prog_file = 'prog.txt'
        self.__start_time = time()

    async def progress(self):
        self.__total_time = await mediainfo(self.dl_path, get_duration=True)
        if isinstance(self.__total_time, str):
            self.__total_time = 1.0

        while not (self.__proc is None or self.is_cancelled):
            async with aiopen(self.__prog_file, 'r+') as p:
                text = await p.read()

            if text:
                t = findall(r"out_time_ms=(\d+)", text)
                time_done = floor(int(t[-1]) / 1000000) if t else 1

                s = findall(r"total_size=(\d+)", text)
                ensize = int(s[-1]) if s else 0

                diff = time() - self.__start_time
                speed = ensize / max(diff, 0.01)
                percent = round((time_done / self.__total_time) * 100, 2)
                tsize = ensize / (max(percent, 0.01) / 100)
                eta = (tsize - ensize) / max(speed, 0.01)

                bar = floor(percent / 8) * "■" + (12 - floor(percent / 8)) * "□"

                progress_str = f"""<blockquote>‣ <b>Anime Name :</b> <b><i>{self.__name}</i></b></blockquote>
<blockquote>‣ <b>Status :</b> <i>Encoding</i>
    <code>[{bar}]</code> {percent}%</blockquote> 
<blockquote>   ‣ <b>Size :</b> {convertBytes(ensize)} out of ~ {convertBytes(tsize)}
    ‣ <b>Speed :</b> {convertBytes(speed)}/s
    ‣ <b>Time Took :</b> {convertTime(diff)}
    ‣ <b>Time Left :</b> {convertTime(eta)}</blockquote>
<blockquote>‣ <b>File(s) Encoded:</b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code></blockquote>"""

                await editMessage(self.message, progress_str)

                prog = findall(r"progress=(\w+)", text)
                if prog and prog[-1] == 'end':
                    break

            await asleep(8)

    async def download_watermark(self, url: str) -> str | None:
        try:
            if not url:
                return None

            parsed = urlparse(url)
            filename = unquote(pathlib.Path(parsed.path).name) or "watermark"
            filename = filename.replace("/", "_").replace("\\", "_")
            local_path = ospath.join("encode", filename)

            if ospath.exists(local_path):
                LOGS.info(f"Using cached watermark: {local_path}")
                return local_path

            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        LOGS.warning(f"Failed to download watermark {url} status {resp.status}")
                        return None
                    async with aiopen(local_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024 * 32):
                            if not chunk:
                                break
                            await f.write(chunk)
            LOGS.info(f"Watermark downloaded to: {local_path}")
            return local_path
        except Exception:
            LOGS.exception("Error downloading watermark")
            return None

    def detect_audio_languages(self, filepath: str):
        """
        Use ffprobe to detect audio track languages.
        Returns: list of tuples -> [(index, lang), ...]
        """
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index:stream_tags=language",
                "-of", "json", filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            langs = []
            for stream in data.get("streams", []):
                index = stream.get("index")
                lang = stream.get("tags", {}).get("language", "und")
                langs.append((index, lang))
            return langs
        except Exception as e:
            LOGS.exception(f"Language detection failed: {e}")
            return []

    async def start_encode(self):
        if ospath.exists(self.__prog_file):
            await aioremove(self.__prog_file)

        async with aiopen(self.__prog_file, 'w+'):
            LOGS.info("Progress Temp Generated!")

        dl_npath = ospath.join("encode", "ffanimeadvin.mkv")
        out_npath = ospath.join("encode", "ffanimeadvout.mkv")
        await aiorename(self.dl_path, dl_npath)

        # HDRip/HDRi detection
        is_hdrip = any(term.lower() in self.__name.lower() for term in ("hdrip", "hdri"))

        watermark = None
        if not is_hdrip:
            wm = await db.get_watermark()
            if wm and (wm.startswith("http://") or wm.startswith("https://")):
                local_wm = await self.download_watermark(wm)
                watermark = local_wm if local_wm else None

        ffcode = f"ffmpeg -hide_banner -loglevel error -progress '{self.__prog_file}' -i '{dl_npath}'"

        if is_hdrip:
            ffcode += " -c copy"
        else:
            if watermark and ospath.exists(watermark):
                ffcode += (
                    f" -i '{watermark}' "
                    f"-filter_complex '[0:v][1:v] overlay=W-w-70:H-h-70,{scale_values[self.__qual]}:flags=lanczos [out]' "
                    f"-map '[out]' -map 0:a -map 0:s?"
                )
            else:
                ffcode += (
                    f" -filter_complex '{scale_values[self.__qual]}:flags=lanczos[out]' "
                    f"-map '[out]' -map 0:a -map 0:s?"
                )

            # Preserve all metadata
            ffcode += " -map_metadata 0"

            # Detect audio languages dynamically
            audio_langs = self.detect_audio_languages(dl_npath)
            for idx, lang in audio_langs:
                ffcode += f" -metadata:s:a:{idx} title='@ongoing_nxivm'"
                #ffcode += f" -metadata:s:a:{idx} #language={lang} -metadata:s:a:{idx} #title='@chrunchyrool'"

        ffcode += f" '{out_npath}' -y"

        LOGS.info(f'FFCode: {ffcode}')

        self.__proc = await create_subprocess_shell(ffcode, stdout=PIPE, stderr=PIPE)
        proc_pid = self.__proc.pid
        ffpids_cache.append(proc_pid)

        _, return_code = await gather(create_task(self.progress()), self.__proc.wait())
        ffpids_cache.remove(proc_pid)

        await aiorename(dl_npath, self.dl_path)

        if self.is_cancelled:
            return

        if return_code == 0 and ospath.exists(out_npath):
            await aiorename(out_npath, self.out_path)
            return self.out_path
        else:
            stderr_output = (await self.__proc.stderr.read()).decode().strip()
            await rep.report(stderr_output, "error")

    async def cancel_encode(self):
        self.is_cancelled = True
        if self.__proc is not None:
            try:
                self.__proc.kill()
            except:
                pass