"""Utilities for saved result screenshots."""
from __future__ import annotations

from PIL import Image


RESULT_FULL_SIZE = (1080, 1920)
RESULT_INFO_CROP_RECT = (0, 786, 1080, 1650)
RESULT_INFO_CROP_SIZE = (1080, 864)


def crop_result_info_area(img: Image.Image) -> Image.Image:
    """Return the result information area used for compact saved images."""
    if img.size == RESULT_INFO_CROP_SIZE:
        return img.copy()
    if img.size == RESULT_FULL_SIZE:
        return img.crop(RESULT_INFO_CROP_RECT).copy()
    return img.copy()


def expand_result_info_area(img: Image.Image) -> Image.Image:
    """Restore a compact result image to the normal 1080x1920 coordinate space."""
    if img.size != RESULT_INFO_CROP_SIZE:
        return img.copy()

    mode = img.mode
    if mode == 'P':
        img = img.convert('RGB')
        mode = img.mode

    background = (0, 0, 0, 0) if mode == 'RGBA' else 0 if mode == 'L' else (0, 0, 0)
    full = Image.new(mode, RESULT_FULL_SIZE, background)
    full.paste(img, (RESULT_INFO_CROP_RECT[0], RESULT_INFO_CROP_RECT[1]))
    return full
