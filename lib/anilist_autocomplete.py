import aiohttp
import discord
from discord.ext import commands
from discord.ext import tasks

from lib.bot import TMWBot

ANILIST_NAME_QUERY = """
query ($search: String, $type: MediaType) {
  Page(perPage: 10) {
    media(search: $search, type: $type) {
      id
      title {
        english
        native
      }
      coverImage {
        medium
      }
    }
  }
}"""

ANILIST_ID_QUERY = """
query ($id: Int) {
  Media(id: $id) {
    id
    title {
      english
      native
    }
    coverImage {
      medium
    }
  }
}"""

CACHED_ANILIST_RESULTS_CREATE_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS cached_anilist_results (
    primary_key INTEGER PRIMARY KEY AUTOINCREMENT,
    anilist_id INTEGER UNIQUE,
    title_english TEXT,
    title_native TEXT,
    cover_image_url TEXT,
    media_type TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_ANILIST_INDEX_QUERY_1 = """
CREATE INDEX IF NOT EXISTS idx_title_english ON cached_anilist_results (title_english);
"""
CREATE_ANILIST_INDEX_QUERY_2 = """
CREATE INDEX IF NOT EXISTS idx_title_native ON cached_anilist_results (title_native);
"""

CACHED_ANILIST_RESULTS_INSERT_QUERY = """
INSERT INTO cached_anilist_results (anilist_id, title_english, title_native, cover_image_url, media_type) 
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(anilist_id) DO UPDATE SET 
    title_english=excluded.title_english,
    title_native=excluded.title_native,
    cover_image_url=excluded.cover_image_url,
    media_type=excluded.media_type,
    timestamp=CURRENT_TIMESTAMP;
"""

CACHED_ANILIST_RESULTS_SEARCH_QUERY = """
SELECT anilist_id, title_english, title_native, cover_image_url 
FROM cached_anilist_results 
WHERE (LOWER(REPLACE(title_english, ' ', '')) LIKE '%' || LOWER(REPLACE(?, ' ', '')) || '%' 
    OR LOWER(REPLACE(title_native, ' ', '')) LIKE '%' || LOWER(REPLACE(?, ' ', '')) || '%') 
AND media_type = ? 
LIMIT 10;
"""

CACHED_ANILIST_RESULTS_BY_ID_QUERY = """
SELECT anilist_id, title_english, title_native, cover_image_url FROM cached_anilist_results 
WHERE anilist_id = ? AND media_type = ?;
"""

CACHED_ANILIST_THUMBNAIL_QUERY = """
SELECT cover_image_url FROM cached_anilist_results
WHERE anilist_id = ?;
"""


async def query_anilist(interaction: discord.Interaction, current_input: str, bot: TMWBot):
    url = "https://graphql.anilist.co"

    media_type = interaction.namespace['media_type'].upper()
    if current_input.isdigit():
        query = ANILIST_ID_QUERY
        variables = {
            "id": int(current_input)
        }
    else:
        query = ANILIST_NAME_QUERY
        variables = {
            "search": current_input,
            "type": media_type
        }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"query": query, "variables": variables}) as response:
            if response.status == 200:
                data = await response.json()
                if current_input.isdigit():
                    media_list = [data.get("data", {}).get("Media", {})]
                else:
                    media_list = data.get("data", {}).get("Page", {}).get("media", [])

                choices = []
                for media in media_list:
                    media_id = media.get("id")
                    title_english = media.get("title", {}).get("english")
                    title_native = media.get("title", {}).get("native")
                    cover_image_url = media.get("coverImage", {}).get("medium")
                    title = title_english or title_native
                    if not title or not media_id:
                        continue

                    choice_name = f"{title[:80]} (ID: {media_id})"
                    if title:
                        choices.append(discord.app_commands.Choice(name=choice_name, value=str(media_id)))

                    await bot.RUN(CACHED_ANILIST_RESULTS_INSERT_QUERY, (media_id, title_english, title_native, cover_image_url, media_type))

                return choices[:10]
            elif response.status == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"API rate limit exceeded. Please wait {retry_after} seconds before retrying.")
                return []
            else:
                return []


async def anime_manga_name_autocomplete(interaction: discord.Interaction, current_input: str):
    tmw_bot = interaction.client
    tmw_bot: TMWBot

    media_type = interaction.namespace['media_type'].upper()

    if current_input.isdigit():
        cached_result = await tmw_bot.GET_ONE(CACHED_ANILIST_RESULTS_BY_ID_QUERY, (int(current_input), media_type))
        if cached_result:
            anilist_id, title_english, title_native, _ = cached_result
            title = title_english or title_native
            if title:
                choice_name = f"{title[:80]} (ID: {anilist_id})"
                return [discord.app_commands.Choice(name=choice_name, value=str(anilist_id))]
        else:
            return await query_anilist(interaction, current_input, tmw_bot)
    else:
        cached_results = await tmw_bot.GET(CACHED_ANILIST_RESULTS_SEARCH_QUERY, (f"%{current_input}%", f"%{current_input}%", media_type))
        choices = []
        for cached_result in cached_results:
            anilist_id, title_english, title_native, _ = cached_result
            title = title_english or title_native
            if title:
                choice_name = f"{title[:80]} (ID: {anilist_id})"
                choices.append(discord.app_commands.Choice(name=choice_name, value=str(anilist_id)))

        if len(choices) < 3:
            anilist_choices = await query_anilist(interaction, current_input, tmw_bot)
            choices.extend(anilist_choices)

        return choices[:10]


async def listening_autocomplete(interaction: discord.Interaction, current_input: str):
    # TODO: TMDB API
    return []