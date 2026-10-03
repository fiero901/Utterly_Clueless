# JeevanRoute — AI Emergency Commander (triage)

A public, no-login emergency triage agent for Nepal. The caller describes what
is happening (in Nepali or English); the agent interviews them, gives safe
immediate guidance, and — when it has enough — emits a structured triage state
ready to hand to a routing/facility agent.

Built on the SimulaChat OpenAI-compatible API (`default` model → Qwen3.8-27B),
LangGraph orchestration, and a Gradio chat frontend.

## Architecture

```
 Browser  ->  Gradio UI (app.py)  ->  LangGraph (agent_graph.py)
                                      ├─ triage_turn() -> SimulaChat API
                                      └─ route()        -> freehealth.mohp.gov.np (live beds)
                                      \-> build_context_block() (context.py)
                                           ├─ Nominatim/OSM  (geocode district + hospital)
                                           ├─ OSRM           (real road ETA)
                                           ├─ Open-Meteo     (current weather)
                                           └─ BIPAD          (nearby earthquake/fire alerts)
                                      \-> find_officer() (publicbodies.py)
                                           └─ data/publicbodies.csv (agency + info officer, offline)
```

The API key lives **server-side** in `.env` and is never sent to the browser.

Flow: the user describes the emergency and sets their **district**. The Triage
Agent interviews them and, when ready, emits the structured state. The Routing
Agent then queries the live public bed feed, picks the best hospital for the
triage requirements, and appends a "🏥 Recommended: …" block to the card.

## Setup (using `uv`)

```bash
cd jeevanroute
uv sync --extra dev     # creates .venv + installs deps (fast, reproducible)

cp .env.example .env    # then put your real key in .env

./fetch_model.sh        # downloads the local embedding model (~120MB, one-off)
```

`fetch_model.sh` is only needed for **semantic recall** (local memory search).
The app runs without it — recall just degrades to recency-only. The model is
served locally at `/models`, so the browser never contacts huggingface.co.

## Run

```bash
# Development (auto-reloads on any .py change):
uv run watchfiles "uv run app.py" .

# Production / no reload:
uv run app.py
```

Both open http://localhost:7860.

> `uvx` is for one-off tools (e.g. `uvx ruff check .`); use `uv run` for the
> app itself so your local modules are on the path and the `.venv` is used.

Or run the triage agent headless (no UI):

```bash
python triage_agent.py          # interactive chat, type 'quit' to exit
python triage_agent.py --demo   # scripted, no input needed
```

## Files

| File | Purpose |
|---|---|
| `app.py` | Gradio public chat UI; renders the emergency card + routing block |
| `agent_graph.py` | LangGraph state graph coordinating triage and hospital routing |
| `triage_agent.py` | Triage Agent: interviews the user, calls `finish_triage` tool |
| `routing_agent.py` | Routing Agent: picks a hospital from live freehealth bed data |
| `context.py` | Live context: real OSRM ETA + Open-Meteo weather + BIPAD disaster alerts (all free, keyless) |
| `publicbodies.py` | Public body + Information Officer lookup for the caller's district (offline CSV) |
| `memory.js` | Browser-side local memory: IndexedDB + localStorage + local embeddings (Transformers.js) |
| `data/publicbodies.csv` | Vendored snapshot of the Open Knowledge Nepal publicbodies dataset |
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

## Free data sources (all keyless, no signup)

`context.py` enriches the routing recommendation with live context from public
endpoints that require **no API key and no account**:

| Source | Used for | Notes |
|---|---|---|
| **Nominatim** (OSM) | Geocode the caller's district + the hospital's municipality | Rate-limited ~1 req/s; we sleep between calls |
| **OSRM** (demo) | Real driving ETA between the two points | Demo server; self-host for production |
| **Open-Meteo** | Current weather (rain / heat / wind) at the caller | Flags adverse conditions that slow transport |
| **BIPAD** | Recent earthquakes & fires near the caller | Official Nepal disaster platform, public API |

`publicbodies.py` adds one more, **offline** source:

| Source | Used for | Notes |
|---|---|---|
| **Open Knowledge Nepal** (`publicbodies-data`) | The relevant public body + its **Information Officer** (name, phone, email) for the caller's district | Vendored CSV (432 bodies, 71 districts); no network call. Re-copy `data/publicbodies.csv` to refresh. |

Every call degrades gracefully — if a source is slow or down, the emergency
card still renders (the context block is simply omitted).

Still on the roadmap (need a key, registration, or offline data work):
- **OpenAQ** (air quality) — free key, v3 API only.
- **NHFR** (facility capabilities) — no public API; parse the MoHP PDF offline.
- **WorldPop** (population rasters) — for the "healthcare desert" map.
- **Nepal DHS 2022** — free registration for microdata.

## Local memory (browser-side, private)

JeevanRoute can **remember user preferences and conversation history locally in
the browser** — on the user's device only. Nothing is sent to any server.

```
Browser
├── localStorage  → tiny prefs: language, preferred district, consent, location-shared
└── IndexedDB     → memories (text + embedding + metadata)
      └── local embedding model (Transformers.js, multilingual MiniLM, 384-dim)
            → brute-force cosine similarity → top-k semantic recall
```

- **Hybrid retrieval**: known facts (language, district) use key-value lookup;
  fuzzy recall ("what did I say before about my mother's hospital?") uses local
  vector search.
- **Consent-first**: a first-run prompt asks "Remember this on this device?"
  before anything is stored.
- **Status bar + gate**: the app shows `🧠 Local memory: on | 📍 Location:
  shared (KATHMANDU) [change]`. The chat input is **disabled until both**
  memory consent and a district are set — the district row only appears when
  the user clicks **[set]**/**[change]**, then hides again once saved.
- Local memory can be removed by clearing this site's browser data.
- **Offline-safe**: the embedding model is **served locally** by the app
  (`models/` → `http://localhost:7860/models/...`), so no huggingface.co
  access is needed. If the model can't load, recall degrades to recency-only
  — the app never breaks.

> **Your personal context never leaves your device.** This is a feature, not a
> limitation — ideal for a health app where callers may be hesitant to share
> sensitive details with a server.

## Security

- The API key is read from the `SIMULACHAT_API_KEY` env var only.
- `.env` is in `.gitignore` — never commit it.
- Rotate any key that has been shared in plaintext.
- Local memory is **browser-only** (IndexedDB/localStorage). It is never
  transmitted to the backend or any third party.

## Roadmap

- [x] Routing Agent: take `requirements` + district, query
      `https://freehealth.mohp.gov.np/api/bed-summary` (public, no auth) and
      recommend the best hospital.
- [ ] Blood-bank lookup via `/api/blood-bank/blood-groups/detail`.
- [ ] Voice input (Whisper / realtime) for callers who can't type.
- [ ] Real ETA via a routing/maps API (currently a model estimate).
