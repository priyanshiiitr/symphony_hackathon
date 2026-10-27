# TradeCall × Bolna

## What you must do (once)

### 1. Bolna API key

1. Open **https://platform.bolna.ai** → sign up / log in  
2. **Developers → API Keys** → create a key  
3. In PowerShell:

```powershell
$env:BOLNA_API_KEY = "bn-xxxxxxxx"
```

(Optional: add that line to your user env vars so it persists.)

### 2. Keep API + tunnel running

Terminal A — backend:

```powershell
cd e:\Voice_Ops\backend
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

Terminal B — tunnel:

```powershell
cd e:\Voice_Ops
.\scripts\start-tunnel.ps1
```

Copy the new `https://….trycloudflare.com` URL into `scripts\PUBLIC_URL.txt` (overwrite).

Smoke:

```powershell
.\scripts\smoke-public.ps1 -BaseUrl (Get-Content .\scripts\PUBLIC_URL.txt)
```

### 3. Create outbound agent

```powershell
cd e:\Voice_Ops
.\bolna\outbound\create-agent.ps1
```

If Bolna rejects Sarvam/Deepgram (no BYOK credits), open the agent in the dashboard and pick voices/STT your wallet supports, or add provider keys under Bolna → Providers.

### 4. Real phone test

Put **your** number (E.164):

```powershell
.\bolna\outbound\make-test-call.ps1 -To "+91XXXXXXXXXX" -RetailerId "R01"
```

Answer, place a small order (e.g. MCB 2 piece). Then check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/whatsapp/outbox
Invoke-RestMethod http://127.0.0.1:8000/v1/retailers/R01/last-order
```

### 5. Also tell the agent (in chat)

After you set the key, say: **“key is set — create the agent”** and paste nothing secret in chat if you prefer — just confirm it’s in `$env:BOLNA_API_KEY`.

## Files

| Path | Role |
|------|------|
| `outbound/graph_nodes.json` | Outbound order graph |
| `outbound/tools.json` | Stock / order / WA tools |
| `outbound/create_agent.py` / `update_agent.py` / `make_test_call.py` | Outbound lifecycle |
| `inbound/graph_nodes.json` | Inbound status graph |
| `inbound/tools.json` | Lookup + order status tools |
| `inbound/create_agent.py` / `update_agent.py` / `setup_inbound.py` | Inbound lifecycle |
| `inbound/DUAL_DEMO.md` | Outbound → inbound demo script |

## Learning note

Bolna is the **voice runtime**. Your FastAPI is still the **source of truth**. Tools are just HTTPS calls from Bolna → tunnel → `127.0.0.1:8000`.
