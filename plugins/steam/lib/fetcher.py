"""Steam Web API 取数：最近游玩、总时长、等级与玩家概要。

Steam 官方接口需要两个凭据——`api_key`（Steam Web API Key）与 `steam_id`（64 位 ID）。
本插件不在代码里内置任何密钥，二者由 URL 查询参数传入，也可在管理面板的「插件配置」
里通过 `DEFAULT_ARGS` 预置默认值（URL 显式传了的以 URL 为准）。
Key 申请入口：https://steamcommunity.com/dev/apikey

网络失败按「拿不到数据」抛 ParamError，让请求明确报错而不是静默出一张空图；
异常消息带上异常类型与原始信息，不把超时/连接失败糊成一句泛化文案。
"""
import asyncio
import time

import httpx

from modules.errors.errors import ParamError

_TIMEOUT_SECONDS = 10.0
_API_BASE = "https://api.steampowered.com"


async def fetch_steam_data(api_key, steam_id):
    if not api_key or not steam_id:
        raise ParamError("Missing api_key or steam_id")

    urla = f"{_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v1/?key={api_key}&steamid={steam_id}&format=json"
    urlb = f"{_API_BASE}/IPlayerService/GetOwnedGames/v0001/?key={api_key}&steamid={steam_id}&format=json"
    urlc = f"{_API_BASE}/IPlayerService/GetSteamLevel/v0001/?key={api_key}&steamid={steam_id}&format=json"
    urld = f"{_API_BASE}/isteamuser/GetPlayerSummaries/v2/?key={api_key}&steamids={steam_id}&format=json"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            follow_redirects=True,
        ) as client:
            responsea = await client.get(urla)
            dataa = responsea.json()

            # 频率限制：Steam Web API 对同一 Key 有调用频率上限，间隔一小会儿再打下一枪
            await asyncio.sleep(0.3)

            responseb = await client.get(urlb)
            datab = responseb.json()

            responsec = await client.get(urlc)
            datac = responsec.json()

            responsed = await client.get(urld)
            datad = responsed.json()
    except httpx.HTTPError as exc:
        # httpx 超时异常的 str() 可能是空串，带上类型名才看得出是超时还是连不上
        raise ParamError(f"Error fetching Steam data: {type(exc).__name__}: {str(exc)}")
    except ValueError as exc:
        raise ParamError(f"Error fetching Steam data: 响应解析失败: {exc}")

    for response in (responsea, responseb, responsec, responsed):
        if response.status_code != 200:
            raise ParamError(f"Error fetching Steam data: HTTP {response.status_code}")

    steam_level = datac.get("response", {}).get("player_level", 0)
    players = datad.get("response", {}).get("players", [])
    if not players:
        raise ParamError("Player not found")
    player_data = players[0]

    last_logoff = time.strftime("%Y-%m-%d %H:%M", time.localtime(player_data.get("lastlogoff", 0)))

    total_playtime = 0
    games = datab.get("response", {}).get("games", [])
    for game in games:
        total_playtime += game.get("playtime_forever", 0)

    total_playtime_hours = round(total_playtime / 60.0, 1)
    game_count = datab.get("response", {}).get("game_count", 0)

    recent_games_list = dataa.get("response", {}).get("games", [])
    recent_game_names = []
    for game in recent_games_list:
        playtime_2weeks = game.get("playtime_2weeks", 0)
        playtime_2weeks_hours = round(playtime_2weeks / 60, 1)
        recent_game_names.append(f"{game['name']}({playtime_2weeks_hours} h)")

    return {
        "total_playtime_hours": total_playtime_hours,
        "game_count": game_count,
        "recent_game_count": len(recent_games_list),
        "recent_game_names": recent_game_names,
        "steam_level": steam_level,
        "nickname": player_data.get("personaname", "Unknown"),
        "last_logoff": last_logoff,
    }
