# JeevanRoute — Agno Backend + Gradio 6 Emergency UI — Design

- **Date:** 2026-10-03
- **Status:** Draft for review
- **Owner:** sushantgautam
- **Path:** docs/superpowers/specs/2026-10-03-agno-gradio-emergency-ui-design.md

## 1. Purpose

Re-architect JeevanRoute (an AI emergency triage + hospital routing agent for
Nepal) from a **LangGraph** orchestration onto **Agno**, and rework the **Gradio 6**
frontend from a single chat column into a true **emergency command UI**:
visible agent activity, a live triage/routing status card, a step-based
Walkthrough, and browser-local conversation history — with **no React, no custom
agent loop, no custom chat-history code, and minimal custom CSS.**

The differentiator that must be protected is the **Nepal data + workflow**:
the live `freehealth.mohp.gov.np` bed feed, the free context layer
(weather / road ETA / disaster alerts), and the offline public-body lookup.

## 2. Verified feasibility (spike evidence — do NOT re-litigate)

A throwaway spike ran against the real SimulaChat endpoint with
`agno==3.1.1` and the installed `gradio==6.29.1`. All capabilities the design
depends on were **confirmed working**:

| Capability | Mechanism (Agno 3.1.1 / Gradio 6.29.1) | Result |
|---|---|---|
| LLM chat via SimulaChat | `OpenAIChat(id="default", api_key=…, base_url="https://simulachat.sushant.info.np/api/v1")` | ✅ returned `PONG` |
| Tool call + capture | `@tool(stop_after_tool_call=True)`; `out.tools: list[ToolExecution]` with `.tool_name/.tool_args/.result` | ✅ called `finish_triage` |
| Pydantic structured output | `Agent(output_schema=TriageState, structured_outputs=True)` → schema-shaped JSON in `out.content` | ✅ produced valid JSON |
| Multi-turn history | Requires a `db`. `InMemoryDb()` (no infra) | ✅ turn 2 recalled turn 1 |
| Browser-local state | `gr.BrowserState(default_value, storage_key=…)` (encrypted JSON in localStorage) | ✅ present in install |
| Tool activity in chat | `ChatMessage.metadata = {"title","status",…}` (collapsible) | ✅ present in install |
| Rich card in a message | `Chatbot(type="messages")` with `ComponentMessage` (`type="component"`) | ✅ present in install |
| Step-based flow | `gr.Walkthrough` + `gr.Step` | ✅ present in install |

**Critical finding that shapes the design:** the Qwen model does **NOT**
honor constrained enums in tool args. In the spike it returned
`urgency="Immediate — call EMS/911 now; time-critical stroke window"` instead
of `critical|urgent|stable`. Therefore all model output **must be coerced by a
deterministic Python layer** — never trusted raw. This justifies the
"hybrid" architecture in §4.

## 3. Non-goals (YAGNI)

- No server-side patient database; the caller is the data source.
- No React / JS framework / custom CSS framework / custom agent loop.
- No custom chat-history implementation (use `BrowserState` + `Chatbot`).
- No deployment/AgentOS runtime, no Postgres, no MCP — single `uv run` process.
- Phase 1 does **not** do medical image diagnosis (see §9).
- No live voice input (Whisper) in Phase 1 (see §9).

## 4. Architecture (Approach A)

```
                       BROWSER (user's device only)
 ┌────────────────────────────────────────────────────────────────┐
 │ Gradio 6 (gr.Blocks)                                            │
 │  • gr.Chatbot(type="messages")  — middle column                 │
 │      assistant messages carry:                                  │
 │        metadata  = visible tool activity (collapsible)          │
 │        type="component" = rich hospital card                    │
 │  • gr.Walkthrough — 6-step progress (top bar)                   │
 │  • Live Status card (right column) — urgency/vitals/loc/hospital│
 │  • gr.BrowserState — prefs (lang, district, consent) +          │
 │      previous-emergencies (ChatGPT-like history)                │
 │  • geolocation JS (small, only for coords)                      │
 └───────────────────────────────┬────────────────────────────────┘
                                 │  (Python event handlers)
 ┌───────────────────────────────▼────────────────────────────────┐
 │ app.py — orchestration (replaces agent_graph.py + memory.js)    │
 │   for each user message:                                        │
 │     1. agent.run(msg, session_id=emergency_id)  [Agno]          │
 │     2. if out.tools has finish_triage -> coerce TriageState     │
 │     3. deterministic pipeline:                                  │
 │          assess_urgency()  (rules) -> urgency, call_102?        │
 │          rank_hospitals()  (score) -> top facility              │
 │          build_context_block() (context.py) weather/ETA/disaster │
 │          find_officer() (publicbodies.py) -> contact            │
 │     4. render ChatMessage(s) + Live Status + Walkthrough step   │
 │     5. persist to BrowserState (history) + state                │
 └───────┬───────────────────────────────┬────────────────────────┘
         │                               │
 ┌───────▼────────────┐          ┌────────▼─────────────────────────┐
 │ commander.py (Agno)│          │ triage_state.py (Pydantic + rules)│
 │ Agent(model, tools)│          │   TriageState model               │
 │  tool: finish_triage           │   coerce_triage()  (enum fix)    │
 │  memory: InMemoryDb           │   assess_urgency() (deterministic)│
 │  instructions (Nep/Eng)       │   rank_hospitals() (deterministic)│
 └───────┬────────────┘          └──────────────────────────────────┘
         │
 SimulaChat (OpenAI-compatible, model="default")
```

**Key structural change:** Agno owns *only conversational triage*. The
**deterministic pipeline** owns every safety-critical decision (urgency
severity, the "call 102" gate, hospital ranking) — the model cannot make them.

## 5. Components & files

| File | Purpose | Status |
|---|---|---|
| `commander.py` | Agno `Agent` (SimulaChat) + `finish_triage` tool + `InMemoryDb` memory + instructions. Exposes `run_turn(emergency_id, message, context) -> TurnResult` | **new** |
| `triage_state.py` | `TriageState` (Pydantic), `coerce_triage(raw)`, `assess_urgency()`, `rank_hospitals(cands, triage, district)` — all deterministic | **new** |
| `context.py` | Live context (OSRM ETA, Open-Meteo, BIPAD) | **keep** (unchanged) |
| `publicbodies.py` | Offline public-body / Information Officer lookup | **keep** (unchanged) |
| `app.py` | `gr.Blocks` UI + event handlers + orchestration loop + `BrowserState` + Walkthrough + rich card rendering | **rewrite** |
| `agent_graph.py` | LangGraph graph | **delete** (replaced by app.py loop) |
| `triage_agent.py` / `routing_agent.py` | Old OpenAI-based agents | **delete** (replaced by commander.py + triage_state.py) |
| `memory.js` | Browser memory (IndexedDB + embeddings + consent JS) | **delete** (replaced by `BrowserState`); semantic-recall kept as Phase 2 |
| `data/publicbodies.csv` | Vendored offline data | **keep** |
| `models/` + `fetch_model.sh` | Local embedding model | **keep**, only used by Phase 2 recall |

## 6. Data flow (one user turn)

1. **User submits** text (and optional geolocation). Python handler receives
   `(message, history, district, coords, prefs)` where `history` is the full
   message list for this emergency (recovered from `BrowserState`).
2. **`commander.run_turn(emergency_id, message, context)`**:
   - builds `context` string = district + "coords available for routing" +
     (Phase 2) recalled memories.
   - `agent.run(message, session_id=emergency_id)`.
   - returns `TurnResult`:
     - if a `finish_triage` tool ran → `raw_triage` (its `tool_args`) +
       final `reply_text`;
     - else → the agent's follow-up question (`reply_text`), `raw_triage=None`.
3. **`triage_state.coerce_triage(raw_triage)`** → a validated `TriageState`:
   maps free-text urgency to `critical|urgent|stable` (keyword/regex rules),
   validates `requirements` against a known set, fills defaults. **Never**
   trusts the raw enum.
4. **`assess_urgency(triage)`** (deterministic) → re-derives urgency from
   hard red flags (unconscious, no breathing, major bleeding, stroke symptoms,
   chest pain + sweating) and sets `call_102` + `needs_ambulance`. This can
   **override** the coerced value upward (never down).
5. **`rank_hospitals(cands, triage, district, eta_map=None)`** (deterministic,
   **pure/offline** — no network): filter district-first (else same-province),
   then rank by a transparent score over the fields the feed actually has:
   `score = 1.0*norm(free_beds) + 0.5*norm(capacity) + 0.5*norm(eta)`
   - `capacity` = `total_bed_capacity` (larger facility ⇒ more likely to have
     CT/ICU/stroke capability). **The live feed has NO capability flags** (why
     the old code used the LLM to *assume* them), so we proxy capability from
     facility size rather than inventing it.
   - `eta` term is only applied when the caller passes an optional
     `eta_map = {facility_name: eta_minutes}` (computed by `app.py` via
     `context.driving_minutes`); otherwise it's 0 — so ranking never blocks on
     the slow Nominatim/OSRM calls.
   - **Displayed capabilities** on the card are a small, explicit
     named-facility mapping (e.g. "…Teaching Hospital" ⇒ CT/ICU) labelled
     "assumed"; everything else shows "general emergency".
   - The card's **ETA / weather / disaster** lines come from `context.py`
     (existing, already degrades gracefully). **No LLM in ranking or
     capability display; no raw GPS leaked to the model.**
6. **Render** (assistant turns, in order):
   - the agent's **reply text** (its question or closing guidance);
   - the emergency **card** (urgency emoji, symptoms, do/don't, call-102) as
     formatted Markdown;
   - the **hospital card** as formatted Markdown with real `tel:` and
     Google-Maps links (guaranteed to render in any Gradio theme). (A native
     `Chatbot type="component"` card is the Phase 2 upgrade.)
   - a trailing **status line** listing the completed pipeline steps
     ("🏥 Hospitals ✓  🚑 Ambulance ✓  📍 ETA ✓") — the proven "updating
     status message" pattern already used by the current app. (Native
     `ChatMessage.metadata` collapsible thoughts are the Phase 2 upgrade.)
7. **Update** Live Status card + advance `Walkthrough` step; **persist** the
   message list + current `TriageState` to `BrowserState` (keyed by
   `emergency_id`).

## 7. Live Status card & Walkthrough

- **Live Status (right column)** reflects `TriageState` after each turn:
  urgency (🔴/🟠/🟢), breathing / conscious / bleeding (from `symptoms`),
  district, and the current recommended hospital. Updates via event
  `outputs` each turn — no polling.
- **Walkthrough steps** (top bar):
  ① Understand → ② Assess urgency → ③ Determine care → ④ Find facility →
  ⑤ Find transport → ⑥ Action plan. The handler reflects how far the pipeline
  got this turn (e.g. triage pending = step 1-2; hospital found = step 4-5;
  plan = step 6).

  > **Correction (verified against Gradio 6.29.1):** `gr.Walkthrough` is a
  > *layout* (`BlockContext`), not a data component — its `selected` value
  > **cannot be updated from an event handler** (no `.update()`, no state).
  > Therefore the **live** step-progress is rendered by an updateable
  > `gr.Markdown` (a 3-line ✅/⏳/⬜ checklist that updates each turn), while
  > the native `gr.Walkthrough` + `gr.Step` is retained as a *static*
  > "How this works" legend (collapsible). The six conceptual steps above are
  > compressed to a 3-phase live indicator (understand / assess / route); the
  > finer sub-steps remain visible in the static legend and the status card.

## 8. Browser-local state (replaces `memory.js`)

- `gr.BrowserState(storage_key="jeevanroute")` holds:
  - `prefs`: `{language, district, consent, location_shared}`
  - `history`: `[{emergency_id, title, urgency, messages:[…], state:{…}}]`
- **Privacy:** only preferences + user-chosen emergency profiles are stored;
  raw medical detail stays in the per-emergency message list the user already
  initiated. A first-run **consent** checkbox gates persistence (mirrors the
  current consent-first behavior). "New emergency" clears the active
  `emergency_id` (new Agno `session_id`).
- **Geolocation:** a single small inline JS promise returns `[lat,lng]`
  (only the current `GEO_JS`), reverse-geocoded server-side via
  `context.reverse_geocode`. No `memory.js`.
- **Phase 2 (optional):** re-introduce the local-embedding semantic recall
  behind a flag; `BrowserState` still owns prefs/history. The embedding model
  stays served locally (`/models`).

## 9. Multimodal (Phase 2, optional, bounded)

- Enable `multimodal=True` on the `Chatbot`/input so the user can attach an
  image (e.g. a medical document / injury photo).
- Files are passed to the model as bounded, **non-diagnostic** context
  ("what does this document say about the patient?"). **Never** frame output
  as a medical image diagnosis. If SimulaChat's vision capability is
  unconfirmed at build time, **degrade gracefully**: accept the attachment,
  tell the user it was noted but not interpreted, and continue the text
  interview. This is out of Phase 1 scope.

## 10. Error handling & degradation

- **LLM unreachable** → assistant message: "⚠️ The triage AI is unreachable.
  In a real emergency call **102**." (never crash the UI.)
- **No hospital with free beds** (a district) → "Call 102" fallback (already
  the current behavior).
- **Context sources** (OSRM / weather / BIPAD / officer) → each already
  degrades to empty on failure; a flaky external call never breaks the card.
- **Bad/garbage tool args** → `coerce_triage` sanitizes; on total failure,
  the agent asks one clarifying question rather than emitting a card.
- **Consent not given** → UI still works; history is simply not persisted.

## 11. Testing strategy

- **Unit (deterministic, no network, fast) — the safety net:**
  - `triage_state.coerce_triage`: table of raw model outputs (incl. the
    observed `"Immediate — call EMS/911 now"` case) → expected enum.
  - `assess_urgency`: red-flag cases → critical + `call_102`.
  - `rank_hospitals`: canned candidate list + triage → expected ordering
    (district first, capability, beds).
  These run offline and are the tests that **must** pass.
- **Integration (live, slower, marked):**
  - `commander.run_turn` end-to-end with SimulaChat (the `--demo` scenario).
  - freehealth bed fetch (live) → top pick sanity.
- **UI smoke:** `app.py` launches; a scripted Gradio Client run posts the
  demo message and asserts the assistant reply + a hospital card appear.
- **Validation gate:** unit suite green + `app.py` boots + one scripted
  end-to-end message renders card + status + walkthrough.

## 12. Migration / rollout plan (high level — detailed in writing-plans)

1. **Phase 1 (core, demo-critical):** `triage_state.py` (deterministic, fully
   unit-tested: coerce/assess/rank, offline) → `commander.py` (Agno agent) →
   rewrite `app.py` (Blocks UI + orchestration + `BrowserState` + Walkthrough +
   Markdown cards + visible status line) → delete `agent_graph.py`,
   `triage_agent.py`, `routing_agent.py`, `memory.js` → README + pyproject
   update (drop `langgraph`, keep `agno`) → validation gate.
2. **Phase 2 (optional, time-boxed):** native `Chatbot type="component"`
   hospital card + `ChatMessage.metadata` collapsible tool activity;
   multimodal image (bounded); local-embedding semantic recall behind a flag;
   blood-bank lookup.

## 13. Open risks / watch items

- **R1 (main):** Qwen tool-arg enum drift → mitigated by `coerce_triage`
  (unit-tested). Residual risk: model phrasing that the keyword rules miss →
  default to `urgent` + always show "call 102 if in doubt".
- **R2:** freehealth feed schema/availability at demo time → cached fallback
  list + "call 102" message (already present).
- **R3:** Gradio `Chatbot type="component"` rendering of a custom card →
  de-risk early in Phase 1 with a static card before wiring the live pick.
- **R4:** vision for multimodal is unconfirmed → bounded + graceful degrade.
- **Assumption:** `simulachat…/api/v1` stays OpenAI-compatible and exposes
  `model="default"` (verified during spike; no code depends on anything more).
