# One-shot READ-ONLY: probe the CRM feeds from the box (the only host the CRM
# accepts) without auth, to see which endpoints need login credentials.
$ErrorActionPreference = "Stop"
$BoxHost = "ubuntu@13.206.119.190"
$Pem = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem"

$remote = @'
probe() {
  echo "--- $1"
  curl -s -o /tmp/crm_probe.out -w 'HTTP %{http_code}, %{size_download} bytes\n' --max-time 30 "$1" || echo 'curl failed'
  head -c 200 /tmp/crm_probe.out; echo
}
B=http://hariomapp.dyndns-server.com:8599
probe $B/api/crm/GetPendingUserDesk/102
probe $B/api/procurement/getpendingpolist/102
probe $B/api/procurement/getpopdf?CompanyId=102
'@

ssh -i $Pem -o StrictHostKeyChecking=accept-new $BoxHost $remote
