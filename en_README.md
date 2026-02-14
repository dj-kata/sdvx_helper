I've created a simple English version of the manual.
I might consider implementing an English version of the UI in the future. 

説明書の日本語版は[こちら](https://github.com/dj-kata/sdvx_helper#readme)。

# sdvx_helper
The sdvx_helper is an application for SOUND VOLTEX EXCEED GEAR コナステ.  
It aims for streaming with Open Broadcaster Software (OBS).  
Even when the chart area is enlarged on your streaming layout,  current music information can be displayed clearly with this application.
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/5d33134e-942b-4fb6-a580-d81ad191e57a)

With this application, you can save result images automatically, and can 
generate a playlog image using them.
Each time a result image is captured, the playlog image is updated.
You can also save a screenshot on pressing F6 key.
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/95173020-f846-4a4f-b320-9e8018cb5059)

Using the [sdvx_helper portal](https://sh-portal.maya2silence.com),  
you can check Konasute version scores online and generate various images from Vaddict.  
https://sh-portal.maya2silence.com  
<img width="900" alt="image" src="https://github.com/user-attachments/assets/d32d3f6b-1a11-48d9-afb3-7bb5d0f911d6" />
<img width="900" alt="image" src="https://github.com/user-attachments/assets/535d1f05-01e6-4e38-aabb-994c40749061" />

Additionally, you can configure automatic control settings for OBS.
You can show or hide sources and switch scenes
for each in-game scene(play, result, select).
For example, you can display camera footage showing your hands only
during playing songs, and hide the VTuber avatar only on result
scene.

You can look at your konasute scores via portal site by [sdvx_helper portal](https://sh-portal.maya2silence.com)を利用することで、
Web上でコナステ版のスコアを確認したり、Vaddictから様々な画像を生成することができます。  
https://sh-portal.maya2silence.com  
<img width="900" alt="image" src="https://github.com/user-attachments/assets/d32d3f6b-1a11-48d9-afb3-7bb5d0f911d6" />
<img width="900" alt="image" src="https://github.com/user-attachments/assets/535d1f05-01e6-4e38-aabb-994c40749061" />

## The principles of this application
Just to clarify, the processing of this application is not related to reverse engineering.
The application periodically captures the game screen and determines the type of screen through image processing.
This application obtains the capture via OBS websocket,
which helps to minimize the load on the PC.

## The environment for verification
This application has been tested in the following environment.
```
OS: Windows10 64bit(22H2)
CPU: Intel Core i7-12700F
GPU: NVIDIA RTX3050
Antivirus software: Windows Defender
OBS: 29.1.2
```

Make sure you have OBS version 28 or newer for the latest WebSocket API. 
Even AMD CPUs should work fine (it's pretty stable via WebSocket). 
Just a heads up, your antivirus might block communication with OBS through TCP port 4444.

# Includings

|file name|description|
|-|-|
|sdvx_helper.exe|Execution file for sdvx_helper|
|update.exe|Execution file for auto-updating this application|
|version.txt|The version information|
|README.txt|Concise instruction manual|
|out/|The destination directory for outputting music information, playlog, etc...|
|out/nowplaying.html|An HTML file for displaying song information. You can use it by dragging and dropping it into OBS.|
|out/summary_full.png|A play log images of the day(detailed)|
|out/summary_small.png|A play log images of the day(summary)|
|resources/|Set of files for recognition|

# How to install
Download the ```sdvx_helper.zip``` at the top of [the release page](https://github.com/dj-kata/sdvx_helper/releases)
and extract it to a folder of your choice (excluding the desktop). Click on ```sdvx_helper.exe``` to run it.

An automatic update function is equipped in this tool,
which executes an update process if there are any
updates.

# How to setup sdvx_helper
## 1. Configure WebSocket on OBS(version 28 or later).
If OBSwebsocket is not installed, please download the latest alpha version without 'alpha'
in the name (e.g., ~Windows-Installer.exe)
from [here](https://github.com/obsproject/obs-websocket/releases) and install it.
In OBS, go to 'Tools' in the menu bar,
then select 'WebSocket Server Settings' and configure it as follows."
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/7b4fd58e-9e0c-4ffc-a875-3ec427312012)

## 2. Run sdvx_helper.exe and open '設定(settings)' from the menu bar.
## 3. Enter the port number and password you configured in step 1.
If you see a message saying 'Cannot connect to OBS', suspect the following.  
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/6b63586e-8d9f-4429-876f-2fe12fefe459)

## 4. Select the orientation of the screen specified in the e-AMUSEMENT Cloud version of Sound Voltex in the settings.
The settings in Sound Voltex and this tool correspond as follows:
![image](https://github.com/user-attachments/assets/40e717b7-5756-4264-b694-a175f3900714)

## 5. Close the settings window.
## 6. Open 'OBS制御設定(OBS control settings)' from the menu bar.
## 7. Choose the scene name for OBS streaming, select the source name to capture the game screen, and then press 'set' next to the game screen.
These settings are essential to capture the game screen.
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/7fdd5401-c2cb-4b7a-af04-3bb98f511357)

By the way, in the OBS control settings, you can control the visibility of sources for each scene (song selection, playing, results).

For example, you can easily do the following:
- Display hand camera only during play.
- Transition to a different scene on the results/song selection screen.

## 8. "Drag and drop 'out\nowplaying.html' into OBS.
Double-click on 'nowplaying.html' source and set the width to 820
and height to 900 for a nice layout with good margins.
Also, you can set it to show only during gameplay using OBS control settings.
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/f7a78147-7bc7-45a5-acdd-39ed55920d01)

Note that the source name must be 'nowplaying.html' or 'nowplaying'
for automatic reloading to occur.
If you directly place images from the 'out' folder in OBS,
they seem to be reloaded automatically.

## (For those who need it) Drag and drop 'out\summary_small.png' into OBS
I've designed it to display a history of 30 songs,
but if you want to reduce the number of songs,
you can trim by Alt+Mouse drag.
The 'out\summary_full.png' is a slightly larger version, including score rates.

To use this feature, be mindful of the following two points:

1. Set the 'リザルト自動保存先フォルダ(The folder where result images are automatically saved)' in the settings window.
2. Results need to be saved after launching.

Regarding 2., it's recommended to enable '更新に関係なく常時保存する(automatically save result images regardless of whether there are updates or not)'.
There's also a feature during summary image generation that filters out only Rank D results (I might expand this further in the future).

Main Specifications:

- Summary image is generated based on result images in the specified result folder(リザルト自動保存先フォルダ) which you selected in the settings window.
- The 'summary_*.png' is updated when results are saved.
- This application aggregates results saved **2 hours before or after the app was launched**.
- The update process is executed once at app startup (if a result was generated within 2 hours).

Due to the specifications, if it doesn't work as expected, consider restarting the app once. 
With a 2-hour window for fetching results, you should see the same image even after a restart.
Also, if a weird image (duplicated, faded colors, etc.)
is included due to a failed result fetch,
deleting the respective result image file will fix it in the next generation process."

## (For those who need it) Turn on notifications when BLASTER GAUGE is at maximum.
By checking 'Remind with sound when BLASTER GAUGE is at maximum' in the settings,
an alert sound (resources\blastermax.wav) will play when the gauge is
at maximum on the song selection screen.
![image](https://github.com/dj-kata/sdvx_helper/assets/61326119/d2695579-7aef-4476-bb4b-27c53e45df5b)

Also, if you create a text source (GDI+) named 'sdvx_helper_blastermax' in OBS,
it will display the text 'BLASTER GAUGE is at maximum!'
only when the gauge is at maximum.
(To make it easier to use during filter scroll settings,
we have added several dozen full-width spaces at the end.)
Nothing will be displayed if the gauge is not enough.
In OBS control settings, it might be a good idea to show
sdvx_helper_blastermax only on the song selection screen."

## (For those who need it) Display the number of songs played.
If you create a text source (GDI+) named 'sdvx_helper_playcount' in OBS,
it will display the number of songs played after launching this application,
like ```plays: 13```.

Procedure:

1. Right-click in the sources list → Add → Text (GDI+).
2. Customize the settings such as color and font to your liking. (Entering some temporary text can help you remember where you placed it.)
3. Right-click on the created source → Rename → Set it to ```sdvx_helper_playcount```

## (For those who need it) Display VF and grade changes before and after the stream.
By dragging and dropping the following image files into OBS, you can display information such as VF:
- vf_cur.png: Current VF
- vf_pre.png: VF at the app's startup
- class_cur.png: Current grade
- class_pre.png: Grade at the app's startup

# How to Use
If you have set up the above, simply keep it running when doing OBS streaming or recording.
Press the F6 key to save the captured image in the specified folder with the correct orientation.

# Miscellaneous
The license complies with Apache 2.0.

While there is no specific requirement for giving credit,
I would appreciate if you could mention it in the description.

Troubleshooting information will be compiled on [this page](https://github.com/dj-kata/sdvx_helper/wiki/%E3%83%88%E3%83%A9%E3%83%96%E3%83%AB%E3%82%B7%E3%83%A5%E3%83%BC%E3%83%86%E3%82%A3%E3%83%B3%E3%82%B0).

For bug reports or requests, please contact [the Issues section of this repository](https://github.com/dj-kata/sdvx_helper/issues)or Twitter(@[cold_planet_](https://twitter.com/cold_planet_)).
I might be ego-searching with ytlive_helper.
