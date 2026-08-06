$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $repositoryRoot ".runtime\test-environment.json"
if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
  Write-Output "Brak aktywnego środowiska testowego."
  exit 0
}

$state = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($state.repository -ne $repositoryRoot) {
  throw "Plik PID należy do innego repozytorium."
}

function Stop-ProjectProcessTree {
  param([int]$RootPid, [string]$Marker)
  $all = @(Get-CimInstance Win32_Process)
  $root = $all | Where-Object ProcessId -eq $RootPid | Select-Object -First 1
  if (-not $root) { return }
  if (-not $root.CommandLine -or -not $root.CommandLine.Contains($Marker)) {
    throw "Proces PID $RootPid nie pasuje do zapisanego polecenia projektu."
  }
  $ids = [System.Collections.Generic.List[int]]::new()
  $ids.Add($RootPid)
  for ($index = 0; $index -lt $ids.Count; $index++) {
    foreach ($child in $all | Where-Object ParentProcessId -eq $ids[$index]) {
      if (-not $ids.Contains([int]$child.ProcessId)) { $ids.Add([int]$child.ProcessId) }
    }
  }
  for ($index = $ids.Count - 1; $index -ge 0; $index--) {
    Stop-Process -Id $ids[$index] -Force -ErrorAction SilentlyContinue
  }
}

Stop-ProjectProcessTree -RootPid ([int]$state.pipeline.pid) -Marker ([string]$state.pipeline.marker)
Stop-ProjectProcessTree -RootPid ([int]$state.next.pid) -Marker ([string]$state.next.marker)
Remove-Item -LiteralPath $pidFile -Force
Write-Output "Środowisko testowe zatrzymane."
