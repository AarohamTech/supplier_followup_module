# One-shot: fast-forward the Mumbai box to latest main, enable
# COMMITMENT_VIA_EMAIL_ENABLED (parse supplier reply tables into commitments —
# safe now that the parser rejects forwarded-header garbage), restart the
# backend, and poll /healthz.
#
# Run:  powershell -ExecutionPolicy Bypass -File backend\deploy_latest_to_box.ps1
# Box IP is DYNAMIC - if the connection times out, update it from the AWS console.
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.206.119.190"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

# NOTE: no double quotes inside the remote block (PowerShell mangles them).
$remote = @'
set -e
cd ~/supplier_followup_module
echo -n 'box was at: '; git rev-parse --short HEAD
git fetch origin main
git reset --hard origin/main
echo -n 'box now at: '; git rev-parse --short HEAD
cd backend
if grep -q ^COMMITMENT_VIA_EMAIL_ENABLED= .env; then
  sed -i s/^COMMITMENT_VIA_EMAIL_ENABLED=.*/COMMITMENT_VIA_EMAIL_ENABLED=true/ .env
else
  printf 'COMMITMENT_VIA_EMAIL_ENABLED=true\n' >> .env
fi
# CRM ingest must be durable in .env — the Settings-UI toggle is in-process
# only and every restart silently disabled ingestion until now.
if grep -q ^CRM_INGEST_ENABLED= .env; then
  sed -i s/^CRM_INGEST_ENABLED=.*/CRM_INGEST_ENABLED=true/ .env
else
  printf 'CRM_INGEST_ENABLED=true\n' >> .env
fi
echo -n 'flags: '; grep -E '^(COMMITMENT_VIA_EMAIL_ENABLED|CRM_INGEST_ENABLED)=' .env | tr '\n' ' '; echo
sudo systemctl restart sfa-backend
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo backend healthy after ~$((i*2))s - LATEST MAIN IS LIVE, COMMITMENT-FROM-EMAIL ON
    exit 0
  fi
  sleep 2
done
echo healthcheck FAILED - recent logs:
sudo journalctl -u sfa-backend --since -3min --no-pager | tail -30
exit 1
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
