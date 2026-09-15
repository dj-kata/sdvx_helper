"""_load_results_from_csv() / import_personal_csv() の最小自己チェック。
pytest不要、python misc/test_personal_csv_import.py で実行。
"""
import datetime
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.result_database import ResultDatabase
from src.classes import difficulty, clear_lamp

PLAIN_CSV = "title,difficulty,Lv,score,lamp\n" \
            "TestSong,EXH,17,9800000,PUC\n" \
            "TestSong2,NOV,,5000000,CLEAR\n"

ARCADE_CSV = (
    "楽曲名,難易度,楽曲レベル,ハイスコア,クリアランク,EXスコア\n"
    "アーケード曲,MAXIMUM,18.5,9900000,PUC,1234\n"
)

TIMESTAMP_UNIX_CSV = "title,difficulty,Lv,score,lamp,timestamp\n" \
                      "TestSong,EXH,17,9800000,PUC,1700000000\n"

TIMESTAMP_DATE_CSV = "title,difficulty,Lv,score,lamp,Last Played\n" \
                      "TestSong,EXH,17,9800000,PUC,2023-11-14 22:13\n"

TIMESTAMP_JP_CSV = "title,difficulty,Lv,score,lamp,タイムスタンプ\n" \
                    "TestSong,EXH,17,9800000,PUC,1700000000\n"


def _fake_self():
    return SimpleNamespace(song_database=SimpleNamespace(get_song_info=lambda title: None))


def test_plain_format():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write(PLAIN_CSV)
        path = f.name
    try:
        results = ResultDatabase._load_results_from_csv(_fake_self(), path)
        assert results is not None
        assert len(results) == 2
        assert results[0].title == "TestSong"
        assert results[0].difficulty == difficulty.exhaust
        assert results[0].score == 9800000
        assert results[0].lamp == clear_lamp.puc
        assert results[1].difficulty == difficulty.novice
    finally:
        os.remove(path)


def test_arcade_format():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write(ARCADE_CSV)
        path = f.name
    try:
        results = ResultDatabase._load_results_from_csv(_fake_self(), path)
        assert results is not None
        assert len(results) == 1
        r = results[0]
        assert r.title == "アーケード曲"
        assert r.difficulty == difficulty.maximum
        assert r.score == 9900000
        assert r.exscore == 1234
        assert r.level == 18
    finally:
        os.remove(path)


def test_missing_file_returns_none():
    assert ResultDatabase._load_results_from_csv(_fake_self(), "no_such_file.csv") is None


def test_timestamp_unix_column():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write(TIMESTAMP_UNIX_CSV)
        path = f.name
    try:
        results = ResultDatabase._load_results_from_csv(_fake_self(), path)
        assert results[0].timestamp == 1700000000
    finally:
        os.remove(path)


def test_timestamp_date_column():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write(TIMESTAMP_DATE_CSV)
        path = f.name
    try:
        results = ResultDatabase._load_results_from_csv(_fake_self(), path)
        expected = int(datetime.datetime.strptime("2023-11-14 22:13", "%Y-%m-%d %H:%M").timestamp())
        assert results[0].timestamp == expected
    finally:
        os.remove(path)


def test_timestamp_jp_column():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write(TIMESTAMP_JP_CSV)
        path = f.name
    try:
        results = ResultDatabase._load_results_from_csv(_fake_self(), path)
        assert results[0].timestamp == 1700000000
    finally:
        os.remove(path)


def test_no_timestamp_column_defaults_to_now():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
        f.write(PLAIN_CSV)
        path = f.name
    try:
        before = int(datetime.datetime.now().timestamp())
        results = ResultDatabase._load_results_from_csv(_fake_self(), path)
        after = int(datetime.datetime.now().timestamp())
        assert before <= results[0].timestamp <= after
    finally:
        os.remove(path)


if __name__ == "__main__":
    test_plain_format()
    test_arcade_format()
    test_missing_file_returns_none()
    test_timestamp_unix_column()
    test_timestamp_date_column()
    test_timestamp_jp_column()
    test_no_timestamp_column_defaults_to_now()
    print("OK")
