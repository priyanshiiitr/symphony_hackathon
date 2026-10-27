# Creates (or prints) the TradeCall outbound agent on Bolna.
# Requires: BOLNA_API_KEY env var, running API + tunnel, PUBLIC_URL.txt

param(
    [string]$BaseUrl = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

if (-not $env:BOLNA_API_KEY) {
    Write-Host @"

BOLNA_API_KEY is not set.

Do this:
  1. Open https://platform.bolna.ai  (sign up / log in)
  2. Go to Developers → API Keys → create a key
  3. In PowerShell (this machine):

       `$env:BOLNA_API_KEY = "bn-your-key-here"

  4. Re-run:  .\bolna\outbound\create-agent.ps1

"@
    exit 1
}

& (Join-Path $here "build-payload.ps1") -BaseUrl $BaseUrl | Out-Null
$payloadPath = Join-Path $here "agent_payload.json"
$body = Get-Content $payloadPath -Raw

if ($DryRun) {
    Write-Host "Dry run — payload at $payloadPath (not uploaded)"
    exit 0
}

Write-Host "Checking Bolna account..."
$me = Invoke-RestMethod -Uri "https://api.bolna.ai/user/me" -Headers @{ Authorization = "Bearer $env:BOLNA_API_KEY" }
Write-Host ("OK: {0}  wallet={1}" -f $me.email, $me.wallet)

Write-Host "Creating agent..."
try {
    $resp = Invoke-RestMethod -Method POST -Uri "https://api.bolna.ai/v2/agent" `
        -Headers @{
            Authorization = "Bearer $env:BOLNA_API_KEY"
            "Content-Type" = "application/json"
        } `
        -Body $body
} catch {
    Write-Host "Create failed:"
    Write-Host $_.ErrorDetails.Message
    throw
}

$resp | ConvertTo-Json -Depth 6
$agentId = $resp.agent_id
if ($agentId) {
    Set-Content -Path (Join-Path $here "AGENT_ID.txt") -Value $agentId -NoNewline
    Write-Host ""
    Write-Host "Saved agent_id → bolna\outbound\AGENT_ID.txt"
    Write-Host "Next: .\bolna\outbound\make-test-call.ps1 -To +91YOURNUMBER"
}
