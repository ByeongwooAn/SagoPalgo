param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl,
    [switch]$IncludeImportPreview
)

# 조회만 수행합니다. 계좌번호·인증값·외부 API 원문은 출력하지 않습니다.
$ErrorActionPreference = 'Stop'
$origin = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$origin) -or
    $origin.Scheme -notin @('http', 'https') -or $origin.UserInfo -or
    $origin.Query -or $origin.Fragment -or $origin.AbsolutePath -ne '/') {
    throw 'ApiBaseUrl must be an HTTP(S) origin without credentials, path, query, or fragment.'
}
$base = $origin.AbsoluteUri.TrimEnd('/')

function Get-Api {
    param([string]$Path)
    try {
        $response = Invoke-WebRequest -Uri "$base$Path" -UseBasicParsing -TimeoutSec 10
        $body = $response.Content | ConvertFrom-Json -ErrorAction Stop
        if ($body.success -ne $true) {
            return [pscustomobject]@{ Status = [int]$response.StatusCode; Code = 'API_FAILURE'; Data = $null }
        }
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Code = 'OK'; Data = $body.data }
    } catch {
        $status = 0
        if ($null -ne $_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        $code = 'REQUEST_FAILED'
        try {
            $body = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction Stop
            if ($body.error.code -match '^[A-Z0-9_]+$') { $code = $body.error.code }
        } catch { }
        return [pscustomobject]@{ Status = $status; Code = $code; Data = $null }
    }
}

$responses = [ordered]@{}
foreach ($entry in @(
    @('capital', '/api/v1/capital'),
    @('portfolio', '/api/v1/holdings'),
    @('kbHoldings', '/api/v1/kb/accounts/primary/holdings'),
    @('kbSettlement', '/api/v1/kb/accounts/primary/balances/settlement'),
    @('kbExecution', '/api/v1/kb/accounts/primary/balances/execution')
)) {
    $result = Get-Api $entry[1]
    $responses[$entry[0]] = $result
    Write-Output "$($entry[0]): HTTP $($result.Status) ($($result.Code))"
}

if ($IncludeImportPreview) {
    $result = Get-Api '/api/v1/kb/portfolio-import/preview'
    $responses['preview'] = $result
    Write-Output "preview: HTTP $($result.Status) ($($result.Code))"
    if ($result.Code -eq 'OK') {
        Write-Output "preview importable rows: $(@($result.Data.items | Where-Object { $_.action -in @('CREATE', 'UPDATE') }).Count)"
        Write-Output "preview retained KB rows: $($result.Data.retainedImportedCount)"
    }
}

$valid = @($responses.Values | Where-Object { $_.Code -ne 'OK' }).Count -eq 0
if ($responses.capital.Code -eq 'OK') {
    Write-Output "app available capital: $($responses.capital.Data.availableCapital) KRW"
}
if ($responses.kbSettlement.Code -eq 'OK') {
    $summary = $responses.kbSettlement.Data.summary
    Write-Output "KB settlement deposit: $($summary.cashDeposit) KRW"
    Write-Output "KB settlement order-available cash: $($summary.orderAvailableCash) KRW (different basis from app capital)"
}
if ($responses.kbExecution.Code -eq 'OK') {
    Write-Output "KB execution net assets: $($responses.kbExecution.Data.summary.netAssetValuationAmount) KRW"
}
if ($responses.kbHoldings.Code -eq 'OK') {
    Write-Output "KB holding rows in current response: $(@($responses.kbHoldings.Data.items).Count) (not proof of a complete account scan)"
}
if ($responses.portfolio.Code -eq 'OK') {
    $rows = @($responses.portfolio.Data.items)
    $calculatedProfit = [decimal]0
    foreach ($row in $rows) {
        $calculatedProfit += ([decimal]$row.currentPrice - [decimal]$row.buyPrice) * [decimal]$row.quantity
    }
    $reportedProfit = [decimal]$responses.portfolio.Data.summary.totalProfit
    $matches = [Math]::Abs($calculatedProfit - $reportedProfit) -le [decimal]0.01
    Write-Output "app holding rows: $($rows.Count)"
    Write-Output "row/summary profit matches (0.01 KRW tolerance): $matches"
    Write-Output "fallback rows: $(@($rows | Where-Object { $_.priceFallback -eq $true }).Count)"
    Write-Output "rows without price provenance: $(@($rows | Where-Object { -not $_.priceProvider }).Count)"
    if (-not $matches) { $valid = $false }
}
Write-Output 'Import POST and order submission: not sent'
if (-not $valid) { exit 1 }
