# One-shot: copy the local S3_* values from backend\.env to the Mumbai box's
# backend/.env (only if not already there), verify boto3 is installed, restart
# the backend service, and poll /healthz until it's up.
#
# Run from any PowerShell:  powershell -ExecutionPolicy Bypass -File backend\push_s3_env_to_box.ps1
# Needs: %USERPROFILE%\Downloads\MUMBAI_SERVER.pem and the box IP below.
# The box IP is DYNAMIC — if the connection times out, replace it with the
# current public IP from the AWS console (EC2 -> instance -> Public IPv4).
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.207.55.174"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

$envFile = Join-Path $PSScriptRoot ".env"
$lines = Select-String -Path $envFile -Pattern '^S3_(BUCKET|REGION|ACCESS_KEY_ID|SECRET_ACCESS_KEY)=' |
    ForEach-Object { $_.Line }
if (@($lines).Count -lt 4) {
    throw "Expected the 4 S3_* lines in backend\.env, found $(@($lines).Count). Fill them in first."
}
$payload = ($lines -join "`n") + "`n"

# NOTE: no double quotes anywhere in the remote script — PowerShell mangles
# embedded double quotes when passing the block as one ssh argument.
$remote = @'
set -e
cd ~/supplier_followup_module/backend
if grep -q ^S3_BUCKET= .env; then
  echo S3 keys already present in box .env - leaving untouched
  cat > /dev/null
else
  printf '\n' >> .env
  cat >> .env
  echo S3 keys appended to box .env
fi
.venv/bin/python -c 'import boto3; print(boto3.__version__)' && echo boto3 installed
git log --oneline -1
sudo systemctl restart sfa-backend
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo backend healthy after ~$((i*2))s - attachments are LIVE
    exit 0
  fi
  sleep 2
done
echo healthcheck FAILED - recent logs:
sudo journalctl -u sfa-backend --since -3min --no-pager | tail -30
exit 1
'@

$payload | ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
