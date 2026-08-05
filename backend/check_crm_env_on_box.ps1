# One-shot READ-ONLY: list CRM-related config lines on the box (passwords masked).
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.206.119.190"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

$remote = @'
cd ~/supplier_followup_module/backend
echo '--- CRM lines in .env (values masked) ---'
grep -E '^CRM' .env | sed -E 's/(PASSWORD=).+/\1***MASKED***/' || echo 'NO CRM lines at all'
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
