"""
Kick.com 直播平台请求链模拟代码
根据 example1.saz 自动生成

使用方法:
    python kick_automation.py --channel serwinter

依赖:
    pip install requests
"""
import base64
import os
import threading
import urllib

import m3u8
import requests
import json
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import rqsession


import re
from typing import List

import websocket
from rqsession import EnhancedRequestSession

from browser_forge_tmp import BrowserClient, Chrome119


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
    print(resp.headers)
    print(resp.text)
    data = resp.json()
    return data


class KickClient:
    """Kick.com 客户端 - 模拟完整请求链"""
    
    def __init__(self, cookies: Optional[Dict[str, str]] = None):
        """
        初始化客户端
        
        Args:
            cookies: 认证Cookie字典 (需要21个Cookie)
        """
        #self.session = requests.Session()
        self.session = rqsession.EnhancedRequestSession(
            rust_backend_url="http://127.0.0.1:5005"
        )

        # 设置通用请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Authorization': 'Bearer 290087940|ZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ',
            'Origin': 'https://kick.com',
            'Referer': 'https://kick.com/',
            'sec-ch-ua': '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Cookie': 'USER_LOCALE=en; __stripe_mid=c9d16fe5-18aa-4f48-949c-55c544e47e198f440b; XSRF-TOKEN=eyJpdiI6IlNjeGUyYU1MQ1BnUnEyb3ZWM3pRMmc9PSIsInZhbHVlIjoiOUp3d1VtcERGN3BSeWNHMEJONUR0cEgwNG9kZTJQZ1pONzJqZ3U1UlNYYXFtZDRDd2RKV3VreW93ekhXak5EVmZPS0NheDBqOUJnKzVUQ2drSCsxL1QwQjFxZVkyWUlXcUtNWjdSVlkwT01iS2NaVzRxRnhBeHVqaVlwNURMKzIiLCJtYWMiOiI5N2E5MmVmNzVkYzVmMWYxOGNhY2RkYjBhZmEzODE1MWE3MTI4MjgxZjcxOWE0NjAyZjYwZTQwMDA3ZTA5NDk3IiwidGFnIjoiIn0%3D; kick_session=eyJpdiI6ImpoSTRBYzN0bE1wQkVRTHIvM0YvVnc9PSIsInZhbHVlIjoiTEM5L2k5ZW14b3BuUDVmUGlnQmFWVTU4ZkQvVENLTUdSeUI3Kzc1TWJIdWN2UTlqNGd3ZFNCSXRGN2F3Q00yVW9zL1VmKzJQNVBIV1ozS3I3aEdYczBDbG12TklXU3ExQ0wvYmJGMmQzTE9aRmFDU2RIUEdQVGt5ZEJ5Mk50N0UiLCJtYWMiOiJiMzVlZWY2NTg2NzIzMTQ5ZjY1ZDA3MzY5YThiNWIyZGM2YjFlZjdiNWRiMWYyYzliMGU0NWRlMjdhODBjZDE0IiwidGFnIjoiIn0%3D; HOFY3aEOalzCKoIXg7qUVJ0NhPauqw0pbnPDS3mJ=eyJpdiI6Iis3czdocEFzc0dzemVrMkJXY3FBS1E9PSIsInZhbHVlIjoiUWZoVml5MXpWdWpDZW9KSzltSEFkMTY2T1pwK3RFcW1IdkVTVlYyVVhvS0l1VE5yaEZYYnRvWExqNWhzNXArb3JpMkVYMVh1dkNQRm0wQXY3QWNPdDM3QTdFRWlRNWFjWHBUOEs2MThQL2pocGNyWnBRUDVFbG1NQjhSbThWVUZueHdtUEozSFFtRitBVzZUS3crdjc3aWlvdm5YR21JNUxRb3c5T3Z4citDTjhnVUF3emx6VmRva2NHOWpCcXZTOFVRb1huckoyVE5MMVA1UEJ2K3JtVGt6NEFqSlNoQUF5NVAyclJ6cXpsb2JrbHd4SHY0ZDdZczg2VnhuMkN6SXNVVGFCNGFXdHVrUGc0YVlmMU1vK2xrN1d5K0VDdjhYbUkxZDVpNjNObTlTbFZ4RE10eDFOV255M0JFQnhVeWQ1SXpRcHV6cXB5WUtwNm9wV1hSaHpJNHBUcW13SXpCNFpwVlQwOG9DREkrTGZ6MEd6NVlpL0x3cmFFVEhiK2F2Yng1K2hCejZlZGJLVDVkTVFKRTJRQmNVc0l4V2tueHAvRnVpYUVrZW5OdUdIamF6SldRWWl5WlRrV2F4V2ZETVE2aGlzRHdaNWszL0diL2MvbEYrSlNvUUgzN1FWUlViRTdhSkZBOEVjNGorMm1YVENScnU0dWxmSWVIbDBFUHkiLCJtYWMiOiIwMTY5MDE4YmFhZDFjMjc2NTAwOGU5YmZjMDQxMDBlYTZiZGM2MmZlNjk0YTAyNTYxYjM0ZDJlNzhjMjZjZTA3IiwidGFnIjoiIn0%3D; session_token=290087940%7CZvaEORzZ2jrvfeR7wCe9lYQ5Dze5wJ4IvkAFIERZ; cookie_preferences_set_v1=%7B%22state%22%3A%7B%22preferences%22%3A%7B%22necessary%22%3Atrue%2C%22functional%22%3Atrue%2C%22performance%22%3Atrue%2C%22targeting%22%3Atrue%2C%22userHasMadeChoice%22%3Atrue%7D%2C%22functionalEnabled%22%3Atrue%2C%22performanceEnabled%22%3Atrue%2C%22targetingEnabled%22%3Atrue%7D%2C%22version%22%3A0%7D; _gcl_au=1.1.153574574.1762047950; _ga=GA1.1.1903246644.1762047950; _iidt=SY2Z6gDYpZMC5shHrtadg7aRJoNI6zwUyosBaedgJ1V6q8EXwl73dx9EgKIrmOr+N+9/AczP5oaeNGMdz137hBnfKY5ukzFz9o0JHts=; _cfuvid=APvvoiVMfLvNxO7ekUgLHIKd7jH46HbVQdgdhKQaTHo-1763551109499-0.0.1.1-604800000; __stripe_sid=0930339d-5d85-4ae7-9a73-e86539601933fc66d1; cf_clearance=zlx6Mf_NQZmA7d7fEReiJDv56bZw421tcU7SlBzEcJ4-1763563935-1.2.1.1-dODkZ3XbtOf_rxE75Tr9tKBFz3JAoyYbV2I0w0rMRqaK5.jUkJx4L0LXomf9CoP3pvBsYjGSc_AbCZ.UeGER.5jvczHr1rrOhfbBPw5p.qPqiRncwpV1UluoscbWZUVnTaYy5i9ztR4ogHfPJtT5c0Tx8qOADIHRgp3IPZzrHb56O0C1PG6Vw1bofC4Lv1q1YZkvihpnKydibqmHXkpGIeZiho4OB1TU6iHqkfFr99U; _ga_YS2DLSGQ53=GS2.1.s1763560751$o32$g1$t1763563937$j60$l0$h1074758248; __cf_bm=5OXHAHPpYiJ9pqcLg1Dvp4Yiy5EyLXKaGtCBWrV9c60-1763564946-1.0.1.1-qzQh75NNnf7rGXCiHinymtvRI9OgRyhsCJ4A3OiQ6CrnsIIWd.giJW4iXPIjzAPMrncR.R_jhATQkyAKAgNCemR2KfmRE0ecHP4dCSwYb2Y'
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
    
    def step_1_load_channel_page(self, channel_slug: str) -> Dict:
        """
        Session #560 - 加载频道主页
        
        Args:
            channel_slug: 频道名称 (例如: serwinter)
            
        Returns:
            包含频道信息的字典
        """
        print(f"[步骤1] 加载频道主页: {channel_slug}")
        
        self.channel_slug = channel_slug
        url = f"https://kick.com/{channel_slug}"
        
        try:
            response = self.session.get(url)
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
    
    
    def step_2_get_followed_channels(self) -> Dict:
        """
        Session #564 - 获取关注的频道列表
        
        Returns:
            关注的频道列表
        """
        print("[步骤2] 获取关注列表")
        
        url = "https://kick.com/api/v2/channels/followed"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            print(f"  ✓ 获取成功: {len(data.get('channels', []))} 个频道")
            return data
            
        except Exception as e:
            print(f"  ✗ 获取失败: {e}")
            return {'status': 'error', 'error': str(e)}
    
    
    def step_3_get_chatroom_info(self) -> Dict:
        """
        Session #583 - 获取聊天室信息
        
        Returns:
            聊天室配置信息
        """
        print("[步骤3] 获取聊天室信息")
        
        url = f"https://kick.com/api/v2/channels/{self.channel_slug}/chatroom"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            # 提取关键信息
            self.chatroom_id = data.get('id')
            print(f"  ✓ 聊天室ID: {self.chatroom_id}")
            
            return data
            
        except Exception as e:
            print(f"  ✗ 获取失败: {e}")
            return {'status': 'error', 'error': str(e)}
    
    
    def step_4_get_user_identity(self) -> Dict:
        """
        Session #584 - 获取当前用户在频道的身份
        
        Returns:
            用户身份信息
        """
        print("[步骤4] 获取用户身份")
        
        url = f"https://kick.com/api/v2/channels/{self.channel_slug}/me"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            print(f"  ✓ 用户身份获取成功")
            return data
            
        except Exception as e:
            print(f"  ✗ 获取失败: {e}")
            return {'status': 'error', 'error': str(e)}
    
    
    def step_5_get_silenced_users(self) -> Dict:
        """
        Session #585 - 获取禁言用户列表
        
        Returns:
            禁言用户列表
        """
        print("[步骤5] 获取禁言用户")
        
        url = "https://kick.com/api/v2/silenced-users"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            print(f"  ✓ 获取成功")
            return data
            
        except Exception as e:
            print(f"  ✗ 获取失败: {e}")
            return {'status': 'error', 'error': str(e)}
    
    
    def step_6_parallel_load_channel_data(self) -> Dict:
        """
        Session #586-595 - 并行加载频道各类数据
        
        包括: 视频、表情、观众数、排行榜、投票、用户徽章、频道目标
        
        Returns:
            所有数据的汇总
        """
        print("[步骤6] 并行加载频道数据")
        
        results = {}
        
        # 6.1 视频列表
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/videos"
            response = self.session.get(url)
            results['videos'] = response.json() if response.ok else None
            print(f"  ✓ 视频列表")
        except Exception as e:
            print(f"  ✗ 视频列表失败: {e}")
            results['videos'] = None
        
        # 6.2 表情包
        try:
            url = f"https://kick.com/emotes/{self.channel_slug}"
            response = self.session.get(url)
            results['emotes'] = response.json() if response.ok else None
            print(f"  ✓ 表情包")
        except Exception as e:
            print(f"  ✗ 表情包失败: {e}")
            results['emotes'] = None
        
        # 6.3 当前观众数 (需要频道ID)
        if self.chatroom_id:
            try:
                url = f"https://kick.com/current-viewers?ids[]={self.chatroom_id}"
                response = self.session.get(url)
                results['viewers'] = response.json() if response.ok else None
                print(f"  ✓ 观众数")
            except Exception as e:
                print(f"  ✗ 观众数失败: {e}")
                results['viewers'] = None
        
        # 6.4 排行榜
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/leaderboards"
            response = self.session.get(url)
            results['leaderboards'] = response.json() if response.ok else None
            print(f"  ✓ 排行榜")
        except Exception as e:
            print(f"  ✗ 排行榜失败: {e}")
            results['leaderboards'] = None
        
        # 6.5 投票
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/polls"
            response = self.session.get(url)
            results['polls'] = response.json() if response.ok else None
            print(f"  ✓ 投票")
        except Exception as e:
            print(f"  ✗ 投票失败: {e}")
            results['polls'] = None
        
        # 6.6 频道目标
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/goals"
            response = self.session.get(url)
            results['goals'] = response.json() if response.ok else None
            print(f"  ✓ 频道目标")
        except Exception as e:
            print(f"  ✗ 频道目标失败: {e}")
            results['goals'] = None
        
        return results
    
    
    def step_7_get_global_settings(self) -> Dict:
        """
        Session #598 - 获取全局设置
        
        Returns:
            全局配置
        """
        print("[步骤7] 获取全局设置")
        
        url = "https://kick.com/api/internal/settings/global"
        
        try:
            response = self.session.get(url)
            
            if response.status_code == 304:
                print(f"  ✓ 使用缓存 (304)")
                return {'status': 'cached'}
            
            response.raise_for_status()
            data = response.json()
            print(f"  ✓ 获取成功")
            return data
            
        except Exception as e:
            print(f"  ✗ 获取失败: {e}")
            return {'status': 'error', 'error': str(e)}
    
    
    # ========================================================================
    # 阶段2: 服务初始化
    # ========================================================================
    def _iter_connect_frames(self, response, chunk_size: int = 1024):
        """
        解析 Connect/gRPC 风格的 streaming 响应帧:
        每帧结构: 1字节 flags + 4字节大端 length + length 字节 payload
        payload 为 JSON 文本
        """
        buffer = b""
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            buffer += chunk

            # 循环消费 buffer 中已经凑齐的帧
            while True:
                if len(buffer) < 5:
                    # 还不够一个头
                    break
                flags = buffer[0]
                length = int.from_bytes(buffer[1:5], "big")
                if len(buffer) < 5 + length:
                    # 还没收完这一帧
                    break

                payload = buffer[5:5 + length]
                buffer = buffer[5 + length:]

                yield flags, payload

    def step_8_connect_feature_flags(self) -> Dict:
        """
        Session #612 - 连接功能标志服务 (EventStream)

        使用 Connect 协议的 streaming POST:
        请求帧: 1字节 flags(0) + 4字节长度(2) + "{}"
        响应帧: 1字节 flags + 4字节长度 + JSON payload
        """
        print("[步骤8] 连接功能标志服务")

        url = "https://flags.kick.com/flagd.evaluation.v1.Service/EventStream"

        # 只强制与 Connect 协议相关的头，其它 UA / sec-ch-* 等交给你的 EnhancedRequestSession 去伪造
        headers = {
            "accept": "*/*",
            "content-type": "application/connect+json",
            "connect-protocol-version": "1",
            "Origin": "https://kick.com",
            "Referer": "https://kick.com/",
        }

        # 与浏览器 fetch 的 body 对齐: "\u0000\u0000\u0000\u0000\u0002{}"
        # = flags(0x00) + length(0x00000002) + "{}"
        body = b"\x00\x00\x00\x00\x02{}"

        try:
            # 用你的 EnhancedRequestSession 建立 streaming POST
            resp = self.session.post(
                url,
                headers=headers,
                data=body,
                stream=True,
                timeout=30,  # 可按需调整
            )
            resp.raise_for_status()

            print("  ✓ EventStream 连接成功, 开始读取事件...")

            events = []
            start_ts = time.time()

            # 防止脚本被这个长连接一直卡住，只读一小段时间/若干条事件
            max_events = 10
            max_seconds = 20

            for flags, payload in self._iter_connect_frames(resp):
                try:
                    text = payload.decode("utf-8", errors="ignore")
                    evt = json.loads(text)
                except Exception as e:
                    print(f"  ✗ 解析帧失败 flags={flags}: {e!r}")
                    continue

                evt_type = evt.get("type")
                print(f"  → 收到事件: type={evt_type}, data={evt.get('data')}")
                events.append(evt)

                if evt_type == "provider_ready":
                    print("  ✓ provider_ready - 特性开关服务已就绪")

                # 退出条件：达到数量或时间上限
                if len(events) >= max_events:
                    print("  ⚠ 已达到最大事件数, 停止读取")
                    break
                if time.time() - start_ts > max_seconds:
                    print("  ⚠ 已达到最大读取时间, 停止读取")
                    break

            try:
                resp.close()
            except Exception:
                pass

            return {
                "status": "ok",
                "events_count": len(events),
                "events": events,
            }

        except Exception as e:
            print(f"  ✗ 连接失败: {e}")
            return {"status": "error", "error": str(e)}

    def step_9_get_chatroom_rules(self) -> Dict:
        """
        Session #619 - 获取聊天室规则
        
        Returns:
            聊天室规则列表
        """
        print("[步骤9] 获取聊天室规则")
        
        url = f"https://kick.com/api/v2/channels/{self.channel_slug}/chatroom/rules"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            rules_count = len(data.get('rules', []))
            print(f"  ✓ 规则数量: {rules_count}")
            return data
            
        except Exception as e:
            print(f"  ✗ 获取失败: {e}")
            return {'status': 'error', 'error': str(e)}
    
    
    # ========================================================================
    # 阶段3: Web API数据加载
    # ========================================================================
    
    def step_10_load_web_api_data(self) -> Dict:
        """
        Session #620-624 - 加载web.kick.com的API数据
        
        Returns:
            所有Web API数据的汇总
        """
        print("[步骤10] 加载Web API数据")
        
        results = {}
        base_url = "https://web.kick.com/api/v1"
        
        # 10.1 推荐直播
        try:
            url = f"{base_url}/livestreams/featured"
            response = self.session.get(url)
            results['featured'] = response.json() if response.ok else None
            print(f"  ✓ 推荐直播")
        except Exception as e:
            print(f"  ✗ 推荐直播失败: {e}")
            results['featured'] = None
        
        # 10.2 聊天历史
        if self.chatroom_id:
            try:
                url = f"{base_url}/chat/{self.chatroom_id}/history"
                response = self.session.get(url)
                results['chat_history'] = response.json() if response.ok else None
                print(f"  ✓ 聊天历史")
            except Exception as e:
                print(f"  ✗ 聊天历史失败: {e}")
                results['chat_history'] = None
        
        # 10.3 用户会话
        try:
            url = f"{base_url}/user/session"
            response = self.session.get(url)
            results['user_session'] = response.json() if response.ok else None
            print(f"  ✓ 用户会话")
        except Exception as e:
            print(f"  ✗ 用户会话失败: {e}")
            results['user_session'] = None
        
        # 10.4 掉落活动
        try:
            url = f"{base_url}/drops/campaigns/livestream"
            response = self.session.get(url)
            results['drops'] = response.json() if response.ok else None
            print(f"  ✓ 掉落活动")
        except Exception as e:
            print(f"  ✗ 掉落活动失败: {e}")
            results['drops'] = None
        
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
    # 阶段4: 广播认证
    # ========================================================================
    
    def step_11_broadcasting_auth(self) -> Dict:
        """
        Session #628-630 - 广播服务认证
        
        实际会进行3次认证请求
        
        Returns:
            认证结果
        """
        print("[步骤11] 广播服务认证")
        
        url = "https://kick.com/broadcasting/auth"
        results = []
        
        # 进行3次认证 (根据原始请求链)
        for i in range(3):
            try:
                response = self.session.post(url)
                
                if response.ok:
                    data = response.json()
                    results.append(data)
                    print(f"  ✓ 认证 {i+1}/3 成功")
                else:
                    print(f"  ✗ 认证 {i+1}/3 失败: {response.status_code}")
                    results.append(None)
                    
            except Exception as e:
                print(f"  ✗ 认证 {i+1}/3 失败: {e}")
                results.append(None)
            
            # 短暂延迟
            time.sleep(0.1)
        
        return {'auth_results': results}
    
    
    # ========================================================================
    # 阶段5: WebSocket连接
    # ========================================================================
    
    def step_12_get_websocket_token(self) -> Optional[str]:
        """
        Session #660 - 获取WebSocket连接token
        
        Returns:
            WebSocket token或None
        """
        print("[步骤12] 获取WebSocket Token")
        
        url = "https://websockets.kick.com/viewer/v1/token"
        
        try:
            #response = self.session.get(url)
            #response = self.session.get(url)
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
    
    
    def step_13_connect_websocket(self, token: str) -> Dict:
        """
        Session #665 - 建立WebSocket连接
        
        注意: 需要websocket库支持,这里只是示例
        
        Args:
            token: WebSocket token
            
        Returns:
            连接状态
        """
        print("[步骤13] 建立WebSocket连接")
        
        # WebSocket连接需要特殊库 (websocket-client)
        # 这里只是展示URL构造
        ws_url = f"wss://websockets.kick.com/viewer/v1/connect?token={token}"
        
        print(f"  ⚠ WebSocket连接需要专门的库")
        print(f"  连接URL: {ws_url}")
        print(f"  建议使用: pip install websocket-client")
        self.connect_kick_viewer_ws(token=token)
        
        # 实际连接代码示例:
        # import websocket
        # ws = websocket.create_connection(ws_url)
        # message = ws.recv()
        # ws.close()
        
        return {
            'status': 'info',
            'ws_url': ws_url,
            'message': 'WebSocket连接需要额外的库支持'
        }


    def connect_kick_viewer_ws(self, channel_id: int, token: str, livestream_id: int):
        # 有些 token 里可能有 + / = 等字符，保险起见做 URL 编码
        #encoded_token = urllib.parse.quote(token, safe="")
        encoded_token = token

        ws_url = (
            f"wss://websockets.kick.com/viewer/v1/connect?"
            f"token={encoded_token}"
        )

        # 生成方式示例
        random_bytes = os.urandom(16)
        websocket_key = base64.b64encode(random_bytes).decode()
        print(websocket_key)  # 每次都不同


        # 头尽量贴近浏览器，后面你可以根据抓包再细调
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://kick.com",
            "Pragma": "no-cache",
            # "host": "websockets.kick.com",
            # "connection": "upgrade",
            # "Cache-Control": "no-cache",
            # "sec-websocket-extensions": "permessage-deflate; client_max_window_bits",
            # "sec-websocket-key": websocket_key, #"QY/Gu7SPzGksZMNhqehoOA==",
            # "sec-websocket-version": "13",
            # "upgrade": "websocket"
        }

        # 每次连接都应该生成新的 key
        def generate_ws_key():
            return base64.b64encode(os.urandom(16)).decode()

        ws = websocket.create_connection(
            ws_url,
            header=headers
        )

        print("[+] WebSocket connected")
        # ========= 开始接收服务器推送 =========
        # 暂时只打印收到的消息，后面再从这里面找 socket_id
        for i in range(6000):
            try:
                ws.send(json.dumps({"type": "ping"}))
                print(">> Sent ping")
                time.sleep(5)
                print(f"i: {i}")
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
                    print(">> Sent handshake:", handshake_msg)
                    time.sleep(0.1)
                    living_event = json.dumps({"type":"user_event","data":{"message":{"name":"tracking.user.watch.livestream","channel_id":channel_id,"livestream_id":livestream_id}}})
                    print(f">> Sent tracking event: {living_event}")
                    ws.send(living_event)

                msg = ws.recv()
                print("<<", msg)
            except Exception as e:
                print(e)

        wss_1 = "wss://ws-mt1.pusher.com/app/73aa60a071d0943a6b3e?protocol=7&client=js&version=8.4.0&flash=false"
        wss_2 = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
        wss_3 = "wss://ws-us3.pusher.com/app/dd11c46dae0376080879?protocol=7&client=js&version=8.4.0&flash=false"

    # ========================================================================
    # 完整流程执行
    # ========================================================================
    def run_complete_flow(self, channel_slug: str) -> Dict:
        """
        执行完整的请求链流程
        
        Args:
            channel_slug: 频道名称
            
        Returns:
            所有步骤的结果汇总
        """
        print("\n" + "="*80)
        print(f"开始执行完整请求链: {channel_slug}")
        print("="*80 + "\n")
        
        results = {}
        
        # 阶段1: 主页面加载
        print("\n【阶段1: 主页面加载】")
        print("-" * 80)
        results['stage1'] = {}
        results['stage1']['main_page'] = self.step_1_load_channel_page(channel_slug)
        channel_id = results['stage1']['main_page']['channel_id']
        time.sleep(0.5)

        # TODO post访问
        client = BrowserClient(
            Chrome119,
            proxy="http://127.0.0.1:7890"
        )
        #resp =self.session.post(results['stage1']['main_page']['m3u8_url'][0])
        m3u8_url = results['stage1']['main_page']['m3u8_url'][0]

        resp = client.get(m3u8_url, headers={
            "accept": "application/x-mpegURL, application/vnd.apple.mpegurl, application/json, text/plain",
            "Referer": "https://kick.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
        })
        # 初始化时的m3u8总分配链接
        init_m3u8_obj = m3u8.M3U8(resp.text)

        if not init_m3u8_obj.is_variant:
            print("不知标准m3u8")
        else:
            print("标准m3u8")
        # 解析的不同清晰度的局部总链接
        variants = []
        for playlist in init_m3u8_obj.playlists:
            print(playlist.uri)
            variant_url = playlist.uri
            resolution = playlist.stream_info.resolution
            variants.append((variant_url, resolution))
        print("len(variants)")
        print(len(variants))
        if variants:
            lowest_resolution_variant = min(variants, key=lambda x: x[1])
            # lowest_resolution_variant = variants[1]
            channel_url = lowest_resolution_variant[0]
            print("选择清晰度最低的频道")
            print("访问呢完毕")
        else:
            return {}

        segment_list = self.session.get(channel_url).text
        pattern = r'(https://[^\s\n]+\.ts(?:\?[^\s\n]+)?)'

        # 解析出的对应, 每个连接的最近片段访问文件地址
        if isinstance(segment_list, str):
            ts_now = re.findall(pattern, segment_list)[::2]
            # 这里优化，减小内存、ts数量折半
            if isinstance(ts_now, list) and len(ts_now) == 0:
                # 处理为 0 的情况
                print("匹配mp4格式数据")
                mp4_pattern = r'(https://[^\s\n]+\.mp4(?:\?[^\s\n]+)?)'
                ts_now = re.findall(mp4_pattern, segment_list)

        # 正常访问segment url
        resp = self.session.get(ts_now[-1])
        print(f"正常访问片段：{resp.status_code}")
        # 必须要访问一次ts206，得到206响应才行
        # ts 206 segement
        #ts206 = segment_list[-2]
        ts206 = segment_list.split("#EXT-X-PREFETCH:")[-2].strip()
        print(ts206)
        resp = self.session.get(ts206, headers={
            "range": "bytes=0-32766",
            "Referer": "https://kick.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
        })
        print(f"访问ts206片段：{resp.status_code}")

        data = self.step_12_get_websocket_token()

        # TODO 建立websocket
        videos_data = live_videos(name=channel_slug)
        for raw in videos_data:
            if 'is_live' in raw and raw["is_live"]:
                print("直播")
                living_stream_id = raw['id']
                self.connect_kick_viewer_ws(channel_id=channel_id, token=data, livestream_id=living_stream_id)



        self.session.get("https://global.poe.live-video.net/")




        results['stage1']['followed'] = self.step_2_get_followed_channels()
        time.sleep(0.2)
        
        results['stage1']['chatroom'] = self.step_3_get_chatroom_info()
        time.sleep(0.2)
        
        results['stage1']['identity'] = self.step_4_get_user_identity()
        time.sleep(0.2)
        
        results['stage1']['silenced'] = self.step_5_get_silenced_users()
        time.sleep(0.2)
        
        results['stage1']['channel_data'] = self.step_6_parallel_load_channel_data()
        time.sleep(0.2)
        
        results['stage1']['settings'] = self.step_7_get_global_settings()
        
        # 阶段2: 服务初始化
        print("\n【阶段2: 服务初始化】")
        print("-" * 80)
        results['stage2'] = {}
        results['stage2']['feature_flags'] = self.step_8_connect_feature_flags()
        time.sleep(0.2)
        
        results['stage2']['rules'] = self.step_9_get_chatroom_rules()
        
        # 阶段3: Web API数据
        print("\n【阶段3: Web API数据加载】")
        print("-" * 80)
        results['stage3'] = {}
        results['stage3']['web_api'] = self.step_10_load_web_api_data()
        
        # 阶段4: 广播认证
        print("\n【阶段4: 广播认证】")
        print("-" * 80)
        results['stage4'] = {}
        results['stage4']['auth'] = self.step_11_broadcasting_auth()
        
        # 阶段5: WebSocket连接
        print("\n【阶段5: WebSocket连接】")
        print("-" * 80)
        results['stage5'] = {}
        token = self.step_12_get_websocket_token()
        
        if token:
            results['stage5']['websocket'] = self.step_13_connect_websocket(token)
        else:
            results['stage5']['websocket'] = {'status': 'error', 'error': 'No token'}
        
        print("\n" + "="*80)
        print("请求链执行完成!")
        print("="*80 + "\n")
        
        return results


# ============================================================================
# 主函数 - 命令行入口
# ============================================================================

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Kick.com 请求链模拟工具')
    parser.add_argument('--channel', type=str, default='serwinter',
                        help='频道名称 (默认: serwinter)')
    parser.add_argument('--cookies-file', type=str,
                        help='Cookie文件路径 (JSON格式)')
    
    args = parser.parse_args()
    
    # 加载Cookie
    cookies = None
    if args.cookies_file:
        try:
            with open(args.cookies_file, 'r') as f:
                cookies = json.load(f)
            print(f"✓ 已加载Cookie: {len(cookies)} 个")
        except Exception as e:
            print(f"✗ Cookie加载失败: {e}")
            print("  继续执行 (可能会因为认证失败)")
    else:
        print("⚠ 未提供Cookie文件,部分请求可能失败")
        print("  提示: 使用 --cookies-file cookies.json 提供认证信息")
    
    # 创建客户端
    client = KickClient(cookies=cookies)
    
    # 执行完整流程
    results = client.run_complete_flow(args.channel)
    
    # 保存结果
    output_file = f"kick_{args.channel}_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✓ 结果已保存到: {output_file}")
    except Exception as e:
        print(f"\n✗ 结果保存失败: {e}")


if __name__ == '__main__':
    main()
