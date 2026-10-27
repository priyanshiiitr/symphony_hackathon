# Expose local TradeCall API (port 8000) to the public internet for Bolna tools.
# Keep this window open while demoing. URL changes each run (quick tunnel).

$ErrorActionPreference = "Stop"
$cloudflared = Join-Path $PSScriptRoot "bin\cloudflared.exe"

if (-not (Test-Path $cloudflared)) {
    Write-Host "Missing $cloudflared — download cloudflared-windows-amd64.exe into scripts\bin\"
    exit 1
}

Write-Host "Tunneling http://127.0.0.1:8000 ..."
Write-Host "Copy the https://....trycloudflare.com URL into Bolna tool configs."
& $cloudflared tunnel --url http://127.0.0.1:8000
