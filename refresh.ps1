# Fetch new activities and rebuild the page. The nightly task runs this (README: Keep it up to date).
# The output of the last run is in ~/.route-browser/refresh.log; a refused Garmin key also shows on the page.
Set-Location $PSScriptRoot
# a scheduled task keeps the environment from logon, so a key saved since then is read from the registry
if (-not $env:GARMIN_PERSONAL_API_KEY) {
    $env:GARMIN_PERSONAL_API_KEY = [Environment]::GetEnvironmentVariable("GARMIN_PERSONAL_API_KEY", "User")
}
$log = Join-Path $HOME ".route-browser\refresh.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
# through cmd, so the log is plain text and Python's error messages are not wrapped as PowerShell errors
cmd /c "python fetch.py > ""$log"" 2>&1 & python build_map.py >> ""$log"" 2>&1"
