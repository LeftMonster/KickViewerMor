"""
Kick.com 直播平台请求链模拟代码
根据 example1.saz 自动生成

使用方法:
    python kick_automation.py --channel serwinter

依赖:
    pip install requests
"""
import copy
import json
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

from browser_forge_tmp import BrowserClient, Chrome120


class KickClient:
    """Kick.com 客户端 - 模拟完整请求链"""

    def __init__(self, cookies: Optional[Dict[str, str]] = None):
        """
        初始化客户端
        
        Args:
            cookies: 认证Cookie字典 (需要21个Cookie)
        """
        # 使用你自己的 TLS 指纹模拟客户端 (curl_cffi + 自定义 TLS)
        # profile = Chrome120()  # 你也可以换成自己封装的其它 profile
        profile = copy.deepcopy(Chrome120)  # 你也可以换成自己封装的其它 profile
        self.session = BrowserClient(
            profile=profile,
            proxy=None,
            randomize_tls=False,
            impersonate=None,
            verify=True,
        )

        # 统一额外请求头：后面每次请求都用 headers=self.common_headers 传进去
        self.common_headers = {
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
        }

        # 如果提供了Cookie,设置到 session（BrowserClient 内部是 curl_cffi.Session）
        if cookies:
            self.session.cookies.update(cookies)

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
            response = self.session.get(url, headers=self.common_headers)
            response.raise_for_status()

            # 从HTML中提取频道信息 (实际需要解析HTML)
            # 这里简化处理,假设从响应中提取
            print(f"  ✓ 主页加载成功: {response.status_code}")

            # 注意: 实际需要从HTML中解析这些值
            # 这里使用示例值
            return {
                'status': 'success',
                'html_length': len(response.text)
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
            response = self.session.get(url, headers=self.common_headers)
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
            response = self.session.get(url, headers=self.common_headers)
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
            response = self.session.get(url, headers=self.common_headers)
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
            response = self.session.get(url, headers=self.common_headers)
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
            response = self.session.get(url, headers=self.common_headers)
            results['videos'] = response.json() if response.ok else None
            print(f"  ✓ 视频列表")
        except Exception as e:
            print(f"  ✗ 视频列表失败: {e}")
            results['videos'] = None

        # 6.2 表情包
        try:
            url = f"https://kick.com/emotes/{self.channel_slug}"
            response = self.session.get(url, headers=self.common_headers)
            results['emotes'] = response.json() if response.ok else None
            print(f"  ✓ 表情包")
        except Exception as e:
            print(f"  ✗ 表情包失败: {e}")
            results['emotes'] = None

        # 6.3 当前观众数 (需要频道ID)
        if self.chatroom_id:
            try:
                url = f"https://kick.com/current-viewers?ids[]={self.chatroom_id}"
                response = self.session.get(url, headers=self.common_headers)
                results['viewers'] = response.json() if response.ok else None
                print(f"  ✓ 观众数")
            except Exception as e:
                print(f"  ✗ 观众数失败: {e}")
                results['viewers'] = None

        # 6.4 排行榜
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/leaderboards"
            response = self.session.get(url, headers=self.common_headers)
            results['leaderboards'] = response.json() if response.ok else None
            print(f"  ✓ 排行榜")
        except Exception as e:
            print(f"  ✗ 排行榜失败: {e}")
            results['leaderboards'] = None

        # 6.5 投票
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/polls"
            response = self.session.get(url, headers=self.common_headers)
            results['polls'] = response.json() if response.ok else None
            print(f"  ✓ 投票")
        except Exception as e:
            print(f"  ✗ 投票失败: {e}")
            results['polls'] = None

        # 6.6 频道目标
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel_slug}/goals"
            response = self.session.get(url, headers=self.common_headers)
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
            response = self.session.get(url, headers=self.common_headers)

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

    def step_8_connect_feature_flags(self, max_events: int = 5, max_seconds: float = 10.0) -> Dict:
        """
        Session #612 - 连接功能标志服务 (EventStream)

        这里只做“短时间监听”：
        - 发起 POST (application/connect+json)
        - 保持连接，读取几条事件预览后主动退出
        """
        print("[步骤8] 连接功能标志服务 (EventStream)")

        url = "https://flags.kick.com/flagd.evaluation.v1.Service/EventStream"

        # 浏览器抓到的 body: \u0000\u0000\u0000\u0000\u0002{}
        body = b"\x00\x00\x00\x00\x02{}"

        headers = self.common_headers.copy()
        headers.update({
            "Accept": "*/*",
            "Content-Type": "application/connect+json",
            "connect-protocol-version": "1",
            # 这个接口是 same-site 而不是 same-origin
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        })

        events = []
        start = time.time()
        buffer = ""

        try:
            resp = self.session.post(
                url,
                data=body,
                headers=headers,
                stream=True,  # 关键：保持流
                timeout=30,
            )
            resp.raise_for_status()
            print("  ✓ EventStream 连接建立成功，开始读取事件 ...")

            for chunk in resp.iter_content(chunk_size=None):
                if chunk is None:
                    continue

                # 解码 + 把 NUL 替换成换行，方便切分
                buffer += chunk.decode("utf-8", errors="ignore")
                buffer = buffer.replace("\x00", "\n")

                # 按行拆分，最后一段可能是不完整 JSON，保留到下一轮
                *lines, buffer = buffer.split("\n")

                for line in lines:
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        evt = json.loads(line)
                        events.append(evt)
                        print(f"  ▹ 收到事件: {evt.get('type')}")
                    except json.JSONDecodeError:
                        # 不完整 / 噪声就丢掉
                        continue

                # 只预览前 max_events 个事件，或者超过 max_seconds 就停
                if len(events) >= max_events or (time.time() - start) > max_seconds:
                    print("  ⏹ 达到预览上限，主动结束监听")
                    break

            # 主动关闭底层连接
            try:
                resp.close()
            except Exception:
                pass

            return {
                "status": "success",
                "event_count": len(events),
                "events_preview": events,
            }

        except Exception as e:
            print(f"  ✗ 功能标志流连接失败: {e}")
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
            response = self.session.get(url, headers=self.common_headers)
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
            response = self.session.get(url, headers=self.common_headers)
            results['featured'] = response.json() if response.ok else None
            print(f"  ✓ 推荐直播")
        except Exception as e:
            print(f"  ✗ 推荐直播失败: {e}")
            results['featured'] = None

        # 10.2 聊天历史
        if self.chatroom_id:
            try:
                url = f"{base_url}/chat/{self.chatroom_id}/history"
                response = self.session.get(url, headers=self.common_headers)
                results['chat_history'] = response.json() if response.ok else None
                print(f"  ✓ 聊天历史")
            except Exception as e:
                print(f"  ✗ 聊天历史失败: {e}")
                results['chat_history'] = None

        # 10.3 用户会话
        try:
            url = f"{base_url}/user/session"
            response = self.session.get(url, headers=self.common_headers)
            results['user_session'] = response.json() if response.ok else None
            print(f"  ✓ 用户会话")
        except Exception as e:
            print(f"  ✗ 用户会话失败: {e}")
            results['user_session'] = None

        # 10.4 掉落活动
        try:
            url = f"{base_url}/drops/campaigns/livestream"
            response = self.session.get(url, headers=self.common_headers)
            results['drops'] = response.json() if response.ok else None
            print(f"  ✓ 掉落活动")
        except Exception as e:
            print(f"  ✗ 掉落活动失败: {e}")
            results['drops'] = None

        # 10.5 排行榜
        if self.chatroom_id:
            try:
                url = f"{base_url}/kicks/{self.chatroom_id}/leaderboard"
                response = self.session.get(url, headers=self.common_headers)
                results['leaderboard'] = response.json() if response.ok else None
                print(f"  ✓ Kicks排行榜")
            except Exception as e:
                print(f"  ✗ Kicks排行榜失败: {e}")
                results['leaderboard'] = None

        return results

    # ========================================================================
    # 阶段4: 广播认证
    # ========================================================================

    def step_11_broadcasting_auth(self, socket_id: Optional[str] = None) -> Dict:
        """
        Session #628-630 - 广播服务认证
        
        实际会进行3次认证请求
        
        Returns:
            认证结果
        """
        print("[步骤11] 广播服务认证")

        url = "https://kick.com/broadcasting/auth"
        results = []

        # 如果没传 socket_id，为了让整个流程能跑通，先用抓包里的示例值

        if socket_id is None:
            # 实战建议：从 WebSocket 握手 (Pusher 等) 中拿到真实 socket_id 传进来
            socket_id = "799565.700994"

            # channel_name 一般就是 private-{chatroom_id}
        channel_name = (
            f"private-{self.chatroom_id}"
            if self.chatroom_id
            else "private-84789239"
        )

        payload = {
            "socket_id": socket_id,
            "channel_name": channel_name,
        }

        # 进行3次认证 (根据原始请求链)
        for i in range(3):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self.common_headers,
                )

                if response.ok:
                    data = response.json()
                    results.append(data)
                    print(f"  ✓ 认证 {i + 1}/3 成功, auth 前缀: {str(data.get('auth', ''))[:16]}...")
                else:
                    print(f"  ✗ 认证 {i + 1}/3 失败: {response.status_code}")
                    results.append(None)
            except Exception as e:
                print(f"  ✗ 认证 {i + 1}/3 失败: {e}")
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
            response = self.session.get(url, headers=self.common_headers)
            response.raise_for_status()
            data = response.json()

            token = data.get('token')
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
        print("\n" + "=" * 80)
        print(f"开始执行完整请求链: {channel_slug}")
        print("=" * 80 + "\n")

        results = {}

        # 阶段1: 主页面加载
        print("\n【阶段1: 主页面加载】")
        print("-" * 80)
        results['stage1'] = {}
        results['stage1']['main_page'] = self.step_1_load_channel_page(channel_slug)
        time.sleep(0.5)

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

        print("\n" + "=" * 80)
        print("请求链执行完成!")
        print("=" * 80 + "\n")

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
