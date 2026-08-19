"""スマホ向けスコア閲覧HTTPサーバ。"""

from __future__ import annotations

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.logger import get_logger

logger = get_logger(__name__)


class MobileScoreHTTPServer:
    """ResultDatabase の内容をLAN内ブラウザへ配信する軽量HTTPサーバ。"""

    def __init__(self, result_database, host: str = "0.0.0.0", port: int = 8787):
        self.result_database = result_database
        self.host = host
        self.port = int(port)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self):
        if self.httpd is not None:
            return

        handler = self._make_handler()
        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as e:
            logger.error(f"スマホ向けHTTPサーバ起動失敗: {self.host}:{self.port} {e}")
            self.httpd = None
            return

        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="MobileScoreHTTPServer",
            daemon=True,
        )
        self.thread.start()
        logger.info(f"スマホ向けHTTPサーバ起動: http://{self.host}:{self.port}/")

    def stop(self):
        if self.httpd is None:
            return
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception as e:
            logger.error(f"スマホ向けHTTPサーバ停止エラー: {e}")
        finally:
            self.httpd = None
            self.thread = None
            logger.info("スマホ向けHTTPサーバ停止")

    def _make_handler(self):
        result_database = self.result_database

        class Handler(BaseHTTPRequestHandler):
            server_version = "SDVXHelperMobileHTTP/1.0"

            def log_message(self, format, *args):
                logger.debug("HTTP " + format, *args)

            def do_GET(self):
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                query = parse_qs(parsed.query)

                try:
                    if path == "/" or path == "/index.html":
                        self._send_file(Path("template") / "mobile_score_viewer.html")
                    elif path.startswith("/api/"):
                        self._handle_api(path, query)
                    elif path.startswith("/jackets/"):
                        self._send_file(Path("jackets") / Path(path).name)
                    elif path.startswith("/resources/"):
                        self._send_file(Path("resources") / Path(path).name)
                    else:
                        self._send_error(HTTPStatus.NOT_FOUND, "not found")
                except Exception as e:
                    logger.error(f"スマホ向けHTTPリクエストエラー: {e}")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error")

            def _handle_api(self, path: str, query: dict[str, list[str]]):
                if path == "/api/folders":
                    self._send_json(result_database.get_mobile_folders_data())
                    return
                if path.startswith("/api/folders/level/"):
                    level_text = path.rsplit("/", 1)[-1]
                    self._send_json(result_database.get_mobile_level_folder_data(int(level_text)))
                    return
                if path == "/api/folders/vf":
                    self._send_json(result_database.get_mobile_vf_folder_data())
                    return
                if path == "/api/folders/current":
                    self._send_json(result_database.get_mobile_current_folder_data())
                    return
                if path == "/api/history":
                    limit = int((query.get("limit") or ["200"])[0])
                    offset = int((query.get("offset") or ["0"])[0])
                    self._send_json(result_database.get_mobile_history_data(limit, offset))
                    return
                if path.startswith("/api/charts/"):
                    chart_id = path.rsplit("/", 1)[-1]
                    data = result_database.get_mobile_chart_detail_data(chart_id)
                    if data is None:
                        self._send_error(HTTPStatus.NOT_FOUND, "chart not found")
                    else:
                        self._send_json(data)
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "api not found")

            def _send_json(self, data: dict):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_file(self, path: Path):
                if not path.exists() or not path.is_file():
                    self._send_error(HTTPStatus.NOT_FOUND, "file not found")
                    return
                body = path.read_bytes()
                content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                if path.suffix.lower() == ".html":
                    content_type = "text/html; charset=utf-8"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_error(self, status: HTTPStatus, message: str):
                body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
