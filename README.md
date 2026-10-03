# JeevanRoute — AI Emergency Commander (triage)

A public, no-login emergency triage agent for Nepal. The caller describes what
is happening (in Nepali or English); the agent interviews them, gives safe
immediate guidance, and — when it has enough — emits a structured triage state
ready to hand to a routing/facility agent.

Built on the SimulaChat OpenAI-compatible API (`default` model → Qwen3.8-27B)
with a Gradio `ChatInterface` frontend.

## Architecture

```
Browser  ->  Gradio UI (app.py)  ->  triage_turn() (triage_agent.py)  ->  SimulaChat API
                                 \-> route() (routing_agent.py)      ->  freehealth.mohp.gov.np (live beds)
```

The API key lives **server-side** in `.env` and is never sent to the browser.

Flow: the user describes the emergency and sets their **district**. The Triage
Agent interviews them and, when ready, emits the structured state. The Routing
Agent then queries the live public bed feed, picks the best hospital for the
triage requirements, and appends a "🏥 Recommended: …" block to the card.

## Setup

```bash
cd jeevanroute
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt

cp .env.example .env    # then put your real key in .env
```

## Run

```bash
python app.py           # opens http://localhost:7860
```

Or run the triage agent headless (no UI):

```bash
python triage_agent.py          # interactive chat, type 'quit' to exit
python triage_agent.py --demo   # scripted, no input needed
```

## Files

| File | Purpose |
|---|---|
| `app.py` | Gradio public chat UI; renders the emergency card + routing block |
| `triage_agent.py` | Triage Agent: interviews the user, calls `finish_triage` tool |
| `routing_agent.py` | Routing Agent: picks a hospital from live freehealth bed data |
| `.env` | Local secrets (gitignored) |
| `.env.example` | Template for `.env` |
| `requirements.txt` | Dependencies |

## How it works

- `triage_turn(history)` sends the chat history to the model with a
  `finish_triage` tool.
- If the model still needs info, it returns a question (in the user's language).
- When it has enough, it **calls `finish_triage`**; the tool arguments are the
  structured state: `urgency`, `suspected_pathway`, `symptoms`, `requirements`,
  `immediate_actions`, `do_not`, `needs_ambulance`.
- `app.py` renders that state as a clean emergency card (🔴/🟠/🟢).

## Security

- The API key is read from the `SIMULACHAT_API_KEY` env var only.
- `.env` is in `.gitignore` — never commit it.
- Rotate any key that has been shared in plaintext.

## Roadmap

- [x] Routing Agent: take `requirements` + district, query
      `https://freehealth.mohp.gov.np/api/bed-summary` (public, no auth) and
      recommend the best hospital.
- [ ] Blood-bank lookup via `/api/blood-bank/blood-groups/detail`.
- [ ] Voice input (Whisper / realtime) for callers who can't type.
- [ ] Real ETA via a routing/maps API (currently a model estimate).
