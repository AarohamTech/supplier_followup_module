# Deploy origin/main's backend to the Windows server (C:\hconnect), over SSH.
# Run from the repo root on a PC that can reach the server (Tailscale today).
#   powershell -ExecutionPolicy Bypass -File backend\deploy_to_windows_server.ps1
param(
    [string]$Server = 'administrator@100.122.29.21',
    [string]$Key = "$env:USERPROFILE\.ssh\id_ed25519_hconnect",
    [string]$Ref = 'origin/main'
)
$ErrorActionPreference = 'Stop'
git fetch -q origin
$zip = Join-Path $env:TEMP 'hconnect-backend.zip'
git archive --format=zip -o $zip $Ref backend
if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
"deploying $(git rev-parse --short $Ref) to $Server"
scp -q -i $Key $zip "${Server}:C:/hconnect/backend.zip"
scp -q -i $Key backend/windows/deploy.ps1 "${Server}:C:/hconnect/deploy.ps1"
ssh -i $Key $Server 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\hconnect\deploy.ps1'
Remove-Item $zip -Force
