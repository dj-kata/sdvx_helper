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
import xml.etree.ElementTree as ET

specialTitles = {
        'Death by Glamour  華麗なる死闘':  'Death by Glamour / 華麗なる死闘',
        'Electric Sister Bitch':'Electric "Sister" Bitch',
        'Lunatic Dial':'Lunartic Dial',
        'ASGORE  アズゴア':'ASGORE / アズゴア',
        'archivezip':'archive::zip',
        'Sakura Reflection (PLight Slayer Remix)':'Sakura Reflection (P*Light Slayer Remix)',
        'Spider Dance  スパイダーダンス':'Spider Dance / スパイダーダンス',
        'U.N. Owen was her (Hyuji Remix)':'U.N. Owen was her? (Hyuji Remix)',
        'I’m Your Treasure Box ＊あなたは マリンせんちょうを たからばこからみつけた。':'I’m Your Treasure Box ＊あなたは マリンせんちょうを たからばこからみつけた。',
        'The Sampling Paradise (PLight Remix)':'The Sampling Paradise (P*Light Remix)',
        'Finale  フィナーレ':'Finale / フィナーレ',
        'コンベア速度Max!しゃいにん☆廻転ズシSushi&Peace':'コンベア速度Max!? しゃいにん☆廻転ズシ"Sushi&Peace"',
        'VoynichManuscript':'Voynich:Manuscript',
        #'Pure Evil':'Pure Evil',
        'Believe (y)our Wings {VIVID RAYS}':'Believe (y)our Wings {V:IVID RAYS}',
        'チルノのパーフェクトさんすう教室 ⑨周年バージョン':'チルノのパーフェクトさんすう教室　⑨周年バージョン',
        'Wuv U(picoustic rmx)':'Wuv U(pico/ustic rmx)',
        'Battle Against a True Hero  本物のヒーローとの戦い':'Battle Against a True Hero / 本物のヒーローとの戦い',
        'rEVoltagers':'rE:Voltagers',
        'S1CK F41RY':'S1CK_F41RY',
        'ニ分間の世界':'二分間の世界',
        'ReRose Gun Shoooot!':'Re:Rose Gun Shoooot!',
        'gigadelic (かめりあ\'s The TERA RMX)':'gigadelic (かめりあ\'s "The TERA" RMX)',
        'PROVOESPROPOSE êl fine':'PROVOES*PROPOSE <<êl fine>>',
        'LuckyClover':'Lucky*Clover',
        '壊Raveit!! 壊Raveit!!':'壊Rave*it!! 壊Rave*it!!',
        'BLACK or WHITE':'BLACK or WHITE?',
        'MrVIRTUALIZER':'Mr.VIRTUALIZER',
        '#Fairy dancing in lake':'#Fairy_dancing_in_lake',
        '゜。Chantilly Fille。°':'゜*。Chantilly Fille。*°'
    }

def restoreTitle(songTitle):       
    return specialTitles.get(songTitle.strip(),songTitle.strip())

def isSpecialTitle(songTitle):
    return songTitle.strip() in specialTitles

def loadSongList(songList):
    ret = None
    with open(f'{songList}/musiclist.pkl', 'rb') as f:
        ret = pickle.load(f)
    return ret

def loadPlaysList(allogFolder):
    ret = None
    with open(f'{allogFolder}/alllog.pkl', 'rb') as f:
        ret = pickle.load(f)
    return ret


def save(dat:dict, allogFolder):
    with open(f'{allogFolder}/alllog.pkl', 'wb') as f:
        pickle.dump(dat, f)

        
def isSongInLog(songLog, songToSearch,fileNumber):
        
    songExists = False
    songDifferentDate = False
    
    allPlaysOfSong = []
    
    for songFromLog in songLog:
        if songFromLog.title == restoreTitle(songToSearch.title) and songFromLog.difficulty == songToSearch.difficulty:
            allPlaysOfSong.append(songFromLog)
    
    songSSDate = datetime.strptime(songToSearch.date.split('_')[0], "%Y%m%d")            
    songSSTime = datetime.strptime(songToSearch.date.split('_')[1], '%H%M%S')
    
    for songFromLog in allPlaysOfSong:
                    
        if not "_" in songToSearch.date or len(songToSearch.date.split('_')) < 2 : 
            print(f'Mallformed song data: {songToSearch.disp()}')
            return True
        
        songLogDate = datetime.strptime(songFromLog.date.split('_')[0], "%Y%m%d")
        songLogTime = datetime.strptime(songFromLog.date.split('_')[1], '%H%M%S')
                        
        diferenceInSeconds = abs((songSSTime - songLogTime).total_seconds())
        diferenceInDays = abs((songLogDate - songSSDate)).days
        
        if diferenceInDays == 0 and diferenceInSeconds < 120:
            songExists = True
            if songDifferentDate == True :
                print(f'[{fileNumber}] [{songToSearch.title}-{songToSearch.difficulty.upper()}] Found: Log: {songFromLog.date} | Screenshot: {songToSearch.date}\n')
            break;
        elif diferenceInDays == 0 and diferenceInSeconds >= 120: 
            print(f'[{fileNumber}] [{songToSearch.title}-{songToSearch.difficulty.upper()}] Difference time: Log: {songLogTime} | Screenshot: {songSSTime} ({diferenceInSeconds}s)')
            songDifferentDate = True
        elif diferenceInDays > 0 :
            print(f'[{fileNumber}] [{songToSearch.title}-{songToSearch.difficulty.upper()}] Difference date: Log: {songLogDate} | Screenshot: {songSSDate} ({diferenceInDays}d)')
            songDifferentDate = True

    if songExists == False :
        print(f'[{fileNumber}] [{songToSearch.title}-{songToSearch.difficulty.upper()}] not found in play log')
        
            
    return songExists    
    

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
        
        songLog = loadPlaysList(songLogFolder)
    else :
        print(f'Cannot run log sync: alllog folder \'{songLogFolder}\' is not a folder', file=sys.stderr)
        exit(1)
        

    print('Initialising OCR...')
    # When running manually, call in the settings yourself to be able to run from the IDE
    start = datetime(year=2023, month=10, day=15, hour=0)
    genSummary = GenSummary(start, rootFolder + '/sync', 'true', 255, 2)
    
    print(f'Processing {len(os.listdir(rootFolder))} files from folder \'{rootFolder}\'')
    
    dtStart = datetime.now()

    updatedSongs = 0
    processedFiles = 0
    for playScreenshotFileName in os.listdir(rootFolder):                
        # We ignore files which are a summary and are not png
        if playScreenshotFileName.find('summary') > 0 :
            continue
        
        if playScreenshotFileName.find('png') < 0 :
            continue
        
        if not playScreenshotFileName.startswith("sdvx") :
            continue

        nameSplits = playScreenshotFileName.split("_")                
                        
        songTitle = ''
        for i in range(1,len(nameSplits)) :
            
            # Read all chunks as song title until we hit and difficulty identifier
            if nameSplits[i] != 'NOV' and nameSplits[i] != 'ADV' and nameSplits[i] != 'EXH' :         
                songTitle += nameSplits[i] + ' '
                lastIndexOfName = i
                continue
            else :
                break;
         
        # Set the rest of the data based on offset of the last chunk of the title       
        dif = nameSplits[lastIndexOfName+1]
        
        # If the chunk after the difficulty is 'class' we know it's a screenshot of the Skill Analyser mode and we skip that chunk
        if nameSplits[lastIndexOfName+2] == 'class' :
            lastIndexOfName+=1
            
        lamp = nameSplits[lastIndexOfName+2]
        
        # It can happen that the score is empty and we have a file of type
        # sdvx_プナイプナイたいそう_NOV_failed__20250111_173755
        # In the case, consider the score 0 otherwise things might break later 
        # if the playDate chunks are not assigned correctly
        if nameSplits[lastIndexOfName+3] == '' :
            score = 0
        else :
            score = nameSplits[lastIndexOfName+3]
            
        playDate = nameSplits[lastIndexOfName+4]+'_'+nameSplits[lastIndexOfName+5]
        playDate = playDate.removesuffix('.png')
                
        #print(f'Read from file: {songTitle} / {dif} / {lamp} / {score} / {playDate}')

        if songTitle != '':
            
            if isSpecialTitle(songTitle) :                
                for i in range(0,len(songLog)) :                    
                    if songLog[i].title == songTitle.strip() :
                        songLog.pop(i)
                        print(f'Removed incorrect song with title {songTitle} from play log.')
                        break                                                                    
                        
            songTitle = restoreTitle(songTitle)
            
            img = Image.open(os.path.abspath(f'{rootFolder}/{playScreenshotFileName}'))
            scoreFromImage = genSummary.get_score(img)                
            
            songFromScreenshot = OnePlayData(songTitle, scoreFromImage[0], scoreFromImage[1], lamp, dif.lower(), playDate.removesuffix('.png_'))

            # If the song is not in the long, with a tolerance of 120 seconds, add it to the log                
            if not isSongInLog(songLog, songFromScreenshot,processedFiles):
                print(f'[{processedFiles}] [{songFromScreenshot.title}-{songFromScreenshot.difficulty.upper()}] Adding to log with date {songFromScreenshot.date}\n')
                songLog.append(songFromScreenshot)
                updatedSongs += 1
        
        processedFiles += 1
        if processedFiles % 100 == 0:
            print(f'{processedFiles} files processed...')
    
    dtEnd = datetime.now()
    duration = dtEnd - dtStart
    print(f'Update song log with {updatedSongs} songs out of {processedFiles} valid files in {round(duration.total_seconds(),2)}s')
    save(songLog, songLogFolder)
    
    
def findSongRating(songFromLog, songList):
    
    rating = 0
    
    # Find the numeric value of the song rating based on it's difficulty category
    song = songList['titles'].get(restoreTitle(songFromLog.title),None)
    
    if song is not None :
        if songFromLog.difficulty == 'nov' : 
            rating = song[3]
        elif songFromLog.difficulty == 'adv' :
            rating = song[4]
        elif songFromLog.difficulty == 'exh' :
            rating = song[5]
        else :
            rating = song[6]
                
    if rating == 0 :
        print(f'Could not find song in song list for rating: {songFromLog.title}')
        
    return str(rating)
    
def dump(songLogFolder, songListFolder):
    
    songLog = loadPlaysList(songLogFolder)
    songList = loadSongList(songListFolder)
    
    songListElement = ET.Element("songList")
    xmlTree = ET.ElementTree(songListElement)
    plays={}
    
    print(f'Dumping {len(songLog)} song plays to XML...')
    for songFromLog in songLog:
        
        title = restoreTitle(songFromLog.title)
        
        rating = findSongRating(songFromLog, songList)
        songHash = str(hash(title+"_"+songFromLog.difficulty+"_"+rating))
                
        existingNode = plays.get(songHash,None)
        
        #Format the date to more similar to ISO
        songDate = datetime.strptime(songFromLog.date, '%Y%m%d_%H%M%S')
        formatted_date = songDate.strftime("%Y-%m-%d %H:%M:%S")
        
        # If we already added this song, create new "play" entry under the same song and difficulty / rating
        if existingNode is not None:       
            ET.SubElement(existingNode,"play",score=str(songFromLog.cur_score), lamp=songFromLog.lamp, date=formatted_date)
        else :
            songNode = ET.SubElement(songListElement, "song", title=title)
            playsNode = ET.SubElement(songNode,"plays", difficulty=songFromLog.difficulty, rating=rating)
            ET.SubElement(playsNode,"play",score=str(songFromLog.cur_score), lamp=songFromLog.lamp, date=formatted_date)
            plays[songHash] = playsNode
        
        
    print(f'Writing XML to {songLogFolder}/played_songs.xml')
    ET.indent(xmlTree, space="\t", level=0)
    xmlTree.write(songLogFolder+"/played_songs.xml",encoding="UTF-8",xml_declaration=True)
        
        
if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Reads the sdvx results folders and re-inserts missing songs into the alllog.pkl')
    parser.add_argument('--songLog', required=True, help='The directory containing the alllog (alllog.pkl) file')
    parser.add_argument('--results', required=True, help='The directory containing the result screenshots')
    parser.add_argument('--dump', required=False, help='Dumps the alllog.pkl into an xml file', action='store_true')
    parser.add_argument('--songList', required=False, help='The directory containing the song list (musiclist.pkl) file, only used with the --dump option')
    
    args = parser.parse_args()
    main(args.songLog, args.results)
    
    if args.dump :
        dump(args.songLog, args.songList)
    
    

