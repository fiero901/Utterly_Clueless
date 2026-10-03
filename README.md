# JeevanRoute — AI Emergency Commander (triage + routing)

A public, no-login emergency triage agent for Nepal. The caller describes what
is happening (in Nepali or English); a single AI "Commander" agent interviews
them, gives safe immediate guidance, and — when it has enough — emits a
structured triage state. A **deterministic Python layer** (no LLM) then finalizes
urgency, the "call 102 now" decision, and the recommended hospital from the live
public bed feed, rendered as a rich card in the UI.

Built on the **Agno** agent framework + a **Gradio 6** `gr.Blocks` UI, driven by
the SimulaChat OpenAI-compatible API (`default` model → Qwen3.8-27B).

## Architecture

```
 Browser  ->  Gradio 6 UI (app.py, 3-column gr.Blocks)
                 ├─ BrowserState (prefs / history / last triage — browser-local)
                 ├─ geolocation (navigator.geolocation -> reverse-geocode to district)
                 └─ chat  ->  commander.run_turn()
                                      │
                          Agno "Commander" Agent (commander.py)
                          ├─ model: SimulaChat OpenAI-compatible API
                          ├─ db:    InMemoryDb  (multi-turn session memory)
                          └─ tool:  finish_triage()  -> raw triage dict
                                      │
                          deterministic layer (triage_state.py)  [NO LLM]
                          ├─ coerce_triage()      (safe type coercion — model
                          │                         does not honor enum constraints)
                          ├─ assess_urgency()     (red-flag rules, 102/call-now)
                          └─ candidate_pool + rank_hospitals (pure ranking)
                                      │
                          context.py (live, keyless)  +  publicbodies.py (offline)
                          ├─ freehealth.mohp.gov.np   live public beds
                          ├─ Nominatim/OSM            geocode district + hospital
                          ├─ OSRM                     real road ETA
                          ├─ Open-Meteo               current weather
                          ├─ BIPAD                    nearby earthquake/fire alerts
                          └─ data/publicbodies.csv    agency + info officer (offline)
```

**Hybrid triage (the design that makes this safe):** the LLM conducts the
interview and proposes a triage; deterministic Python is the *source of truth*
for urgency, the 102/call-now rule, and hospital ranking. The model's output is
treated as a *proposal* that is coerced and double-checked — it can never
escalate a case out of a red-flag branch or rank a hospital arbitrarily.

The API key lives **server-side** in `.env` and is never sent to the browser.

Flow: the user describes the emergency and sets their **district** (typed, or
via the 📍 browser geolocation button). The Commander interviews them and, when
ready, calls `finish_triage`. The deterministic layer then finalizes urgency,
queries the live bed feed, ranks the best hospital for the caller's district,
and renders a card: urgency badge → 🚨 call 102 (if warranted) → red flags →
recommended hospital with a `tel:` link → alternates → live context
(weather / ETA / nearby alerts).

## Setup (using `uv`)

```bash
cd jeevanroute
uv sync --extra dev     # creates .venv + installs deps (fast, reproducible)

cp .env.example .env    # then put your real SIMULACHAT_API_KEY in .env
```

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

## Test / lint

```bash
uv run pytest -q        # deterministic layer + commander (stubbed) + context
uv run ruff check .     # lint (line-length 100, E/F/I/W)
```

The test suite is **offline** (SimulaChat + the bed feed are stubbed/
monkeypatched), so it runs in a couple of seconds with no network or API key.

## Files

| File | Purpose |
|---|---|
| `app.py` | Gradio 6 `gr.Blocks` 3-column emergency command UI; renders the card |
| `commander.py` | The single Agno "Commander" agent (`finish_triage` tool, multi-turn session) |
| `triage_state.py` | Deterministic layer: `TriageState`, `coerce_triage`, `assess_urgency`, `rank_hospitals` (no LLM) |
| `context.py` | Live context: freehealth beds + OSRM ETA + Open-Meteo weather + BIPAD alerts (all free, keyless) |
| `publicbodies.py` | Public body + Information Officer lookup for the caller's district (offline CSV) |
| `data/publicbodies.csv` | Vendored snapshot of the Open Knowledge Nepal publicbodies dataset |
| `tests/` | Offline pytest suite for the deterministic layer, commander, and context |
| `.env` | Local secrets (gitignored) |
| `.env.example` | Template for `.env` |
| `requirements.txt` | Dependencies (mirrors `pyproject.toml`) |

## How it works

- `commander.run_turn(message, emergency_id, district)` sends the message to the
  Agno agent (with an optional `<context>` district prefix). Multi-turn history
  is kept by an Agno `InMemoryDb` session keyed `emergency:<emergency_id>`.
- If the model still needs info, it returns a question in the user's language.
- When it has enough, it **calls `finish_triage`**; `run_turn` extracts the tool
  arguments from the run output and coerces them into a `TriageState` via
  `coerce_triage` (which never raises on malformed model output).
- `triage_state.assess_urgency` applies red-flag rules and finalizes
  `urgency` / `needs_ambulance` / `call_now`.
- `app.py` pools + ranks hospitals for the caller's district from the live bed
  feed and renders the card (🔴/🟠/🟢), with a "📍 Context" block (weather / ETA
  / nearby alerts) from `context.py`.

## Free data sources (all keyless, no signup)

`context.py` enriches the recommendation with live context from public
endpoints that require **no API key and no account**:

| Source | Used for | Notes |
|---|---|---|
| **freehealth.mohp.gov.np** | Live public hospital beds (`/api/bed-summary`) | Official MoHP feed; facility size proxies capability |
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

## Local state (browser-side, private by design)

Preferences and triage history persist **only in the browser** via Gradio's
`BrowserState` (localStorage, `storage_key="jeevanroute"`):

- **What is stored:** preferred language, district, a short list of past
  *structured* triage entries (district, urgency, recommended hospital,
  timestamp), and the last triage state.
- **What is never stored:** the medical conversation text itself. This is a
  deliberate privacy boundary — we persist a routing *summary*, not the patient
  narrative.
- Clear this site's browser data to remove it.

## Security

- The API key is read from the `SIMULACHAT_API_KEY` env var only.
- `.env` is in `.gitignore` — never commit it.
- Rotate any key that has been shared in plaintext.
- Browser state is **local-only** (localStorage). It is never transmitted to the
  backend or any third party, and holds no medical chat text.

## Roadmap

- [x] Agno "Commander" agent driving a Gradio 6 three-column emergency UI.
- [x] Deterministic triage layer (coerce + red-flag urgency + hospital ranking).
- [x] Live public-bed feed (freehealth) + OSRM ETA + weather + disaster alerts.
- [ ] Per-hospital road ETA from the caller's precise coordinates (Phase 1.x).
- [ ] Rich card as a Gradio component (structured result with Call/Directions
      buttons) instead of Markdown (Phase 2).
- [ ] Voice input (Whisper / realtime) for callers who can't type.
- [ ] Blood-bank lookup via `/api/blood-bank/blood-groups/detail`.
