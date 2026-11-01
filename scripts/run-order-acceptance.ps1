param([string]$Flutter = 'flutter')

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$compose = Join-Path $root 'Back/spring-server/compose.order-acceptance.yml'
$environmentFile = Join-Path $root 'Back/spring-server/src/test/resources/order-acceptance.env'
$artifacts = Join-Path $root ('Front/app_version/build/order-acceptance/' + [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss'))
$owned = $false
$nativeCounts = @{}
New-Item -ItemType Directory -Path $artifacts -Force | Out-Null

function Compose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    & docker compose --env-file $environmentFile -f $compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Isolated compose action failed: $($Arguments[0])" }
}
function Query([string]$Sql) {
    $shell = @'
set -eu
export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
mysql -N -B -uroot sagopalgo_acceptance_test <<'SQL'
'@ + "`n" + $Sql + "`nSQL`n"
    $rows = @($shell | docker compose --env-file $environmentFile -f $compose exec -T mysql sh -c "tr -d '\r' | sh")
    if ($LASTEXITCODE -ne 0) { throw 'Isolated database query failed' }
    return $rows
}
function Wait-Api {
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    do {
        try {
            $r = Invoke-RestMethod -Uri 'http://127.0.0.1:18082/api/v1/orders/readiness' -TimeoutSec 2
            if ($r.success -eq $true -and $r.data.canSubmit -eq $false -and
                @($r.data.checks | Where-Object { $_.code -eq 'SUBMISSION_TRANSPORT' -and $_.passed }).Count -eq 1) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Isolated API readiness timed out'
}
function Windows-Test([string]$Phase) {
    Push-Location (Join-Path $root 'Front/app_version')
    try {
        & $Flutter test integration_test/order_lifecycle_acceptance_test.dart -d windows --no-pub --reporter expanded `
            '--dart-define=SAGOPALGO_ORDER_ACCEPTANCE=true' `
            "--dart-define=SAGOPALGO_ACCEPTANCE_PHASE=$Phase" `
            "--dart-define=SAGOPALGO_ACCEPTANCE_ARTIFACTS=$artifacts" *> (Join-Path $artifacts "$Phase.log")
        if ($LASTEXITCODE -ne 0) { throw "Windows acceptance phase '$Phase' failed; see $artifacts" }
        $summary = @(Get-Content -LiteralPath (Join-Path $artifacts "$Phase.log") | Where-Object { $_ -match 'All tests passed!' })
        if ($summary.Count -eq 0 -or $summary[-1] -notmatch '\+(\d+)') { throw 'Native test success summary missing' }
        $script:nativeCounts[$Phase] = [int]$Matches[1]
        if ($script:nativeCounts[$Phase] -ne $(if ($Phase -eq 'before') {16} else {1})) { throw 'Native test coverage count mismatch' }
    } finally { Pop-Location }
}
function Assert-UnchangedRealTables {
    $counts = Query @'
SELECT (SELECT COUNT(*) FROM manual_order_commands)+(SELECT COUNT(*) FROM order_approvals)+(SELECT COUNT(*) FROM order_submission_guards)+(SELECT COUNT(*) FROM order_prechecks)+(SELECT COUNT(*) FROM trade_records)+(SELECT COUNT(*) FROM holdings)+(SELECT COUNT(*) FROM user_capital);
'@
    if (($counts -join '').Trim() -ne '0') { throw 'Acceptance modified a non-simulator table' }
}

Push-Location $root
try {
    # 기존 스택을 가져다 쓰거나 정리하지 않습니다. 운영 Compose/.env는 읽지 않습니다.
    $existing = @(Compose -Arguments @('ps','-a','-q'))
    if ($existing.Count -gt 0) { throw 'Acceptance containers already exist; inspect them before running.' }
    if (Get-NetTCPConnection -LocalPort 18082 -State Listen -ErrorAction SilentlyContinue) { throw 'Acceptance port 18082 is already in use' }
    $owned = $true
    Compose -Arguments @('up','-d','--build','--wait','--wait-timeout','150')
    Wait-Api
    $apiId = (Compose -Arguments @('ps','-q','api') | Out-String).Trim()
    $startedBefore = (& docker inspect --format '{{.State.StartedAt}}' $apiId | Out-String).Trim()
    $apiImage = (& docker inspect --format '{{.Image}}' $apiId | Out-String).Trim()
    $networkInternal = (& docker network inspect --format '{{.Internal}}' sagopalgo-order-acceptance_isolated | Out-String).Trim()
    $apiNetworkCount = (& docker inspect --format '{{len .NetworkSettings.Networks}}' $apiId | Out-String).Trim()
    if ($networkInternal -ne 'true' -or $apiNetworkCount -ne '1') { throw 'Acceptance API network isolation check failed' }
    if (((Query "SELECT marker FROM acceptance_environment_marker;") -join '').Trim() -ne 'SAGOPALGO_ORDER_ACCEPTANCE_ONLY') {
        throw 'Acceptance database marker missing'
    }
    Assert-UnchangedRealTables
    Write-Output 'Windows UI / HTTP / MySQL acceptance: before restart'
    Windows-Test before
    Assert-UnchangedRealTables
    $snapshotSql = 'SELECT session_id,revision,SHA2(CAST(state_json AS CHAR),256) FROM order_simulation_sessions ORDER BY session_id;'
    $before = (Query $snapshotSql) -join "`n"
    if (-not $before) { throw 'No persisted acceptance sessions' }
    $before | Set-Content -LiteralPath (Join-Path $artifacts 'database-before.txt') -Encoding utf8
    Compose -Arguments @('restart','api')
    Wait-Api
    $startedAfter = (& docker inspect --format '{{.State.StartedAt}}' $apiId | Out-String).Trim()
    if (-not $startedBefore -or $startedBefore -ceq $startedAfter) { throw 'API process restart was not confirmed' }
    Write-Output 'Windows UI / HTTP / MySQL acceptance: new app process after JVM restart'
    Windows-Test after
    $after = (Query $snapshotSql) -join "`n"
    $after | Set-Content -LiteralPath (Join-Path $artifacts 'database-after.txt') -Encoding utf8
    if ($before -cne $after) { throw 'Restart or read-only reopening changed stored simulator state/revisions' }
    Assert-UnchangedRealTables
    [pscustomobject]@{
        passed=$true
        checkedAt=[DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(9)).ToString('o')
        baseCommit=(& git rev-parse HEAD)
        scope='NATIVE_WINDOWS_UI_REAL_HTTP_ISOLATED_MYSQL'
        apiRestarted=$true
        apiImage=$apiImage
        nativeTests=$nativeCounts
        nativeAppRelaunched=$true
        databaseStateAndRevisionsUnchanged=$true
        nonSimulatorTablesEmpty=$true
        externalNetwork='API_MYSQL_INTERNAL;INGRESS_PROXY_ONLY'
        productionComposeAndEnvUsed=$false
        artifacts=$artifacts
    } | ConvertTo-Json | Tee-Object -FilePath (Join-Path $artifacts 'report.json')
} finally {
    if ($owned) {
        & docker compose --env-file $environmentFile -f $compose logs --no-color api *> (Join-Path $artifacts 'api.log')
        & docker compose --env-file $environmentFile -f $compose down
    }
    Pop-Location
}
