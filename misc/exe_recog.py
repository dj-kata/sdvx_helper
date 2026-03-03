import sys
import pickle
import os
from PIL import Image
import numpy as np
import imagehash
import glob

from src.screen_reader import ScreenReader
from src.logger import get_logger
from src.result import *
from src.result_database import ResultDatabase
from src.classes import *
from src.config import Config
from src.funcs import *
from src.screen_reader import *
logger = get_logger('exe_recog')

if __name__ == '__main__':
    sdb = SongDatabase()
    sr = ScreenReader(sdb)

    def read_result(f):#debug/result\ex1874.png
        img = Image.open(f)
        sr.update_screen(img)
        result = sr.read_from_result()
        print(f"{f} - {result['title']}({result['difficulty']}), sc:{result['score']}, ex:{result['exscore']}, lamp:{result['lamp']}")
    def read_select(f):#debug/result\ex1874.png
        img = Image.open(f)
        sr.update_screen(img)
        result = sr.read_from_select()
        print(f"{f} - {result['title']}({result['difficulty']}), sc:{result['score']}, ex:{result['exscore']}, lamp:{result['lamp']}")

    # for f in glob.glob('debug/result/*png'):
        # read_result(f)
    for f in glob.glob('debug/select/*png'):
        read_select(f)
    for f in glob.glob('debug/select2/*png'):
        read_select(f)
    # for f in glob.glob('debug/select/exh_996*png'):
    #     read_select(f)