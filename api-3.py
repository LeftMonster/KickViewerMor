import asyncio
import base64
import datetime
import json
import os
import queue
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Optional, Union, Dict, List

import numpy as np
import socks
import websocket
from rqsession import RequestSession, EnhancedRequestSession
from browser_forge import AsyncRustTLSProxyClient, Edge142, Chrome119, BrowserClient
from typing_extensions import deprecated

from data_acc import lines
from drops_priority_manager import DropsPriorityManager
from utils.decorator import retry
from utils.logger_util import logger

import platform


def parse_datetime_with_microseconds(dt_str) -> datetime.datetime:
    try:
        # 尝试解析带微秒的日期格式，例如："2024-04-30T08:59:59.999Z"
        return datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        try:
            # 如果解析失败，尝试解析不带微秒的日期格式，例如："2024-04-30T08:59:59Z"
            return datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%fZ")


def extract_m3u8_urls(html: str) -> List[str]:
    """
    从 HTML 文本中提取所有形如 "https://xxx.m3u8?xxxx" 的 URL 字符串。
    只匹配双引号中的内容，返回去掉引号后的 URL 列表。
    """
    # 匹配模式说明：
    # "(https://[^"]+\.m3u8\?[^"]*)"
    # 1. "                匹配开头的双引号
    # 2. ( ... )         捕获组，里面是我们想要的 URL
    # 3. https://        固定前缀
    # 4. [^"]+           任意非引号字符（直到 .m3u8? 之前）
    # 5. \.m3u8          匹配 .m3u8
    # 6. \?              匹配问号
    # 7. [^"]*           问号后任意非引号字符
    # 8. "               结尾的双引号
    res = []
    pattern = r'"(https://[^"]+\.m3u8\?[^"]*)"'
    for line in re.findall(pattern, html):
        if line.endswith("\\"):
            line = line.replace("\\", "")
            res.append(line)
    return res


def extract_channel_id(text: str):
    """
    从任意文本中提取 "channel_id":52304 这样的数字
    返回 int 或 None
    "\"channel_id\":52304,\"descrip"
    "\"channel_id\":52304,\"months\""
    "\"channel_id\":52304,\"created_at\""
    """
    cid = text.split(r'\"channel_id\":')[1].split(r',\"')[0]
    m = re.search(r'"channel_id"\s*:\s*(\d+)', text)
    if m:
        return int(m.group(1))
    return cid

def extract_livestream_id(text: str):
    """从HTML中提取livestream_id"""
    # 示例匹配: "livestream_id":12345
    m = re.search(r'"livestream.*?_id"\s*:\s*(\d+)', text)
    if m:
        return int(m.group(1))
    return None

def inventory_get(oauth: str = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ"):
    url = "https://web.kick.com/api/v1/livestreams/featured?language=en"
    session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")
    authorization = "Bearer {}".format(oauth)
    session.headers['Authorization'] = authorization
    resp = session.get(url)
    logger.info(resp.status_code)
    logger.info(resp.headers)
    logger.info(resp.text)
    data = resp.json()
    return data


async def async_progress(oauth):
    url = "https://web.kick.com/api/v1/drops/progress"
    headers = Edge142.headers.to_dict()
    headers.pop("order")
    headers["authorization"] = "Bearer {}".format(oauth)
    async with AsyncRustTLSProxyClient(
            base_url="http://127.0.0.1:5005",
            default_profile="chrome_119_windows",
    ) as client:
        resp = await client.get(url, headers=headers)
        logger.info(f"progress数据获取: {resp.status_code}")
        return resp.json()


def live_videos(oauth: str = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ", name: str = None):
    url = "https://kick.com/api/v2/channels/{}/videos".format(name)
    session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

    authorization = "Bearer {}".format(oauth)
    session.headers['Authorization'] = authorization
    resp = session.get(url)
    logger.info(resp.status_code)
    logger.info(resp.headers)
    logger.info(resp.text)
    data = resp.json()
    return data


async def async_live_videos(oauth, name):
    url = "https://kick.com/api/v2/channels/{}/videos".format(name)
    headers = Edge142.headers.to_dict()
    headers.pop("order")
    headers["authorization"] = "Bearer {}".format(oauth)
    async with AsyncRustTLSProxyClient(
            base_url="http://127.0.0.1:5005",
            default_profile="chrome_119_windows",
    ) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.info(f"频道数据获取: {resp.status_code}")
        return resp.json()


async def channel_token(oauth):
    url = "https://websockets.kick.com/viewer/v1/token"
    headers = Edge142.headers.to_dict()
    headers.pop("order")
    headers["x-client-token"] = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
    headers["authorization"] = "Bearer {}".format(oauth)
    async with AsyncRustTLSProxyClient(
            base_url="http://127.0.0.1:5005",
            default_profile="chrome_119_windows",
    ) as client:
        resp = await client.get(url, headers=headers)
        logger.info(f"token获取: {resp.status_code}")
        return resp.json()


async def async_campaigns(oauth):
    url = "https://web.kick.com/api/v1/drops/campaigns"
    headers = Edge142.headers.to_dict()
    headers.pop("order")
    headers["authorization"] = "Bearer {}".format(oauth)
    async with AsyncRustTLSProxyClient(
            base_url="http://127.0.0.1:5005",
            default_profile="chrome_119_windows",
    ) as client:
        resp = await client.get(url, headers=headers)
        logger.info(f"progress数据获取: {resp.status_code}")
        return resp.json()


def campaigns(oauth):
    url = "https://web.kick.com/api/v1/drops/campaigns"
    headers = Edge142.headers.to_dict()
    headers.pop("order")
    logger.info(headers)
    headers["authorization"] = "Bearer {}".format(oauth)
    client = BrowserClient(
        Chrome119,
        proxy="http://127.0.0.1:7890"
    )
    resp = client.get(url, headers=headers)
    logger.info(f"progress数据获取: {resp.status_code}")
    return resp.json()


def live_stream(oauth: str = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ"):
    url = "https://web.kick.com/api/v1/drops/campaigns/livestream?channel_id=109579&category_id=13"
    session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

    authorization = "Bearer {}".format(oauth)
    session.headers['Authorization'] = authorization
    resp = session.get(url)
    logger.info(resp.status_code)
    logger.info(resp.headers)
    logger.info(resp.text)
    data = resp.json()
    return data


def parse_channel():
    payload = {
        "event": "master_manifest_ready",
        "properties": {
            "audio_codec": "",
            "backend": "mediaplayer", "browser_family": "microsoft edge",
            "browser_version": "142.0", "buffer_empty_count": 0, "build_dist_id": "npm",
            "catch_up_mode": "none", "content_id": "BfGqaoEoRAkq", "core_version": "1.45.0",
            "customer_id": "196233775518", "device_manufacturer": "", "device_model": "",
            "domain": "kick.com", "hidden": False, "host": "kick.com",
            "initial_buffer_duration": 2000, "live": True, "low_latency": False, "minutes_logged": 0,
            "mobile_connection_type": "unknown",
            "muted": True, "os_name": "Windows",
            "os_version": "NT 10.0", "platform": "web",
            "play_session_id": "cc493eee623947feb387d6298a0fdab4", "player": "web", "protocol": "",
            "quality": "auto", "time_to_master_playlist_ready": 476,
            "time_to_master_playlist_request": 6, "transcoder_version": "",
            "url": "https://kick.com/oilrats",  # TODO 主播地址
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            "video_buffer_size": 0, "video_codec": "", "volume": 0
        }
    }
    url = "https://player.stats.live-video.net/"
    session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

    # authorization = "Bearer {}".format(oauth)
    # session.headers['Authorization'] = authorization
    session.headers['Content-Type'] = "application/x-www-form-urlencoded; charset=UTF-8"
    data = base64.b64encode(json.dumps(payload, separators=(',', ':')).encode("utf-8"))
    logger.info(data)
    resp = session.post(url, data={
        "data": data,
    })
    logger.info(resp.status_code)
    logger.info(resp.headers)
    logger.info(resp.text)
    return data


def claim_drops(reward_id, campaign_id, oauth):
    url = "https://web.kick.com/api/v1/drops/claim"

    # payload = {"reward_id":"01K8X31CKQSSSFVJG7XMB8PTVS","campaign_id":"01K8X4S18DE0JMXSX8A5WWNS0N"}
    payload = {"reward_id":reward_id,"campaign_id":campaign_id}
    client = BrowserClient(
        Edge142,
        proxy="http://127.0.0.1:7890"
    )
    headers = Edge142.headers.to_dict()
    headers.pop('order')
    headers.update({
        "authorization": "Bearer {}".format(oauth),
    })
    resp = client.post(url, data=payload, headers=headers)
    if resp.status_code != 200:
        logger.info(resp.status_code)
        logger.info(resp.text)
        logger.info("领取失败")
        return False
    data = resp.json()
    # data["data"]["id"]
    # data["message"]
    return data



def drops_parser(res_dict: dict, slug: set[str]):
    """
        slug - 指定的哪个游戏de name

        数据结构：
            [
                {
                  "category_id": 13,    # drop分类id
                  "id": "01K8X3T8Q3Z942YKJF6T42BYJX",   # 掉宝id
                  "image_url": "drops/reward-image/01k8x3t8q3z942ykjf6t42byjx.png",
                  "name": "Team Ser Winter Thompson",       # drop name
                  "organization_id": "01K6WKP5BBMPZJ89G5Y7QK1E9P",  # company id
                  "required_units": 120,     # require timeto watch
                  "streamer": []        # can gain from which one, [] refers to all streamers who have drops tag
                }
            ]
    """
    ignore_slug = False
    if slug in [{}, None]:
        ignore_slug = True
    if 'data' in res_dict and isinstance(res_dict['data'], list):
        drops_list = []
        for camp in res_dict['data']:
            if ignore_slug or camp['category']['slug'] in slug:
                # 对应游戏
                # 收集频道主播与drops

                #if 'channels' in camp and isinstance(camp['channels'], list):
                # 特定频道掉宝
                # 收集掉宝
                for drop in camp['rewards']:
                    # 支持的主播列表
                    drop['streamer'] = camp.get('channels', [])
                    drop['starts_at'] = camp['starts_at']
                    drop['game_id'] = camp['category']['id']
                    drop['slug'] = camp['category']['slug']
                    drop['game'] = camp['category']['name']
                    drop['current_minutes'] = camp.get('progress_units', 0)
                    drop['starts_at'] = parse_datetime_with_microseconds(camp.get('starts_at', 0))
                    drop['ends_at'] = parse_datetime_with_microseconds(camp.get('ends_at', 0))
                    drops_list.append(drop)
        return drops_list
    logger.info("其他情况")
    return []


async def progress_check(oauth):
    pass

@retry(exception_to_catch=Exception, num_times=3, delay_seconds=1)
async def init_channel_page(oauth, name):
    url = "https://kick.com/" + name
    headers = Edge142.headers.to_dict()
    headers.pop("order")
    headers["x-client-token"] = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
    headers["authorization"] = "Bearer {}".format(oauth)
    async with AsyncRustTLSProxyClient(
            base_url="http://127.0.0.1:5005",
            default_profile="chrome_119_windows",
    ) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.info(f"homepage获取: {resp.status_code}")
        return resp.text


async def check_online_status_v1(config_oauth, streamer_name):
    resp_text = await init_channel_page(config_oauth, streamer_name)
    if r'is_live\":true' in resp_text:
        #logger.info("正在直播")
        return True
    return False


async def check_online_status(config_oauth, streamer_name):
    resp_text = await init_channel_page(config_oauth, streamer_name)

    if r'is_live\":true' in resp_text:
        channel_id = extract_channel_id(resp_text)
        # 新增: 提取living_stream_id
        #living_stream_id = extract_livestream_id(resp_text)  # 需要实现这个函数
        return True, channel_id

    return False, None


class KickStreamer:
    def __init__(self, config_oauth, streamer_name, online: bool = False):
        self.config_oauth = config_oauth
        self.streamer_name = streamer_name
        self.online = online
        self.initialed = False

        self.drops_list = []
        self.campaigns = []

        self.channel_id = None
        self.livestream_id = None

    @retry(exception_to_catch=Exception, num_times=3, delay_seconds=1)
    async def init_data(self):
        is_online, channel_id= await check_online_status(
            config_oauth=self.config_oauth,
            streamer_name=self.streamer_name
        )

        livestream_id = None
        videos_data = await async_live_videos(oauth=self.config_oauth, name=self.streamer_name)
        for raw in videos_data:
            if 'is_live' in raw and raw["is_live"]:
                livestream_id = raw['id']
                break

        self.online = is_online
        self.channel_id = channel_id
        self.livestream_id = livestream_id
        self.initialed = True

    async def init_data_v1(self):
        # client = BrowserClient(
        #     Chrome119
        # )
        # Done 先检测在线与否
        is_online = await check_online_status(config_oauth=self.config_oauth, streamer_name=self.streamer_name)
        self.online = is_online
        logger.info("{} is living...".format(self.streamer_name))
        # TODO 再检测相关drops

        self.initialed = True

    def add_drop(self, drop: dict):
        self.drops_list.append(drop)


class KickPool:
    def __init__(self, config_oauth, streamers_list: list[str] = []):
        self.stream_oauth = config_oauth
        self.streamers_list = list(set(streamers_list))
        # self.streamers: list[KickStreamer] = []
        self.streamers_exist: set = set(streamers_list)
        # self.streamers: queue.Queue[KickStreamer] = queue.Queue()
        self.streamers: queue.Queue = queue.Queue(maxsize=100)
        self.queue_timeout = -1
        # queue.PriorityQueue
        self.pause_interval = 60 * 5

        # campaigns
        self.campaigns = []
        self.drops_list = []

        self.init_finished = False

    def __getitem__(self, item):
        if isinstance(item, int):
            return None
        elif isinstance(item, str):
            if item in self.streamers_exist and item in self.streamers_list:
                for index in range(self.streamers.qsize()):
                    streamer = self.streamers.get(block=True, timeout=self.pause_interval)
                    self.streamers.put(streamer)
                    if streamer == item:
                        return streamer
                return None
        else:
            logger.info("不支持的获取方式!")
            return None

    def __delitem__(self, key):
        return self.remove_streamer(key)

    async def run(self):
        for name in self.streamers_exist:
            streamer = KickStreamer(config_oauth=self.stream_oauth, streamer_name=name)
            await streamer.init_data()
            self.streamers.put(streamer)
        logger.info("初始化完毕, 开始循环检测在线状态")
        await self.init_campaigns()
        self.init_finished = True
        await self.loop_update_streamer()


    async def add_streamer(self, streamer: Union[KickStreamer, str]) -> bool:
        # filter
        if isinstance(streamer, KickStreamer):
            if streamer.streamer_name in self.streamers_exist:
                logger.info("already added")
                return False
            await streamer.init_data()
            self.streamers.put(streamer)
        elif isinstance(streamer, KickStreamer):
            if streamer in self.streamers_exist:
                logger.info("already added")
                return False
            self.streamers.put(KickStreamer(config_oauth=self.stream_oauth, streamer_name=streamer))
        else:
            logger.info("加入失败")
            return False

        self.streamers_exist.add(streamer.streamer_name)
        return True

    async def remove_streamer(self, name: str) -> bool:
        flag_1 = False
        flag_2 = False
        flag_3 = False
        if name in self.streamers_exist:
            self.streamers_exist.remove(name)
            flag_1 = True
        for item in self.streamers_list:
            if item == name:
                self.streamers_list.remove(item)
                flag_2 = True
        for index in range(self.streamers.qsize()):
            streamer = self.streamers.get(block=False, timeout=self.pause_interval)
            if streamer.streamer_name == name:
                flag_3 = True
                break
            self.streamers.put(streamer)
        return flag_1 and flag_2 and flag_3

    async def loop_update_streamer(self):
        await asyncio.sleep(self.pause_interval)
        while not self.streamers.empty():
            # for streamer in self.streamers:
            streamer = self.streamers.get(block=True, timeout=self.pause_interval)
            flag, channel_id = await check_online_status(config_oauth=self.stream_oauth, streamer_name=streamer.streamer_name)
            streamer.online = flag
            streamer.channel_id = channel_id
            self.streamers.put(streamer)

    async def loop_update_campaigns(self):
        pass

    @retry(exception_to_catch=Exception, num_times=3, delay_seconds=1)
    async def init_campaigns(self):
        data = await async_campaigns(self.stream_oauth)
        self.drops_list = drops_parser(res_dict=data, slug={'rust'})
        # mapping streamer to drops
        for i in range(self.streamers.qsize()):
            streamer = self.streamers.get(block=True, timeout=self.pause_interval)
            for drop in self.drops_list:
                for liver in drop["streamer"]:
                    if liver['slug'].lower() == streamer.streamer_name.lower():
                        streamer.add_drop(drop)
            self.streamers.put(streamer)

class KickDrops:
    def __init__(self, drop_id, name, game_slug, game_id, game_name, streamers):
        self.drop_id = drop_id
        self.name = name
        self.game_slug = game_slug
        self.game_id = game_id
        self.game_name = game_name
        self.streamers = streamers


class KickAccount:

    def __init__(self, username, password, opt_code, session_token, *args, **kwargs):
        self.username = username
        self.password = password
        self.opt_code = opt_code
        self.session_token = session_token
        self.args = args
        self.kwargs = kwargs

        # self.drops_record =

    async def query_progress(self):
        pass




class KickClientPool:
    """Kick.com 客户端 - 模拟完整请求链"""

    def __init__(self, cookies: Optional[Dict[str, str]] = None, oauth: str = None, username: str = None,
                 channel_id: str = None, living_stream_id: str = None):


        self.oauth = oauth
        self.channel_id = channel_id
        self.living_stream_id = living_stream_id

        # 设置通用请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Authorization': 'Bearer {}'.format(self.oauth),
            'Origin': 'https://kick.com',
            'Referer': 'https://kick.com/',
            'sec-ch-ua': '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }


        # 存储提取的数据
        self.channel_id = None
        self.chatroom_id = None
        self.user_id = None
        self.channel_slug = None

        self.choose_game_slug = 'rust'
        self.kick_accounts: list[KickAccount] = []
        self.drop_manager = DropsPriorityManager()

    async def homepage(self, oauth, channel_slug):
        url = f"https://kick.com/{channel_slug}"
        async with AsyncRustTLSProxyClient(
                base_url="http://127.0.0.1:5005",
                default_profile="chrome_119_windows",
        ) as client:
            #async with client.get(url) as response:
            response = await client.get(url, headers=self.headers)
            ttt = await response.text
            # 从HTML中提取频道信息 (实际需要解析HTML)
            # 观看实际视频地址
            m3u8_url = extract_m3u8_urls(ttt)
            # 频道id
            channel_id = extract_channel_id(ttt)
            return {
                'status': 'success',
                'm3u8_url': m3u8_url,
                'channel_id': int(channel_id),
            }


    # @staticmethod
    # @deprecated
    # async def streamer_homepage(channel_slug: str) -> Dict:
    #     logger.info(f"[步骤1] 加载频道主页: {channel_slug}")
    #     self.channel_slug = channel_slug
    #
    #
    #     try:
    #         for account in self.kick_accounts:
    #             pass
    #
    #
    #     except Exception as e:
    #         logger.error(f"  ✗ 主页加载失败: {e}")
    #         return {'status': 'error', 'error': str(e)}

    # ========================================================================
    # 阶段5: WebSocket连接
    # ========================================================================
    async def get_websocket_token(self) -> List[str]:
        """
        Session #660 - 获取WebSocket连接token

        Returns:
            WebSocket token或None
        """
        async def token_query(url, oauth):
            try:
                headers = self.headers.copy()
                headers.update({
                    "x-client-token": "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823",
                    "authorization": f"Bearer {oauth}",
                })
                async with AsyncRustTLSProxyClient(
                        base_url="http://127.0.0.1:5005",
                        default_profile="chrome_119_windows",
                ) as client:
                    response = await client.get(url, headers=headers)
                    logger.info(response.status_code)
                    resp = response.json()
                    token = resp['data']['token']
                    if token:
                        logger.info(f"  ✓ Token获取成功: {token[:20]}...")
                        return token
                    else:
                        logger.error(f"  ✗ 响应中没有token")
                        return None
            except Exception as e:
                logger.error(f"  ✗ Token获取失败: {e}")
                return None

        logger.info("获取WebSocket Token")
        url = "https://websockets.kick.com/viewer/v1/token"
        task_list = []
        batch = 50
        # total task
        res = []
        num = len(self.kick_accounts)
        for i in range(num // batch + 1):
            # escape 429
            for account in self.kick_accounts[i * batch:(i + 1) * batch]:
                task = asyncio.create_task(token_query(url, account.session_token))
                task_list.append(task)
            result = await asyncio.gather(*task_list, return_exceptions=False)
            res.extend(result)
            await asyncio.sleep(0.1)
        return res


    @retry(exception_to_catch=Exception, num_times=3, delay_seconds=1)
    async def connect_kick_viewer_ws(self, channel_id: int, token_list: list[str], livestream_id: int):
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 7890)
        socket.socket = socks.socksocket

        #async def connect_to_ws(token, headers):
        def connect_to_ws(token, headers):
            ws_url = (
                f"wss://websockets.kick.com/viewer/v1/connect?"
                f"token={token}"
            )
            ws = websocket.create_connection(
                ws_url,
                header=headers,
                timeout=5
            )
            logger.info("[+] WebSocket connected")
            # ========= 开始接收服务器推送 =========
            for i in range(360):
                try:
                    ws.send(json.dumps({"type": "ping"}))
                    # logger.info(">> Sent ping")
                    time.sleep(5)
                    if i % 24 == 0:
                        handshake_msg = {
                            "type": "channel_handshake",
                            "data": {
                                "message": {
                                    "channelId": str(channel_id)
                                }
                            }
                        }
                        ws.send(json.dumps(
                            {"type": "channel_handshake", "data": {"message": {"channelId": f"{str(channel_id)}"}}}))
                        logger.info(f"i: {i}")
                        logger.info(">> Sent handshake:", handshake_msg)
                        time.sleep(0.1)
                        living_event = json.dumps({"type": "user_event", "data": {
                            "message": {"name": "tracking.user.watch.livestream", "channel_id": channel_id,
                                        "livestream_id": livestream_id}}})
                        logger.info(f">> Sent tracking event: {living_event}")
                        ws.send(living_event, opcode=websocket.ABNF.OPCODE_TEXT)

                    msg = ws.recv()
                    if i % 24 == 0:
                        logger.info("<< {}".format(msg))
                except websocket.WebSocketTimeoutException:
                    logger.info("发送超时")
                    raise
                except websocket.WebSocketConnectionClosedException:
                    logger.info("连接已关闭")
                    raise
                except Exception as e:
                    logger.info(e)
                    raise

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://kick.com",
            "Pragma": "no-cache",
        }
        fts = []
        for token in token_list:
            if token is not None:
                future_ws = ws_pool.submit(connect_to_ws, token=token, headers=headers)
                fts.append(future_ws)
        wait(fts)

    @retry(exception_to_catch=Exception, num_times=3, delay_seconds=1)
    def async_connect_kick_viewer_ws(self, channel_id: int, livestream_id: int):
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 7890)
        socket.socket = socks.socksocket

        # async def connect_to_ws(token, headers):
        def connect_to_ws(token, headers):
            ws_url = (
                f"wss://websockets.kick.com/viewer/v1/connect?"
                f"token={token}"
            )
            ws = websocket.create_connection(
                ws_url,
                header=headers,
                timeout=5
            )
            logger.info("[+] WebSocket connected")
            # ========= 开始接收服务器推送 =========
            for i in range(360):
                try:
                    ws.send(json.dumps({"type": "ping"}))
                    # logger.info(">> Sent ping")
                    time.sleep(5)
                    if i % 24 == 0:
                        handshake_msg = {
                            "type": "channel_handshake",
                            "data": {
                                "message": {
                                    "channelId": str(channel_id)
                                }
                            }
                        }
                        ws.send(json.dumps(
                            {"type": "channel_handshake", "data": {"message": {"channelId": f"{str(channel_id)}"}}}))
                        logger.info(f"i: {i}")
                        logger.info(">> Sent handshake:", handshake_msg)
                        time.sleep(0.1)
                        living_event = json.dumps({"type": "user_event", "data": {
                            "message": {"name": "tracking.user.watch.livestream", "channel_id": channel_id,
                                        "livestream_id": livestream_id}}})
                        logger.info(f">> Sent tracking event: {living_event}")
                        ws.send(living_event, opcode=websocket.ABNF.OPCODE_TEXT)

                    msg = ws.recv()
                    if i % 24 == 0:
                        logger.info("<< {}".format(msg))
                except websocket.WebSocketTimeoutException:
                    logger.info("发送超时")
                    raise
                except websocket.WebSocketConnectionClosedException:
                    logger.info("连接已关闭")
                    raise
                except Exception as e:
                    logger.info(e)
                    raise

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://kick.com",
            "Pragma": "no-cache",
        }
        fts = []
        # while not token_queue.empty():
        #     token = token_queue.get(block=True, timeout=-1)
        #     if token is not None:
        #         future_ws = ws_pool.submit(connect_to_ws, token=token, headers=headers)
        #         fts.append(future_ws)
        wait(fts)

    def uniform_sample_array(self):
        """
        从数组中均匀抽取元素，抽取数量介于 10 到 500 之间，
        目标约为数组总数的 1/10。

        Args:
            arr (list or np.ndarray): 输入数组。

        Returns:
            list: 抽样后的元素列表。
        """
        N = len(self.kick_accounts)

        # 1. 处理小于等于 10 的边缘情况
        if N <= 10:
            return self.kick_accounts

        # 2. 确定目标抽样数量 T (约 1/10)
        # 使用 round() 来四舍五入到最接近的 1/10
        target_size = round(N / 10)

        # 3. 应用上下限约束 (10 到 500)
        # 确保抽样数量 S >= 10 且 S <= 500
        S = max(min(target_size, 500), 10)

        # --- 开始抽样 ---
        # 转换为 NumPy 数组，以便高效处理
        np_arr = np.asarray(self.kick_accounts)

        # np.linspace(start, stop, num) 生成 num 个均匀分布的数值。
        # 这里用于生成 S 个均匀分布的索引，从 0 到 N-1 (包含)
        # dtype=int 确保生成的索引是整数
        indices = np.linspace(0, N - 1, num=S, dtype=int)

        # 使用这些索引进行切片获取元素
        sampled_array = np_arr[indices]

        # 返回为 Python list，方便后续操作
        return sampled_array.tolist()


    async def async_progress(self, game_slug):
        sample_accounts = self.uniform_sample_array()

        task_list = []
        for account in sample_accounts:
            task = asyncio.create_task(async_progress(account.session_token))
            task_list.append(task)

        drops_list = await asyncio.gather(*task_list, return_exceptions=True)
        flatten_drops = []
        for drops in drops_list:
            flatten_drops.extend(drops_parser(drops, slug=game_slug))

        # TODO 计算先后
        # 按照drop的id、做一个字典、每个drop的观看时间与数量之和，最
        # 观看时间段、活动结束时间、已有观看分钟数的优先
        # 展开drop
        drop_unique = {}
        """
        {
            sum:
            current_num:
            total_minutes:
            require_minutes: 
        }
        """
    # 这里应该输出一个drop与主播的观看列表顺序
    ### TODO 这个队列优先级整理着一块

    # ========================================================================
    # 完整流程执行
    # ========================================================================
    async def run_complete_flow(self, kick_pool: KickPool) -> Dict:
        # TODO 随机挑选账号、抽样产看进度、决定观看谁、整理完后会有一个主播观看优先队列、然后后面kickpool中获取对应的主播数据进行建立连接就ok了
        self.async_progress(game_slug=self.choose_game_slug)

        # TODO 然后从pool管理池子中的主播实体上获取到channel和living stream、例如从队列、或者整理的优先级别队列get一个主播，得到
        channel_id = ""
        living_stream_id = ""
        token_queue = queue.Queue(maxsize=1024)
        # TODO 完成token获取、ws连接、挂起等待、目前这里先用同步、线程池的方式、后续我会调整
        token_list = await self.get_websocket_token(token_queue=token_queue)

        self.connect_kick_viewer_ws(channel_id=channel_id, token_list=token_list, livestream_id=living_stream_id)
        logger.info("\n" + "=" * 80)
        logger.info("请求链执行完成!")

        return {}

    async def run_auto_drops_watcher(self, kick_pool):
        """
        自动Drops观看器 - 主循环

        使用方法:
        在你的 KickClientPool 类中添加这个方法,然后:

        await kick_client.run_auto_drops_watcher(kick_pool)
        """
        manager = DropsPriorityManager()
        current_ws_connections = None  # WebSocket连接列表

        while True:
            try:
                # ===== 步骤1: 查询进度并生成队列 =====
                logger.info("\n[队列更新] 查询drops进度...")
                if kick_pool.streamers.qsize() == 0 or not kick_pool.init_finished:
                    logger.info("主播信息还在加载中...")
                    await asyncio.sleep(3)
                    continue

                # 采样查询
                sample_size = max(10, len(self.kick_accounts) // 10)
                sample_accounts = self.kick_accounts[:sample_size]

                tasks = [async_progress(acc.session_token) for acc in sample_accounts]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 解析
                drops_list = []
                for result in results:
                # for result in kick_pool.drops_list:
                    #if not isinstance(result, Exception):
                    res = drops_parser(result, slug={self.choose_game_slug})
                    drops_list.extend(res)

                # 聚合
                drop_stats = manager.aggregate_progress(drops_list, kick_pool.drops_list)

                # ===== 步骤2: 获取在线主播 =====
                online_streamers = {}
                temp_queue = []

                for i in range(kick_pool.streamers.qsize()):
                    streamer = kick_pool.streamers.get(block=True)
                    temp_queue.append(streamer)

                    if streamer.online:
                        cid = getattr(streamer, 'channel_id', None)
                        lid = getattr(streamer, 'livestream_id', None)
                        if cid and lid:
                            online_streamers[streamer.streamer_name.lower()] = (cid, lid)

                # 放回队列
                for s in temp_queue:
                    kick_pool.streamers.put(s)

                logger.info(f"[在线检测] {len(online_streamers)} 个主播在线")

                # ===== 步骤3: 生成优先级队列 =====
                queue = manager.generate_queue(drop_stats, online_streamers, total_drops=kick_pool.drops_list)

                if not queue:
                    logger.info("[警告] 没有可用的drops,等待5分钟后重试")
                    await asyncio.sleep(3)
                    continue

                # 显示队列
                logger.info(f"\n[优先级队列] 共 {len(queue)} 个drops:")
                for i, task in enumerate(queue[:5], 1):
                    status = "🟢在线" if task.channel_id else "🔴离线"
                    logger.info(f"  {i}. [{status}] {task.name} - "
                          f"完成{task.completion_rate * 100:.1f}% - "
                          f"分数{task.priority_score:.0f}")

                # ===== 步骤4: 选择任务 =====
                # 优先选择在线的任务
                next_task = None
                for task in queue:
                    if task.channel_id:
                        next_task = task
                        break

                # 如果都不在线,选第一个
                if not next_task:
                    next_task = queue[0]
                    logger.info(f"\n[注意] 优先主播不在线,等待5分钟后重试")
                    await asyncio.sleep(3)
                    continue

                # ===== 步骤5: 检查是否已完成 =====
                if next_task.completion_rate >= 1.0:
                    logger.info(f"✅ Drop已完成: {next_task.name}")
                    # 从队列移除并继续下一个
                    continue

                # ===== 步骤6: 建立连接 =====
                logger.info(f"\n[开始观看] {next_task.name}")
                logger.info(f"  主播: {next_task.selected_streamer}")
                logger.info(f"  进度: {next_task.avg_progress:.0f}/{next_task.required_units}分钟")
                logger.info(f"  完成度: {next_task.completion_rate * 100:.1f}%")

                # 获取tokens
                token_list = await self.get_websocket_token()

                # 关闭旧连接 (如果有)
                if current_ws_connections:
                    # TODO: 实现关闭逻辑
                    pass

                # 建立新连接 (所有账号看同一个主播)
                await self.connect_kick_viewer_ws(
                    channel_id=int(next_task.channel_id),
                    token_list=token_list,
                    livestream_id=int(next_task.livestream_id)
                )

                # ===== 步骤7: 监控循环 =====
                check_interval = 5  # 10分钟检查一次

                for check_count in range(3):  # 最多观看1小时
                    await asyncio.sleep(check_interval)

                    # 重新查询状态
                    sample_tasks = [async_progress(acc.session_token) for acc in sample_accounts[:3]]
                    sample_results = await asyncio.gather(*sample_tasks, return_exceptions=True)

                    sample_drops = []
                    for result in sample_results:
                        if not isinstance(result, Exception):
                            sample_drops.extend(drops_parser(result, slug={self.choose_game_slug}))

                    # 检查当前drop状态
                    current_drop_completed = False
                    for drop in sample_drops:
                        if drop['id'] == next_task.drop_id:
                            progress = drop.get('current_minutes', 0)
                            completion = progress / next_task.required_units

                            logger.info(f"[进度更新] {next_task.name}: {completion * 100:.1f}%")

                            if completion >= 1.0:
                                logger.info(f"✅ Drop完成!")
                                current_drop_completed = True
                                break

                    if current_drop_completed:
                        break

                    # 检查主播是否还在线
                    for i in range(kick_pool.streamers.qsize()):
                        streamer = kick_pool.streamers.get(block=False)
                        if streamer.streamer_name.lower() == next_task.selected_streamer:
                            if not streamer.online:
                                logger.info(f"[主播下线] {next_task.selected_streamer} 已下线,切换任务")
                                kick_pool.streamers.put(streamer)
                                break
                            kick_pool.streamers.put(streamer)
                            break
                        kick_pool.streamers.put(streamer)
                    else:
                        # 主播下线,退出监控循环
                        break

                # 一轮结束,重新生成队列
                logger.info("\n[轮次结束] 重新生成队列...")

            except Exception as e:
                logger.info(f"[错误] {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)


def logic_run():
    config_oauth = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ"

    slug_list = ['omni', 'oilrats', 'agustabell212', 'coconutb', 'welyn', 'templetaps', 'posty', 'trainwreckstv',
                 'lifestomper', 'qaixx', 'picco', 'panpots', 'hutnik', 'serwinter', 'dilanzito', 'spoonkid', 'winnie',
                 'mendo', 'hjune', 'blazed', 'ricoy', 'xqc']
    kick_pool = KickPool(config_oauth=config_oauth, streamers_list=slug_list)
    kick_client = KickClientPool()

    event_loop_list = [kick_pool.run(), kick_client.run_complete_flow(kick_pool)]
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(event_loop_list))


async def main():
    config_oauth = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ"

    streamers_list = ['omni', 'oilrats', 'agustabell212', 'coconutb', 'welyn', 'templetaps', 'posty', 'trainwreckstv',
                 'lifestomper', 'qaixx', 'picco', 'panpots', 'hutnik', 'serwinter', 'dilanzito', 'spoonkid', 'winnie',
                 'mendo', 'hjune', 'blazed', 'ricoy', 'xqc']
    #streamers_list = ['dilanzito']
    kick_pool = KickPool(config_oauth, streamers_list)
    kick_client = KickClientPool(oauth=config_oauth)

    # Done init account
    accounts = []
    for line in lines[75:200]:
        # oauth = line.strip().split(",")[3]
        # username = line.strip().split(",")[0]
        # username = line.strip().split(",")[0]
        username,pwd,opt_code,session_token,email,em_pwd,xsrf_token,client_id,accesstoken = line.strip().split(",")
        accounts.append(KickAccount(username=username, password=pwd, session_token=session_token, opt_code=opt_code))
    kick_client.kick_accounts = accounts

    # 启动自动观看
    loop = asyncio.get_running_loop()
    # 仅在 Windows 上执行此操作
    logger.info(platform.system())
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop.create_task(kick_pool.run())
    await kick_client.run_auto_drops_watcher(kick_pool)





if __name__ == "__main__":
    ws_pool = ThreadPoolExecutor(max_workers=1024)
    # loop_main = asyncio.get_event_loop()
    # loop_main.run_until_complete()
    asyncio.run(main())
