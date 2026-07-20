# One-shot: set AUTO_PO_FOLLOWUP_ENABLED=true in the Mumbai box's backend/.env,
# restart the backend, and poll /healthz. From this moment the ingest cron
# auto-queues AND SENDS green/yellow/red/black follow-up mails to every supplier
# that has an active email mapping in Email Master.
#
# Run:  powershell -ExecutionPolicy Bypass -File backend\enable_auto_followups_on_box.ps1
# Box IP is DYNAMIC - if the connection times out, update it from the AWS console.
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.207.55.174"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

# NOTE: no double quotes inside the remote block (PowerShell mangles them).
$remote = @'
set -e
cd ~/supplier_followup_module/backend
echo -n 'before: '; grep ^AUTO_PO_FOLLOWUP_ENABLED= .env || echo 'AUTO_PO_FOLLOWUP_ENABLED not set (default false)'
if grep -q ^AUTO_PO_FOLLOWUP_ENABLED= .env; then
  sed -i s/^AUTO_PO_FOLLOWUP_ENABLED=.*/AUTO_PO_FOLLOWUP_ENABLED=true/ .env
else
  printf 'AUTO_PO_FOLLOWUP_ENABLED=true\n' >> .env
fi
echo -n 'after:  '; grep ^AUTO_PO_FOLLOWUP_ENABLED= .env
sudo systemctl restart sfa-backend
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo backend healthy after ~$((i*2))s - AUTO PO FOLLOW-UPS ARE LIVE
    exit 0
  fi
  sleep 2
done
echo healthcheck FAILED - recent logs:
sudo journalctl -u sfa-backend --since -3min --no-pager | tail -30
exit 1
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
