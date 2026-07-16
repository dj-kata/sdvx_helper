"""Debug result-screen mode recognition.

Reads debug screenshots and dumps the detected screen mode as JSON Lines.
Default targets are the detect, normal-score, and EX-score debug folders.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image

import imagehash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.define import (
    HASH_RESULT_EXSCORE,
    HASH_RESULT_MODE_SCORE,
    HASH_RESULT_SCORE_LARGE,
    HASH_RESULT_SCORE_SMALL,
    RECT_RESULT_EXSCORE,
    RECT_RESULT_EXSCORE_EXMODE,
    RECT_RESULT_MODE,
    RECT_RESULT_SCORE_EXMODE,
    RECT_RESULT_SCORE_LARGE,
    RECT_RESULT_SCORE_SMALL,
)
from src.classes import detect_mode
from src.result_image import RESULT_INFO_CROP_SIZE, expand_result_info_area
from src.screen_reader import ScreenReader
from src.songinfo import SongDatabase
from src.summary_generator import (
    _generate_from_items_sync,
    capture_summary_item_from_screen,
)


# デフォルトで読み込まれる入力画像を指定
DEFAULT_PATTERNS = (
    "debug/detect/*",
    "debug/cut/*",
    "debug/exscore/*",
)

SELECT_IMAGE_TARGETS = {
    "jacket_img": "select_jacket.png",
    "whole_img": "select_whole.png",
    "title_img": "select_title.png",
    "lv_img": "select_level.png",
    "diff_img": "select_difficulty.png",
    "bpm_img": "select_bpm.png",
    "ef_img": "select_effector.png",
    "illust_img": "select_illustrator.png",
}


def _enum_name(value: Any) -> str | None:
    return getattr(value, "name", None)


def _nearest_digit_debug(
    img: Image.Image, rects: list, hash_dict: dict
) -> dict[str, Any]:
    digits = []
    distances = []
    for rect in rects:
        h = imagehash.average_hash(img.crop(rect))
        dists = {
            k: int(abs(h - tmpl_hash))
            for k, tmpl_hash in hash_dict.items()
            if tmpl_hash is not None
        }
        if dists:
            best_digit = min(dists, key=dists.get)
            best_distance = dists[best_digit]
        else:
            best_digit = "?"
            best_distance = None
        digits.append(str(best_digit))
        distances.append(best_distance)
    return {"digits": "".join(digits), "distances": distances}


def _save_select_images(data: dict[str, Any], out_dir: Path = Path("out")) -> list[str]:
    out_dir.mkdir(exist_ok=True)
    saved: list[str] = []
    for key, filename in SELECT_IMAGE_TARGETS.items():
        image = data.get(key)
        if image is None:
            continue
        path = out_dir / filename
        image.save(path)
        saved.append(str(path))
    return saved


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

        if mode == detect_mode.detect:
            image_data = reader.read_detect_images() or {}
            item["updated_select_images"] = _save_select_images(image_data)

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
                if _enum_name(score_display_mode) == "exscore":
                    score_debug = _nearest_digit_debug(
                        img2, RECT_RESULT_SCORE_EXMODE, HASH_RESULT_EXSCORE
                    )
                    exscore_debug = _nearest_digit_debug(
                        img2, RECT_RESULT_EXSCORE_EXMODE, HASH_RESULT_SCORE_LARGE
                    )
                    item["nearest_score"] = score_debug["digits"]
                    item["nearest_score_distances"] = score_debug["distances"]
                    item["nearest_exscore"] = exscore_debug["digits"]
                    item["nearest_exscore_distances"] = exscore_debug["distances"]
                else:
                    score_large_debug = _nearest_digit_debug(
                        img2, RECT_RESULT_SCORE_LARGE, HASH_RESULT_SCORE_LARGE
                    )
                    score_small_debug = _nearest_digit_debug(
                        img2, RECT_RESULT_SCORE_SMALL, HASH_RESULT_SCORE_SMALL
                    )
                    exscore_debug = _nearest_digit_debug(
                        img2, RECT_RESULT_EXSCORE, HASH_RESULT_EXSCORE
                    )
                    item["nearest_score"] = (
                        score_large_debug["digits"] + score_small_debug["digits"]
                    )
                    item["nearest_score_distances"] = (
                        score_large_debug["distances"] + score_small_debug["distances"]
                    )
                    item["nearest_exscore"] = exscore_debug["digits"]
                    item["nearest_exscore_distances"] = exscore_debug["distances"]
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


def _capture_summary_item_from_file(reader: ScreenReader, path: str):
    with Image.open(path) as img:
        screen = (
            expand_result_info_area(img) if img.size == RESULT_INFO_CROP_SIZE else img
        )
        reader.update_screen(screen)
        mode = reader.detect_screen()
        if not mode.is_result_screen():
            return None
        target = reader.corrected_screen or screen
        return capture_summary_item_from_screen(target, int(os.path.getmtime(path)))


def _generate_summary_from_loaded_results(
    reader: ScreenReader,
    files: list[str],
    bg_alpha: int,
    min_rows: int,
) -> int:
    items = []
    for path in files:
        try:
            item = _capture_summary_item_from_file(reader, path)
            if item is not None:
                items.append(item)
        except Exception as exc:
            print(f"summary capture failed: {path}: {exc}", file=sys.stderr)

    if not items:
        print("No result images available for summary.", file=sys.stderr)
        return 1

    if not _generate_from_items_sync(items, bg_alpha, min_rows):
        print("Failed to generate summary images.", file=sys.stderr)
        return 1

    print(
        f"Generated summary images from {len(items)} result image(s).", file=sys.stderr
    )
    return 0


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
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Generate out/summary_full.png and out/summary_small.png from detected result images.",
    )
    parser.add_argument(
        "--summary-bg-alpha",
        type=int,
        default=200,
        help="Background alpha for --summary output.",
    )
    parser.add_argument(
        "--summary-min-rows",
        type=int,
        default=15,
        help="Minimum row count for --summary output.",
    )
    args = parser.parse_args(argv)

    files = _iter_files(args.paths)
    if not files:
        print("No target images found.", file=sys.stderr)
        return 1

    reader = ScreenReader(SongDatabase())
    rows = [_detect_file(reader, path) for path in files]
    summary_status = 0
    if args.summary:
        summary_status = _generate_summary_from_loaded_results(
            reader,
            files,
            args.summary_bg_alpha,
            args.summary_min_rows,
        )

    if args.pretty:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return summary_status


if __name__ == "__main__":
    raise SystemExit(main())
