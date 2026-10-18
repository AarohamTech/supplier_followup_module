# Server side of a deploy: unpacks C:\hconnect\backend.zip (a `git archive` of
# the backend folder, uploaded by deploy_to_windows_server.ps1), installs
# requirements and restarts the backend task. backend\.env is never touched.
$ErrorActionPreference = 'Stop'
$root = 'C:\hconnect'
$task = 'HConnect Backend'
$zip = "$root\backend.zip"
$stage = "$root\stage"

if (-not (Test-Path "$root\venv\Scripts\python.exe")) {
    & py -3.12 -m venv "$root\venv"
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed (is Python 3.12 installed?)' }
}

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $stage -Force

& "$root\venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
& "$root\venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "$stage\backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

$running = (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue).State -eq 'Running'
if ($running) { Stop-ScheduledTask -TaskName $task }
# The task's child python keeps running after the task stops; end it too.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn app\.main:app' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

New-Item -ItemType Directory -Force "$root\app\backend" | Out-Null
robocopy "$stage\backend" "$root\app\backend" /MIR /XF .env /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
Copy-Item "$stage\backend\windows\run_backend.ps1" "$root\run_backend.ps1" -Force
Remove-Item $stage -Recurse -Force

if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
    Start-ScheduledTask -TaskName $task
    "deployed and restarted '$task'"
} else {
    "deployed; run install_task.ps1 once to register '$task'"
}
