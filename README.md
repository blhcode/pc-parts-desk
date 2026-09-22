# PC Parts Desk

Local email-inbox PC building shop sim. Fake customers (via your LAN Ollama) email build requests; you reply with a [PCPartPicker](https://pcpartpicker.com) list link; they rate your work. Your shop has a star rating, reputation-driven inbound volume, SLA pressure while you play, and Game Over from bad-review streaks.

## Requirements

- Python 3.11+
- Node.js 20+
- Ollama reachable at `http://192.168.1.233:11434` with model `llama3.1:8b` (configurable in `.env`)

Optional (Cloudflare-blocked PCPartPicker fetches):

```bash
backend/.venv/bin/playwright install chromium
```

## Quick start

```bash
cd ~/Projects/pc-parts-desk
chmod +x start.sh
./start.sh
```

- Frontend: http://127.0.0.1:5173  
- API: http://127.0.0.1:8765  

Or run separately:

```bash
# terminal 1
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765

# terminal 2
cd frontend && npm run dev
```

## How to play

1. Create a save and name your shop.
2. Keep the inbox tab focused — heartbeats only run while you are actively playing (visible tab). No new mail or SLA aging when you leave.
3. Wait for customer emails (first one within about a minute of play).
4. Ask clarifying questions with **Send message**, or finish with **Send parts proposal** (PCPartPicker URL or paste).
5. Read the customer’s review. Build reputation for more frequent jobs. Too many bad reviews → Shop Closed.

## Config (`.env`)

| Variable | Default |
|----------|---------|
| `OLLAMA_URL` | `http://192.168.1.233:11434/api/chat` |
| `OLLAMA_MODEL` | `llama3.1:8b` |
| `PORT` | `8765` |
| `HEARTBEAT_TIMEOUT_SEC` | `15` |

Saves live in `backend/data/saves/`.
