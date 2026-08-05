# One-shot: install the Hariom CRM login on the Mumbai box and verify ingest.
#
# WHY THIS EXISTS: the box .env is built from the LOCAL .env by
# provision_new_box.ps1, and the local file never carried CRM_LOGIN_EMAIL /
# CRM_LOGIN_PASSWORD — they were hand-added to the OLD box and died with it in
# the 2026-07-26 rebuild. Result: CRM ingestion has returned
# "CRM connection is not configured" (config resolves to None) ever since.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File backend\set_crm_login_on_box.ps1 `
#       -CrmEmail "<crm app login email>" -CrmPassword "<password>"
#
# The password is written straight to the box .env over SSH and is never echoed.
param(
    [Parameter(Mandatory = $true)][string]$CrmEmail,
    [Parameter(Mandatory = $true)][string]$CrmPassword,
    [string]$DeskId = "102",
    [string]$BoxIp = "13.206.119.190"
)
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@$BoxIp"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"
if (-not (Test-Path $Pem)) { throw "SSH key not found: $Pem" }

# set_key <KEY> <VALUE> — replace the line if present, else append.
# NOTE: no double quotes inside the remote block (PowerShell mangles them).
$remote = @"
set -e
cd ~/supplier_followup_module/backend
set_key() {
  if grep -q "^\$1=" .env; then
    grep -v "^\$1=" .env > .env.tmp && mv .env.tmp .env
  fi
  printf '%s=%s\n' "\$1" "\$2" >> .env
}
set_key CRM_LOGIN_EMAIL '$CrmEmail'
set_key CRM_LOGIN_PASSWORD '$CrmPassword'
set_key CRM_DESK_ID '$DeskId'
set_key CRM_DEVICE_ID '$DeskId'
set_key CRM_INGEST_ENABLED true
echo 'CRM keys now in .env (password masked):'
grep -E '^CRM' .env | sed -E 's/(PASSWORD=).+/\1***MASKED***/'
sudo systemctl restart sfa-backend
for i in \$(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "backend healthy after ~\$((i*2))s"
    break
  fi
  sleep 2
done
echo 'waiting for the first ingest tick (up to 4 min)...'
for i in \$(seq 1 48); do
  sleep 5
  if sudo journalctl -u sfa-backend --since -5min --no-pager | grep -qiE 'crm.*ingest|ingest.*created'; then
    sudo journalctl -u sfa-backend --since -5min --no-pager | grep -iE 'crm|ingest' | tail -5
    break
  fi
done
"@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
Write-Host ""
Write-Host "Now check the CRM Ingestion page - status should be OK (not DISABLED)." -ForegroundColor Cyan
