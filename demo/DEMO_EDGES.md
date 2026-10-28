# Phase E — Edge-case demo scripts

Keep API + tunnel running. Console: http://127.0.0.1:8000/console/

Outbound agent and inbound agent must be updated after tunnel URL changes:
```powershell
py -3.12 bolna/outbound/update_agent.py
py -3.12 bolna/inbound/update_agent.py
```

---

## E1 — Barge-in (outbound)

**Setup:** Console → Sharma Electricals → **Call now** (costs 1 credit).

**Script:**
1. Let greeting start.
2. While Ravi is still talking, interrupt:  
   `Bhai suno — mujhe MCB nahi, PVC pipe chahiye`
3. Judge should see: agent **stops**, acknowledges pipe, continues without restarting the whole greeting.

**Pass:** No full reset; conversation continues on the interrupted intent.

---

## E2 — OOS + substitute (outbound)

**Setup:** Same outbound call (or a fresh one).

**You say:**  
`Mujhe 10 piece PVC pipe 1 inch chahiye`

**Expect:**
- Stock tool → **out_of_stock** (seed `PVC-PIPE-1` qty = 0)
- Agent offers substitute **PVC Pipe 3/4 inch** (or reduce qty)
- You: `Haan, 3/4 inch 10 piece de do`
- Confirm → order books on substitute

**Pass:** Tool-driven OOS + spoken substitute, not invented stock.

---

## E3 — Busy → callback (outbound)

**Setup:** Fresh outbound to Sharma.

**You say (early):**  
`Abhi busy hoon, shaam 5 baje call karna`

**Expect:**
- Routes to callback (no order)
- Agent asks/confirms time
- `@log_callback` fires
- Console **Callbacks** panel shows `CB-…. · shaam 5 baje`

**Pass:** Disposition visible on ops console.

---

## E4 — Unknown inbound caller

**Setup:** Call **+918064261996** from a number **not** in seed  
(or temporarily use father’s unverified SIM).  
Do **not** use +919571025342 for this story.

**You say:**  
`Order status chahiye` →  
`ORD one zero zero six` / `ORD-1006`

**Expect:**
- Agent does **not** invent “Sharma Electricals”
- Asks for order ID
- Speaks ORD-1006 status + ETA from API (without phone ownership block)

**Pass:** Unknown CLI → order-id path → real status.

---

## Quick offline proofs (no call credits)

```powershell
# OOS
Invoke-RestMethod -Method POST http://127.0.0.1:8000/v1/stock/check -ContentType application/json `
  -Body '{"retailer_id":"R01","sku_or_name":"PVC Pipe 1 inch","qty":"10"}'

# Callback log
Invoke-RestMethod -Method POST http://127.0.0.1:8000/v1/callbacks -ContentType application/json `
  -Body '{"retailer_id":"R01","phone":"+919571025342","shop_name":"Sharma Electricals","callback_slot":"shaam 5 baje","reason":"busy"}'
Invoke-RestMethod http://127.0.0.1:8000/v1/callbacks
```
