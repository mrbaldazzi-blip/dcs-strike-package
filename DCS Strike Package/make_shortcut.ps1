# Creates "DCS Strike Package" shortcuts (with the icon) in this folder and on the Desktop.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$icon = Join-Path $here "dcsgen\assets\icon.ico"
$pyw = $env:DCSGEN_PYW
if (-not $pyw -or -not (Test-Path $pyw)) { $pyw = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source }
$ws = New-Object -ComObject WScript.Shell

function Make-Link($path) {
    $s = $ws.CreateShortcut($path)
    if ($pyw) {
        $s.TargetPath = $pyw
        $s.Arguments = "-m dcsgen gui"
    } else {
        $s.TargetPath = Join-Path $here "DCS Strike Package.bat"
    }
    $s.WorkingDirectory = $here
    $s.IconLocation = "$icon,0"
    $s.Description = "DCS Strike Package mission generator"
    $s.Save()
    Write-Host "Created $path"
}

Make-Link (Join-Path $here "DCS Strike Package.lnk")
try { Make-Link (Join-Path ([Environment]::GetFolderPath("Desktop")) "DCS Strike Package.lnk") }
catch { Write-Host "Could not put one on the Desktop: $_" }
Write-Host ""
Write-Host "Done. Double-click 'DCS Strike Package' to start. (If it ever fails to open, use 'DCS Strike Package.bat' instead: it shows error messages.)"
