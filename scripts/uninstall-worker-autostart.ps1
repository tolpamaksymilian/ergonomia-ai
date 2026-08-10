param([string]$TaskName = "Ergonomia AI Pipeline Supervisor")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Zadanie nie jest zarejestrowane: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Usunięto zadanie: $TaskName"
