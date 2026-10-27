# Usage: .\scripts\smoke-public.ps1 -BaseUrl "https://xxxx.trycloudflare.com"

param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$BaseUrl = $BaseUrl.TrimEnd("/")
Write-Host "GET $BaseUrl/health"
Invoke-RestMethod "$BaseUrl/health" | ConvertTo-Json
Write-Host "GET $BaseUrl/v1/retailers"
(Invoke-RestMethod "$BaseUrl/v1/retailers").count
