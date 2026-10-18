# One-time: registers the "HConnect Backend" scheduled task that starts
# run_backend.ps1 at boot as SYSTEM (no login needed) and starts it now.
$ErrorActionPreference = 'Stop'
$task = 'HConnect Backend'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\hconnect\run_backend.ps1'
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $task
"registered and started '$task'"

# Nightly database backup (D:\hconnect-backups, 14 days kept).
if ($PSScriptRoot -ne 'C:\hconnect') {
    Copy-Item "$PSScriptRoot\backup_db.ps1" 'C:\hconnect\backup_db.ps1' -Force
}
$bAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\hconnect\backup_db.ps1'
$bTrigger = New-ScheduledTaskTrigger -Daily -At '02:30'
$bSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName 'HConnect DB Backup' -Action $bAction -Trigger $bTrigger `
    -Principal $principal -Settings $bSettings -Force | Out-Null
"registered 'HConnect DB Backup' (daily 02:30)"
