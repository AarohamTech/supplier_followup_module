# One-shot: persist CRM_INGEST_ENABLED=true in the Mumbai box's backend/.env
# and restart. The ingest was previously enabled only via the runtime Settings
# toggle, which does not survive a service restart — this makes it durable.
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.206.119.190"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

$remote = @'
set -e
cd ~/supplier_followup_module/backend
if grep -q ^CRM_INGEST_ENABLED= .env; then
  sed -i s/^CRM_INGEST_ENABLED=.*/CRM_INGEST_ENABLED=true/ .env
else
  printf 'CRM_INGEST_ENABLED=true\n' >> .env
fi
echo -n 'flag: '; grep ^CRM_INGEST_ENABLED= .env
sudo systemctl restart sfa-backend
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo backend healthy after ~$((i*2))s - CRM INGEST ENABLED DURABLY
    exit 0
  fi
  sleep 2
done
echo healthcheck FAILED - recent logs:
sudo journalctl -u sfa-backend --since -3min --no-pager | tail -30
exit 1
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
