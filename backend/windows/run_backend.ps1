# Keeps the H-Connect backend running on the Windows server (started at boot by
# the "HConnect Backend" scheduled task, see install_task.ps1). Restarts uvicorn
# if it ever exits, writes one log file per day and keeps 14 days of logs.
#
# Layout (C:\hconnect):
#   app\backend\        code (deploy.ps1 replaces it; .env is preserved)
#   app\backend\.env    settings copied from the old AWS box
#   venv\               Python 3.12 virtualenv
#   dbpw.txt            password of the local Postgres role "hconnect"
#   logs\               backend-YYYYMMDD.log
$root = 'C:\hconnect'
$port = 3000
$backend = "$root\app\backend"
New-Item -ItemType Directory -Force "$root\logs" | Out-Null

# Settings that differ from the AWS .env are forced here (real env vars beat .env).
$pw = (Get-Content "$root\dbpw.txt" -Raw).Trim()
$env:DATABASE_URL = "postgresql+psycopg2://hconnect:$pw@127.0.0.1:5432/hconnect"
$env:RAG_ENABLED = 'false'          # no pgvector on this Postgres
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'

while ($true) {
    $log = "$root\logs\backend-$(Get-Date -Format yyyyMMdd).log"
    Get-ChildItem "$root\logs\backend-*.log" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    if (-not (Test-Path "$backend\.env")) {
        "$(Get-Date -Format s) waiting for $backend\.env" | Add-Content $log
        Start-Sleep -Seconds 60
        continue
    }
    "$(Get-Date -Format s) starting uvicorn on :$port" | Add-Content $log
    Push-Location $backend
    cmd /c "`"$root\venv\Scripts\python.exe`" -m uvicorn app.main:app --host 0.0.0.0 --port $port --proxy-headers >> `"$log`" 2>&1"
    $code = $LASTEXITCODE
    Pop-Location
    "$(Get-Date -Format s) uvicorn exited ($code), restarting in 10s" | Add-Content $log
    Start-Sleep -Seconds 10
}
