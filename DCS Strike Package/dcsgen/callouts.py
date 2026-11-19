"""AWACS kill calls: "Hammer one, Overlord. Splash one." in a voice, plus the same as on-screen text.

The voice clips are made at build time with Windows' own speech (System.Speech, through PowerShell),
so nothing has to be installed. Without it the calls still appear as text."""

import os
import subprocess
import sys

KINDS = {                      # kind -> what the AWACS says after the callsigns
    "air": ("Splash one.", "Splash one"),
    "ground": ("Target destroyed.", "Target destroyed"),
    "ship": ("Ship destroyed.", "Ship destroyed"),
}

_NUMBERS = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
            "7": "seven", "8": "eight", "9": "nine", "0": "zero"}


def spoken(callsign):
    """'Hammer 1' -> 'Hammer one' so the voice reads it the way a pilot would."""
    return " ".join(_NUMBERS.get(w, w) for w in str(callsign).replace("-", " ").split())


def slug(text):
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def plan_clips(flight_callsigns, awacs_name):
    """{group name: {kind: (file name, spoken text, on-screen text)}}"""
    out = {}
    for cs in flight_callsigns:
        out[cs] = {}
        for kind, (say, show) in KINDS.items():
            text = f"{spoken(cs)}, {awacs_name}. {say}"
            out[cs][kind] = (f"awacs_{slug(cs)}_{kind}.wav", text, f"{awacs_name}: {cs}, {show.lower()}.")
    return out


def synthesise(clips, folder):
    """Write the wav files with Windows speech. Returns the file names actually made."""
    if sys.platform != "win32":
        return set()
    items = [(fn, said) for per in clips.values() for fn, said, _show in per.values()]
    if not items:
        return set()
    os.makedirs(folder, exist_ok=True)
    lines = ["Add-Type -AssemblyName System.Speech",
             "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
             "$s.Rate = 1"]
    for fn, said in items:
        path = os.path.join(folder, fn).replace("'", "''")
        lines.append(f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{said.replace(chr(39), chr(39) * 2)}')")
    lines.append("$s.Dispose()")
    script = os.path.join(folder, "speak.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
                       check=True, capture_output=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:  # noqa: BLE001 - no speech available: the text calls still work
        return set()
    return {fn for fn, _ in items if os.path.exists(os.path.join(folder, fn))}


def kill_call_lua(clips, made, side):
    """A Lua event handler: when one of our flights kills something, the AWACS calls it."""
    def q(s):
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
    rows = []
    for group, per in clips.items():
        inner = ", ".join(
            f"{kind}={{file={q(fn) if fn in made else 'nil'}, text={q(show)}}}"
            for kind, (fn, _said, show) in per.items())
        rows.append(f"  [{q(group)}] = {{{inner}}},")
    return f"""local CALLS = {{
{chr(10).join(rows)}
}}
local SIDE = coalition.side.{side.upper()}
local lastCall = {{}}
local handler = {{}}
function handler:onEvent(e)
  if e.id ~= world.event.S_EVENT_KILL or not e.initiator or not e.target then return end
  local ok, err = pcall(function()
    local g = e.initiator:getGroup()
    if not g then return end
    local name = g:getName()
    local call = CALLS[name]
    if not call then return end
    if e.target:getCoalition() == SIDE then return end
    local kind = 'ground'
    local cat = e.target:getCategory()
    if cat == Object.Category.UNIT then
      local c = e.target:getDesc().category
      if c == Unit.Category.AIRPLANE or c == Unit.Category.HELICOPTER then kind = 'air'
      elseif c == Unit.Category.SHIP then kind = 'ship' end
    end
    local now = timer.getTime()
    if lastCall[name .. kind] and now - lastCall[name .. kind] < 6 then return end
    lastCall[name .. kind] = now
    local c = call[kind]
    if not c then return end
    if c.file then trigger.action.outSoundForCoalition(SIDE, c.file) end
    trigger.action.outTextForCoalition(SIDE, c.text, 8)
  end)
end
world.addEventHandler(handler)
"""
