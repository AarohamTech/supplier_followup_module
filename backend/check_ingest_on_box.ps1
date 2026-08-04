# One-shot: inspect CRM ingest state on the Mumbai box (read-only).
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.206.119.190"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

$remote = @'
set -e
cd ~/supplier_followup_module/backend
echo '--- ingest-related .env flags ---'
grep -E '^(CRM_INGEST_ENABLED|CRM_DESK_ID|CRM_102|CRM_101|SCHEDULER_ENABLED|AUTO_PO_FOLLOWUP_ENABLED|COMMITMENT_VIA_EMAIL_ENABLED)' .env || echo 'none found'
echo '--- recent ingest/scheduler journal ---'
sudo journalctl -u sfa-backend --since -30min --no-pager | grep -iE 'ingest|scheduler|cron' | tail -20
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
