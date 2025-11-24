"""
KickClientPool 扩展方法
直接添加到你的 KickClientPool 类中
"""


# ========== 添加到 KickClientPool 类中的方法 ==========

async def run_auto_drops_watcher(self, kick_pool):
    """
    自动Drops观看器 - 主循环

    使用方法:
    在你的 KickClientPool 类中添加这个方法,然后:

    await kick_client.run_auto_drops_watcher(kick_pool)
    """
    from drops_priority_manager import DropsPriorityManager
    from kick.viewer_chain import async_progress, drops_parser

    manager = DropsPriorityManager()
    current_ws_connections = None  # WebSocket连接列表

    while True:
        try:
            # ===== 步骤1: 查询进度并生成队列 =====
            print("\n[队列更新] 查询drops进度...")

            # 采样查询
            sample_size = max(10, len(self.kick_accounts) // 10)
            sample_accounts = self.kick_accounts[:sample_size]

            tasks = [async_progress(acc.session_token) for acc in sample_accounts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 解析
            drops_list = []
            for result in results:
                if not isinstance(result, Exception):
                    drops_list.extend(drops_parser(result, slug={self.choose_game_slug}))

            # 聚合
            drop_stats = manager.aggregate_progress(drops_list)

            # ===== 步骤2: 获取在线主播 =====
            online_streamers = {}
            temp_queue = []

            for i in range(kick_pool.streamers.qsize()):
                streamer = kick_pool.streamers.get(block=False)
                temp_queue.append(streamer)

                if streamer.online:
                    cid = getattr(streamer, 'channel_id', None)
                    lid = getattr(streamer, 'livestream_id', None)
                    if cid and lid:
                        online_streamers[streamer.streamer_name.lower()] = (cid, lid)

            # 放回队列
            for s in temp_queue:
                kick_pool.streamers.put(s)

            print(f"[在线检测] {len(online_streamers)} 个主播在线")

            # ===== 步骤3: 生成优先级队列 =====
            queue = manager.generate_queue(drop_stats, online_streamers)

            if not queue:
                print("[警告] 没有可用的drops,等待5分钟后重试")
                await asyncio.sleep(300)
                continue

            # 显示队列
            print(f"\n[优先级队列] 共 {len(queue)} 个drops:")
            for i, task in enumerate(queue[:5], 1):
                status = "🟢在线" if task.channel_id else "🔴离线"
                print(f"  {i}. [{status}] {task.name} - "
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
                print(f"\n[注意] 优先主播不在线,等待5分钟后重试")
                await asyncio.sleep(300)
                continue

            # ===== 步骤5: 检查是否已完成 =====
            if next_task.completion_rate >= 1.0:
                print(f"✅ Drop已完成: {next_task.name}")
                # 从队列移除并继续下一个
                continue

            # ===== 步骤6: 建立连接 =====
            print(f"\n[开始观看] {next_task.name}")
            print(f"  主播: {next_task.selected_streamer}")
            print(f"  进度: {next_task.avg_progress:.0f}/{next_task.required_units}分钟")
            print(f"  完成度: {next_task.completion_rate * 100:.1f}%")

            # 获取tokens
            token_list = await self.get_websocket_token()

            # 关闭旧连接 (如果有)
            if current_ws_connections:
                # TODO: 实现关闭逻辑
                pass

            # 建立新连接 (所有账号看同一个主播)
            await self.connect_kick_viewer_ws(
                channel_id=next_task.channel_id,
                token_list=token_list,
                livestream_id=next_task.livestream_id
            )

            # ===== 步骤7: 监控循环 =====
            check_interval = 600  # 10分钟检查一次

            for check_count in range(6):  # 最多观看1小时
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

                        print(f"[进度更新] {next_task.name}: {completion * 100:.1f}%")

                        if completion >= 1.0:
                            print(f"✅ Drop完成!")
                            current_drop_completed = True
                            break

                if current_drop_completed:
                    break

                # 检查主播是否还在线
                for i in range(kick_pool.streamers.qsize()):
                    streamer = kick_pool.streamers.get(block=False)
                    if streamer.streamer_name.lower() == next_task.selected_streamer:
                        if not streamer.online:
                            print(f"[主播下线] {next_task.selected_streamer} 已下线,切换任务")
                            kick_pool.streamers.put(streamer)
                            break
                        kick_pool.streamers.put(streamer)
                        break
                    kick_pool.streamers.put(streamer)
                else:
                    # 主播下线,退出监控循环
                    break

            # 一轮结束,重新生成队列
            print("\n[轮次结束] 重新生成队列...")

        except Exception as e:
            print(f"[错误] {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(60)


# ========== 使用示例 ==========

"""
在你的主程序中:

async def main():
    # 初始化
    kick_pool = KickPool(oauth, streamers_list)
    kick_client = KickClientPool(oauth=oauth)
    kick_client.kick_accounts = your_accounts
    kick_client.choose_game_slug = 'rust'

    # 启动自动观看
    await kick_client.run_auto_drops_watcher(kick_pool)

asyncio.run(main())
"""