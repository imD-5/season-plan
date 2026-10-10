# Open the Season board in its own window (the Windows counterpart of Season.app).
# Starts the server first if it is not answering. The Start menu "Season" shortcut runs this.
# Keep this file ASCII: Windows PowerShell 5.1 misreads UTF-8 without a BOM.

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Port = if ($env:SEASON_PORT) { [int]$env:SEASON_PORT } else { 8765 }
$Url  = "http://127.0.0.1:$Port/"

function Test-Board {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 ($Url + 'api/board') | Out-Null; return $true }
    catch { return $false }
}

if (-not (Test-Board)) {
    $Pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
    Start-Process -FilePath $Pythonw -ArgumentList ('"' + (Join-Path $Root 'serve.py') + '"') -WorkingDirectory $Root
    for ($i = 0; $i -lt 40 -and -not (Test-Board); $i++) { Start-Sleep -Milliseconds 250 }
}

# Edge "app" mode: a plain window with no tabs or address bar, sized like the Mac app.
$candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$browser = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if ($browser) {
    Start-Process -FilePath $browser -ArgumentList @("--app=$Url", '--window-size=620,800')
} else {
    Start-Process $Url      # default browser, as a normal tab
}
