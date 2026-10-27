# Place an outbound test call to a real phone (use your number for demo).
param(
    [Parameter(Mandatory = $true)]
    [string]$To,
    [string]$RetailerId = "R01",
    [string]$AgentId = ""
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

if (-not $env:BOLNA_API_KEY) {
    Write-Host 'Set $env:BOLNA_API_KEY first.'; exit 1
}

if (-not $AgentId) {
    $idFile = Join-Path $here "AGENT_ID.txt"
    if (Test-Path $idFile) { $AgentId = (Get-Content $idFile -Raw).Trim() }
}
if (-not $AgentId) { throw "Pass -AgentId or create agent first (AGENT_ID.txt)" }

# Seed shops — override phone in user_data to YOUR number for the demo
$shops = @{
    R01 = @{ shop_name = "Sharma Electricals"; retailer_name = "Ramesh Sharma"; phone = $To }
    R02 = @{ shop_name = "Gupta Sanitary"; retailer_name = "Suresh Gupta"; phone = $To }
}

$shop = $shops[$RetailerId]
if (-not $shop) { throw "Unknown RetailerId $RetailerId" }

$week = (Get-Date).ToString("dd MMM")
$body = @{
    agent_id = $AgentId
    recipient_phone_number = $To
    user_data = @{
        retailer_id = $RetailerId
        retailer_name = $shop.retailer_name
        shop_name = $shop.shop_name
        retailer_phone = $To
        distributor_name = "Bharat Hardware Distributors"
        week_label = $week
        preferred_language = "hi"
        timezone = "Asia/Kolkata"
        flow = "outbound"
    }
} | ConvertTo-Json -Depth 6

Write-Host "Calling $To as $($shop.shop_name) ($RetailerId)..."
$resp = Invoke-RestMethod -Method POST -Uri "https://api.bolna.ai/call" `
    -Headers @{
        Authorization = "Bearer $env:BOLNA_API_KEY"
        "Content-Type" = "application/json"
    } `
    -Body $body

$resp | ConvertTo-Json
if ($resp.execution_id) {
    Set-Content (Join-Path $here "LAST_EXECUTION_ID.txt") -Value $resp.execution_id -NoNewline
    Write-Host "execution_id saved. Phone should ring shortly."
}
