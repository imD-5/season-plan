# Season board for Windows: start the server at login and add a "Season" shortcut.
#
#   powershell -ExecutionPolicy Bypass -File app\windows\install.ps1           install, then start
#   powershell -ExecutionPolicy Bypass -File app\windows\install.ps1 -Remove   stop and uninstall
#
# No admin rights needed. It adds two shortcuts for the current user:
#   Startup folder   -> runs the server (pythonw, no console window) when you sign in
#   Start menu       -> "Season": opens the board in its own window (open-season.ps1)
# Keep this file ASCII: Windows PowerShell 5.1 misreads UTF-8 without a BOM.

[CmdletBinding()]
param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$Root      = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Name      = 'Season'
$Startup   = Join-Path ([Environment]::GetFolderPath('Startup')) "$Name server.lnk"
$StartMenu = Join-Path ([Environment]::GetFolderPath('Programs')) "$Name.lnk"
$Port      = if ($env:SEASON_PORT) { [int]$env:SEASON_PORT } else { 8765 }

function Stop-SeasonServer {
    # Only the pythonw that runs this checkout's serve.py; other Python processes are left alone.
    $serve = Join-Path $Root 'serve.py'
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($serve) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if ($Remove) {
    Stop-SeasonServer
    Remove-Item -LiteralPath $Startup, $StartMenu -ErrorAction SilentlyContinue
    Write-Host "Removed the Season shortcuts and stopped the server."
    exit 0
}

$Pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $Pythonw)) {
    Write-Error "No .venv yet. Run 'uv sync' in $Root first."
}

$Shell = New-Object -ComObject WScript.Shell

# 1. server at sign-in
$lnk = $Shell.CreateShortcut($Startup)
$lnk.TargetPath       = $Pythonw
$lnk.Arguments        = '"' + (Join-Path $Root 'serve.py') + '"'
$lnk.WorkingDirectory = $Root
$lnk.WindowStyle      = 7      # minimized; pythonw has no window anyway
$lnk.Description      = 'Season board server'
$lnk.Save()

# 2. "Season" in the Start menu
$Launcher = Join-Path $PSScriptRoot 'open-season.ps1'
$lnk = $Shell.CreateShortcut($StartMenu)
$lnk.TargetPath       = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
$lnk.Arguments        = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Launcher + '"'
$lnk.WorkingDirectory = $Root
$lnk.WindowStyle      = 7
$lnk.Description      = 'Season board'
$Edge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
if (Test-Path -LiteralPath $Edge) { $lnk.IconLocation = "$Edge,0" }
$lnk.Save()

# 3. (re)start the server now
Stop-SeasonServer
Start-Process -FilePath $Pythonw -ArgumentList ('"' + (Join-Path $Root 'serve.py') + '"') -WorkingDirectory $Root
for ($i = 0; $i -lt 40; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/api/board" | Out-Null
        Write-Host "Season is running at http://127.0.0.1:$Port/ (open 'Season' from the Start menu)."
        exit 0
    } catch { Start-Sleep -Milliseconds 250 }
}
Write-Error "The server did not answer on port $Port. See $Root\server.log"
