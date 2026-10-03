# JeevanRoute

## Hackathon submission

**Team:** Utterly Clueless<br>
**Institution:** St. Xaviers College, Maitighar, Nepal

**Submission repository:** <https://github.com/fiero901/Utterly_Clueless>

JeevanRoute is a no-login emergency triage and care-routing assistant for Nepal. A caller describes what is happening in English or Nepali; the app asks focused questions, identifies urgency, recommends immediate action, and routes the caller to a nearby hospital with available beds when live data is available.

## Why it is safe

- The AI conducts the conversation but does not own the final urgency decision.
- Deterministic Python rules detect high-risk red flags and decide when to surface **Call 102 / 112 now**.
- Hospital recommendations use a deterministic ranking layer based on free beds, location, facility size, public status, and optional road ETA.
- Browser history stores only structured routing summaries; medical conversation text is not persisted.
- API credentials stay server-side in `.env` and are never sent to the browser.

## How it works

```text
Gradio UI → Agno Commander → structured triage proposal
                         ↓
              deterministic safety checks
                         ↓
       live beds + routing context + hospital ranking
```

The app combines:

- Agno + SimulaChat for the focused interview
- Gradio 6 for the web interface
- MoHP free-bed data for hospital availability
- Nominatim and OSRM for geocoding and road ETA
- Open-Meteo for weather
- BIPAD for nearby earthquake and fire context
- A vendored public-bodies CSV for local information-officer contacts

All external data sources are keyless and degrade gracefully when unavailable.

## Run locally

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
cp .env.example .env
# Set SIMULACHAT_API_KEY in .env
uv run app.py
```

Open <http://localhost:7860>.

For development with auto-reload:

```bash
uv run watchfiles "uv run app.py" .
```

## Verify

The test suite is offline: external APIs and the model are stubbed.

```bash
uv run pytest -q
uv run ruff check .
```

## Repository guide

| Path | Purpose |
|---|---|
| `app.py` | Gradio UI, browser state, streaming flow, card rendering |
| `commander.py` | Agno Commander and model interaction |
| `triage_state.py` | Safety checks, triage coercion, and hospital ranking |
| `context.py` | Live beds, geocoding, ETA, weather, and disaster context |
| `publicbodies.py` | Offline public-body and information-officer lookup |
| `knowledge/` | Verified Nepal-specific operator guidance |
| `data/publicbodies.csv` | Vendored public-body dataset |
| `tests/` | Offline regression tests |

## Submission notes

Upload the tracked project files to the hackathon repository manually. Do **not** upload:

- `.env` or any API key
- `.venv/`
- Python/tool caches such as `__pycache__/`, `.pytest_cache/`, or `.ruff_cache/`

Use `.env.example` as the configuration template. Emergency numbers and local service coverage should be rechecked before production use.
