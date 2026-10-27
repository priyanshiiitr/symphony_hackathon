# Offline smoke for Phase C APIs (no Bolna call credits)
param(
    [string]$BaseUrl = (Get-Content (Join-Path $PSScriptRoot "..\..\scripts\PUBLIC_URL.txt") -Raw).Trim()
)
$BaseUrl = $BaseUrl.TrimEnd("/")
$phone = "+919571025342"
Write-Host "Base=$BaseUrl"
Invoke-RestMethod "$BaseUrl/health" | ConvertTo-Json -Compress
Invoke-RestMethod "$BaseUrl/v1/inbound/caller-context?contact_number=%2B919571025342" | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method POST -Uri "$BaseUrl/v1/retailers/lookup-by-phone" -ContentType "application/json" -Body (@{ phone = $phone } | ConvertTo-Json)
Invoke-RestMethod -Method POST -Uri "$BaseUrl/v1/orders/status" -ContentType "application/json" -Body (@{ order_id = "ORD-1006"; phone = $phone } | ConvertTo-Json)
