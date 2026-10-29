$ErrorActionPreference = 'Stop'
$entry = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'source\run.py'))
# Only stop processes whose command line names this exact application entry point.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains('"' + $entry + '"') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
$appPython = Join-Path $PSScriptRoot 'source\.venv\Scripts\python.exe'
& $appPython $entry --disable-startup
if ($LASTEXITCODE -ne 0) { throw 'Could not remove sign-in startup.' }
Write-Output 'Meeting Light stopped and sign-in startup removed. Source files, encrypted calendar data, and cal.txt were preserved.'
