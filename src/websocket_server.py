"""
WebSocketサーバー - SDVX用リアルタイムデータ配信
"""
import asyncio
import websockets
import json
import time
from typing import Set
import logging
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning, message='coroutine.*was never awaited')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='Enable tracemalloc.*')

try:
    from src.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class DataWebSocketServer:
    """リアルタイムデータ配信用WebSocketサーバー"""

    def __init__(self, port: int = 8767):
        self.port = port
        self.clients: Set = set()
        self.server = None
        self.loop = None
        self.heartbeat_task = None

        # 各ページ用の最新データ（接続時の初期配信に使用）
        self.cursong_data       = None
        self.today_results_data = None
        self.vf_data            = None
        self.stats_data         = None
        self.nowplaying_data    = None

    # ── 接続管理 ─────────────────────────────────────────────────────────────

    async def register_client(self, websocket):
        """クライアントを登録し、最新データを初期配信"""
        self.clients.add(websocket)
        logger.info(f"クライアント接続: {websocket.remote_address}, 総{len(self.clients)}件")

        await websocket.send(json.dumps({'type': 'hello', 'time': time.time()}))
        await self._send_latest(websocket)

    async def _send_latest(self, websocket, requested_type: str | None = None):
        """指定クライアントへ保持中の最新データを送る。"""
        latest_data = [
            ('cursong',       self.cursong_data),
            ('today_results', self.today_results_data),
            ('vf',            self.vf_data),
            ('stats',         self.stats_data),
            ('nowplaying',     self.nowplaying_data),
        ]

        for type_, data in latest_data:
            if requested_type and type_ != requested_type:
                continue
            if data is not None:
                try:
                    await websocket.send(json.dumps({'type': type_, 'data': data}))
                except Exception:
                    pass

    async def unregister_client(self, websocket):
        """クライアントを登録解除"""
        self.clients.discard(websocket)
        try:
            logger.info(f"クライアント切断: {websocket.remote_address}, 総{len(self.clients)}件")
        except Exception:
            logger.info(f"クライアント切断: 総{len(self.clients)}件")

    async def handler(self, websocket):
        """WebSocket接続ハンドラ"""
        try:
            await self.register_client(websocket)
            async for message in websocket:
                try:
                    data = json.loads(message)
                except Exception:
                    continue
                if data.get('type') == 'request_latest':
                    await self._send_latest(websocket, data.get('target'))
                elif data.get('type') == 'ping':
                    await websocket.send(json.dumps({'type': 'pong', 'time': time.time()}))
        except websockets.exceptions.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"ハンドラーエラー: {e}")
        finally:
            await self.unregister_client(websocket)

    # ── ブロードキャスト（async） ─────────────────────────────────────────────

    async def _broadcast(self, type_: str, data: dict):
        """全クライアントにデータを送信"""
        if self.clients:
            msg = json.dumps({'type': type_, 'data': data})
            clients = list(self.clients)
            results = await asyncio.gather(
                *[c.send(msg) for c in clients],
                return_exceptions=True
            )
            for client, result in zip(clients, results):
                if isinstance(result, Exception):
                    self.clients.discard(client)

    async def _heartbeat_loop(self):
        """OBSブラウザソースの stale connection を検出しやすくするための死活通知。"""
        try:
            while True:
                await asyncio.sleep(10)
                await self._broadcast('heartbeat', {'time': time.time()})
        except asyncio.CancelledError:
            pass

    async def _broadcast_cursong(self, data: dict):
        self.cursong_data = data
        await self._broadcast('cursong', data)

    async def _broadcast_today_results(self, data: dict):
        self.today_results_data = data
        await self._broadcast('today_results', data)

    async def _broadcast_vf(self, data: dict):
        self.vf_data = data
        await self._broadcast('vf', data)

    async def _broadcast_stats(self, data: dict):
        self.stats_data = data
        await self._broadcast('stats', data)

    async def _broadcast_nowplaying(self, data: dict):
        self.nowplaying_data = data
        await self._broadcast('nowplaying', data)

    # ── サーバー制御 ─────────────────────────────────────────────────────────

    def start(self, loop=None):
        """サーバーを開始"""
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        async def _start():
            self.server = await websockets.serve(
                self.handler,
                'localhost',
                self.port,
                ping_interval=10,
                ping_timeout=10,
            )
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info(f"WebSocketサーバー起動: ポート {self.port}")

        asyncio.run_coroutine_threadsafe(_start(), loop)

    def stop(self):
        """サーバーを停止"""
        if self.server and self.loop:
            async def _stop():
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                    await asyncio.gather(self.heartbeat_task, return_exceptions=True)
                    self.heartbeat_task = None
                if self.clients:
                    await asyncio.gather(
                        *[ws.close() for ws in self.clients.copy()],
                        return_exceptions=True
                    )
                self.server.close()
                await self.server.wait_closed()
                logger.info("WebSocketサーバー停止")

            try:
                asyncio.run_coroutine_threadsafe(_stop(), self.loop).result(timeout=5.0)
            except Exception as e:
                logger.error(f"サーバー停止エラー: {e}")

    # ── 同期メソッド（UIスレッドから呼ぶ） ───────────────────────────────────

    def update_cursong_data(self, data: dict):
        """現在曲データを更新して配信"""
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_cursong(data), self.loop
            )

    def update_today_results_data(self, data: dict):
        """今日のリザルトデータを更新して配信"""
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_today_results(data), self.loop
            )

    def update_vf_data(self, data: dict):
        """VFランキングデータを更新して配信"""
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_vf(data), self.loop
            )

    def update_stats_data(self, data: dict):
        """統計データを更新して配信"""
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_stats(data), self.loop
            )

    def update_nowplaying_data(self, data: dict):
        """曲決定画面の楽曲情報を更新して配信"""
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_nowplaying(data), self.loop
            )
