"""WindowsゲームウィンドウをPIL Imageとして直接取得する。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PIL import Image, ImageGrab
from PySide6.QtGui import QGuiApplication, QImage

from src.config import Config
from src.logger import get_logger

logger = get_logger(__name__)

_LANDSCAPE_SIZE = (1920, 1080)
_PORTRAIT_SIZE = (1080, 1920)


class DirectWindowCapture:
    """指定exe/タイトルのウィンドウをQtのgrabWindowで取得する薄いラッパー。"""

    def __init__(self, config: Config):
        self.config = config
        self.hwnd: int | None = None
        self.last_error = ""
        self._next_error_log_at = 0.0

    def set_config(self, config: Config) -> None:
        self.config = config
        self.hwnd = None
        self.last_error = ""

    def read_frame(self) -> Image.Image | None:
        if not sys.platform.startswith("win"):
            self.last_error = "直接取得はWindows専用です"
            return None

        hwnd = self._ensure_window()
        if not hwnd:
            return None

        try:
            x, y, width, height = self._client_geometry(hwnd)
            if width <= 0 or height <= 0:
                self.last_error = "対象ウィンドウのクライアント領域を取得できません"
                self.hwnd = None
                return None

            image = self._grab_client_area(hwnd, x, y, width, height)
            if image is None:
                self.last_error = "対象ウィンドウの画像取得に失敗しました"
                self.hwnd = None
                return None

            return self._normalize_size(image)
        except Exception as e:
            self.last_error = str(e)
            self.hwnd = None
            self._log_error("直接キャプチャエラー: %s", e)
            return None

    def _ensure_window(self) -> int | None:
        if self.hwnd and self._is_window_usable(self.hwnd):
            return self.hwnd

        self.hwnd = self._find_target_window()
        if not self.hwnd:
            exe = self.config.direct_capture_exe
            title = self.config.direct_capture_title
            self.last_error = f"対象ウィンドウが見つかりません: {exe} / {title}"
            self._log_error(self.last_error)
        else:
            self.last_error = ""
            logger.info("直接キャプチャ対象を検出: hwnd=%s", self.hwnd)
        return self.hwnd

    def _find_target_window(self) -> int | None:
        user32 = ctypes.windll.user32
        enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        target_exe = self.config.direct_capture_exe.strip().casefold()
        target_title = self.config.direct_capture_title.strip().casefold()
        found: list[int] = []

        def callback(hwnd, _lparam):
            if not self._is_window_usable(hwnd):
                return True

            title = self._window_text(hwnd)
            if target_title and target_title not in title.casefold():
                return True

            exe_name = self._window_process_name(hwnd)
            if target_exe and exe_name.casefold() != target_exe:
                return True

            found.append(int(hwnd))
            return False

        user32.EnumWindows(enum_windows_proc(callback), 0)
        return found[0] if found else None

    def _is_window_usable(self, hwnd: int) -> bool:
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return False
        if user32.IsIconic(hwnd):
            return False
        return bool(self._window_text(hwnd).strip())

    def _window_text(self, hwnd: int) -> str:
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _window_process_name(self, hwnd: int) -> str:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return ""

        process_query_limited_information = 0x1000
        handle = kernel32.OpenProcess(process_query_limited_information, False, process_id.value)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return ""
            return buffer.value.rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)

    def _client_geometry(self, hwnd: int) -> tuple[int, int, int, int]:
        user32 = ctypes.windll.user32
        client_rect = wintypes.RECT()
        window_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            return 0, 0, 0, 0
        if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
            return 0, 0, 0, 0

        client_origin = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            return 0, 0, 0, 0

        x = client_origin.x - window_rect.left
        y = client_origin.y - window_rect.top
        width = client_rect.right - client_rect.left
        height = client_rect.bottom - client_rect.top
        return x, y, width, height

    def _client_screen_bbox(self, hwnd: int) -> tuple[int, int, int, int] | None:
        user32 = ctypes.windll.user32
        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            return None

        top_left = wintypes.POINT(client_rect.left, client_rect.top)
        bottom_right = wintypes.POINT(client_rect.right, client_rect.bottom)
        if not user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
            return None
        if not user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
            return None
        return top_left.x, top_left.y, bottom_right.x, bottom_right.y

    def _grab_client_area(self, hwnd: int, x: int, y: int, width: int, height: int) -> Image.Image | None:
        bbox = self._client_screen_bbox(hwnd)
        if bbox is not None:
            try:
                return ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")
            except Exception as e:
                self._log_error("ImageGrabで直接キャプチャできませんでした: %s", e)

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None

        pixmap = screen.grabWindow(hwnd, x, y, width, height)
        if pixmap.isNull():
            return None
        return self._qimage_to_pil(pixmap.toImage())

    def _qimage_to_pil(self, image: QImage) -> Image.Image:
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        width = image.width()
        height = image.height()
        stride = image.bytesPerLine()
        data = image.constBits().tobytes()
        return Image.frombytes("RGB", (width, height), data, "raw", "RGB", stride).copy()

    def _normalize_size(self, image: Image.Image) -> Image.Image:
        target_size = _LANDSCAPE_SIZE if image.width >= image.height else _PORTRAIT_SIZE
        if image.size == target_size:
            return image
        return image.resize(target_size, Image.Resampling.LANCZOS)

    def _log_error(self, message: str, *args) -> None:
        now = time.monotonic()
        if now < self._next_error_log_at:
            return
        self._next_error_log_at = now + 30.0
        logger.error(message, *args)
