$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$canonicalDirectory = Join-Path $repositoryRoot "supabase\migrations"
$legacyDirectory = Join-Path $repositoryRoot "src\lib\supabase\migrations"
$required = @(
  "20260806120000_integrate_risk_worker_v1.sql",
  "20260806203000_integrate_report_worker_v1.sql",
  "20260806210500_finalize_pipeline_v021.sql"
)

foreach ($fileName in $required) {
  if (-not (Test-Path -LiteralPath (Join-Path $canonicalDirectory $fileName) -PathType Leaf)) {
    throw "Brak migracji: $fileName"
  }
}

if (Test-Path -LiteralPath $legacyDirectory) {
  $legacyFiles = @(Get-ChildItem -LiteralPath $legacyDirectory -Filter "*.sql" -File)
  if ($legacyFiles.Count -gt 0) {
    throw "Migracje SQL nadal istnieją poza supabase/migrations."
  }
}

$duplicateNames = Get-ChildItem -LiteralPath $canonicalDirectory -Filter "*.sql" -File |
  Group-Object Name |
  Where-Object Count -gt 1
if ($duplicateNames) {
  throw "Wykryto zduplikowane nazwy migracji."
}

Write-Output "MIGRATIONS_READY=true"
Write-Output "MIGRATION_COUNT=$(@(Get-ChildItem -LiteralPath $canonicalDirectory -Filter '*.sql' -File).Count)"
