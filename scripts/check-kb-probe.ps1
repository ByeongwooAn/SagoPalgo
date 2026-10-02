param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl
)

$ErrorActionPreference = 'Stop'
$uri = $null
if (-not [Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -notin @('http', 'https') -or
    $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') {
    throw 'ApiBaseUrl must be an HTTP(S) origin without credentials, path, query, or fragment.'
}
$base = $uri.AbsoluteUri.TrimEnd('/')

function Get-Endpoint {
    param([string]$Path)

    try {
        $response = Invoke-WebRequest -Uri "$base$Path" -UseBasicParsing -TimeoutSec 10
        $data = $null
        if ($Path -ne '/health') {
            $body = $response.Content | ConvertFrom-Json -ErrorAction Stop
            $data = $body.data
        }
        return [pscustomobject]@{
            Status = [int]$response.StatusCode
            Code = 'OK'
            Data = $data
        }
    } catch {
        $status = 0
        if ($null -ne $_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        $code = 'REQUEST_FAILED'
        if ($_.ErrorDetails.Message) {
            try {
                $body = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction Stop
                if ($body.error.code -match '^[A-Z0-9_]+$') {
                    $code = $body.error.code
                }
            } catch {
                # The response was not an API error envelope.
            }
        }
        return [pscustomobject]@{
            Status = $status
            Code = $code
            Data = $null
        }
    }
}

$health = Get-Endpoint '/health'
$readiness = Get-Endpoint '/api/v1/orders/readiness'
$latest = Get-Endpoint '/api/v1/orders/readiness/probe/latest'
$history = Get-Endpoint '/api/v1/orders/readiness/probe/history'

Write-Output "health: HTTP $($health.Status) ($($health.Code))"
Write-Output "readiness: HTTP $($readiness.Status) ($($readiness.Code))"

$requiredReady = $true
foreach ($code in @('ACCOUNT_SWITCH', 'CREDENTIALS', 'ACCOUNT_NUMBER', 'HTTPS_ENDPOINT')) {
    $check = @($readiness.Data.checks | Where-Object { $_.code -eq $code })
    $passed = $check.Count -eq 1 -and $check[0].passed -eq $true
    Write-Output "$($code): $($passed.ToString().ToLowerInvariant())"
    if (-not $passed) { $requiredReady = $false }
}

Write-Output "probe/latest: HTTP $($latest.Status) ($($latest.Code))"
Write-Output "probe/history: HTTP $($history.Status) ($($history.Code))"
Write-Output 'KB probe POST: not sent'

if ($health.Status -ne 200 -or $readiness.Status -ne 200 -or
    $latest.Status -ne 200 -or $history.Status -ne 200 -or -not $requiredReady) {
    exit 1
}
exit 0
