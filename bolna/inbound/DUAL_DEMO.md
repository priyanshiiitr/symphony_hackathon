# Phase C — Dual demo (outbound → inbound)

## Prerequisites

1. API on `:8000` + Cloudflare tunnel (`scripts/PUBLIC_URL.txt` current)
2. Outbound agent already works (Phase B)
3. Inbound agent created + linked to a Bolna number
4. Seed retailer **R01** phone = your mobile `+919571025342`

## One-time setup

```powershell
$env:BOLNA_API_KEY = [System.Environment]::GetEnvironmentVariable("BOLNA_API_KEY", "User")
cd e:\Voice_Ops
py -3.12 .\bolna\inbound\create_agent.py   # already done → AGENT_ID.txt
```

**Phone number (required for live inbound):** Bolna account currently has `GET /phone-numbers/all → []`.  
In [platform.bolna.ai](https://platform.bolna.ai) buy/assign a Plivo (or other) number, then:

```powershell
py -3.12 .\bolna\inbound\setup_inbound.py
# or: py -3.12 .\bolna\inbound\setup_inbound.py --phone-id <uuid>
```

Optional — Bolna dashboard → inbound agent → Identify callers → Internal API URL:

`{PUBLIC_URL}/v1/inbound/caller-context`

Optional: Bolna dashboard → inbound agent → **Identify callers** → Internal API:

`GET {PUBLIC_URL}/v1/inbound/caller-context`

(no auth needed for demo; Bolna will pass `contact_number`)

After tunnel URL changes:

```powershell
py -3.12 .\bolna\inbound\update_agent.py
```

## Script (flawless loop)

1. **Outbound** (optional if ORD-1006 still in memory): place order as R01 → note `order_id`
2. Optionally scrub status:
   ```powershell
   Invoke-RestMethod -Method PATCH -Uri "http://127.0.0.1:8000/v1/orders/ORD-1006/status" `
     -ContentType "application/json" `
     -Body '{"status":"dispatched","eta_text":"Kal dopahar tak pahunch jayega"}'
   ```
3. From **same phone** (`+919571025342`), dial **`+918064261996`** (TradeCall inbound / VoBiz)
4. Agent greets Sharma Electricals → status + ETA
5. Check WA outbox from outbound step: `GET /v1/whatsapp/outbox`

## Offline smoke (no call credits)

```powershell
$u = (Get-Content e:\Voice_Ops\scripts\PUBLIC_URL.txt -Raw).Trim()
Invoke-RestMethod "$u/v1/inbound/caller-context?contact_number=%2B919571025342"
Invoke-RestMethod -Method POST -Uri "$u/v1/retailers/lookup-by-phone" -ContentType "application/json" `
  -Body '{"phone":"+919571025342"}'
Invoke-RestMethod -Method POST -Uri "$u/v1/orders/status" -ContentType "application/json" `
  -Body '{"order_id":"ORD-1006","phone":"+919571025342"}'
```
