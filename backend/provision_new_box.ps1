# One-shot: provision a BLANK Ubuntu EC2 box into a working sfa-backend host.
#
# Use this when the box is brand new (no ~/supplier_followup_module, no venv, no
# systemd unit). For an already-provisioned box, don't use this - push to main
# and let .github/workflows/deploy-backend.yml do it.
#
# Installs: python3-venv, git, uv (CI needs uv), the repo, the venv, backend/.env
# (built from your LOCAL backend\.env with production overrides applied), and the
# sfa-backend systemd unit. Then polls /healthz.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File backend\provision_new_box.ps1 `
#       -BoxIp 13.206.119.190 -FrontendUrl https://your-app.vercel.app
#
# Needs: %USERPROFILE%\Downloads\MUMBAI_SERVER.pem and a filled-in backend\.env.
param(
    [string]$BoxIp       = "13.206.119.190",
    [string]$FrontendUrl = "",
    [string]$Pem         = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"
)
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@$BoxIp"

if (-not (Test-Path $Pem)) { throw "SSH key not found: $Pem" }
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { throw "Local backend\.env not found - it is the source of the box's secrets." }

# ---- Build the production .env from the local one -------------------------
# The local file is a DEV config (DEBUG=true, localhost CORS). Override the
# handful of values that must differ in production; carry everything else
# (DATABASE_URL, JWT_SECRET, S3_*, IMAP/SMTP, LLM/OpenAI) across verbatim.
$lines = Get-Content $envFile
$out   = New-Object System.Collections.Generic.List[string]
foreach ($l in $lines) {
    if ($l -match '^DEBUG=') { $out.Add('DEBUG=false'); continue }
    if ($l -match '^CORS_ORIGINS=' -and $FrontendUrl) {
        $out.Add('CORS_ORIGINS=["' + $FrontendUrl.TrimEnd('/') + '"]'); continue
    }
    $out.Add($l)
}
if (-not ($lines -match '^DEBUG='))            { $out.Add('DEBUG=false') }
# VM/container defaults per docs/DEPLOY.md (NOT the serverless ones).
if (-not ($lines -match '^RUN_STARTUP_INIT=')) { $out.Add('RUN_STARTUP_INIT=true') }
if (-not ($lines -match '^DB_USE_NULLPOOL='))  { $out.Add('DB_USE_NULLPOOL=false') }

$autoFollowup = ($out | Where-Object { $_ -match '^AUTO_PO_FOLLOWUP_ENABLED=' }) -join ''
$smtp         = ($out | Where-Object { $_ -match '^SMTP_ENABLED=' }) -join ''
Write-Host "About to provision $BoxHost" -ForegroundColor Cyan
Write-Host "  mail sending : $smtp"
Write-Host "  auto followup: $autoFollowup"
if (-not $FrontendUrl) {
    Write-Host "  CORS_ORIGINS : left as-is (no -FrontendUrl given)" -ForegroundColor Yellow
}
Write-Host ""

# Ship the .env with scp, NOT by piping it into ssh. Piping a string to a native
# command on Windows PowerShell 5.1 can prepend a UTF-8 BOM, which corrupts the
# FIRST key (APP_NAME -> ﻿APP_NAME) and makes pydantic reject the config.
# WriteAllText with UTF8Encoding($false) guarantees no BOM and LF endings.
$payload = ($out -join "`n") + "`n"
$payload = $payload.Replace([string][char]0xFEFF, '')
$tmp = Join-Path $env:TEMP "sfa_box.env"
[IO.File]::WriteAllText($tmp, $payload, (New-Object System.Text.UTF8Encoding $false))
Write-Host "Copying .env to the box..." -ForegroundColor Cyan
scp -i $Pem -o StrictHostKeyChecking=accept-new $tmp "${BoxHost}:/tmp/box.env"
$scpCode = $LASTEXITCODE
Remove-Item $tmp -Force
if ($scpCode -ne 0) { throw "scp of .env to the box failed." }

# NOTE: no double quotes anywhere in the remote block - PowerShell mangles
# embedded double quotes when passing the block as one ssh argument.
$remote = @'
set -e

echo '=== installing system packages ==='
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip git curl

echo '=== installing uv (the CI deploy workflow calls it) ==='
if ! [ -x $HOME/.local/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH=$HOME/.local/bin:$PATH
uv --version

echo '=== cloning repo ==='
cd $HOME
if [ ! -d supplier_followup_module ]; then
  git clone https://github.com/AarohamTech/supplier_followup_module.git
fi
cd supplier_followup_module
git fetch --quiet origin main
git reset --hard origin/main
git log --oneline -1

echo '=== python venv + deps ==='
cd backend
# Do NOT use the system python3. Recent Ubuntu ships 3.14, and pydantic-core
# 2.23.4 has no 3.14 wheel - uv falls back to a source build and pyo3 0.22.2
# hard-caps at 3.13, so it fails. Pin an uv-managed 3.12, which has prebuilt
# wheels for every pin in requirements.txt.
uv python install 3.12
# Always recreate - uv does it in about a second, and it guarantees we are not
# reusing a venv built by the wrong interpreter from an earlier failed run.
rm -rf .venv
uv venv --python 3.12 .venv
.venv/bin/python --version
uv pip install --python .venv/bin/python -r requirements.txt

echo '=== installing .env ==='
mv /tmp/box.env .env
chmod 600 .env
grep -c . .env | xargs -I{} echo '.env installed with {} lines'
# Guard against BOM/encoding damage: a stray BOM corrupts the first key only,
# which surfaces much later as a confusing pydantic 'APP_NAME Field required'.
if ! head -1 .env | grep -q '^APP_NAME='; then
  echo FATAL - first line of .env is not APP_NAME, the file got mangled in transit
  head -1 .env | od -c | head -2
  exit 1
fi

echo '=== installing systemd unit ==='
sudo cp ../deploy/backend.service /etc/systemd/system/sfa-backend.service
sudo systemctl daemon-reload
sudo systemctl enable sfa-backend
sudo systemctl restart sfa-backend

echo '=== waiting for /healthz (schema + pgvector init takes ~15s) ==='
for i in $(seq 1 45); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo BACKEND HEALTHY after ~$((i*2))s
    curl -s http://localhost:8000/healthz
    echo
    sudo systemctl is-active sfa-backend
    exit 0
  fi
  sleep 2
done
echo HEALTHCHECK FAILED - recent logs:
sudo journalctl -u sfa-backend --since -5min --no-pager | tail -40
exit 1
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
if ($LASTEXITCODE -ne 0) { throw "Provisioning failed - see the logs above." }

Write-Host ""
Write-Host "Box is healthy on localhost. Now verifying from the internet..." -ForegroundColor Cyan
try {
    $r = Invoke-WebRequest -Uri "http://${BoxIp}:8000/healthz" -TimeoutSec 20 -UseBasicParsing
    Write-Host "  external /healthz -> $($r.StatusCode) $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  external /healthz FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  -> the app is up but port 8000 is not open to the internet." -ForegroundColor Yellow
    Write-Host "     Add an inbound rule: Custom TCP 8000 from 0.0.0.0/0 in the security group." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "REMAINING MANUAL STEPS:" -ForegroundColor Cyan
Write-Host "  1. Allocate + associate an Elastic IP (or this breaks again on next restart)."
Write-Host "  2. Vercel: NEXT_PUBLIC_API_BASE = http://<elastic-ip>:8000  -> then REDEPLOY"
Write-Host "     (rewrites bake at build time; saving the var alone does nothing)."
Write-Host "  3. GitHub repo secrets: EC2_HOST = <elastic-ip>,"
Write-Host "     EC2_SSH_KEY = contents of MUMBAI_SERVER.pem  (both are currently stale)."
