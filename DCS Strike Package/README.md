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

## Command line

    python -m dcsgen generate --era late_cold_war --map caucasus --aircraft f16c \
        --mission strike --posture preemptive --seed 7 --dry-run

    pip uninstall dcs        # only if you installed "dcs" before: it is a different, unrelated package
    pip install pydcs        # the real library (setup.bat prefers the newer GitHub version)
    python -m dcsgen diagnose # shows which package is installed and whether it loads
    python -m dcsgen check-units          # run once: lists unit names your pydcs does not know
    python -m dcsgen list-airbases --map caucasus
    python -m dcsgen generate --era modern --map persian_gulf --aircraft fa18c --mission sead \
        --start-kind supercarrier --start cvn75 --out sead.miz

    python -m dcsgen list-aircraft --era mid_cold_war
    python -m dcsgen list-maps

Also: `--side blue|red`, `--pdf` (write the briefing PDF), `--no-kneeboard`,
`python -m dcsgen scan-mods` (finds the A-4E-C / OV-10A mods in Saved Games),
`python -m dcsgen dump-names` (writes every unit name your pydcs knows).

Options: `--mission` strike|cas|sead|dead|cap, `--posture` preemptive|active_war,
`--flights 1-3`, `--flight-size 1-4`, `--max-units N` (default 100), `--seed N`.

## Postures

- **preemptive**: SAMs and AAA are dormant and wake when a blue aircraft is within 5-10 nm of
  the objective. Enemy fighters sit on ground alert and scramble when the package is detected
  35-50 nm out. No frontline.
- **active_war**: a frontline with friendly and enemy ground groups, hostile CAP in the air,
  early-warning radar, everything live from the start.

## Layout

- `dcsgen/eras.py` - era data, including DCS unit names
- `dcsgen/catalog.py` - aircraft: eras, roles, carrier capability
- `dcsgen/maps.py` - map registry
- `dcsgen/planner.py` - builds the plan and package timing (pure Python)
- `dcsgen/budget.py` - trims low-priority units to stay under `--max-units`
- `dcsgen/briefing.py` - briefing pages: overview + one per flight (pure Python)
- `dcsgen/render.py` - draws pages to images, the PDF and kneeboard PNGs (Pillow)
- `dcsgen/unitnames.py` - resolves our unit names against whatever pydcs is installed
- `dcsgen/mods.py` - finds installed aircraft mods and their DCS type ids
- `dcsgen/theme.py` - the dark blue window theme
- `dcsgen/builder.py` - writes the `.miz` with pydcs
- `dcsgen/gui_logic.py` - which options are valid together, conflict repair (pure Python)
- `dcsgen/gui.py` - the Tkinter window, a thin layer over `gui_logic`
- `tests/` - `python -m unittest discover -s tests -t .`

## Options added in 0.4

- **Start state** (cold, hot, runway), **time of day** (daytime about 11:00, night, sunrise +10 min,
  pre-sunrise -10 min, sunset -25 min, random), **season** and **weather** (scattered clouds by
  default, plus clear, few, broken, overcast, rain, thunderstorm, fog, haze or random).
  Sunrise and sunset are calculated per map and date, so they are close but not exact.
- **Ground units** 60-100 around the target and **static objects** 20-50 on the airfields and target.
  Statics are not counted in the unit limit.
- **Target photos**: stylised overhead photos (wide and close-up) for the objective, and for the SAM
  site when a SEAD flight is in the package. They are drawn from the mission layout, not real imagery.
- **All aircraft** toggle: offer every aircraft of your side instead of only historical ones.
  Otherwise each aircraft is also offered one era after its own.
- Three suggested airbases per map and side, the Germany (Cold War) map and the South Atlantic map.

## Aircraft notes

- Red has few era-appropriate flyable aircraft in the early and mid Cold War (MiG-15bis,
  MiG-21bis). All nine Flaming Cliffs 3 aircraft are offered in their historical eras.
- F-100D (early access) and the community mods A-4E-C and OV-10A Bronco are not in pydcs.
  The builder makes a stand-in class carrying the real DCS type id; for mods it reads the id from
  `Saved Games\DCS\Mods\aircraft\*\entry.lua`. Mods must be installed to appear in the cockpit.
- Kneeboard pages are written to `KNEEBOARD/<aircraft type id>/IMAGES/` inside the `.miz`.
  That layout is reported to work, but check it in-game; "Export kneeboard PNGs" is the fallback
  (copy them to `Saved Games\DCS\Kneeboard\<aircraft>\`).

## Status

Tested (79 tests): planner, timing, unit budget, validation, sides, catalog, briefing tabs,
page layout (every briefing page fits one sheet across all era/side/mission/posture
combinations), PDF and PNG output, kneeboard zip injection, name resolution and the GUI's form
logic and window code (against a fake tkinter).

**Not tested: `builder.py` against real pydcs**, and the real Tkinter window and dark theme.
Optional features fail soft and are reported as warnings; unit names that pydcs does not know are
skipped and listed. Run `check-units` and send `setup_report.txt` / `pydcs_names.txt` so names
can be corrected.

Not built yet: aerial-style target imagery (2 per target), a standalone .exe installer,
applied weather, radio frequencies and TACAN, tankers and AWACS, AI skill levels,
per-aircraft payloads, a real land/sea check for target placement. Iraq and South Atlantic maps
are hidden because pydcs 1.0.0 lacks them.

## What's new in 0.9

- **An icon and a proper name.** The program has its own icon (title bar and taskbar). Run
  `make_shortcut.bat` once to get a "DCS Strike Package" shortcut with the icon on your Desktop.
  `start.bat` is now "DCS Strike Package.bat" (the old name still works).

- **Airfield attack.** About one Strike in four is now an attack on an enemy airfield: aircraft parked
  in the open on the ramp, fuel and stores beside the runway, with the usual defences. The briefing
  says so. If no suitable airfield is in range it quietly becomes an ordinary strike.
- **Convoys that drive.** Enemy supply convoys run along the road toward the objective, and in an
  Active warzone a friendly convoy drives up to the front. Don't shoot the friendly one.
- **A lively front line.** In an Active warzone there are burning vehicles in the gap between the
  armies and an occasional shell landing there (a small Lua script the mission runs after a few seconds).
- **More briefing variety.** Several versions of the situation, mission, tasking and sign-off
  text for every mission type, chosen by the seed (same seed, same briefing).

## What's new in 0.8

- **A living airfield.** Your start airfield now has AA guns, trucks and a fuel truck, a few
  parked (uncontrolled) aircraft and a parked helicopter. Not used on carrier starts.
- **Helicopter traffic** in Active warzone missions: usually one to three helicopters taking
  off, flying a short leg behind your lines and landing, or arriving to land (transport, and
  sometimes a gunship).
- **No SEAD flight?** The SEAD flight only exists when there are radar SAMs to hunt, i.e.
  Medium or Heavy defences. At Light defences the package is strike + CAP, and the briefing
  notes now say so.
- **Real coastlines.** Run `fetch_coast.bat` once (needs internet). It downloads public Natural Earth
  coastline data and saves a small file in `dcsgen/data/`. Ground units, statics and airfield
  dressing are then kept on land. Without it a rougher guess is used and a warning is shown.
- **Real runways.** Run `fetch_runways.bat` once (needs internet). It downloads public OurAirports
  runway data (length, width, both ends). Airfield dressing then follows the real runway, and
  runway starts line up at the real threshold. Fictional airfields keep the heading-only layout.
- `probe_land.bat` (or `py -m dcsgen probe-land`) writes `pydcs_land.txt`, a report of whether your
  pydcs can tell land from water; used to stop units spawning in the sea.
- Ground dressing is placed 1.3-2.4 km from the airfield reference point; if a truck ever sits
  on a taxiway, change the seed.

## What's new in 0.4

- Renamed **DCS Strike Package** (the Python package is still `dcsgen`).
- **Enemy defences**: Light (no SAMs, AAA only), Medium (1-2 SAM sites), Heavy (5-7 layered sites plus
  an AAA belt). SEAD and DEAD always need a SAM, so Light is raised to Medium for those. CLI: `--defences`.
- **Red aircraft**: Su-27/Su-33/J-11A can now fly strike and CAS; added MiG-19P, L-39C/ZA, JF-17 and the
  community-mod MiG-23MLD, MiG-25PD, MiG-27K, Su-17M4, Su-24M, Su-30, Su-34, MiG-31.
- **Sunrise/sunset timing** uses each map's real clock offset and the target's real position
  (southern-hemisphere maps flip the seasons). Times are estimates; DCS may differ by a few minutes.
- **Target photos** draw unit silhouettes (tanks, IFVs, trucks, SAM launchers, radars, AAA) instead of boxes.
- **Runway starts** line the aircraft up at the departure end of the runway, facing along it. The
  runway length is not in pydcs, so the distance is an estimate.

## What's new in 0.5

- **Tidy ground groups**: parked groups sit in rows side by side, convoys drive nose to tail in column,
  AAA and front-line groups stand in a line, and SAM sites put radars in the middle with launchers around
  them. The same layout is used in the mission and in the target photos.
- **AWACS** (on by default; only where one existed for that side and date: E-3A, E-2C from a carrier,
  A-50) and an optional **tanker** matched to your aircraft: KC-135 for boom receivers, KC-135 MPRS
  (boom and drogue) or KC-130 for probe aircraft, Il-78M for red. Frequencies and TACAN are in the briefing.
- **Target position** in the briefing in the format of the era (chart plotting before GPS, INS lat/long,
  GPS, then MGRS for modern), plus bearing and range from your base.
- **Imagery** pages now carry an intel story (source and 12-72 hours old) instead of a "stylised" note.
- Mission files are named `Strike_Package_<era>_<side>_<mission>_<map>_<seed>.miz`.

## What's new in 0.6

- **Pre-emptive strike timing**: the scrambled fighters are timed to reach their intercept point after you
  have hit the target, so most of the fight is on the way out. There is a 15% chance per mission that they
  are already airborne and meet you before the target.
- **Shorter flights**: the plan aims for 15-35 minutes of total flight time, averaging about 20.
- **New mission type: Intercept**. You scramble from the runway (hot start on a carrier) to meet an incoming
  enemy strike package. The raid's size follows the Defences setting (light: 2 bombers, medium: 3 plus
  2 escorts, heavy: 4 plus 4). Your other flights follow you up.
- **New mission type: Naval strike**. The target is an enemy warship, cargo ship or aircraft carrier at sea.
  The Defences setting changes how many escort ships defend it. Only offered on maps with open water
  (not Nevada or Afghanistan). Target photos show the ships on open water.

Not testable outside DCS: ship and raid placement is built with pydcs and has only been checked in a
planning and rendering test harness, so please report anything odd (ship on land, raid not moving).

## Countries and liveries (0.7)

- **My country / Enemy country** drop-downs. Blue defaults to the United States, Red to Russia (the Soviet
  Union before 1992); the list offers other traditionally Blue or Red countries for the era.
- **Enemy country = Random** picks by era: Russia/USSR 40% against a Blue player, the USA 70% against a
  Red player, the rest weighted to countries that fit the era (for example Iran, China, Syria in the
  modern era). Equipment still follows the era's Red/Blue kit; the country sets the flag, liveries and
  the wording in the briefing.
- **Liveries**: each aircraft type gets one random stock livery for its country, shared by every flight
  of that type. If your pydcs lists none for a country, the default skin is kept and a warning says so.
- **Headers**: each country has its own air-force title, band colour and roundel on the briefing and
  kneeboard pages. US flights use the United States Air Force header, except F/A-18C, F-14 and A-4E
  (United States Navy) and the AV-8B (Marine Corps).
- **Liveries source**: dcsgen reads the livery folders in your DCS install and Saved Games itself. If it
  cannot find DCS, put the install path (for example `C:\Program Files\Eagle Dynamics\DCS World`) in a
  text file named `dcs_path.txt` next to `start.bat`.
