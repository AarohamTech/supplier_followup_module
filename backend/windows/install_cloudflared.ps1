# Cloudflare Tunnel for the backend: Vercel reaches https://api.<domain> and
# Cloudflare forwards it to http://localhost:3000 here — no router ports needed.
#
#   1) without a token: downloads the official cloudflared.exe and checks its
#      Cloudflare code signature (safe to run any time)
#   2) with -Token <tunnel token from the Cloudflare Zero Trust dashboard>:
#      installs it as the "Cloudflared" Windows service (auto-start, reconnects)
param([string]$Token)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$dir = 'C:\hconnect\cloudflared'
$exe = "$dir\cloudflared.exe"
New-Item -ItemType Directory -Force $dir | Out-Null

if (-not (Test-Path $exe)) {
    $url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile "$exe.download"
    $sig = Get-AuthenticodeSignature "$exe.download"
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Cloudflare') {
        Remove-Item "$exe.download" -Force
        throw "cloudflared signature check failed: $($sig.Status) $($sig.SignerCertificate.Subject)"
    }
    Move-Item "$exe.download" $exe -Force
}
& $exe --version

if ($Token) {
    if (Get-Service Cloudflared -ErrorAction SilentlyContinue) {
        & $exe service uninstall
    }
    & $exe service install $Token
    Start-Sleep -Seconds 5
    Get-Service Cloudflared | Select-Object Name, Status, StartType | Out-String
}
