param(
    [string]$ApiBaseUrl = 'http://localhost:8080',
    [string]$EnvFile = '.env'
)

$ErrorActionPreference = 'Stop'
$apiUri = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$apiUri) -or
    $apiUri.Scheme -notin @('http','https') -or $apiUri.UserInfo -or
    $apiUri.Query -or $apiUri.Fragment -or $apiUri.AbsolutePath -ne '/') {
    throw 'ApiBaseUrl must be an HTTP(S) origin without credentials, path, query, or fragment.'
}
$base = $apiUri.AbsoluteUri.TrimEnd('/')
$checks = [Collections.Generic.List[object]]::new()
function Add-Check([string]$Code, [bool]$Passed) {
    $checks.Add([pscustomobject]@{code=$Code;passed=$Passed})
}
function Get-Data([string]$Path) {
    $response = Invoke-WebRequest -Uri "$base$Path" -UseBasicParsing -TimeoutSec 15
    $body = $response.Content | ConvertFrom-Json
    if ([int]$response.StatusCode -ne 200 -or $body.success -ne $true) { throw 'API check failed' }
    return $body.data
}

# DB/로컬 GET만 사용합니다. KB 조회, 주문·승인·시뮬레이터 POST, 스위치 변경은 없습니다.
$sql = @'
SELECT 'DB_016',COUNT(*)=2 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('manual_order_commands','manual_order_observations');
SELECT 'DB_017',COUNT(*)=2 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('manual_order_reconciliations','manual_order_reconciliation_preparations');
SELECT 'DB_018',COUNT(*)=1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='order_simulation_sessions';
SELECT 'DB_019',COUNT(*)=2 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('manual_order_dispatches','manual_order_dispatch_recoveries');
SELECT 'DB_020',COUNT(*)=1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='manual_order_diagnostics';
SELECT 'DB_021',COUNT(*)=2 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('manual_order_review_preparations','manual_order_reviews');
SELECT 'DB_022_COLUMNS',COUNT(*)=5 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='manual_order_reservation_aborts' AND IS_NULLABLE='NO' AND ((COLUMN_NAME='command_id' AND COLUMN_TYPE='char(36)') OR (COLUMN_NAME='user_id' AND DATA_TYPE='bigint') OR (COLUMN_NAME='execution_key' AND COLUMN_TYPE='char(36)') OR (COLUMN_NAME='account_fingerprint' AND COLUMN_TYPE='char(64)') OR (COLUMN_NAME='aborted_at' AND COLUMN_TYPE='datetime(6)'));
SELECT 'DB_022_PHASE',COUNT(*)=1 FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='chk_manual_dispatch_phase' AND CHECK_CLAUSE LIKE '%ABORTED%';
SELECT 'DB_022_KEYS',COUNT(*)=3 FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='manual_order_reservation_aborts' AND ((CONSTRAINT_NAME='PRIMARY' AND COLUMN_NAME='command_id') OR (COLUMN_NAME='command_id' AND REFERENCED_TABLE_NAME='manual_order_dispatches' AND REFERENCED_COLUMN_NAME='command_id') OR (COLUMN_NAME='user_id' AND REFERENCED_TABLE_NAME='users' AND REFERENCED_COLUMN_NAME='user_id'));
'@
$shellScript = @'
set -eu
export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
mysql -N -B -uroot "$MYSQL_DATABASE" <<'SQL'
'@ + "`n" + $sql + "`nSQL`n"
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $rows = @($shellScript | docker compose --env-file $EnvFile exec -T mysql sh -c "tr -d '\r' | sh" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $rows.Count -ne 9) { Add-Check 'DATABASE_ACCESS' $false }
    else {
        foreach ($row in $rows) {
            $parts = "$row" -split "`t"
            if ($parts.Count -eq 2 -and $parts[0] -match '^DB_[0-9A-Z_]+$') { Add-Check $parts[0] ($parts[1] -eq '1') }
            else { Add-Check 'DATABASE_RESULT_FORMAT' $false }
        }
    }
} catch { Add-Check 'DATABASE_ACCESS' $false }
finally { Pop-Location }

$liveOrderEnabled = $null
try {
    $readiness = Get-Data '/api/v1/orders/readiness'
    Add-Check 'MANUAL_ORDER_STORAGE' (@($readiness.checks | Where-Object { $_.code -eq 'SUBMISSION_TRANSPORT' -and $_.passed -eq $true }).Count -eq 1)
    $live = @($readiness.checks | Where-Object { $_.code -eq 'LIVE_ORDER_SWITCH' })
    if ($live.Count -eq 1) { $liveOrderEnabled = [bool]$live[0].passed }
} catch { Add-Check 'MANUAL_ORDER_READINESS_API' $false }
try { $null = Get-Data '/api/v1/orders/manual'; Add-Check 'MANUAL_ORDER_HISTORY_API' $true }
catch { Add-Check 'MANUAL_ORDER_HISTORY_API' $false }

$passed = @($checks | Where-Object { -not $_.passed }).Count -eq 0
[pscustomobject]@{
    checkedAt = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(9)).ToString('o')
    passed = $passed
    scope = 'LOCAL_DATABASE_AND_GET_ONLY'
    liveOrderEnabled = $liveOrderEnabled
    checks = @($checks.ToArray())
    limitations = 'Does not verify broker order results, partial-change deployment version, or long-term operation.'
} | ConvertTo-Json -Depth 5
if (-not $passed) { exit 1 }
