# One-shot: point company 101 (Enterprise) at its CRM desk and restart.
# 101 reuses 102's CRM login/token — only the desk id differs — so a single
# CRM_101_DESK_ID line activates its ingestion (see docs/RUNBOOK-activate-company-101.md).
param(
    [string]$DeskId = "101",
    [string]$BoxIp = "13.206.119.190"
)
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@$BoxIp"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"
if (-not (Test-Path $Pem)) { throw "SSH key not found: $Pem" }

# LITERAL here-string: bash keeps its own $ and $(...).
$remote = @'
set -e
cd ~/supplier_followup_module/backend
if grep -q "^CRM_101_DESK_ID=" .env; then
  grep -v "^CRM_101_DESK_ID=" .env > .env.tmp && mv .env.tmp .env
fi
printf 'CRM_101_DESK_ID=%s\n' '__DESK__' >> .env
echo 'CRM keys (passwords masked):'
grep -E '^CRM' .env | sed -E 's/(PASSWORD=).+/\1***MASKED***/'
sudo systemctl restart sfa-backend
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "backend healthy after ~$((i*2))s"
    break
  fi
  sleep 2
done
echo 'waiting for an ingest cycle covering both companies (up to ~4 min)...'
for i in $(seq 1 48); do
  sleep 5
  if sudo journalctl -u sfa-backend --since -6min --no-pager | grep -qi 'crm_ingestion_runner'; then
    break
  fi
done
sudo journalctl -u sfa-backend --since -6min --no-pager | grep -iE 'crm_ingestion|101' | tail -6
'@

$remote = $remote.Replace('__DESK__', $DeskId)
ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
