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
from src.classes import *
from src.config import Config
from src.funcs import *
logger = get_logger('test_opt_conv')

if __name__ == '__main__':
    logger.info('start')
    opt = PlayOption()

    sample = [
        None
        ,'RAN / RAN, FLIP'
        ,'RAN / RAN, FLIP, LEGACY'
        ,'S-RAN / MIR'
        ,'?'
        ,'RAN / MIR, LEGACY'
        ,'R-RAN / OFF'
        ,'H-RAN / OFF'
        ,'OFF / RAN, FLIP'
        ,'S-RAN / S-RAN, FLIP, A-SCR'
        ,'S-RAN / S-RAN, LEGACY'
        ,'R-RAN / RAN, FLIP'
        ,'OFF'
        ,'MIR / RAN, FLIP, LEGACY'
        ,'OFF / RAN'
        ,'BATTLE, SYMM-RAN, A-SCR'
        ,'RAN / R-RAN, LEGACY'
        ,'MIR / RAN, FLIP'
        ,'RAN'
        ,'OFF / R-RAN, FLIP'
        ,'S-RAN / S-RAN, A-SCR'
        ,'R-RANDOM'
        ,'BATTLE, S-RAN / S-RAN, A-SCR'
        ,'MIR / MIR'
        ,'BATTLE, H-RAN / H-RAN, A-SCR'
        ,'S-RANDOM, LEGACY'
        ,'BATTLE, RAN / RAN, A-SCR'
        ,'MIR / MIR, FLIP'
        ,'OFF / MIR'
        ,'MIR / R-RAN'
        ,'RAN / S-RAN, FLIP, LEGACY'
        ,'MIR / R-RAN, FLIP, LEGACY'
        ,'R-RAN / R-RAN, FLIP'
        ,'S-RAN / MIR, FLIP, LEGACY'
        ,'RANDOM'
        ,'BATTLE, MIR / OFF, A-SCR'
        ,'OFF / OFF, A-SCR'
        ,'BATTLE, SYNC-RAN, A-SCR'
        ,'MIR / RAN'
        ,'BATTLE, OFF / MIR, A-SCR'
        ,'S-RAN / MIR, FLIP'
        ,'RAN / RAN'
        ,'RAN / MIR, FLIP, LEGACY'
        ,'BATTLE, OFF / MIR'
        ,'S-RAN / S-RAN'
        ,'OFF / R-RAN'
        ,'R-RAN / S-RAN'
        ,'S-RAN'
        ,'MIR / S-RAN, FLIP'
        ,'MIR / MIR, FLIP, LEGACY'
        ,'RAN / OFF, FLIP'
        ,'S-RAN / RAN, FLIP'
        ,'BATTLE, MIR / RAN'
        ,'OFF / OFF, FLIP'
        ,'MIR / OFF, FLIP, LEGACY'
        ,'RAN / MIR, FLIP'
        ,'OFF / S-RAN'
        ,'RAN / RAN, LEGACY'
        ,'S-RAN / MIR, LEGACY'
        ,'RAN / MIR'
        ,'BATTLE, MIR / OFF'
        ,'OFF / OFF'
        ,'MIR / R-RAN, FLIP'
        ,'R-RAN / R-RAN'
        ,'S-RAN / OFF'
        ,'RAN / OFF'
        ,'OFF / OFF, LEGACY'
        ,'MIR / R-RAN, FLIP, A-SCR'
        ,'MIR / OFF, FLIP'
        ,'OFF / S-RAN, FLIP'
        ,'BATTLE, MIR / OFF, LEGACY'
        ,'BATTLE, RAN / RAN'
        ,'MIRROR'
        ,'MIR / R-RAN, LEGACY'
        ,'MIR / OFF'
        ,'S-RAN / S-RAN, FLIP, LEGACY'
        ,'RAN / R-RAN, FLIP'
        ,'RANDOM, LEGACY'
        ,'R-RAN'
        ,'RAN / R-RAN'
        ,'OFF / MIR, FLIP'
        ,'MIR'
        ,'S-RANDOM'
        ,'R-RAN / RAN'
        ,'RAN / S-RAN'
    ]

    # 先にSP
    for i,o in enumerate(sample):
        if o and '/' in o:
            continue
        opt = PlayOption()
        opt.convert_from_v2(o)
        print(' pre:', o)
        print('post:', opt, ', special:', opt.special)
        print()
    # DP
    for i,o in enumerate(sample):
        if o and '/' not in o:
            continue
        opt = PlayOption()
        opt.convert_from_v2(o)
        print(' pre:', o)
        print('post:', opt, ', special:', opt.special)
        print()