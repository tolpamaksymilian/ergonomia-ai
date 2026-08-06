$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDirectory = Join-Path $repositoryRoot ".runtime"
$pidFile = Join-Path $runtimeDirectory "test-environment.json"
$pythonPath = Join-Path $repositoryRoot "worker\.venv\Scripts\python.exe"
$pipelineManager = Join-Path $repositoryRoot "worker\src\pipeline_manager.py"

if (Test-Path -LiteralPath $pidFile) {
  throw "Środowisko ma już plik PID. Najpierw uruchom scripts\stop-test-environment.ps1."
}
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) { throw "Nie znaleziono Node.js." }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw "Nie znaleziono npm.cmd." }
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) { throw "Nie znaleziono FFmpeg w PATH." }
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw "Brak worker/.venv dla Python 3.11." }
if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot ".env.local") -PathType Leaf)) { throw "Brak .env.local." }
if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot "worker\.env") -PathType Leaf)) { throw "Brak worker/.env." }

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

$escapedRoot = $repositoryRoot.Replace("'", "''")
$escapedPython = $pythonPath.Replace("'", "''")
$escapedManager = $pipelineManager.Replace("'", "''")
$nextCommand = "Set-Location -LiteralPath '$escapedRoot'; & npm.cmd run dev"
$pipelineCommand = "Set-Location -LiteralPath '$escapedRoot'; & '$escapedPython' '$escapedManager'"

$nextProcess = Start-Process powershell.exe -ArgumentList @("-NoProfile", "-Command", $nextCommand) `
  -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $runtimeDirectory "next.stdout.log") `
  -RedirectStandardError (Join-Path $runtimeDirectory "next.stderr.log")

try {
  $pipelineProcess = Start-Process powershell.exe -ArgumentList @("-NoProfile", "-Command", $pipelineCommand) `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDirectory "pipeline.stdout.log") `
    -RedirectStandardError (Join-Path $runtimeDirectory "pipeline.stderr.log")
} catch {
  Stop-Process -Id $nextProcess.Id -Force -ErrorAction SilentlyContinue
  throw
}

@{
  repository = $repositoryRoot
  next = @{ pid = $nextProcess.Id; marker = "npm.cmd run dev" }
  pipeline = @{ pid = $pipelineProcess.Id; marker = "pipeline_manager.py" }
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $pidFile -Encoding UTF8

Write-Output "Środowisko testowe uruchomione."
Write-Output "Aplikacja: http://localhost:3000"
Write-Output "Logi: .runtime\next.stdout.log oraz .runtime\pipeline.stdout.log"
