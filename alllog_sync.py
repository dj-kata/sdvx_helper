import pickle
import os
import argparse
import shutil
import sys
from os import path
from PIL import Image
from datetime import datetime 
from sdvxh_classes import OnePlayData
from gen_summary import GenSummary


def load(allogFolder):
    ret = None
    with open(f'{allogFolder}/alllog.pkl', 'rb') as f:
        ret = pickle.load(f)
    return ret


def save(dat:dict, allogFolder):
    with open(f'{allogFolder}/alllog.pkl', 'wb') as f:
        pickle.dump(dat, f)

        
def isSongInLog(songLog, songToSearch):
    
    songFound = False
    songExistOnDate = False
    for songFromLog in songLog:
        if songFromLog.title == songToSearch.title and songFromLog.date == songToSearch.date:
#            print(f'Song {songToSearch.title} already exists on file')
            songFound = True
            break
        elif songFromLog.title == songToSearch.title:
            songLogDate = songFromLog.date.split('_')[0]
            songLogTime = datetime.strptime(songFromLog.date.split('_')[1], '%H%M%S')
            
            if not "_" in songToSearch.date: 
                print(f'Mallformed song data: {songToSearch.disp()}')
            
            songSSDate = songToSearch.date.split('_')[0]
            songSSTime = datetime.strptime(songToSearch.date.split('_')[1], '%H%M%S')
            
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
    
def print_logo():
    print(' _                  __  __           _        ____                   ')
    print('| |    ___   __ _  |  \\/  |_   _ ___(_) ___  / ___| _   _ _ __   ___ ')
    print('| |   / _ \\ / _` | | |\\/| | | | / __| |/ __| \\___ \\| | | | \'_ \\ / __|')
    print('| |__| (_) | (_| | | |  | | |_| \\__ \\ | (__   ___) | |_| | | | | (__ ')
    print('|_____\\___/ \\__, | |_|  |_|\\__,_|___/_|\\___| |____/ \\__, |_| |_|\\___|')
    print('            |___/                                   |___/            ')
    
def main(songLogFolder, resultsFolder):
    
    print_logo()
    
    if os.path.isdir(resultsFolder) : 
        rootFolder = resultsFolder
    else :
        print(f'Cannot run log sync: results folder \'{resultsFolder}\' is not a folder', file=sys.stderr)
        exit(1)
        
    if os.path.isdir(songLogFolder) :       
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S') 
        backupLogFile = 'alllog.pkl.'+timestamp
        print(f'Backuping log file to {backupLogFile}')
        shutil.copyfile(f'{songLogFolder}/alllog.pkl', f'{songLogFolder}/{backupLogFile}')
        
        songLog = load(songLogFolder)
    else :
        print(f'Cannot run log sync: alllog folder \'{songLogFolder}\' is not a folder', file=sys.stderr)
        exit(1)
        

    print('Initialising OCR...')
    # When running manually, call in the settings yourself to be able to run from the IDE
    start = datetime(year=2023, month=10, day=15, hour=0)
    genSummary = GenSummary(start, rootFolder.join('/sync'), 'true', 255, 2)
    
    print(f'Processing {len(os.listdir(rootFolder))} files from folder \'{rootFolder}\'')

    updatedSongs = 0
    processedFiles = 0
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
        # in the filename of the resultsFolder screenshot
        for split in nameSplits:
            if split == 'sdvx':
                continue
            
            # Files that have no information about them on the filename should try to get their information
            # From the resultsFolder screenshot
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
        
        processedFiles += 1
        if processedFiles % 100 == 0:
            print(f'{processedFiles} files processed...')
        
    print(f'Update song log with {updatedSongs} songs out of {processedFiles} valid files')
    save(songLog, songLogFolder)

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Reads the sdvx results folders and re-inserts missing songs into the alllog.pkl')
    parser.add_argument('--songLog', required=True, help='The directory containing the alllog file')
    parser.add_argument('--results', required=True, help='The directory containing the result screenshots')
    
    args = parser.parse_args()
    main(args.songLog, args.results)
    
    
