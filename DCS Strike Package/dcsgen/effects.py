"""Frontline atmosphere: burning vehicles and the odd shell landing in no-man's land.

Built as a small Lua script that the mission runs a few seconds after start (DCS trigger scripting:
trigger.action.effectSmokeBig for fires, trigger.action.explosion for shells). Pure text generation
so it can be tested without DCS. Positions are DCS map coordinates (x north, y east) of points in
the gap between the two armies, so the shells and fires never land on a unit.
"""


def frontline_lua(points, fires=None, shells=None, seed=0):
    """Lua source. `points` is [(x, y), ...]; `fires` / `shells` default to most / all of the points."""
    pts = list(points)
    if not pts:
        return ""
    fire_pts = pts if fires is None else list(fires)
    shell_pts = pts if shells is None else list(shells)
    fire_lines = []
    for i, (x, y) in enumerate(fire_pts):
        preset = 1 + (i + seed) % 3          # small / medium / large smoke and fire
        density = 0.55 + 0.1 * ((i * 7 + seed) % 4)
        fire_lines.append(f'  {{x={x:.1f}, y={y:.1f}, p={preset}, d={density:.2f}}},')
    shell_lines = [f"  {{x={x:.1f}, y={y:.1f}}}," for x, y in shell_pts]
    return f"""-- DCS Strike Package: frontline atmosphere
local fires = {{
{chr(10).join(fire_lines)}
}}
for i, f in ipairs(fires) do
  local h = land.getHeight({{x = f.x, y = f.y}})
  trigger.action.effectSmokeBig({{x = f.x, y = h, z = f.y}}, f.p, f.d, "dsp_fire_" .. i)
end
local shells = {{
{chr(10).join(shell_lines)}
}}
local function shell()
  local s = shells[math.random(#shells)]
  local x = s.x + math.random(-300, 300)
  local y = s.y + math.random(-300, 300)
  local h = land.getHeight({{x = x, y = y}})
  trigger.action.explosion({{x = x, y = h, z = y}}, math.random(20, 60))
  return timer.getTime() + math.random(20, 75)
end
timer.scheduleFunction(shell, nil, timer.getTime() + 25)
"""
