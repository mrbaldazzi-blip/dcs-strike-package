# DCS Strike Package (dcsgen) - era-based DCS World mission generator

Generates one scripted mission as a `.miz`: a briefing, AI wingmen, a fixed plan and a
package of 1-3 simultaneous flights (for example CAP + SEAD + strike) on one timeline.
You choose the side (blue or red), era, map, aircraft, mission type, posture and start location.
The briefing is an overview plus one page per flight, written like a flight lead briefing his
squad, and is exported as a PDF and as in-game kneeboard pages with USAF / USN / USMC /
Soviet / Russian style headers.

**New to this? Open `START_HERE.txt`.** It walks through installing Python, running
`setup.bat` once, and opening the program with `start.bat`, with no typed commands.
The notes below are for people comfortable with a terminal.

## Install and launch the GUI

Needs Python 3.10+ (the python.org Windows installer includes Tkinter).

    pip install .          # run inside this folder; also installs pydcs and pillow
    dcsgen-gui             # opens the window (or: python -m dcsgen gui)

Pick side, era, map, mission type, aircraft, posture and start location. Only valid combinations
are offered; if a choice makes another one impossible (say a carrier start while an F-16 is
selected) the form fixes the dependent choice and says what it changed in the status line.
"Preview briefing" shows the briefing without writing anything. "Generate .miz..." saves the
mission, defaulting to your `Saved Games\DCS\Missions` folder. Start location is a list of
real airbases once pydcs is installed, otherwise a box you type into.


