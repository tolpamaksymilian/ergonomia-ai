param([string]$TaskName = "Ergonomia AI Pipeline Supervisor")
$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepositoryRoot "worker\.venv\Scripts\python.exe"
$Supervisor = Join-Path $RepositoryRoot "worker\src\pipeline_supervisor.py"
if (-not (Test-Path -LiteralPath $Python)) { throw "Nie znaleziono worker/.venv/Scripts/python.exe" }
$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}"' -f $Supervisor) -WorkingDirectory $RepositoryRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Lokalny Pipeline Supervisor Ergonomia AI" -Force | Out-Null
Write-Host "Zarejestrowano zadanie: $TaskName"
