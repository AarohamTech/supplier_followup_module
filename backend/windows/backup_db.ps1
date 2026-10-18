# Nightly backup of the local "hconnect" Postgres database (Supabase used to do
# this for us). Custom-format dump, restorable with pg_restore; keeps 14 days.
# Registered by install_task.ps1 as the "HConnect DB Backup" task (02:30 daily).
$ErrorActionPreference = 'Stop'
$bin = 'C:\Program Files\PostgreSQL\18\bin'
$dir = 'D:\hconnect-backups'
New-Item -ItemType Directory -Force $dir | Out-Null
$env:PGPASSWORD = (Get-Content 'C:\hconnect\dbpw.txt' -Raw).Trim()
$file = "$dir\hconnect-$(Get-Date -Format yyyyMMdd-HHmm).dump"
& "$bin\pg_dump.exe" -h 127.0.0.1 -U hconnect -d hconnect -Fc -f $file
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed ($LASTEXITCODE)" }
Get-ChildItem "$dir\hconnect-*.dump" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force
"backup ok: $file ($([int]((Get-Item $file).Length / 1MB)) MB)"
