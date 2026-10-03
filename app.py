"""JeevanRoute — Agno + Gradio emergency command UI (Phase 1: text + location)."""
# CSS is intentionally kept inline for the single-file Gradio app.
# ruff: noqa: E501
from __future__ import annotations

import os

import gradio as gr
from dotenv import load_dotenv

import context
import triage_state
from commander import run_turn
from translations import badge as _badge
from translations import t as _t
from translations import urgency_upper as _urgency_upper

# --- Browser geolocation (kept from the previous app) ------------------------
GEO_JS = """
() => {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) { resolve([null, null]); return; }
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve([pos.coords.latitude, pos.coords.longitude]),
            () => resolve([null, null]),
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    });
}
"""

# Browser-native speech-to-text. Chromium exposes SpeechRecognition as either
# SpeechRecognition or the older webkitSpeechRecognition name. The transcript
# is inserted into the normal Gradio composer, so the existing submit flow,
# privacy boundary, and streaming milestones remain unchanged.
VOICE_EVENT_JS = """
() => {
  const button = document.querySelector('#jr-speech-button button') || document.querySelector('#jr-speech-button');
  const input = document.querySelector('#jr-input textarea');
  const status = document.querySelector('#jr-voice-status');
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const setStatus = (text) => { if (status) status.textContent = text; };
  if (!button || !input) return;
  if (!Recognition) { setStatus('Voice typing is unavailable in this browser. You can still type or upload audio.'); return; }
  const nepali = [...document.querySelectorAll('#jr-language input')]
    .some((el) => el.checked && el.value === 'Nepali');
  const recognition = new Recognition();
  recognition.lang = nepali ? 'ne-NP' : 'en-US';
  recognition.interimResults = true;
  recognition.onstart = () => {
    button.textContent = '⏹ Stop listening';
    setStatus(`Listening in ${nepali ? 'Nepali' : 'English'}…`);
  };
  recognition.onresult = (event) => {
    let transcript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) transcript += event.results[i][0].transcript;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(input, transcript.trim());
    input.dispatchEvent(new Event('input', { bubbles: true }));
    setStatus('Voice converted to text. Review it, then press send.');
  };
  recognition.onerror = (event) => {
    button.textContent = '🎙️ Speak';
    setStatus(event.error === 'not-allowed'
      ? 'Microphone permission was denied. Allow it for this site, or type instead.'
      : 'Voice typing could not start. You can still type or upload audio.');
  };
  recognition.onend = () => { button.textContent = '🎙️ Speak'; };
  recognition.start();
}
"""

# Preferred-language cookie. Written whenever the language radio changes so the
# choice survives page reloads across sessions (BrowserState already keeps it
# per-queue; the cookie is the durable, cross-reload source of truth).
SAVE_LANG_JS = """
() => {
  const nepali = [...document.querySelectorAll('#jr-language input')]
    .some((el) => el.checked && el.value === 'Nepali');
  const value = nepali ? 'ne' : 'en';
  const d = new Date();
  d.setTime(d.getTime() + 365 * 24 * 60 * 60 * 1000);
  document.cookie = 'jr_lang=' + value + '; path=/; expires=' + d.toUTCString() + '; SameSite=Lax';
}
"""

# On page load, read the language cookie and return the matching radio label so
# the `demo.load` handler can restore the selection and re-render every string.
RESTORE_LANG_JS = """
() => {
  const m = document.cookie.match(/(?:^|;\\s*)jr_lang=([^;]+)/);
  return (m && m[1] === 'ne') ? 'Nepali' : 'English';
}
"""


def get_location(lat, lng):
    """Reverse-geocode browser coords to a district name (the 'Use my location'
    button). Returns (district, status message). Precise-coords ETA is a
    Phase 1.x refinement; Phase 1 routes from the district."""
    if not lat or not lng:
        return "", (
            "⚠️ The browser could not provide your location. Allow location "
            "access and try again, or enter your district manually.")
    district = context.reverse_geocode(float(lat), float(lng))
    if not district:
        return "", "⚠️ Location received, but the district could not be " \
                    "identified. Enter your district manually."
    return district, ""

# --- Browser-persistent local state (replaces memory.js) ---------------------
_BROWSER_DEFAULT = {
    "language": "en",         # "ne" | "en"
    "district": None,          # default district for routing
    "history": [],             # past emergencies: [{district, urgency, hospital, ts}]
    "last_triage": None,       # latest structured triage (structured only, no chat text)
}


# (The ⏳/⬜ step-progress line was removed from the UI — it duplicated the
#  "How this works" cards. _progress_md() is still returned by the handlers
#  so the 5-tuple contract and its regression tests stay intact.)


# --- Card rendering (rich Markdown; Phase 2 upgrades to a component) ---------
def _render_card(triage: triage_state.TriageState, ranked: list,
                 context_block: str, district: str, lang: str | None = None) -> str:
    urgency = triage.urgency
    badge = _badge(urgency, lang)
    lines = [f"### {_t('card_triage', lang)} — {badge}", ""]

    if triage.call_now:
        lines += [
            _t("card_call102", lang),
            _t("card_emergency_line", lang),
            "",
        ]

    if triage.red_flags:
        lines += [_t("card_why", lang)] + [f"- {f}" for f in triage.red_flags] + [""]

    if ranked:
        top = ranked[0]
        h = top["hospital"]
        lines += [
            f"{_t('card_rec', lang)}: {h.get('health_facility_name', '?')}",
            f"- {_t('card_district', lang)}: {h.get('district_name', district or '?')} ({h.get('palika_name', '')})",
            f"- {_t('card_beds', lang)}: **{h.get('free_beds', '?')}**",
            f"- {_t('card_reason', lang)}: {top['reason']}",
        ]
        phone = (h.get("contact_number") or "").replace(" ", "").lstrip("0")
        if phone:
            lines.append(f"- [{_t('card_call', lang)} {h.get('contact_number')}](" + f"tel:+977{phone})")
        lines.append("")
        if len(ranked) > 1:
            lines.append(_t("card_alternates", lang))
            for r in ranked[1:3]:
                lines.append(f"- {r['hospital'].get('health_facility_name', '?')} "
                             f"({_t('card_freebeds', lang)}: {r['hospital'].get('free_beds', '?')}) — {r['reason']}")
            lines.append("")

    if context_block:
        lines += [_t("card_context", lang), context_block]

    lines += [_t("card_footer", lang)]
    return "\n".join(lines)


# --- Orchestration ------------------------------------------------------------
def _route(triage: triage_state.TriageState, district: str) -> tuple[list, str]:
    """Deterministic routing: fetch beds, pool, rank, then build live context.

    `build_context_block` geocodes the origin district itself and adds real
    road ETA / weather / nearby alerts to the card (degrades to "" on any
    network failure). Phase 1 ranks purely (same district, free beds, size);
    a per-hospital `eta_map` is a Phase 1.x refinement.
    """
    beds = context.fetch_beds()
    pool = triage_state.candidate_pool(beds, district, triage)
    ranked = triage_state.rank_hospitals(pool, triage, district)
    context_block = ""
    if district and ranked:
        top = ranked[0]["hospital"]
        try:
            context_block = context.build_context_block(
                district,
                top.get("palika_name") or top.get("district_name"),
                top.get("district_name"),
                None,
            ) or ""
        except Exception:
            context_block = ""
    return ranked, context_block


def _respond(history: list, message: str, emergency_id: str, district: str,
             profile: dict, language: str | None = None) -> tuple:
    """One user turn: interview via commander, then deterministic triage/route.

    `district` is the caller's district (from the widget/profile); it is
    injected into the commander turn and used for deterministic routing.
    `profile` (the BrowserState dict) receives the structured history entry +
    last_triage — never the medical chat text (privacy by design).
    """
    # MultimodalTextbox yields {"text":..., "files":[]}; a plain string is also
    # tolerated (e.g. tests). The agent sees the text part only — Phase 1 does
    # not route files to any vision component (bounded, non-diagnostic use).
    user_text = _message_text(message)
    turn_kwargs = {"emergency_id": emergency_id, "district": district, "agent": _agent()}
    if language is not None:
        turn_kwargs["language"] = language
    res = run_turn(user_text, **turn_kwargs)
    history = history + [{"role": "user", "content": user_text}]

    # Backend/API failure: surface a clean retry prompt (no crash, no false
    # progress). Step 1 stays pending so the caller can resend.
    if res.error is not None:
        history = history + [{
            "role": "assistant",
            "content": _t("err_retry", language),
        }]
        return history, "", _status_md(None, error=True, lang=language), _progress_md(completed=0, active=0, lang=language)

    history = history + [{"role": "assistant", "content": res.text or "_..._"}]

    card_md = ""
    assessed = None
    if res.triage is not None:
        # Deterministic layer owns urgency/red-flags/call-now (no LLM here).
        assessed = triage_state.assess_urgency(res.triage)
        ranked, context_block = _route(assessed, district)
        card_md = _render_card(assessed, ranked, context_block, district, lang=language)
        # Persist the structured triage + history entry (never the chat text).
        if profile is not None:
            profile.setdefault("history", []).append({
                "district": district, "urgency": assessed.urgency,
                "hospital": ranked[0]["hospital"].get("health_facility_name") if ranked else None,
                "ts": _now_iso(),
            })
            profile["last_triage"] = assessed.model_dump()
        if card_md:
            history = history + [{"role": "assistant", "content": card_md}]
        # Live step-progress: step 3 (route) is reached only once triage fired.
        progress = _progress_md(completed=3, lang=language)
    else:
        # Still interviewing: step 1 done, step 2 (assess) in progress.
        progress = _progress_md(completed=1, active=1, lang=language)

    return history, "", _status_md(assessed, lang=language), progress


def _respond_stream(history: list, message: str, emergency_id: str,
                    district: str, profile: dict, language: str | None = None):
    """Stream transparent milestones while the emergency pipeline runs."""
    user_text = _message_text(message)
    base_history = history + [{"role": "user", "content": user_text}]
    trace = []

    # First yield gives the browser immediate feedback before the model call.
    trace.append(gr.ChatMessage(content=_t("ms_reading_body", language),
                                metadata={"title": _t("ms_reading", language), "status": "pending", "id": "read"}))
    yield (base_history + trace,
           "", _t("ms_working", language),
           _progress_md(completed=0, active=0, lang=language), profile)

    turn_kwargs = {"emergency_id": emergency_id, "district": district, "agent": _agent()}
    if language is not None:
        turn_kwargs["language"] = language
    res = run_turn(user_text, **turn_kwargs)
    if res.error is not None:
        error_history = base_history + [{
            "role": "assistant",
            "content": _t("err_retry", language),
        }]
        yield (error_history, "", _status_md(None, error=True, lang=language),
               _progress_md(completed=0, active=0, lang=language), profile)
        return

    trace[0].metadata["status"] = "done"
    conversation = base_history + trace + [{"role": "assistant", "content": res.text or "_..._"}]
    if res.triage is None:
        yield (conversation, "", _t("ms_gathering2", language),
               _progress_md(completed=1, active=1, lang=language), profile)
        return

    trace.append(gr.ChatMessage(content=_t("ms_checking", language),
                                metadata={"title": _t("prog_2", language), "status": "done", "id": "assess"}))
    conversation = base_history + trace + [{"role": "assistant", "content": res.text or "_..._"}]
    yield (conversation, "", _t("ms_checking_urgency", language),
           _progress_md(completed=1, active=1, lang=language), profile)
    assessed = triage_state.assess_urgency(res.triage)
    trace.append(gr.ChatMessage(content=_t("ms_finding", language),
                                metadata={"title": _t("prog_3", language), "status": "pending", "id": "route"}))
    yield (base_history + trace + [{"role": "assistant", "content": res.text or "_..._"}], "",
           f"{_status_md(assessed, lang=language)}\n\n{_t('ms_finding_care', language)}",
           _progress_md(completed=2, active=2, lang=language), profile)

    ranked, context_block = _route(assessed, district)
    trace[-1].metadata["status"] = "done"
    card_md = _render_card(assessed, ranked, context_block, district, lang=language)
    if profile is not None:
        profile.setdefault("history", []).append({
            "district": district, "urgency": assessed.urgency,
            "hospital": ranked[0]["hospital"].get("health_facility_name") if ranked else None,
            "ts": _now_iso(),
        })
        profile["last_triage"] = assessed.model_dump()
    final_history = base_history + trace + [{"role": "assistant", "content": res.text or "_..._"}]
    if card_md:
        final_history.append({"role": "assistant", "content": card_md})
    yield (final_history, "", f"{_status_md(assessed, lang=language)}\n\n{_t('ms_plan_ready', language)}",
           _progress_md(completed=3, lang=language), profile)


def _message_text(message) -> str:
    """Extract text and optionally transcribe a recorded microphone message."""
    if not isinstance(message, dict):
        return message or ""
    text = (message.get("text") or "").strip()
    audio_files = [f for f in (message.get("files") or [])
                   if str(f).lower().endswith((".wav", ".mp3", ".m4a", ".webm", ".ogg"))]
    if audio_files and not text:
        transcription = _transcribe_audio(audio_files[0])
        text = transcription or (
            "A voice note was received, but it could not be transcribed. "
            "Please type who needs help, what happened, and when it started.")
    return text


def _transcribe_audio(path: str) -> str:
    """Best-effort transcription through the configured OpenAI-compatible API."""
    api_key = os.environ.get("SIMULACHAT_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI
        with open(path, "rb") as audio:
            result = OpenAI(api_key=api_key, base_url="https://simulachat.sushant.info.np/api/v1").audio.transcriptions.create(
                model="whisper-1", file=audio)
        return (getattr(result, "text", "") or "").strip()
    except Exception:  # noqa: BLE001 — voice input must degrade gracefully
        return ""


# --- Small helpers ------------------------------------------------------------
def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")


def _agent():
    global _AGENT
    if _AGENT is None:
        from commander import build_agent
        _AGENT = build_agent()
    return _AGENT


_AGENT = None


def _status_md(triage, error: bool = False, lang: str | None = None) -> str:
    if error:
        return _t("st_error", lang)
    if triage is None:
        return _t("st_gathering", lang)
    emoji = {"critical": "🔴", "urgent": "🟠", "stable": "🟢"}[triage.urgency]
    flags = "\n".join(f"- {f}" for f in triage.red_flags) or f"- {_t('none', lang)}"
    return f"{emoji} **{_urgency_upper(triage.urgency, lang)}**\n\n**{_t('red_flags', lang)}:**\n{flags}"


_PROGRESS_STEP_KEYS = ["prog_1", "prog_2", "prog_3"]


def _progress_md(completed: int = 0, active: int = 0, lang: str | None = None) -> str:
    """Render live step-progress as Markdown (updateable; Walkthrough is not).

    `completed` = number of steps finished. `active` = index (0-based) of the
    step currently in progress. Steps render done ✅ / active ⏳ / pending ⬜.
    """
    lines = []
    for i, key in enumerate(_PROGRESS_STEP_KEYS):
        if i < completed:
            icon = "✅"
        elif i == active:
            icon = "⏳"
        else:
            icon = "⬜"
        lines.append(f"{icon} **{i + 1}. {_t(key, lang)}**")
    return "\n".join(lines)


UI_CSS = """
:root {
      --jr-ink: #1c2733;
      --jr-ink-soft: #46586c;
      --jr-muted: #64748b;
      --jr-teal: #0e7490;
      --jr-teal-dark: #155e75;
      --jr-teal-tint: #ecfeff;
      --jr-red: #b91c1c;
      --jr-red-dark: #991b1b;
      --jr-red-tint: #fef2f2;
      --jr-red-line: #fecaca;
      --jr-navy-900: #081527;
      --jr-navy-700: #0d2b52;
      --jr-cream: #f4f2ec;
      --jr-panel: #ffffff;
      --jr-line: #e5e1d8;
      --jr-line-soft: #eeeae1;
      --jr-radius: 16px;
      --jr-gap: 18px;
    }
    /* ── LOCK to light theme in BOTH light & dark mode ───────────────────
       Gradio swaps its theme variables when the browser is in dark mode
       (e.g. --background-fill-secondary -> #111827, --body-text-color ->
       #f3f4f6), which made the chat bubbles and buttons go dark. We pin the
       light palette so no surface can flip. */
    :root, :root.dark, body, body.dark {
      --background: #f4f2ec !important;
      --background-fill-primary: #ffffff !important;
      --background-fill-secondary: #f7f5f0 !important;
      --background-fill-tertiary: #faf9f6 !important;
      --body-text-color: #1c2733 !important;
      --block-background-fill: #ffffff !important;
      --panel-background: #ffffff !important;
      --chatbot-user-message-background-fill: #0e7490 !important;
      --chatbot-bot-message-background-fill: #ffffff !important;
      --block-title-text-color: #46586c !important;
      --block-title-background-fill: #eef2f1 !important;
      --block-label-text-color: #46586c !important;
      --block-label-background-fill: #ffffff !important;
      --block-info-background-fill: #eef2f1 !important;
      --button-primary-background-fill: #0e7490 !important;
      --button-primary-hover-background-fill: #155e75 !important;
      --button-primary-text-color: #ffffff !important;
      --button-secondary-background-fill: #ffffff !important;
      --button-secondary-hover-background-fill: #eef2f1 !important;
      --button-secondary-text-color: #1c2733 !important;
      --input-background-fill: #ffffff !important;
      --input-border-color: #d7d2c7 !important;
      --input-text-color: #1c2733 !important;
      --section-title-text-color: #1c2733 !important;
      --table-header-background-fill: #faf8f4 !important;
      --button-border-color: #d7d2c7 !important;
    }
    body, body.dark {
      background: var(--jr-cream) !important;
      color: var(--jr-ink) !important;
    }
    .gradio-container, body.dark .gradio-container {
      max-width: 1480px !important;
      padding: 0 !important;
      background: var(--jr-cream) !important;
      color: var(--jr-ink) !important;
    }
    body.dark .block, body.dark fieldset, body.dark .panel {
      background: var(--jr-panel) !important;
      color: var(--jr-ink) !important;
      border-color: var(--jr-line) !important;
    }
    /* ── Shell ─────────────────────────────────────────────────────────── */
    .jr-shell { max-width: 1480px; margin: 0 auto; padding: 0 18px 10px; }
    /* ── Hero: deep navy, subtle glow, premium ─────────────────────────── */
    #jr-hero {
      background:
        radial-gradient(820px 320px at 88% -30%, rgba(45, 212, 191, 0.16), transparent 62%),
        radial-gradient(640px 300px at 8% 140%, rgba(14, 116, 144, 0.30), transparent 58%),
        linear-gradient(160deg, var(--jr-navy-900) 0%, #0c2341 55%, var(--jr-navy-700) 100%) !important;
      border: 1px solid rgba(255, 255, 255, 0.06) !important;
      border-top: none !important;
      border-radius: 0 0 22px 22px !important;
      padding: 34px 38px 30px;
      margin-bottom: 14px;
      color: #ffffff !important;
      box-shadow: 0 22px 48px rgba(8, 21, 39, 0.28);
    }
    #jr-hero h1, body.dark #jr-hero h1 {
      color: #ffffff !important;
      font-size: clamp(1.85rem, 3vw, 2.6rem);
      font-weight: 800;
      letter-spacing: -.03em;
      margin: 0 0 6px;
      line-height: 1.15;
    }
    #jr-hero h3, body.dark #jr-hero h3 {
      color: #9bd7cf !important;
      font-size: clamp(1rem, 1.7vw, 1.22rem);
      font-weight: 500;
      margin: 0;
      letter-spacing: .005em;
    }
    /* ── Emergency alert banner: unmistakable red ──────────────────────── */
    #jr-alert {
      background: linear-gradient(135deg, var(--jr-red-tint) 0%, #fff5f5 100%) !important;
      border: 1px solid var(--jr-red-line) !important;
      border-left: 5px solid var(--jr-red) !important;
      border-radius: 12px;
      padding: 13px 18px;
      color: #5f1414 !important;
      box-shadow: 0 8px 20px rgba(185, 28, 28, 0.08);
      margin-bottom: var(--jr-gap);
    }
    #jr-alert em, #jr-alert a { color: inherit !important; }
    #jr-alert p { color: var(--jr-red-dark) !important; }
    #jr-alert strong { color: var(--jr-red-dark) !important; font-weight: 800; }
    /* ── Layout grid ───────────────────────────────────────────────────── */
    #jr-layout {
      display: grid !important;
      gap: var(--jr-gap) !important;
      grid-template-columns: clamp(232px, 17.5vw, 304px) minmax(0, 1fr) clamp(248px, 18.5vw, 312px);
      grid-template-areas: "details chat status";
      align-items: stretch;
    }
    #jr-layout > * { min-width: 0 !important; width: auto !important; }
    #jr-layout > *:nth-child(1) { grid-area: details; }
    #jr-layout > *:nth-child(2) { grid-area: chat; }
    #jr-layout > *:nth-child(3) { grid-area: status; }
    /* ── Panels: warm white cards with subtle elevation ────────────────── */
    .jr-panel {
      background: var(--jr-panel) !important;
      border: 1px solid var(--jr-line) !important;
      border-radius: var(--jr-radius) !important;
      padding: 20px !important;
      box-shadow: 0 2px 6px rgba(28, 39, 51, 0.05), 0 14px 32px rgba(28, 39, 51, 0.06);
      min-width: 0;
    }
    .jr-panel h3 {
      margin: 0 0 4px;
      color: var(--jr-ink) !important;
      font-size: 1.08rem;
      font-weight: 750;
      letter-spacing: -.02em;
    }
    .jr-panel p { color: var(--jr-muted) !important; }
    .jr-panel table { border-collapse: collapse; width: 100%; font-size: .78rem; }
    .jr-panel table th, .jr-panel table td {
      border: 1px solid var(--jr-line-soft);
      padding: 5px 7px;
      color: var(--jr-ink-soft) !important;
    }
    .jr-panel table th { background: #faf8f4; color: var(--jr-ink) !important; }
    /* ── How-this-works cards ──────────────────────────────────────────── */
    #jr-how-title {
      font-size: .98rem !important;
      font-weight: 750 !important;
      color: var(--jr-ink) !important;
      margin: 0 0 4px !important;
    }
    .jr-how-grid { gap: 12px !important; margin-top: 8px; }
    .jr-how-step {
      flex: 1;
      background: #f7f9f8;
      border: 1px solid var(--jr-line-soft);
      border-left: 3px solid var(--jr-teal);
      border-radius: 12px;
      padding: 14px 15px;
      min-height: 112px;
    }
    .jr-how-step h3, .jr-how-step h4 { color: var(--jr-teal-dark) !important; margin: 0 0 8px; font-size: .98rem; }
    .jr-how-step p { color: var(--jr-muted) !important; font-size: .87rem; line-height: 1.5; margin: 0; }
    /* ── Chat ──────────────────────────────────────────────────────────── */
    .chatbot { background: #f8f7f4 !important; border: 1px solid var(--jr-line-soft) !important; border-radius: 14px !important; }
    .message-row.user-row .message-content {
      background: var(--jr-teal) !important;
      color: #ffffff !important;
      border-radius: 14px 14px 4px 14px !important;
      padding: 10px 14px !important;
    }
    .message-row.user-row .message-content p,
    .message-row.user-row .message-content *,
    .message-row.user-row .message-content a { color: #ffffff !important; }
    .message-row.bot-row .message-content {
      background: #ffffff !important;
      border: 1px solid var(--jr-line-soft) !important;
      border-radius: 14px 14px 14px 4px !important;
      padding: 10px 14px !important;
    }
    .chatbot p { overflow-wrap: anywhere; }
    /* ── Composer ──────────────────────────────────────────────────────── */
    #jr-input {
      background: #ffffff !important;
      border: 1px solid #d7d2c7 !important;
      border-radius: 14px !important;
      box-shadow: 0 1px 3px rgba(28, 39, 51, 0.05);
    }
    #jr-input textarea {
      background: transparent !important;
      color: var(--jr-ink) !important;
      border-radius: 14px !important;
      min-height: 56px !important;
      font-size: .95rem;
    }
    #jr-input textarea:focus { outline: none; box-shadow: none; }
    #jr-input textarea::placeholder { color: #8a94a6 !important; opacity: 1 !important; }
    .jr-composer .icon-button { border-radius: 9px; }
    /* ── Voice row ─────────────────────────────────────────────────────── */
    .jr-voice-row { align-items: center !important; gap: 12px !important; margin-top: 2px; flex-wrap: wrap; }
    #jr-speech-button button {
      background: #ffffff !important;
      border: 1px solid #d7d2c7 !important;
      color: var(--jr-ink) !important;
      border-radius: 10px !important;
      font-weight: 650 !important;
      min-height: 34px !important;
    }
    #jr-speech-button button:hover { border-color: var(--jr-teal) !important; color: var(--jr-teal-dark) !important; }
    #jr-voice-status { font-size: .8rem; margin: 0 !important; color: var(--jr-muted) !important; }
    /* ── Examples ──────────────────────────────────────────────────────── */
    .gallery { gap: 8px !important; }
    .gallery-item {
      background: #ffffff !important;
      border: 1px solid var(--jr-line) !important;
      border-radius: 10px !important;
      padding: 8px 11px !important;
      font-size: .82rem !important;
      color: var(--jr-ink-soft) !important;
      text-align: left !important;
    }
    .gallery-item:hover { border-color: var(--jr-teal) !important; color: var(--jr-teal-dark) !important; }
    .gallery-item p { color: inherit !important; font-size: inherit !important; }
    /* ── Language radio pills ──────────────────────────────────────────── */
    #jr-language {
      background: #faf9f6 !important;
      border: 1px solid var(--jr-line) !important;
      border-radius: 14px !important;
      padding: 14px !important;
    }
    #jr-language [data-testid="block-info"] { color: var(--jr-ink-soft) !important; font-weight: 700; }
    #jr-language label {
      background: #ffffff !important;
      color: var(--jr-ink-soft) !important;
      border: 1px solid #d7d2c7 !important;
      border-radius: 999px !important;
      padding: 7px 15px !important;
      cursor: pointer;
      transition: background .15s ease, border-color .15s ease, color .15s ease;
    }
    #jr-language label:hover { border-color: var(--jr-teal) !important; }
    #jr-language label.selected { background: var(--jr-teal) !important; color: #ffffff !important; border-color: var(--jr-teal) !important; }
    #jr-language label span { color: inherit !important; }
    #jr-language input { accent-color: var(--jr-teal); }
    /* ── Textbox / buttons ─────────────────────────────────────────────── */
    .jr-panel .textbox {
      background: #ffffff !important;
      border: 1px solid #d7d2c7 !important;
      border-radius: 11px !important;
      color: var(--jr-ink) !important;
    }
    .jr-panel .textbox textarea { background: transparent !important; color: var(--jr-ink) !important; }
    .jr-panel .textbox textarea::placeholder { color: #8a94a6 !important; opacity: 1 !important; }
    .jr-panel button.secondary {
      background: #ffffff !important;
      border: 1px solid #d7d2c7 !important;
      color: var(--jr-ink) !important;
      border-radius: 11px !important;
      font-weight: 650 !important;
    }
    .jr-panel button.secondary:hover { border-color: var(--jr-teal) !important; color: var(--jr-teal-dark) !important; }
    /* ── Emergency status panel: live-action distinction ───────────────── */
    .jr-status {
      background: linear-gradient(180deg, #ffffff 0%, #f5f7f6 100%) !important;
      border-top: 4px solid var(--jr-teal) !important;
      min-height: 170px;
    }
    .jr-status h3 { margin-bottom: 10px; }
    .jr-status p { color: var(--jr-ink-soft) !important; line-height: 1.55; }
    /* ── Long-word safety + footer ─────────────────────────────────────── */
    #jr-layout .prose, .jr-panel .prose { overflow-wrap: anywhere; }
    footer { opacity: .55; padding-bottom: 12px; }
    /* ── Tablet: chat left, details+status stacked right rail ──────────── */
    @media (max-width: 1119px) {
      #jr-layout {
        grid-template-columns: minmax(0, 1fr) 288px;
        grid-template-areas: "chat details" "chat status";
        grid-auto-rows: minmax(0, auto);
      }
      .jr-panel { padding: 18px !important; }
    }
    @media (max-width: 1023px) {
      #jr-layout { grid-template-columns: minmax(0, 1fr) 264px; }
    }
    /* ── Mobile: single column — chat first ────────────────────────────── */
    @media (max-width: 719px) {
      .jr-shell { padding: 0 10px 8px; }
      #jr-hero { padding: 24px 18px 22px; border-radius: 0 0 16px 16px; margin-bottom: 12px; }
      #jr-alert { margin-bottom: 12px; }
      #jr-layout {
        grid-template-columns: 1fr;
        grid-template-areas: "chat" "details" "status";
        gap: 12px !important;
      }
      #jr-layout > *:nth-child(2) { width: 100% !important; }
      .jr-panel { padding: 14px !important; border-radius: 14px !important; }
      .jr-how-grid { flex-direction: column !important; }
      .jr-how-step { min-height: auto; }
      .jr-voice-row { flex-wrap: wrap !important; }
    }
    """


def build_ui():
    with gr.Blocks(title="JeevanRoute") as demo:
        # v2 avoids parsing malformed BrowserState JSON left by early UI builds.
        profile = gr.BrowserState(_BROWSER_DEFAULT, storage_key="jeevanroute-v2")
        emergency_id = gr.Textbox(label="Session ID (internal)", value="default", visible=False)

        with gr.Column(elem_id="jr-shell"):
            hero_md = gr.Markdown("# 🏥 JeevanRoute\n### Stay calm. Get the next right step.", elem_id="jr-hero")
            alert_md = gr.Markdown("**Immediate danger?** Call **102** for Ambulance Nepal where available. For police call **100**; outside supported areas, use your local emergency service. Otherwise, describe what’s happening and we’ll guide you to the right care.", elem_id="jr-alert")

        with gr.Row(elem_id="jr-layout"):
            # ── Left: conversation history ──────────────────────────────
            with gr.Column(scale=1, min_width=220, elem_classes="jr-panel"):
                details_title_md = gr.Markdown("### Your details", elem_id="jr-details-title")
                details_sub_md = gr.Markdown("Set these once to get a more relevant hospital recommendation.", elem_id="jr-details-sub")
                lang = gr.Radio(["Nepali", "English"], label="Preferred language",
                                value="English", interactive=True, elem_id="jr-language")
                district_in = gr.Textbox(label="District (for routing)", value=None,
                                         placeholder="e.g. Kathmandu", interactive=True, elem_id="jr-district")
                geolocate = gr.Button("📍 Use my location", variant="secondary", elem_id="jr-geolocate")
                geo_status = gr.Markdown("")
                history_md = gr.Markdown("_No past emergencies yet._", elem_id="jr-history")

            # ── Middle: how-it-works + chat ────────────────────────────
            # The three "How this works" cards are static and always visible
            # (no collapsible). Live per-turn milestones stream into the
            # chatbot below; the ⏳/⬜ step-progress line was removed because
            # it duplicated these cards.
            with gr.Column(scale=3, elem_classes="jr-panel"):
                how_title_md = gr.Markdown(_t("how_title", "en"), elem_id="jr-how-title")
                with gr.Row(elem_classes="jr-how-grid", elem_id="jr-how-body"):
                    how_1_md = gr.Markdown(_t("how_1_t", "en") + "\n\n" + _t("how_1", "en"), elem_classes="jr-how-step")
                    how_2_md = gr.Markdown(_t("how_2_t", "en") + "\n\n" + _t("how_2", "en"), elem_classes="jr-how-step")
                    how_3_md = gr.Markdown(_t("how_3_t", "en") + "\n\n" + _t("how_3", "en"), elem_classes="jr-how-step")
                # Gradio 6: Chatbot is ALWAYS messages format (no `type` param).
                chatbot = gr.Chatbot(height=480, placeholder="Your conversation will appear here. Start by describing what is happening.")
                start_md = gr.Markdown("**Start here:** Tell me who needs help, what happened, and when it started. You can write in English or Nepali.", elem_id="jr-start")
                with gr.Row(elem_classes="jr-composer"):
                    msg = gr.MultimodalTextbox(
                        label="Type what’s happening here",
                        placeholder="Describe what’s happening…",
                        file_types=["image", "audio"],
                        sources=["upload"],
                        file_count="multiple", interactive=True, scale=1,
                        elem_id="jr-input")
                with gr.Row(elem_classes="jr-voice-row"):
                    speech_button = gr.Button("🎙️ Speak", elem_id="jr-speech-button", size="sm")
                    voice_status_md = gr.Markdown("Browser speech-to-text • review before sending", elem_id="jr-voice-status")
                gr.Examples(
                    examples=[
                        "Someone has severe chest pain and is sweating.",
                        "My child has trouble breathing and is very drowsy.",
                        "There was a road accident with heavy bleeding.",
                    ],
                    inputs=msg,
                    examples_per_page=3,
                    label="Try an example",
                )

            # ── Right: live emergency status ────────────────────────────
            with gr.Column(scale=1, min_width=260, elem_classes="jr-panel jr-status"):
                status_title_md = gr.Markdown("### Emergency status", elem_id="jr-status-title")
                status_md = gr.Markdown("🔵 **Ready when you are**\n\nI’ll ask only the questions needed to assess urgency and find nearby care.")

        def _save_profile(p, district, language):
            p = dict(p or {})
            if district:
                p["district"] = district.strip()
            p["language"] = ("ne" if language == "Nepali" else "en") if language else None
            return p

        def _show_history(profile):
            hist = (profile or {}).get("history") or []
            if not hist:
                return "_No past emergencies yet._"
            lines = ["| When | District | Urgency | Hospital |", "|---|---|---|---|"]
            for h in hist[-8:][::-1]:
                lines.append(f"| {h.get('ts','')} | {h.get('district') or '—'} | "
                             f"{h.get('urgency','')} | {h.get('hospital') or '—'} |")
            return "\n".join(lines)

        def _respond_w(message, history, emergency_id, profile, district, language):
            # Persist prefs first so later turns + history can use them.
            new_profile = _save_profile(profile, district, language)
            # Route from the district the caller set (widget or geolocation).
            routing_district = (district or (profile or {}).get("district") or "").strip()
            for new_hist, new_msg, status, _progress, profile_state in _respond_stream(
                    history, message, emergency_id, routing_district, new_profile,
                    new_profile.get("language")):
                yield (new_hist, new_msg, status, profile_state,
                       _show_history(profile_state))

        def _locate(lat_lng=None):
            if not lat_lng or len(lat_lng) < 2:
                return "", "⚠️ Could not get location — type your district instead."
            d, note = get_location(lat_lng[0], lat_lng[1])
            return d, note

        def _code(language) -> str:
            return "ne" if language == "Nepali" else "en"

        def _apply_language(language):
            """Re-render every UI string for the chosen language, live (no reload)."""
            code = _code(language)
            return (
                _t("hero_title", code) + "\n" + _t("hero_sub", code),
                _t("alert", code),
                _t("details_title", code),
                _t("details_sub", code),
                gr.update(label=_t("district_label", code)),
                gr.update(placeholder=_t("district_ph", code)),
                gr.update(value=_t("geolocate", code)),
                _t("how_title", code),
                _t("how_1_t", code) + "\n\n" + _t("how_1", code),
                _t("how_2_t", code) + "\n\n" + _t("how_2", code),
                _t("how_3_t", code) + "\n\n" + _t("how_3", code),
                _t("start_here", code),
                gr.update(label=_t("input_label", code)),
                gr.update(placeholder=_t("input_ph", code)),
                _t("voice_status", code),
                _t("status_title", code),
                _t("status_ready", code),
            )

        _lang_outputs = [hero_md, alert_md, details_title_md, details_sub_md, district_in,
                         district_in, geolocate, how_title_md, how_1_md, how_2_md, how_3_md,
                         start_md, msg, msg, voice_status_md, status_title_md, status_md]

        def _restore_language(language):
            """On page load, restore the saved language (from cookie) and re-render
            every string. Returns the radio (value+label) first, then the shared
            re-render tuple, matching `outputs=[lang] + _lang_outputs`."""
            code = _code(language)
            return [gr.update(value=language, label=_t("lang_label", code))] + list(_apply_language(language))

        lang.change(
            _apply_language,
            inputs=[lang],
            outputs=_lang_outputs,
        )
        # Also translate the radio's own "Preferred language" label (separate
        # handler, since a component cannot be its own output).
        def _lang_label(language):
            return gr.update(label=_t("lang_label", "ne" if language == "Nepali" else "en"))
        lang.change(
            _lang_label,
            inputs=[lang],
            outputs=[lang],
        )
        # Persist the chosen language to a real cookie on every change (durable
        # across reloads, unlike the per-queue BrowserState).
        lang.change(
            None,
            inputs=[],
            outputs=[],
            js=SAVE_LANG_JS,
        )
        # Restore the language from the cookie on load: read the cookie in JS,
        # feed it back as the radio value, and re-render all strings.
        demo.load(
            _restore_language,
            inputs=[lang],
            outputs=[lang] + _lang_outputs,
            js=RESTORE_LANG_JS,
        )

        geolocate.click(
            _locate,
            inputs=[],
            outputs=[district_in, geo_status],
            js=GEO_JS)

        _outs = [chatbot, msg, status_md, profile, history_md]
        _ins = [msg, chatbot, emergency_id, profile, district_in, lang]
        speech_button.click(None, inputs=[], outputs=[], js=VOICE_EVENT_JS)
        msg.submit(_respond_w, inputs=_ins, outputs=_outs)

    return demo


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    demo = build_ui()
    _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "jeevanroute-icon.png")
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        css=UI_CSS,
        theme=gr.themes.Soft(),
        pwa=True,
        favicon_path=_icon,
    )


if __name__ == "__main__":
    main()
