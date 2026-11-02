param(
    [Parameter(Mandatory = $true)] [string]$ApiBaseUrl,
    [Parameter(Mandatory = $true)] [string]$ReceiptPath,
    [switch]$Capture,
    [string]$OrderDate,
    [ValidateRange(1, 180)] [int]$TimeoutSeconds = 120
)

# Default: stored-result GET only. -Capture explicitly permits one read-only KB observation.
# Receipts/reports contain metadata only; never write balances, rows, tokens or upstream messages.
$ErrorActionPreference = 'Stop'
$origin = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$origin) -or
    $origin.Scheme -notin @('http', 'https') -or $origin.UserInfo -or
    $origin.Query -or $origin.Fragment -or $origin.AbsolutePath -ne '/') {
    throw 'ApiBaseUrl must be an HTTP(S) origin without credentials, path, query or fragment.'
}
$base = $origin.AbsoluteUri.TrimEnd('/')
$root = '/api/v1/kb/accounts/primary/observations'
$receiptFile = [IO.Path]::GetFullPath($ReceiptPath)
$reportFile = "$receiptFile.report.json"
$report = [ordered]@{ checkedAt = [DateTime]::UtcNow.ToString('o'); captureRequested = [bool]$Capture }

function Get-Api([string]$Path, [string]$Method = 'GET', [string]$Body) {
    try {
        $parameters = @{
            Uri = "$base$Path"; Method = $Method; UseBasicParsing = $true
            TimeoutSec = $TimeoutSeconds; MaximumRedirection = 0
            Headers = @{ Accept = 'application/json' }
        }
        if ($Method -eq 'POST') {
            $parameters.ContentType = 'application/json'
            $parameters.Body = $Body
        }
        $response = Invoke-WebRequest @parameters
        $envelope = $response.Content | ConvertFrom-Json
        if ($envelope.success -isnot [bool] -or -not $envelope.success -or $null -eq $envelope.data) {
            throw 'Invalid API envelope'
        }
        return [pscustomobject]@{
            status = [int]$response.StatusCode; code = 'OK'; data = $envelope.data
            noStore = [bool]([string]$response.Headers['Cache-Control'] -match '(^|[,\s])no-store([,\s]|$)')
        }
    } catch {
        $status = 0
        if ($null -ne $_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        # Even a malformed external error is reduced to a fixed local code.
        return [pscustomobject]@{ status = $status; code = 'REQUEST_UNCONFIRMED'; data = $null; noStore = $false }
    }
}

function Require([bool]$Condition, [string]$Code) {
    if (-not $Condition) { throw $Code }
}

function Is-True($Value) { return $Value -is [bool] -and $Value }
function Is-False($Value) { return $Value -is [bool] -and -not $Value }

function Check-Date([string]$Value) {
    $date = [DateTime]::MinValue
    return $Value -cmatch '^\d{8}$' -and [DateTime]::TryParseExact(
        $Value, 'yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None, [ref]$date)
}

function Check-Detail($Result, $Receipt) {
    Require ($Result.status -eq 200 -and $Result.noStore) 'DETAIL_HTTP_OR_CACHE_INVALID'
    $data = $Result.data
    Require ($data.requestId -ceq $Receipt.requestId -and $data.orderDate -ceq $Receipt.orderDate -and
        (Is-True $data.readOnly)) 'DETAIL_RECEIPT_MISMATCH'
    Require ($data.storageState -cin @('PENDING', 'COMPLETED', 'FAILED')) 'STORAGE_STATE_INVALID'
    $report.storageState = $data.storageState
    Require ($data.storageState -ceq 'COMPLETED') 'OBSERVATION_NOT_COMPLETED'
    $value = $data.observation
    Require ($null -ne $value -and $value.contractVersion -ceq 'KB_ACCOUNT_OBSERVATION_V1' -and
        $value.provider -ceq 'KB' -and $value.accountAlias -ceq 'primary' -and
        (Is-False $value.atomic) -and (Is-False $value.usableForTrading) -and
        $data.observationId -ceq $value.observationId -and
        $data.snapshotStatus -ceq $value.status) 'OBSERVATION_CONTRACT_INVALID'
    Require ($value.status -cin @('SUCCESS', 'PARTIAL', 'FAILED', 'DISABLED')) 'OBSERVATION_CONTRACT_INVALID'
    $report.snapshotStatus = $value.status
    $expected = @('SSQM1801', 'SSQM2932', 'SSQM2952', 'SSQM2341')
    $sections = @($value.sections)
    Require ($sections.Count -eq $expected.Count) 'SECTION_COUNT_INVALID'
    $summaries = @()
    for ($index = 0; $index -lt $expected.Count; $index++) {
        $section = $sections[$index]
        Require ($section.api -ceq $expected[$index] -and
            $section.status -cin @('SUCCESS', 'PARTIAL', 'FAILED', 'DISABLED') -and
            $section.completeness -cin @('COMPLETE', 'PARTIAL', 'UNKNOWN', 'INVALID')) 'SECTION_CONTRACT_INVALID'
        Require (($section.pagesRead -is [int] -or $section.pagesRead -is [long]) -and
            $section.pagesRead -ge 0 -and $section.pagesRead -le 10 -and
            ($section.receivedRowCount -is [int] -or $section.receivedRowCount -is [long]) -and $section.receivedRowCount -ge 0 -and
            $section.rows -is [array] -and $section.issues -is [array]) 'SECTION_CONTRACT_INVALID'
        foreach ($fields in @($section.summary) + @($section.rows | ForEach-Object { $_.fields })) {
            Require ($fields -is [pscustomobject]) 'SECTION_CONTRACT_INVALID'
            foreach ($property in $fields.PSObject.Properties) {
                Require ($null -eq $property.Value -or $property.Value -is [string]) 'SECTION_CONTRACT_INVALID'
            }
        }
        if ($section.api -ceq 'SSQM2341') {
            Require ($section.scope.orderDate -ceq $Receipt.orderDate) 'ORDER_DATE_MISMATCH'
        }
        $issues = @($section.issues)
        $summaries += [pscustomobject]@{
            api = $section.api; status = $section.status; completeness = $section.completeness
            pagesRead = $section.pagesRead; receivedRowCount = $section.receivedRowCount
            retainedRowCount = @($section.rows).Count; issueCount = $issues.Count
            # Output only known contract issue codes; no field values or provider messages.
            issues = @($issues | ForEach-Object {
                if ($_.code -cin @('LOOKUP_FAILED', 'UNSUPPORTED_CONTRACT', 'CONTEXT_CHANGED',
                    'MISSING_RECORDS', 'MISSING_NEXT_KEY', 'MISSING_COUNT', 'COUNT_MISMATCH',
                    'INVALID_COUNT', 'INVALID_RECORDS', 'INVALID_ROW', 'MISSING_IDENTITY',
                    'DUPLICATE_IDENTITY', 'MISSING_FIELD', 'INVALID_NUMBER', 'NEGATIVE_QUANTITY',
                    'INVALID_PROCESS_TIME', 'INVALID_NEXT_KEY', 'REPEATED_NEXT_KEY', 'SCOPE_MISMATCH',
                    'PAGE_LIMIT', 'ROW_LIMIT', 'UNSUPPORTED_PAGINATION', 'ACCOUNT_DISABLED')) { $_.code }
                else { 'UNRECOGNIZED_ISSUE' }
            })
        }
    }
    $report.sections = $summaries
    $report.readOnly = $true
    $report.usableForTrading = $false
    $report.kbAppComparison = 'NOT_PERFORMED'
    $report.sourcesFullySuccessful = $value.status -ceq 'SUCCESS' -and @($summaries | Where-Object {
        $_.status -cne 'SUCCESS' -or $_.completeness -cne 'COMPLETE' -or $_.issueCount -ne 0
    }).Count -eq 0
}

try {
    $receipt = $null
    if ($Capture) {
        Require (-not [IO.File]::Exists($receiptFile)) 'RECEIPT_ALREADY_EXISTS_USE_GET'
        if (-not $OrderDate) { $OrderDate = [DateTime]::UtcNow.AddHours(9).ToString('yyyyMMdd') }
        Require (Check-Date $OrderDate) 'ORDER_DATE_INVALID'
        $collection = Get-Api "$root/collection"
        Require ($collection.status -eq 200 -and $collection.noStore) 'COLLECTION_PREFLIGHT_FAILED'
        Require ((Is-False $collection.data.enabled) -and (Is-True $collection.data.personalModeEnabled) -and
            (Is-True $collection.data.accountEnabled) -and (Is-True $collection.data.connectionConfigured) -and
            $collection.data.state -cin @('NOT_STARTED', 'IDLE', 'PAUSED') -and
            (Is-True $collection.data.readOnly) -and (Is-False $collection.data.usableForTrading)) 'COLLECTION_SETTINGS_INVALID'
        $readiness = Get-Api '/api/v1/orders/readiness'
        Require ($readiness.status -eq 200) 'READINESS_PREFLIGHT_FAILED'
        foreach ($entry in @(@('ORDER_PRECHECK_SWITCH', $false), @('LIVE_ORDER_SWITCH', $false),
            @('ACCOUNT_SWITCH', $true), @('CREDENTIALS', $true), @('HTTPS_ENDPOINT', $true),
            @('OFFICIAL_ORDER_ENDPOINT', $true))) {
            $check = @($readiness.data.checks | Where-Object { $_.code -ceq $entry[0] })
            Require ($check.Count -eq 1 -and $check[0].passed -is [bool] -and
                $check[0].passed -eq $entry[1]) 'READINESS_SETTINGS_INVALID'
        }
        $history = Get-Api "$root`?limit=20"
        Require ($history.status -eq 200 -and $history.noStore) 'HISTORY_PREFLIGHT_FAILED'
        $receipt = [ordered]@{
            version = 1; apiBaseUrl = $base; requestId = [Guid]::NewGuid().ToString('D')
            orderDate = $OrderDate; createdAt = [DateTime]::UtcNow.ToString('o')
        }
        # CreateNew + disk flush before sending. Existing or unwritable receipts prevent POST.
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($receipt | ConvertTo-Json))
        $stream = [IO.File]::Open($receiptFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
        $report.requestId = $receipt.requestId
        $report.orderDate = $receipt.orderDate
        $report.postAttempted = $true
        $post = Get-Api $root 'POST' (@{requestId=$receipt.requestId; orderDate=$receipt.orderDate} | ConvertTo-Json -Compress)
        $report.postHttpStatus = $post.status
        # No second POST even when its response is lost. Stored-detail GET is the only recovery.
    } else {
        Require ([IO.File]::Exists($receiptFile)) 'RECEIPT_REQUIRED'
        $receipt = [IO.File]::ReadAllText($receiptFile) | ConvertFrom-Json
        $id = [Guid]::Empty
        Require ($receipt.version -eq 1 -and $receipt.apiBaseUrl -ceq $base -and
            [Guid]::TryParseExact([string]$receipt.requestId, 'D', [ref]$id) -and
            $id.ToString('D') -ceq $receipt.requestId -and (Check-Date $receipt.orderDate)) 'RECEIPT_INVALID'
        if ($OrderDate) { Require ($OrderDate -ceq $receipt.orderDate) 'ORDER_DATE_MISMATCH' }
        $report.requestId = $receipt.requestId
        $report.orderDate = $receipt.orderDate
        $report.postAttempted = $false
    }
    $detail = Get-Api "$root/$($receipt.requestId)"
    $report.detailHttpStatus = $detail.status
    Check-Detail $detail $receipt
    $listed = Get-Api "$root`?limit=20"
    Require ($listed.status -eq 200 -and $listed.noStore) 'HISTORY_VERIFICATION_FAILED'
    $report.listedInRecentHistory = @($listed.data.items | Where-Object { $_.requestId -ceq $receipt.requestId }).Count -eq 1
    Require $report.listedInRecentHistory 'RECENT_HISTORY_RECORD_NOT_FOUND'
    $report.storageVerified = $true
    Require $report.sourcesFullySuccessful 'OBSERVATION_NOT_FULLY_SUCCESSFUL'
    $report.result = 'API_OBSERVATION_VERIFIED'
} catch {
    $allowed = @('DETAIL_HTTP_OR_CACHE_INVALID', 'DETAIL_RECEIPT_MISMATCH', 'STORAGE_STATE_INVALID',
        'OBSERVATION_NOT_COMPLETED', 'OBSERVATION_CONTRACT_INVALID', 'SECTION_COUNT_INVALID',
        'SECTION_CONTRACT_INVALID', 'ORDER_DATE_MISMATCH', 'OBSERVATION_NOT_FULLY_SUCCESSFUL',
        'RECEIPT_ALREADY_EXISTS_USE_GET', 'ORDER_DATE_INVALID', 'COLLECTION_PREFLIGHT_FAILED',
        'COLLECTION_SETTINGS_INVALID', 'READINESS_PREFLIGHT_FAILED', 'READINESS_SETTINGS_INVALID',
        'HISTORY_PREFLIGHT_FAILED', 'RECEIPT_REQUIRED', 'RECEIPT_INVALID',
        'HISTORY_VERIFICATION_FAILED', 'RECENT_HISTORY_RECORD_NOT_FOUND')
    $report.result = 'UNCONFIRMED'
    $report.failureCode = 'CHECK_FAILED'
    if ($_.Exception.Message -cin $allowed) { $report.failureCode = $_.Exception.Message }
}
$json = $report | ConvertTo-Json -Depth 6
# Do not overwrite another receipt's report when preflight or receipt validation fails.
if ($report.Contains('requestId')) {
    try { [IO.File]::WriteAllText($reportFile, $json, [Text.UTF8Encoding]::new($false)) }
    catch { $report.result = 'UNCONFIRMED'; $report.failureCode = 'REPORT_WRITE_FAILED'; $json = $report | ConvertTo-Json -Depth 6 }
}
Write-Output $json
if ($report.result -ne 'API_OBSERVATION_VERIFIED') { exit 1 }
exit 0
