import pickle
import os
from os import path
from PIL import Image
from datetime import datetime 
from sdvxh_classes import OnePlayData
from gen_summary import GenSummary


def load():
    ret = None
    with open('D:/Tools/SoundVoltex/sdvx_helper/alllog.pkl', 'rb') as f:
        ret = pickle.load(f)
    return ret


def save(dat:dict):
    with open('D:/Tools/SoundVoltex/sdvx_helper/alllog.pkl', 'wb') as f:
        pickle.dump(dat, f)

        
def isSongInLog(songLog, songToSearch):
    
    songFound = False
    songExistOnDate = False
    for songFromLog in songLog:
        if songFromLog.title == songFromScreenshot.title and songFromLog.date == songFromScreenshot.date:
#            print(f'Song {songFromScreenshot.title} already exists on file')
            songFound = True
            break
        elif songFromLog.title == songFromScreenshot.title:
            songLogDate = songFromLog.date.split('_')[0]
            songLogTime = datetime.strptime(songFromLog.date.split('_')[1], '%H%M%S')
            
            if not "_" in songFromScreenshot.date: 
                print(f'Mallformed song data: {songFromScreenshot.disp()}')
            
            songSSDate = songFromScreenshot.date.split('_')[0]
            songSSTime = datetime.strptime(songFromScreenshot.date.split('_')[1], '%H%M%S')
            
            diferenceInSeconds = abs((songSSTime - songLogTime).total_seconds())
            
            if songLogDate == songSSDate and diferenceInSeconds < 120:
                #print(f'Song {songFromScreenshot.title} already exists on file')
                songFound = True
                break
            else: 
                #print(f'Song \'{songFromScreenshot.title}\' already exists on file but with different date: {songFromLog.date} in log vs {songFromScreenshot.date} in screenshot ({diferenceInSeconds}s difference)')
                songExistOnDate = True
            

    if not songFound and not songExistOnDate:
        print(f'Song \'{songFromScreenshot.title}\' is new!')
        return False
    elif not songFound and songExistOnDate : 
        print(f'Song \'{songFromScreenshot.title}\' already exists but with another date. Adding new date.')
        return False

    return True

# TODO: Find a way to extract the data from a result screenshot without data in the filename
def parse_unparsed_results_screen (resultsFilename):
    img = Image.open(os.path.abspath(f'{rootFolder}/{playScreenshotFileName}'))
    parts = genSummary.cut_result_parts(img)
    genSummary.ocr()
    dif = genSummary.difficulty

if __name__ == '__main__':
    songLog = load()
    
    updatedSongs = 0
    
    # TODO: Argument
    rootFolder = 'D:/Tools/SoundVoltex/results'

    # When running manually, call in the settings yourself to be able to run from the IDE
    start = datetime(year=2023, month=10, day=15, hour=0)
    genSummary = GenSummary(start, rootFolder.join('/sync'), 'true', 255, 2)

    for playScreenshotFileName in os.listdir(rootFolder):
        # We ignore files which are a summany and are not png
        if playScreenshotFileName.find('summary') > 0 :
            continue
        
        if playScreenshotFileName.find('png') < 0 :
            continue

        nameSplits = playScreenshotFileName.split("_")
        
        songTitle = ''
        dif = ''
        lamp = ''
        score = ''
        playDate = ''
        
        # Go through all the filename parts to extract the song data. The ocr_reporter must be used 1st to put that inforation
        # in the filename of the results screenshot
        for split in nameSplits:
            if split == 'sdvx':
                continue
            
            # Files that have no information about them on the filename should try to get their information
            # From the results screenshot
            if split.isnumeric() and songTitle == '': 
                #parse_unparsed_results_screen(playScreenshotFileName)
                break
            
            if dif == '' and split != 'NOV' and split != 'ADV' and split != 'EXH':
                 songTitle += split + ' '
            elif dif == '': 
                dif = split
            elif dif != '' and lamp == '':
                lamp = split                
            elif lamp != ''  and score == '':
                score = split
            elif score != '':
                playDate += split + '_'
        
        # print(f'Read from file: {songTitle} - {dif} - {lamp} - {score} - {playDate}')

        if songTitle != '':
            
            img = Image.open(os.path.abspath(f'{rootFolder}/{playScreenshotFileName}'))
            scoreFromImage = genSummary.get_score(img)                
            
            songFromScreenshot = OnePlayData(songTitle.removesuffix(' '), scoreFromImage[0], scoreFromImage[1], lamp, dif.lower(), playDate.removesuffix('.png_'))

            # If the song is not in the long, with a tolerance of 120 seconds, add it to the log                
            if not isSongInLog(songLog, songFromScreenshot):
                songLog.append(songFromScreenshot)
                updatedSongs += 1
        
    print(f'Update song log with {updatedSongs} songs')
    save(songLog)
