import base64
import os
import socket

import m3u8
import requests
import json
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import rqsession


import re
from typing import List

import socks
import websocket
from anyio import sleep
from rqsession import EnhancedRequestSession

from browser_forge import BrowserClient, Chrome119, Chrome120
from parser.tmp.data_acc import lines


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


def live_videos(oauth: str = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ", name: str = None):
    url = "https://kick.com/api/v2/channels/{}/videos".format(name)
    session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

    authorization = "Bearer {}".format(oauth)
    session.headers['Authorization'] = authorization
    resp = session.get(url)
    print(resp.status_code)
    # print(resp.headers)
    # print(resp.text)
    data = resp.json()
    return data


class KickClient:
    """Kick.com 客户端 - 模拟完整请求链"""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None, oauth: str = None, username: str = None, channel_id: str = None, living_stream_id: str = None):
        """
        初始化客户端
        
        Args:
            cookies: 认证Cookie字典 (需要21个Cookie)
        """
        #self.session = requests.Session()
        self.username = username
        self.session = rqsession.EnhancedRequestSession(
            rust_backend_url="http://127.0.0.1:5005"
        )

        self.oauth = oauth
        self.channel_id = channel_id
        self.living_stream_id = living_stream_id

        # 设置通用请求头
        self.session.headers.update({
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
        })
        
        # 如果提供了Cookie,设置到session
        if cookies:
            self.session.cookies.update(cookies)
        
        # 存储提取的数据
        self.channel_id = None
        self.chatroom_id = None
        self.user_id = None
        self.channel_slug = None
        

    def _iter_connect_frames(self, response, chunk_size: int = 1024):
        """
        解析 Connect/gRPC 风格的 streaming 响应帧:
        每帧结构: 1字节 flags + 4字节大端 length + length 字节 payload (JSON 文本)
        """
        buffer = b""
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            buffer += chunk

            while True:
                # 至少要有 1( flags ) + 4( length ) 字节
                if len(buffer) < 5:
                    break

                flags = buffer[0]
                length = int.from_bytes(buffer[1:5], "big")

                # 数据还没收全
                if len(buffer) < 5 + length:
                    break

                payload = buffer[5:5 + length]
                buffer = buffer[5 + length:]

                yield flags, payload


    # ========================================================================
    # 阶段1: 主页面加载
    # ========================================================================

    @staticmethod
    def step_1_load_channel_page(oauth: str, channel_slug: str) -> Dict:
        """
        Session #560 - 加载频道主页
        
        Args:
            channel_slug: 频道名称 (例如: serwinter)
            
        Returns:
            包含频道信息的字典
        """
        print(f"[步骤1] 加载频道主页: {channel_slug}")

        url = f"https://kick.com/{channel_slug}"
        
        try:
            session = rqsession.EnhancedRequestSession(
                rust_backend_url="http://127.0.0.1:5005"
            )
            # 设置通用请求头
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Authorization': 'Bearer {}'.format(oauth),
                'Origin': 'https://kick.com',
                'Referer': 'https://kick.com/',
                'sec-ch-ua': '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            })

            response = session.get(url)
            response.raise_for_status()
            
            # 从HTML中提取频道信息 (实际需要解析HTML)
            # 这里简化处理,假设从响应中提取
            print(f"  ✓ 主页加载成功: {response.status_code}")
            
            # 注意: 实际需要从HTML中解析这些值
            # 这里使用示例值

            m3u8_url = extract_m3u8_urls(response.text)
            channel_id = extract_channel_id(response.text)

            return {
                'status': 'success',
                'html_length': len(response.text),
                'm3u8_url': m3u8_url,
                'channel_id': int(channel_id),
            }
            
        except Exception as e:
            print(f"  ✗ 主页加载失败: {e}")
            return {'status': 'error', 'error': str(e)}

    # ========================================================================
    # 阶段5: WebSocket连接
    # ========================================================================
    
    def establish_websocket(self) -> Optional[str]:
        """
        Session #660 - 获取WebSocket连接token
        
        Returns:
            WebSocket token或None
        """
        print("[步骤12] 获取WebSocket Token")
        
        url = "https://websockets.kick.com/viewer/v1/token"
        
        try:
            client = BrowserClient(
                Chrome119,
                proxy="http://127.0.0.1:7890"
            )
            headers = self.session.headers
            headers["x-client-token"] = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
            response = client.get(url, headers=headers)
            response.raise_for_status()
            token = response.json()['data']['token']
            
            #token = data.get('token')
            if token:
                print(f"  ✓ Token获取成功: {token[:20]}...")
                return token
            else:
                print(f"  ✗ 响应中没有token")
                return None
                
        except Exception as e:
            print(f"  ✗ Token获取失败: {e}")
            return None
    

    def connect_kick_viewer_ws(self, channel_id: int, token: str, livestream_id: int):
        # 有些 token 里可能有 + / = 等字符，保险起见做 URL 编码
        #encoded_token = urllib.parse.quote(token, safe="")
        encoded_token = token
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 7890)
        socket.socket = socks.socksocket

        ws_url = (
            f"wss://websockets.kick.com/viewer/v1/connect?"
            f"token={encoded_token}"
        )

        # 生成方式示例
        random_bytes = os.urandom(16)
        websocket_key = base64.b64encode(random_bytes).decode()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://kick.com",
            "Pragma": "no-cache",
        }

        # 每次连接都应该生成新的 key
        def generate_ws_key():
            return base64.b64encode(os.urandom(16)).decode()

        ws = websocket.create_connection(
            ws_url,
            header=headers,
            timeout=5
        )

        print("[+] WebSocket connected")
        # ========= 开始接收服务器推送 =========
        # 暂时只打印收到的消息，后面再从这里面找 socket_id
        for i in range(72000):
            try:
                ws.send(json.dumps({"type": "ping"}))
                # print(">> Sent ping")
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
                    print(f"i: {i}")
                    print(">> Sent handshake:", handshake_msg)
                    time.sleep(0.1)
                    living_event = json.dumps({"type":"user_event","data":{"message":{"name":"tracking.user.watch.livestream","channel_id":channel_id,"livestream_id":livestream_id}}})
                    print(f">> Sent tracking event: {living_event}--{self.username}")
                    ws.send(living_event, opcode=websocket.ABNF.OPCODE_TEXT)

                msg = ws.recv()
                # print("<<", msg)
            except websocket.WebSocketTimeoutException:
                print("发送超时")
                raise
            except websocket.WebSocketConnectionClosedException:
                print("连接已关闭")
                raise
            except Exception as e:
                print(e)
                raise

        wss_1 = "wss://ws-mt1.pusher.com/app/73aa60a071d0943a6b3e?protocol=7&client=js&version=8.4.0&flash=false"
        wss_2 = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
        wss_3 = "wss://ws-us3.pusher.com/app/dd11c46dae0376080879?protocol=7&client=js&version=8.4.0&flash=false"

    def live_videos(self, name: str = None):
        """
        主播名
        """
        url = "https://kick.com/api/v2/channels/{}/videos".format(name)
        session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

        authorization = "Bearer {}".format(self.oauth)
        session.headers['Authorization'] = authorization
        resp = session.get(url)
        print(resp.status_code)
        print(resp.headers)
        print(resp.text)
        data = resp.json()
        return data
    def progress(self, name: str = None):
        """
        主播名
        """
        url = "https://web.kick.com/api/v1/drops/progress"
        session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

        authorization = "Bearer {}".format(self.oauth)
        session.headers['Authorization'] = authorization
        resp = session.get(url)
        print(resp.status_code)
        print(resp.headers)
        print(resp.text)
        data = resp.json()
        return data
    def all_campaigns(self, name: str = None):
        """
        主播名
        """
        url = "https://web.kick.com/api/v1/drops/campaigns"
        session = EnhancedRequestSession(rust_backend_url="http://127.0.0.1:5005")

        authorization = "Bearer {}".format(self.oauth)
        session.headers['Authorization'] = authorization
        resp = session.get(url)
        print(resp.status_code)
        print(resp.headers)
        print(resp.text)
        data = resp.json()
        return data

    def load_web_api_data(self) -> Dict:
        """
        Session #620-624 - 加载web.kick.com的API数据

        Returns:
            所有Web API数据的汇总
        """
        print("[步骤10] 加载Web API数据")

        results = {}
        base_url = "https://web.kick.com/api/v1"

        # 10.5 排行榜
        if self.chatroom_id:
            try:
                url = f"{base_url}/kicks/{self.chatroom_id}/leaderboard"
                response = self.session.get(url)
                results['leaderboard'] = response.json() if response.ok else None
                print(f"  ✓ Kicks排行榜")
            except Exception as e:
                print(f"  ✗ Kicks排行榜失败: {e}")
                results['leaderboard'] = None

        return results

    # ========================================================================
    # 完整流程执行
    # ========================================================================
    def run_complete_flow(self, channel_slug: str, channel_id: str, living_stream_id: str) -> Dict:
        """
        执行完整的请求链流程
        
        Args:
            channel_slug: 频道名称
            
        Returns:
            所有步骤的结果汇总
        """
        data = self.establish_websocket()
        # Done!! 建立websocket
        self.connect_kick_viewer_ws(channel_id=channel_id, token=data, livestream_id=living_stream_id)
        return {}


def main(oauth, username, channel_id, living_stream_id, channel_slug):
    """
    将会有n个用户、很多，我想同时让他们都运行这个main逻辑，各个用户有自己的oauth、
    """
    cookies = None
    # channel_slug = "serwinter"
    # channel_slug = "winnie"
    # 创建客户端
    client = KickClient(cookies=cookies, oauth=oauth, username=username, channel_id=channel_id, living_stream_id=living_stream_id)
    # 执行完整流程
    while True:
        try:
            client.run_complete_flow(channel_slug=channel_slug, channel_id=channel_id, living_stream_id=living_stream_id)
        except Exception as e:
            print(e)


class StreamRoundRobin:


if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pool = ThreadPoolExecutor(max_workers=100)
    futures = []
    channel_id = ""
    living_stream_id = ""
    streamer_name = "winnie"
    config_oauth = "290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ"
    results = {}

    # 阶段1: 主页面加载
    print("\n【阶段1: 主页面加载】")
    print("-" * 80)
    results['stage1'] = {}
    results['stage1']['main_page'] = KickClient.step_1_load_channel_page(oauth=config_oauth, channel_slug=streamer_name)
    channel_id = results['stage1']['main_page']['channel_id']
    time.sleep(0.1)
    videos_data = live_videos(name=streamer_name)
    for raw in videos_data:
        if 'is_live' in raw and raw["is_live"]:
            print("直播")
            living_stream_id = raw['id']
    for line in lines[:100]:
        oauth = line.strip().split(",")[3]
        username = line.strip().split(",")[0]
        future = pool.submit(main, oauth=oauth, username=username, channel_id=channel_id, living_stream_id=living_stream_id, channel_slug=streamer_name)
        futures.append(future)

    # 等待所有任务完成并获取结果
    results = []
    for future in as_completed(futures):
        try:
            result = future.result()
            results.append(result)
        except Exception as e:
            print(f"Task failed: {e}")

