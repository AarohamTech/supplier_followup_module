# One-shot: restart sfa-backend on the Mumbai box and poll /healthz.
# Used after a DB clear so startup init re-seeds (admin, mail templates,
# schema/pgvector) and the CRM ingest refills procurement data.
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.206.119.190"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

$remote = @'
set -e
sudo systemctl restart sfa-backend
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo backend healthy after ~$((i*2))s
    exit 0
  fi
  sleep 2
done
echo healthcheck FAILED - recent logs:
sudo journalctl -u sfa-backend --since -3min --no-pager | tail -30
exit 1
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
