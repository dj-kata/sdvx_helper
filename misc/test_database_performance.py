import os
import time
import bz2
import pickle
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(os.getcwd())

from src.result import OneResult
from src.classes import difficulty, clear_lamp, detect_mode

def create_dummy_results(count=3000):
    results = []
    now = int(time.time())
    for i in range(count):
        results.append(OneResult(
            title=f"Dummy Song {i}",
            difficulty=difficulty.maximum,
            lamp=clear_lamp.uc,
            score=9900000,
            exscore=4500,
            level=18,
            timestamp=now - i * 60,
            detect_mode=detect_mode.result
        ))
    return results

def test_compression_speed(results, level):
    start = time.time()
    data = pickle.dumps(results)
    with bz2.BZ2File('test_save.bz2', 'wb', compresslevel=level) as f:
        f.write(data)
    end = time.time()
    size = os.path.getsize('test_save.bz2')
    return end - start, size

if __name__ == "__main__":
    print("Creating 3000 dummy results...")
    results = create_dummy_results(3000)
    
    print("\nTesting compression level 9 (Old):")
    t9, s9 = test_compression_speed(results, 9)
    print(f"Time: {t9:.4f}s, Size: {s9/1024:.2f} KB")
    
    print("\nTesting compression level 1 (New):")
    t1, s1 = test_compression_speed(results, 1)
    print(f"Time: {t1:.4f}s, Size: {s1/1024:.2f} KB")
    
    print(f"\nSpeed improvement: {t9/t1:.1f}x faster")
    print(f"Size increase: {s1/s9:.2f}x large")
    
    if os.path.exists('test_save.bz2'):
        os.remove('test_save.bz2')
