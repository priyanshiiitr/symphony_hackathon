# What I need from you (Phase B)

Reply in chat when each item is done.

## Required now

### A) Bolna API key

1. Go to https://platform.bolna.ai and sign up / log in  
2. Open **Developers → API Keys** → create key  
3. In **your** PowerShell (do not paste the key into chat if you prefer privacy):

```powershell
$env:BOLNA_API_KEY = "bn-xxxxxxxx"
```

4. Tell me: **“key is set”**

Then I (or you) run:

```powershell
cd e:\Voice_Ops
.\bolna\outbound\create-agent.ps1
```

### B) Your phone number for the test call

E.164 format, e.g. `+9198XXXXXXXX`  
I’ll use it as “Sharma Electricals” for the outbound demo.

### C) Keep these two running while we test

1. FastAPI on port 8000  
2. Cloudflare tunnel (`.\scripts\start-tunnel.ps1`)  
   — if you restarted the tunnel, update `scripts\PUBLIC_URL.txt` and rebuild:

```powershell
.\bolna\outbound\build-payload.ps1
```

## Optional (if create-agent fails on voice/STT)

In Bolna dashboard → **Providers**, connect free/sponsor keys for:

- Sarvam (Hindi TTS)  
- Deepgram (STT)  
- Or switch agent audio to whatever Bolna gives by default  

Also ensure wallet has a little credit (Bolna signup free credits).

## Not needed yet

Inbound agent, dashboard UI, AiSensy — later phases.
