"""Debug result-screen mode recognition.

Reads result screenshots and dumps the detected screen mode as JSON Lines.
Default targets are the normal-score and EX-score debug result folders.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

import imagehash

from src.define import HASH_RESULT_MODE_SCORE, RECT_RESULT_MODE
from src.result_image import RESULT_INFO_CROP_SIZE, expand_result_info_area
from src.screen_reader import ScreenReader
from src.songinfo import SongDatabase


DEFAULT_PATTERNS = (
    "debug/cut/*",
    "debug/exscore/*",
)


def _enum_name(value: Any) -> str | None:
    return getattr(value, "name", None)


def _detect_file(reader: ScreenReader, path: str) -> dict[str, Any]:
    with Image.open(path) as img:
        input_size = img.size
        screen = (
            expand_result_info_area(img) if img.size == RESULT_INFO_CROP_SIZE else img
        )
        reader.update_screen(screen)
        mode = reader.detect_screen()

        item: dict[str, Any] = {
            "file": path,
            "input_size": list(input_size),
            "expanded_result_info_area": input_size == RESULT_INFO_CROP_SIZE,
            "detect_mode": _enum_name(mode),
            "is_result_screen": mode.is_result_screen(),
        }

        if reader.corrected_screen is not None:
            item["corrected_size"] = list(reader.corrected_screen.size)

        if mode.is_result_screen():
            img2 = reader.corrected_screen
            if img2 is not None:
                score_display_mode = reader._detect_result_score_display_mode(img2)
                item["score_display_mode"] = _enum_name(score_display_mode)
                item["is_exscore_mode"] = mode == type(mode).result_exscore
                mode_hash = imagehash.average_hash(img2.crop(RECT_RESULT_MODE))
                item["result_mode_hash"] = str(mode_hash)
                if HASH_RESULT_MODE_SCORE is not None:
                    item["result_mode_score_hash_distance"] = int(
                        abs(mode_hash - HASH_RESULT_MODE_SCORE)
                    )
                try:
                    result = reader.read_from_result() or {}
                    item["title"] = result.get("title")
                    item["difficulty"] = str(result.get("difficulty"))
                    item["score"] = result.get("score")
                    item["exscore"] = result.get("exscore")
                    item["lamp"] = str(result.get("lamp"))
                except Exception as exc:
                    item["read_result_error"] = str(exc)

        return item


def _iter_files(patterns: list[str]) -> list[str]:
    files: list[str] = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        if matched:
            files.extend(matched)
        elif Path(pattern).exists():
            files.append(pattern)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="*",
        default=list(DEFAULT_PATTERNS),
        help="Image files or glob patterns to inspect.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Dump one pretty-printed JSON array instead of JSON Lines.",
    )
    args = parser.parse_args(argv)

    files = _iter_files(args.paths)
    if not files:
        print("No target images found.", file=sys.stderr)
        return 1

    reader = ScreenReader(SongDatabase())
    rows = [_detect_file(reader, path) for path in files]

    if args.pretty:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
