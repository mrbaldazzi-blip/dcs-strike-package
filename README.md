DCS Strike Package
A simple mission creator for DCS World. Pick an era, a map, your aircraft and a mission type, press a button, and get a ready-to-fly `.miz` file with a full briefing that shows up on your kneeboard.

What it does
Creates a scripted .miz and saves it straight to your `Saved Games\\\\\\\\DCS\\\\\\\\Missions` folder.
Choose your mission type: strike, CAS, SEAD, DEAD, CAP, intercept, naval strike.
Pick era, map and aircraft (early Cold War through modern, blue or red). Only valid combinations are offered.
Package of 1-3 flights (for example CAP + SEAD + strike) on one timeline, with AI wingmen and escorts.
Real weapon loadouts per role and year, set automatically.
Briefing in your kneeboard: an overview page, a page for each flight with waypoints and timings, plus target and SAM photos. Also exported as a PDF.
Active-war or pre-emptive posture, with enemy defences from light to heavy.
Easy to run: double-click `setup.bat` once, then start the program from the shortcut it creates. No typing commands.
Screenshots
Overview page	Flight page
<img width="1600" height="640" alt="image" src="https://github.com/user-attachments/assets/f715bea9-7060-49bc-abed-d472701b525d" />


Target photos	SAM photos
<img width="768" height="1024" alt="image" src="https://github.com/user-attachments/assets/9561525d-bfaf-4837-a4bc-edfdd14d9e22" />


Install
Download the latest zip from Releases and unzip it anywhere.
Double-click `setup.bat`. It installs Python if you don't have it, then the other pieces it needs.
Open DCS Strike Package from the shortcut on your desktop.
Choose your options, click Generate .miz, and load the mission in DCS.
Not found your DCS folder? Run `python -m dcsgen paths` to see what was detected, or put your DCS install path in `dcs\\\\\\\_path.txt`.
Credits and licence
Built on pydcs (LGPL-3.0). Not affiliated with or endorsed by Eagle Dynamics. DCS World is a trademark of Eagle Dynamics SA.
Licence: (to be chosen, see the steps below)
Known issues
This is an early release. Some features, such as AWACS voice calls and airborne starts, have had limited testing in DCS
