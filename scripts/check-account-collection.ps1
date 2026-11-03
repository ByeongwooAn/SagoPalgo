param(
    [Parameter(Mandatory = $true)] [string]$ApiBaseUrl,
    [Parameter(Mandatory = $true)] [string]$ReportPath,
    [ValidateSet('OFF', 'ON')] [string]$ExpectedEnabled = 'OFF',
    [ValidateSet('', 'NOT_STARTED', 'IDLE', 'ACTIVE', 'PAUSED', 'UNCONFIGURED')] [string]$ExpectedState = '',
    [string]$PreviousReport,
    [switch]$RequireUnchanged
)

# GET only. This check never enables collection, resumes it, or queries KB directly.
$ErrorActionPreference = 'Stop'
$origin = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$origin) -or
    $origin.Scheme -notin @('http', 'https') -or $origin.UserInfo -or
    $origin.Query -or $origin.Fragment -or $origin.AbsolutePath -ne '/') {
    throw 'ApiBaseUrl must be an HTTP(S) origin without credentials, path, query or fragment.'
}
$base = $origin.AbsoluteUri.TrimEnd('/')
$root = '/api/v1/kb/accounts/primary/observations'
$report = [ordered]@{version=1;apiBaseUrl=$base;checkedAt=[DateTime]::UtcNow.ToString('o');getOnly=$true}

function Require([bool]$Condition, [string]$Code) { if (-not $Condition) { throw $Code } }
function Is-True($Value) { return $Value -is [bool] -and $Value }
function Is-False($Value) { return $Value -is [bool] -and -not $Value }
function Is-Id($Value) {
    $id = [Guid]::Empty
    return $Value -is [string] -and [Guid]::TryParseExact($Value, 'D', [ref]$id) -and $id.ToString('D') -ceq $Value
}
function Read-Api([string]$Path, [bool]$RequireNoStore = $true) {
    try {
        $response = Invoke-WebRequest -Uri "$base$Path" -Method GET -UseBasicParsing -TimeoutSec 15 -MaximumRedirection 0
        $body = $response.Content | ConvertFrom-Json
        Require ([int]$response.StatusCode -eq 200 -and (Is-True $body.success) -and $null -ne $body.data) 'API_UNCONFIRMED'
        Require (-not $RequireNoStore -or [string]$response.Headers['Cache-Control'] -match '(^|[,\s])no-store([,\s]|$)') 'CACHE_CONTRACT_INVALID'
        return $body.data
    } catch { throw 'API_UNCONFIRMED' }
}

try {
    $previous = $null
    if ($PreviousReport) {
        Require ([IO.Path]::GetFullPath($PreviousReport) -ine [IO.Path]::GetFullPath($ReportPath)) 'PREVIOUS_REPORT_INVALID'
        $previous = Get-Content -LiteralPath $PreviousReport -Raw | ConvertFrom-Json
        Require ($previous.version -eq 1 -and $previous.apiBaseUrl -ceq $base -and $previous.result -ceq 'CHECK_PASSED') 'PREVIOUS_REPORT_INVALID'
    }
    Require (-not $RequireUnchanged -or $null -ne $previous) 'PREVIOUS_REPORT_REQUIRED'
    $value = Read-Api "$root/collection"
    Require ((Is-True $value.readOnly) -and (Is-False $value.usableForTrading) -and
        $value.enabled -is [bool] -and $value.personalModeEnabled -is [bool] -and
        $value.accountEnabled -is [bool] -and $value.connectionConfigured -is [bool] -and
        ($value.intervalSeconds -is [int] -or $value.intervalSeconds -is [long]) -and
        $value.intervalSeconds -ge 60 -and $value.intervalSeconds -le 86400 -and
        $value.state -cin @('NOT_STARTED', 'IDLE', 'ACTIVE', 'PAUSED', 'UNCONFIGURED')) 'COLLECTION_CONTRACT_INVALID'
    $report.enabled = $value.enabled
    $report.state = $value.state
    $report.intervalSeconds = $value.intervalSeconds
    $report.personalModeEnabled = $value.personalModeEnabled
    $report.accountEnabled = $value.accountEnabled
    $report.connectionConfigured = $value.connectionConfigured
    foreach ($field in @('activeRequestId', 'lastRequestId')) {
        Require ($null -eq $value.$field -or (Is-Id $value.$field)) 'REQUEST_ID_INVALID'
        $report[$field] = $value.$field
    }
    Require ($null -eq $value.lastStorageState -or $value.lastStorageState -cin @('PENDING','COMPLETED','FAILED')) 'COLLECTION_CONTRACT_INVALID'
    Require ($null -eq $value.lastSnapshotStatus -or $value.lastSnapshotStatus -cin @('SUCCESS','PARTIAL','FAILED','DISABLED')) 'COLLECTION_CONTRACT_INVALID'
    Require ($null -eq $value.failureCode -or $value.failureCode -cin @('SNAPSHOT_PARTIAL','SNAPSHOT_FAILED',
        'SNAPSHOT_DISABLED','SNAPSHOT_UNUSABLE','OBSERVATION_FAILED','CONTEXT_CHANGED')) 'COLLECTION_CONTRACT_INVALID'
    $report.lastStorageState = $value.lastStorageState
    $report.lastSnapshotStatus = $value.lastSnapshotStatus
    $report.failureCode = $value.failureCode
    Require ($value.enabled -eq ($ExpectedEnabled -eq 'ON')) 'ENABLED_STATE_MISMATCH'
    Require (-not $ExpectedState -or $value.state -ceq $ExpectedState) 'EXPECTED_STATE_MISMATCH'
    $readiness = Read-Api '/api/v1/orders/readiness' $false
    foreach ($code in @('ORDER_PRECHECK_SWITCH', 'LIVE_ORDER_SWITCH')) {
        $checks = @($readiness.checks | Where-Object { $_.code -ceq $code })
        Require ($checks.Count -eq 1 -and (Is-False $checks[0].passed)) 'ORDER_SWITCH_NOT_OFF'
    }
    $report.orderSwitchesOff = $true
    # ACTIVE is not proof of a live process; never release it using elapsed time.
    Require ($value.state -cne 'ACTIVE') 'ACTIVE_RESULT_UNCONFIRMED'
    Require ($value.state -cne 'UNCONFIGURED') 'CONNECTION_UNCONFIGURED'
    if ($value.state -cin @('PAUSED', 'IDLE')) {
        Require ((Is-Id $value.lastRequestId) -and $null -eq $value.activeRequestId) 'TERMINAL_METADATA_INVALID'
        $detail = Read-Api "$root/$($value.lastRequestId)"
        Require ((Is-True $detail.readOnly) -and $detail.requestId -ceq $value.lastRequestId -and
            $detail.storageState -cin @('COMPLETED', 'FAILED') -and
            $detail.storageState -ceq $value.lastStorageState -and
            $detail.snapshotStatus -ceq $value.lastSnapshotStatus) 'TERMINAL_RECEIPT_MISMATCH'
        if ($detail.storageState -ceq 'COMPLETED') {
            Require ($detail.snapshotStatus -cin @('SUCCESS','PARTIAL','FAILED','DISABLED') -and
                $detail.observation.contractVersion -ceq 'KB_ACCOUNT_OBSERVATION_V1' -and
                (Is-False $detail.observation.atomic) -and (Is-False $detail.observation.usableForTrading) -and
                $detail.observation.status -ceq $detail.snapshotStatus) 'TERMINAL_RECEIPT_MISMATCH'
        } else { Require ($null -eq $detail.snapshotStatus) 'TERMINAL_RECEIPT_MISMATCH' }
        Require (($value.state -ceq 'PAUSED' -and $null -ne $value.failureCode) -or
            ($value.state -ceq 'IDLE' -and $null -eq $value.failureCode)) 'TERMINAL_METADATA_INVALID'
        $report.lastReceiptVerified = $true
    } else {
        Require ($null -eq $value.lastRequestId -and $null -eq $value.activeRequestId) 'TERMINAL_METADATA_INVALID'
        $report.lastReceiptVerified = $false
    }
    $history = Read-Api "$root`?limit=100"
    Require ($history.items -is [array]) 'HISTORY_CONTRACT_INVALID'
    $ids = @($history.items | ForEach-Object { Require (Is-Id $_.requestId) 'HISTORY_CONTRACT_INVALID'; $_.requestId })
    Require (@($ids | Select-Object -Unique).Count -eq $ids.Count -and $ids.Count -le 100) 'HISTORY_CONTRACT_INVALID'
    $report.recentRequestIds = $ids
    $report.recentItemCount = $ids.Count
    if ($value.lastRequestId) { Require ($ids -ccontains $value.lastRequestId) 'LAST_RECEIPT_NOT_IN_RECENT_HISTORY' }
    if ($previous) {
        $report.unchanged = $true
        foreach ($field in @('enabled','state','intervalSeconds','personalModeEnabled','accountEnabled',
            'connectionConfigured','activeRequestId','lastRequestId','lastStorageState','lastSnapshotStatus','failureCode')) {
            if ($report[$field] -cne $previous.$field) { $report.unchanged = $false }
        }
        if (($ids -join ',') -cne (@($previous.recentRequestIds) -join ',')) { $report.unchanged = $false }
        Require (-not $RequireUnchanged -or $report.unchanged) 'STATUS_OR_HISTORY_CHANGED'
    }
    # Operational evidence only, not an authorization or a continuous-collection readiness decision.
    $report.result = 'CHECK_PASSED'
} catch {
    $report.result = 'UNCONFIRMED'
    $report.failureCode = 'CHECK_FAILED'
    if ($_.Exception.Message -cin @('API_UNCONFIRMED','CACHE_CONTRACT_INVALID','PREVIOUS_REPORT_INVALID',
        'PREVIOUS_REPORT_REQUIRED','COLLECTION_CONTRACT_INVALID','REQUEST_ID_INVALID','ENABLED_STATE_MISMATCH',
        'EXPECTED_STATE_MISMATCH','ORDER_SWITCH_NOT_OFF','ACTIVE_RESULT_UNCONFIRMED','CONNECTION_UNCONFIGURED',
        'TERMINAL_METADATA_INVALID','TERMINAL_RECEIPT_MISMATCH','HISTORY_CONTRACT_INVALID',
        'LAST_RECEIPT_NOT_IN_RECENT_HISTORY','STATUS_OR_HISTORY_CHANGED')) {
        $report.failureCode = $_.Exception.Message
    }
}
$json = $report | ConvertTo-Json -Depth 5
try { [IO.File]::WriteAllText([IO.Path]::GetFullPath($ReportPath), $json, [Text.UTF8Encoding]::new($false)) }
catch { $report.result='UNCONFIRMED';$report.failureCode='REPORT_WRITE_FAILED';$json=$report | ConvertTo-Json -Depth 5 }
Write-Output $json
if ($report.result -ne 'CHECK_PASSED') { exit 1 }
exit 0
