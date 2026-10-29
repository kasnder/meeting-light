param([string]$Python, [switch]$NoStartup)
$ErrorActionPreference = 'Stop'
$projectDir = Join-Path $PSScriptRoot 'source'
if (-not $Python) {
    $candidates = Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Python') -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'pythoncore-*' } | Sort-Object Name -Descending
    foreach ($candidate in $candidates) {
        $candidateExe = Join-Path $candidate.FullName 'python.exe'
        if (Test-Path -LiteralPath $candidateExe) { $Python = $candidateExe; break }
    }
}
if (-not $Python) { throw 'Pass the installed Python path: .\Install.ps1 -Python C:\path\to\python.exe' }
& $Python -c 'import sys, tkinter; assert sys.version_info >= (3,12)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ with Tkinter is required.' }
$environmentDir = Join-Path $projectDir '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $environmentDir 'Scripts\python.exe'))) {
    & $Python -m venv $environmentDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Python environment.' }
}
$appPython = Join-Path $environmentDir 'Scripts\python.exe'
& $appPython -m pip install --only-binary=:all: -r (Join-Path $projectDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not $NoStartup) {
    & $appPython (Join-Path $projectDir 'run.py') --enable-startup
    if ($LASTEXITCODE -ne 0) { throw 'Startup registration failed.' }
}
# Create an ordinary Windows shortcut; no script runs when it is opened.
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $PSScriptRoot 'Meeting Light.lnk'))
$shortcut.TargetPath = Join-Path $environmentDir 'Scripts\pythonw.exe'
$shortcut.Arguments = '"' + (Join-Path $projectDir 'run.py') + '"'
$shortcut.WorkingDirectory = $projectDir
$shortcut.IconLocation = Join-Path $projectDir 'assets\meetinglight.ico'
$shortcut.Save()
Start-Process -FilePath (Join-Path $environmentDir 'Scripts\pythonw.exe') -ArgumentList ('"' + (Join-Path $projectDir 'run.py') + '" --background') -WindowStyle Hidden
Write-Output 'Meeting Light is running. Open Upcoming events or Settings from its blue calendar tray icon.'
