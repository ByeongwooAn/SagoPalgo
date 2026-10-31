param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl
)

# 모든 요청은 GET입니다. 수집/분석/알림 표시 완료/가상 거래 POST는 보내지 않습니다.
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
        $response = Invoke-WebRequest -Uri "$base$Path" -UseBasicParsing -TimeoutSec 15
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

$results = [ordered]@{}
foreach ($entry in @(
    @('dashboard', '/api/v1/dashboard/snapshot'),
    @('providers', '/api/v1/settings/providers'),
    @('watchlist', '/api/v1/watchlist'),
    @('recommendations', '/api/v1/recommendations?page=0&size=1'),
    @('alerts', '/api/v1/alerts?page=0&size=1'),
    @('pending', '/api/v1/alerts/pending?limit=1'),
    @('paper', '/api/v1/paper-trading')
)) {
    $result = Get-Api $entry[1]
    $results[$entry[0]] = $result
    Write-Output "$($entry[0]): HTTP $($result.Status) ($($result.Code))"
}

$hasBriefing = $null -ne $results.dashboard.Data.marketSummary.index
Write-Output "new briefing contract deployed: $hasBriefing"
if ($hasBriefing) {
    Write-Output "index status: $($results.dashboard.Data.marketSummary.index.status)"
    Write-Output "news status: $($results.dashboard.Data.marketSummary.news.status)"
    Write-Output "news article count: $($results.dashboard.Data.marketSummary.news.articleCount)"
}
Write-Output "stored recommendation total: $($results.recommendations.Data.total)"
Write-Output "stored alert total: $($results.alerts.Data.total)"
if ($results.watchlist.Code -eq 'OK') {
    $stocks = @($results.watchlist.Data | Where-Object { $null -ne $_ })
    Write-Output "watchlist rows: $($stocks.Count)"
    if ($stocks.Count -gt 0) {
        $code = [Uri]::EscapeDataString([string]$stocks[0].stockCode)
        $name = [Uri]::EscapeDataString([string]$stocks[0].stockName)
        $feed = Get-Api "/api/v1/research/feed?stockCode=$code&stockName=$name"
        $sync = Get-Api "/api/v1/research/sync/status?stockCode=$code"
        $results['feed'] = $feed
        $results['sync'] = $sync
        Write-Output "first watchlist stored feed: HTTP $($feed.Status) ($($feed.Code))"
        Write-Output "first watchlist sync status: HTTP $($sync.Status) ($($sync.Code))"
        if ($feed.Code -eq 'OK') {
            Write-Output "stored news/disclosures: $(@($feed.Data.news | Where-Object { $null -ne $_ }).Count)/$(@($feed.Data.disclosures | Where-Object { $null -ne $_ }).Count)"
        }
    } else {
        Write-Output 'No watchlist: register a stock in the app before testing collection/analysis.'
    }
}
Write-Output 'Research sync, analysis, read/sent acknowledgement, paper and live order POST: not sent'
$failures = @($results.GetEnumerator() | Where-Object {
    $_.Value.Code -ne 'OK' -and -not ($_.Key -eq 'paper' -and $_.Value.Code -eq 'PAPER_CAPITAL_REQUIRED')
})
$briefingReady = $hasBriefing -and $results.dashboard.Data.marketSummary.index.status -eq 'SUCCESS' -and
    $results.dashboard.Data.marketSummary.news.status -ne 'FAILED'
if ($failures.Count -gt 0 -or -not $briefingReady) { exit 1 }
