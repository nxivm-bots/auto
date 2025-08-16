from calendar import month_name
from datetime import datetime, timedelta
from random import choice
from asyncio import sleep as asleep
from aiohttp import ClientSession
from anitopy import parse
import re
from bot import Var, bot
from .ffencoder import ffargs
from .func_utils import handle_logs
from .reporter import rep
from .database import db

def stylize_quote(text: str) -> str:
    """Stylize the first line/quote in full-width Unicode for dramatic effect."""
    fancy_map = str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-",
        "𝑨𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟩𝟴𝟵−"
    )
    return text.translate(fancy_map)


CAPTION_FORMAT = """
<b>Episode {ep_no} {lang_info}</b>
<b>How to download - <a href="https://t.me/tutorita/18">Click Here</a></b>
"""




GENRES_EMOJI = {
    "Action": "👊",
    "Adventure": choice(['🪂', '🧗‍♀']),
    "Comedy": "🤣",
    "Drama": " 🎭",
    "Ecchi": choice(['💋', '🥵']),
    "Fantasy": choice(['🧞', '🧞‍♂', '🧞‍♀','🌗']),
    "Hentai": "🔞",
    "Horror": "☠",
    "Mahou Shoujo": "☯",
    "Mecha": "🤖",
    "Music": "🎸",
    "Mystery": "🔮",
    "Psychological": "♟",
    "Romance": "💞",
    "Sci-Fi": "🛸",
    "Slice of Life": choice(['☘','🍁']),
    "Sports": "⚽️",
    "Supernatural": "🫧",
    "Thriller": choice(['🥶', '🔪','🤯'])
}

SEASON_EMOJI = {
    "WINTER": "❄️",
    "SPRING": "🌸",
    "SUMMER": "☀️",
    "FALL": "🍂",
    "AUTUMN": "🍁"  # Sometimes AniList uses this
}


ANIME_GRAPHQL_QUERY = """
query ($id: Int, $search: String, $seasonYear: Int) {
  Media(id: $id, type: ANIME, format_not_in: [MOVIE, MUSIC, MANGA, NOVEL, ONE_SHOT], search: $search, seasonYear: $seasonYear) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    type
    format
    status(version: 2)
    description(asHtml: false)
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    season
    seasonYear
    episodes
    duration
    chapters
    volumes
    countryOfOrigin
    source
    hashtag
    trailer {
      id
      site
      thumbnail
    }
    updatedAt
    coverImage {
      large
    }
    bannerImage
    genres
    synonyms
    averageScore
    meanScore
    popularity
    trending
    favourites
    studios {
      nodes {
         name
         siteUrl
      }
    }
    isAdult
    nextAiringEpisode {
      airingAt
      timeUntilAiring
      episode
    }
    airingSchedule {
      edges {
        node {
          airingAt
          timeUntilAiring
          episode
        }
      }
    }
    externalLinks {
      url
      site
    }
    siteUrl
  }
}
"""

class AniLister:
    def __init__(self, anime_name: str, year: int) -> None:
        self.__api = "https://graphql.anilist.co"
        self.__ani_name = anime_name
        self.__ani_year = year
        self.__vars = {'search': self.__ani_name, 'seasonYear': self.__ani_year}

    def get_episode(self):
        return self.pdata.get("episode_number")

    def get_season(self):
        return self.pdata.get("anime_season")

    def get_audio(self):
        return self.pdata.get("audio")

    def __update_vars(self, year: bool = True) -> None:
        """Update GraphQL variables either by reducing year or removing year constraint."""
        if year:
            self.__ani_year -= 1
            self.__vars['seasonYear'] = self.__ani_year
        else:
            self.__vars = {'search': self.__ani_name}

    async def post_data(self):
        """Post GraphQL query to AniList API and return response details."""
        async with ClientSession() as sess:
            async with sess.post(self.__api, json={'query': ANIME_GRAPHQL_QUERY, 'variables': self.__vars}) as resp:
                return (resp.status, await resp.json(), resp.headers)

    async def get_anidata(self):
        """Fetch anime data with retries on 404, 429, and server errors."""
        res_code, resp_json, res_heads = await self.post_data()

        # Retry by reducing year until 2020
        while res_code == 404 and self.__ani_year > 2020:
            self.__update_vars()
            await rep.report(f"AniList Query Name: {self.__ani_name}, Retrying with {self.__ani_year}", "warning", log=False)
            res_code, resp_json, res_heads = await self.post_data()

        # If still 404, try without the year filter
        if res_code == 404:
            self.__update_vars(year=False)
            res_code, resp_json, res_heads = await self.post_data()

        if res_code == 200:
            return resp_json.get('data', {}).get('Media', {}) or {}

        elif res_code == 429:
            # Too many requests — wait and retry
            retry_after = int(res_heads.get('Retry-After', 5))
            await asleep(retry_after)
            return await self.get_anidata()

        elif res_code in [500, 501, 502]:
            # Server-side error — wait and retry
            await asleep(5)
            return await self.get_anidata()

        # Other errors — log and return empty
        await rep.report(f"AniList API Error: {res_code}", "error", log=False)
        return {}

class TextEditor:
    def __init__(self, name):
        self.__name = name
        self.adata = {}
        self.pdata = parse(name)

    async def load_anilist(self):
        cache_names = []
        for option in [(False, False), (False, True), (True, False), (True, True)]:
            ani_name = await self.parse_name(*option)
            if ani_name in cache_names:
                continue
            cache_names.append(ani_name)
            self.adata = await AniLister(ani_name, datetime.now().year).get_anidata()
            if self.adata:
                break

    async def extract_metadata(self, filename: str):
        filename = filename.lower()

        # Extract episode number
        ep_match = re.search(r'(?:ep?|episode)[\s._-]*?(\d{1,3})', filename)
        episode = ep_match.group(1) if ep_match else "01"

        # Extract quality
        quality_match = re.search(r'(360p|480p|720p|1080p|2160p)', filename)
        quality = quality_match.group(1) if quality_match else "720p"

        # Extract audio type
        if "dual" in filename:
            audio = "DUAL"
        elif "multi" in filename:
            audio = "MULTI"
        elif "eng" in filename and "jap" in filename:
            audio = "DUAL"
        elif "japanese" in filename or "sub" in filename:
            audio = "SUB"
        else:
            audio = "SUB"

        # Extract season
        season_match = re.search(r'(?:s|season)[\s._-]*(\d{1,2})', filename)
        season = season_match.group(1).zfill(2) if season_match else "01"

        # Save to self.pdata
        self.pdata = {
            "episode": episode,
            "quality": quality,
            "audio": audio,
            "season": season
        }

    @handle_logs
    async def parse_name(self, no_s=False, no_y=False):
        anime_name = self.pdata.get("anime_title")
        anime_season = self.pdata.get("anime_season")
        anime_year = self.pdata.get("anime_year")
        if anime_name:
            pname = anime_name
            if not no_s and self.pdata.get("episode_number") and anime_season:
                pname += f" {anime_season}"
            if not no_y and anime_year:
                pname += f" {anime_year}"
            return pname
        return anime_name

    @handle_logs
    async def get_id(self):
        if (ani_id := self.adata.get('id')) and str(ani_id).isdigit():
            return ani_id

    @handle_logs
    async def get_poster(self):
        if anime_id := await self.get_id():
            return f"https://img.anili.st/media/{anime_id}"
        return "https://i.ibb.co/9xqbNd8/20250521-223014.png"

    @handle_logs
    async def get_upname(self, qual=""):
        anime_name = self.pdata.get("anime_title")
        codec = 'HEVC' if 'libx266' in ffargs.get(qual, '') else 'AV1' if 'libaom-avi' in ffargs.get(qual, '') else ''

    # ✅ Try custom rename first
        custom_name = await db.get_custom_rename(anime_name)
        if custom_name:
            await db.remove_custom_rename(anime_name)
            return custom_name.replace("{QUAL}", qual).strip()

    # ✅ Use original filename
        filename = self.__name or self.pdata.get("original_filename", "")
        filename_lower = filename.lower()
        tags = " ".join(re.findall(r'\((.*?)\)', filename)).lower()

    # ✅ Language detection
        lang = (
            "Dual" if "dual" in filename_lower or "dual" in tags
            else "Sub"
        )

        print("Original filename:", filename)
        print("Extracted tags:", tags)
        print("Detected language:", lang)

        ep_number = self.pdata.get("episode_number")
        anime_season = self.pdata.get('anime_season', '01')

        if isinstance(anime_season, list):
            anime_season = anime_season[-1] if anime_season else '01'
        anime_season = str(anime_season).zfill(2)

        if filename and ep_number:
        # Final filename 
            return (
                f"[NA] {filename} - [S{anime_season}- E{str(ep_number).zfill(2)}] "
                f"[{qual}p - {lang}]@ongoing_nxivm.mkv"
            )


    @handle_logs
    async def get_caption(self):
        
        # existing caption logic, but use name_to_use for episode/audio parsing
        sd = self.adata.get('startDate', {})
        season_number = self.pdata.get("anime_season") or "1"
        if isinstance(season_number, list):
            season_number = season_number[-1] if season_number else "1"
        season_number = str(season_number).zfill(2)

        filename = self.__name
        filename_lower = filename.lower()
        tags = " ".join(re.findall(r'\((.*?)\)', filename)).lower()

        lang = (
            "DUAL" if "dual" in filename_lower or "dual" in tags
            else "MULTI" if "multi" in filename_lower or "multi" in tags
            else "SUB"
        )

        print("Original filename:", filename)
        print("Extracted tags:", tags)
        print("Detected language:", lang)

        lang_info = {
            "DUAL": "DUAL[ENG+JAP]",
            "MULTI": "Japanese [E-Sub]",
            "SUB": "Japanese [E-Sub]"
        }.get(lang, "Japanese [E-Sub]")

        next_ep = self.adata.get("nextAiringEpisode")
        season_raw = self.adata.get("season")
        season_year = self.adata.get("seasonYear")

        if season_raw and season_year:
            season_name = season_raw.upper()
            season_emoji = SEASON_EMOJI.get(season_name, "📅")
            seasonal_line = f"{season_emoji} {season_name.title()} {season_year}"
        else:
            seasonal_line = "📅 Not Listed"

        if next_ep:
            airing_unix = next_ep.get("airingAt")
            ep_no_next = next_ep.get("episode")
            airing_date = datetime.utcfromtimestamp(airing_unix).strftime("%d %B %Y")
            next_airing_info = (
                f"ᴇᴘɪꜱᴏᴅᴇ {str(ep_no_next).zfill(2)} Wɪʟʟ ʀᴇʟᴇᴀꜱᴇ ᴏɴ {airing_date} "
                f"ᴀʀᴏᴜɴᴅ ᴛʜᴇ ꜱᴀᴍᴇ ᴛɪᴍᴇ ᴀꜱ ᴛᴏᴅᴀʏ'ꜱ ᴇᴘɪꜱᴏᴅᴇ ᴀɴᴅ ᴡɪʟʟ ʙᴇ ᴜᴘʟᴏᴀᴅᴇᴅ ꜰɪʀꜱᴛ ᴏɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ"
            )
        else:
            next_airing_info = "✅ Sᴇᴀꜱᴏɴ Cᴏᴍᴘʟᴇᴛᴇᴅ"

        startdate = f"{month_name[sd['month']]} {sd['day']}, {sd['year']}" if sd.get('day') and sd.get('year') else ""
        ed = self.adata.get('endDate', {})
        enddate = f"{month_name[ed['month']]} {ed['day']}, {ed['year']}" if ed.get('day') and ed.get('year') else ""

        titles = self.adata.get("title", {})

        return CAPTION_FORMAT.format(
            title=titles.get('english') or titles.get('romaji') or titles.get('native'),
            form=self.adata.get("format") or "N/A",
            genres=", ".join(x for x in (self.adata.get('genres') or [])),
            avg_score=f"{sc}%" if (sc := self.adata.get('averageScore')) else "N/A",
            status=self.adata.get("status") or "N/A",
            start_date=startdate or "N/A",
            end_date=enddate or "N/A",
            season_number=season_number,
            t_eps=self.adata.get("episodes") or "N/A",
            lang_info=lang_info,
            seasonal_line=seasonal_line,
            next_airing_info=next_airing_info,
            plot=(desc if (desc := self.adata.get("description") or "N/A") and len(desc) < 200 else desc[:200] + "..."),
            ep_no=self.pdata.get("episode_number"),
            cred=Var.BRAND_UNAME,
        )
