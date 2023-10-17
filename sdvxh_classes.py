from enum import Enum
class gui_mode(Enum):
    init = 0
    main = 1
    setting = 2
    obs_control = 3
class detect_mode(Enum):
    init = 0
    select = 1
    play = 2
    result = 3

class OnePlayData:
    def __init__(self, title:str, cur_score:int, pre_score:int, lamp:str, difficulty:str, date:str):
        self.title = title
        self.cur_score = cur_score
        self.pre_score = pre_score
        self.lamp = lamp
        self.difficulty = difficulty
        self.date = date
        self.diff = cur_score - pre_score

    def __eq__(self, other):
        if not isinstance(other, OnePlayData):
            return NotImplemented

        return (self.title == other.title) and (self.difficulty == other.difficulty) and (self.cur_score == other.cur_score) and (self.pre_score == other.pre_score) and (self.lamp == other.lamp) and (self.date == other.date)
    
    def disp(self): # debug
        print(f"{self.title}({self.difficulty}), cur:{self.cur_score}, pre:{self.pre_score}({self.diff:+}), lamp:{self.lamp}, date:{self.date}")
