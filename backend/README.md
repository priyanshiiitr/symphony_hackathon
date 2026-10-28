# TradeCall Backend

Mock hardware ERP + **ops console** (Phase D).

## Ops console

With the API running:

- http://127.0.0.1:8000/console/
- or http://127.0.0.1:8000/

Set `BOLNA_API_KEY` on the **uvicorn process** so **Call now** can dial via Bolna.

## Public tunnel (needed before Bolna)

Keep the API running on port 8000, then in another terminal:

```powershell
cd e:\Voice_Ops
.\scripts\start-tunnel.ps1
```

Copy the `https://….trycloudflare.com` URL. Smoke test:

```powershell
.\scripts\smoke-public.ps1 -BaseUrl "https://YOUR-SUBDOMAIN.trycloudflare.com"
```

That public base URL is what Bolna custom tools will call (e.g. `{BASE}/v1/stock/check`).

## Setup (once)

```powershell
cd e:\Voice_Ops\backend
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

## Run the API

```powershell
cd e:\Voice_Ops\backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

## Verify

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/v1/retailers
Invoke-RestMethod http://127.0.0.1:8000/v1/retailers/R01
Invoke-RestMethod http://127.0.0.1:8000/v1/retailers/R01/last-order

$body = @{
  retailer_id = "R01"
  items = @(
    @{ sku_or_name = "mcb batti wala"; qty = 10 },
    @{ sku_or_name = "PVC pipe 1 inch"; qty = 20 }
  )
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/v1/stock/check -ContentType "application/json" -Body $body

$orderBody = @{
  retailer_id = "R01"
  items = @(
    @{ sku_or_name = "MCB-32A"; qty = 5 },
    @{ sku_or_name = "copper wire"; qty = 1 }
  )
  confirmed_by_voice = $true
} | ConvertTo-Json -Depth 5
$created = Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/v1/orders -ContentType "application/json" -Body $orderBody
$created
Invoke-RestMethod "http://127.0.0.1:8000/v1/orders/$($created.order_id)"

# Inbound identify + status scrubber
Invoke-RestMethod "http://127.0.0.1:8000/v1/retailers/by-phone?phone=%2B919876543211"
Invoke-RestMethod "http://127.0.0.1:8000/v1/orders/ORD-1003/status"
$patch = @{ status = "dispatched"; eta_text = "Kal dopahar tak" } | ConvertTo-Json
Invoke-RestMethod -Method PATCH -Uri http://127.0.0.1:8000/v1/orders/ORD-1003/status -ContentType "application/json" -Body $patch

# WhatsApp mock
$wa = @{
  retailer_phone = "+919876543210"
  order_id = "ORD-1006"
  summary_text = "TradeCall: Order ORD-1006 confirmed. MCB 32A x5, Copper Wire 1.5mm x1. Delivery in 2 days."
} | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/v1/whatsapp/send -ContentType "application/json" -Body $wa
Invoke-RestMethod http://127.0.0.1:8000/v1/whatsapp/outbox
```

Interactive docs: http://127.0.0.1:8000/docs

**Note:** Replace `R01` phone in `app/data/seed.json` with your real number before Phase B live calls.
