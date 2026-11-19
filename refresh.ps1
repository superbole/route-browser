# Fetch new activities and rebuild the page. The nightly task runs this (README: Keep it up to date).
# The output of the last run is in ~/.route-browser/refresh.log; a refused Garmin key also shows on the page.
Set-Location $PSScriptRoot
$log = Join-Path $HOME ".route-browser\refresh.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
python fetch.py *> $log
python build_map.py *>> $log
