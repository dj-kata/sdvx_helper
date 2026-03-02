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
logger = get_logger('exe_recog')

if __name__ == '__main__':
    logger.info('start')
    config = Config()
    rdb = ResultDatabase(config = config)
    reader = ScreenReader()
    # for f in glob.glob('debug/option/*.png'):
    for f in glob.glob('debug/option/*easy*.png'):
        # logger.info(f'file={f}')
        reader.update_screen_from_file(f)
        if reader.is_option():
            opt = reader.read_option_screen()
            rdb.broadcast_option_data(opt)
            print(f, opt)
    rdb.shutdown_servers()
