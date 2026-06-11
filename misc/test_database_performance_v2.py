import os
import time
import bz2
import pickle
import sys
import random
import string
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(os.getcwd())

from src.result import OneResult
from src.classes import difficulty, clear_lamp, detect_mode

def get_random_string(length):
    letters = string.ascii_lowercase + string.digits + "あいうえおかきくけこさしすせそ"
    return ''.join(random.choice(letters) for i in range(length))

def create_dummy_results(count=3000):
    results = []
    now = int(time.time())
    for i in range(count):
        results.append(OneResult(
            title=f"Song_{get_random_string(20)}_{i}",
            difficulty=random.choice(list(difficulty)),
            lamp=random.choice(list(clear_lamp)),
            score=random.randint(9000000, 10000000),
            exscore=random.randint(2000, 6000),
            level=random.randint(1, 20),
            timestamp=now - i * random.randint(60, 3600),
            detect_mode=detect_mode.result
        ))
    return results

def test_compression_speed(results, level):
    data = pickle.dumps(results)
    start = time.time()
    with bz2.BZ2File('test_save.bz2', 'wb', compresslevel=level) as f:
        f.write(data)
    end = time.time()
    size = os.path.getsize('test_save.bz2')
    return end - start, size

if __name__ == "__main__":
    count = 10000 # 3000だと最近のCPUではすぐ終わってしまうので1万件にする
    print(f"Creating {count} complex dummy results...")
    results = create_dummy_results(count)
    
    # 複数回試行して平均を取る
    def benchmark(level, runs=3):
        times = []
        sizes = []
        for _ in range(runs):
            t, s = test_compression_speed(results, level)
            times.append(t)
            sizes.append(s)
        return sum(times)/runs, sum(sizes)/runs

    print("\nTesting compression level 9 (Old):")
    t9, s9 = benchmark(9)
    print(f"Avg Time: {t9:.4f}s, Size: {s9/1024:.2f} KB")
    
    print("\nTesting compression level 1 (New):")
    t1, s1 = benchmark(1)
    print(f"Avg Time: {t1:.4f}s, Size: {s1/1024:.2f} KB")
    
    print(f"\nSpeed improvement: {t9/t1:.1f}x faster")
    print(f"Size increase: {s1/s9:.2f}x large")
    
    if os.path.exists('test_save.bz2'):
        os.remove('test_save.bz2')
