# One-time: copy the backend .env (CRM login, SMTP, S3, OpenAI, JWT and
# encryption keys) from the old AWS box straight onto the Windows server. The
# file only passes through %TEMP% and is deleted.
#   powershell -ExecutionPolicy Bypass -File backend\copy_env_aws_to_windows.ps1
param(
    [string]$Aws = 'ubuntu@13.206.119.190',
    [string]$AwsKey = "$env:USERPROFILE\Downloads\MUMBAI_SERVER.pem",
    [string]$Server = 'administrator@100.122.29.21',
    [string]$Key = "$env:USERPROFILE\.ssh\id_ed25519_hconnect"
)
$ErrorActionPreference = 'Stop'
$tmp = Join-Path $env:TEMP 'hconnect-aws.env'
try {
    scp -q -i $AwsKey "${Aws}:supplier_followup_module/backend/.env" $tmp
    if (-not (Test-Path $tmp)) { throw 'could not fetch .env from AWS' }
    scp -q -i $Key $tmp "${Server}:C:/hconnect/app/backend/.env"
    ssh -i $Key $Server 'icacls C:\hconnect\app\backend\.env /inheritance:r /grant Administrators:F /grant SYSTEM:F'
    # run_backend.ps1 polls for .env every 60s and starts uvicorn once it exists.
    '.env copied; the backend starts on the Windows server within a minute'
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}
