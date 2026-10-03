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


# (Live step-progress is rendered by _progress_md() — see the helpers section.)


# --- Card rendering (rich Markdown; Phase 2 upgrades to a component) ---------
def _render_card(triage: triage_state.TriageState, ranked: list,
                 context_block: str, district: str) -> str:
    urgency = triage.urgency
    badge = {"critical": "🔴 Critical", "urgent": "🟠 Urgent",
             "stable": "🟢 Stable"}.get(urgency, urgency)
    lines = [f"### Triage — {badge}", ""]

    if triage.call_now:
        lines += [
            "### 🚨 CALL 102 (Ambulance) / 112 NOW",
            "This is a medical emergency. Keep the line open until help arrives.",
            "",
        ]

    if triage.red_flags:
        lines += ["**Why this is serious:**"] + [f"- {f}" for f in triage.red_flags] + [""]

    if ranked:
        top = ranked[0]
        h = top["hospital"]
        lines += [
            f"### 🏥 Recommended: {h.get('health_facility_name', '?')}",
            f"- District: {h.get('district_name', district or '?')} ({h.get('palika_name', '')})",
            f"- Free beds now: **{h.get('free_beds', '?')}**",
            f"- Reason: {top['reason']}",
        ]
        phone = (h.get("contact_number") or "").replace(" ", "").lstrip("0")
        if phone:
            lines.append(f"- [📞 Call {h.get('contact_number')}](" + f"tel:+977{phone})")
        lines.append("")
        if len(ranked) > 1:
            lines.append("**Alternates:**")
            for r in ranked[1:3]:
                lines.append(f"- {r['hospital'].get('health_facility_name', '?')} "
                             f"(free beds: {r['hospital'].get('free_beds', '?')}) — {r['reason']}")
            lines.append("")

    if context_block:
        lines += ["### 📍 Context", context_block]

    lines += [
        "_Do not leave your phone. Stay on the line until a dispatcher or "
        "medic takes over. If a family member can drive, keep the route clear._",
    ]
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
             profile: dict) -> tuple:
    """One user turn: interview via commander, then deterministic triage/route.

    `district` is the caller's district (from the widget/profile); it is
    injected into the commander turn and used for deterministic routing.
    `profile` (the BrowserState dict) receives the structured history entry +
    last_triage — never the medical chat text (privacy by design).
    """
    # MultimodalTextbox yields {"text":..., "files":[]}; a plain string is also
    # tolerated (e.g. tests). The agent sees the text part only — Phase 1 does
    # not route files to any vision component (bounded, non-diagnostic use).
    user_text = message.get("text") if isinstance(message, dict) else (message or "")
    res = run_turn(user_text, emergency_id=emergency_id, district=district, agent=_agent())
    history = history + [{"role": "user", "content": user_text}]

    # Backend/API failure: surface a clean retry prompt (no crash, no false
    # progress). Step 1 stays pending so the caller can resend.
    if res.error is not None:
        history = history + [{
            "role": "assistant",
            "content": ("⚠️ I couldn't reach the emergency service just now — "
                        "please tap **Send** once more. If it persists, call "
                        "**102** (ambulance) or **112** directly."),
        }]
        return history, "", _status_md(None, error=True), _progress_md(completed=0, active=0)

    history = history + [{"role": "assistant", "content": res.text or "_..._"}]

    card_md = ""
    assessed = None
    if res.triage is not None:
        # Deterministic layer owns urgency/red-flags/call-now (no LLM here).
        assessed = triage_state.assess_urgency(res.triage)
        ranked, context_block = _route(assessed, district)
        card_md = _render_card(assessed, ranked, context_block, district)
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
        progress = _progress_md(completed=3)
    else:
        # Still interviewing: step 1 done, step 2 (assess) in progress.
        progress = _progress_md(completed=1, active=1)

    return history, "", _status_md(assessed), progress


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


def _status_md(triage, error: bool = False) -> str:
    if error:
        return "⚪ **Service temporarily unavailable**\n\nPlease try again."
    if triage is None:
        return "🔵 Gathering symptoms…"
    emoji = {"critical": "🔴", "urgent": "🟠", "stable": "🟢"}[triage.urgency]
    flags = "\n".join(f"- {f}" for f in triage.red_flags) or "- none"
    return f"{emoji} **{triage.urgency.upper()}**\n\n**Red flags:**\n{flags}"


_PROGRESS_STEPS = ["Understand the emergency", "Assess urgency", "Route you to care"]


def _progress_md(completed: int = 0, active: int = 0) -> str:
    """Render live step-progress as Markdown (updateable; Walkthrough is not).

    `completed` = number of steps finished. `active` = index (0-based) of the
    step currently in progress. Steps render done ✅ / active ⏳ / pending ⬜.
    """
    lines = []
    for i, label in enumerate(_PROGRESS_STEPS):
        if i < completed:
            icon = "✅"
        elif i == active:
            icon = "⏳"
        else:
            icon = "⬜"
        lines.append(f"{icon} **{i + 1}. {label}**")
    return "\n".join(lines)


def build_ui():
    ui_css = """
    :root { --jr-ink: #172033; --jr-muted: #627084; --jr-blue: #1463d6; }
    body { background: #f4f7fb; }
    .gradio-container { max-width: 1480px !important; padding: 22px 28px 36px !important; }
    .jr-shell { max-width: 1440px; margin: 0 auto; }
    .jr-hero { background: radial-gradient(circle at 90% 10%, rgba(91,215,206,.28), transparent 33%), linear-gradient(125deg, #102b63 0%, #1463d6 70%, #1c9db8 100%); color: white; border-radius: 24px; padding: 30px 34px; margin-bottom: 14px; box-shadow: 0 18px 42px rgba(16,43,99,.20); }
    .jr-hero h1 { color: white; font-size: clamp(1.9rem, 3vw, 2.7rem); letter-spacing: -.04em; margin: 0 0 6px; }
    .jr-hero h3 { color: rgba(255,255,255,.92); font-size: clamp(1.05rem, 2vw, 1.3rem); font-weight: 500; margin: 0; }
    .jr-alert { background: #fffaf2; border: 1px solid #f7d9a6; border-radius: 14px; padding: 12px 16px; color: #744817; box-shadow: 0 4px 12px rgba(116,72,23,.04); }
    .jr-panel { border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px; background: rgba(255,255,255,.9); box-shadow: 0 10px 28px rgba(23,32,51,.06); }
    .jr-panel h3 { margin-top: 0; color: var(--jr-ink); letter-spacing: -.02em; }
    .jr-panel p { color: var(--jr-muted); }
    .jr-progress { background: #f7faff; border: 1px solid #dfe8f5; border-radius: 12px; padding: 12px 16px; }
    .jr-status { background: linear-gradient(180deg, #f9fcff 0%, #f2f7fc 100%); border-color: #d5e2f0; min-height: 150px; }
    .jr-status h3 { margin-top: 0; }
    .jr-composer textarea { border-radius: 13px !important; border-color: #cbd8e8 !important; min-height: 52px !important; }
    .jr-composer textarea:focus { border-color: var(--jr-blue) !important; box-shadow: 0 0 0 3px rgba(20,99,214,.12) !important; }
    .jr-send button { min-height: 46px; border-radius: 12px; font-weight: 700; box-shadow: 0 7px 16px rgba(20,99,214,.20); }
    .jr-send button:hover { transform: translateY(-1px); }
    button.secondary { border-radius: 10px !important; }
    footer { opacity: .55; }
    @media (max-width: 800px) { .gradio-container { padding: 12px !important; } .jr-hero { padding: 24px; border-radius: 18px; } .jr-shell { padding: 0; } }
    """
    with gr.Blocks(title="JeevanRoute", css=ui_css) as demo:
        profile = gr.BrowserState(_BROWSER_DEFAULT, storage_key="jeevanroute")
        emergency_id = gr.Textbox(label="Session ID (internal)", value="default", visible=False)

        with gr.Column(elem_id="jr-shell"):
            gr.Markdown("# 🏥 JeevanRoute\n### Stay calm. Get the next right step.", elem_id="jr-hero")
            gr.Markdown("**Immediate danger?** Call **102** (ambulance) or **112** now. Otherwise, describe what’s happening and we’ll guide you to the right care.", elem_id="jr-alert")

        with gr.Row(elem_id="jr-shell"):
            # ── Left: conversation history ──────────────────────────────
            with gr.Column(scale=1, min_width=220, elem_classes="jr-panel"):
                gr.Markdown("### Your details")
                gr.Markdown("Set these once to get a more relevant hospital recommendation.")
                history_md = gr.Markdown("_No past emergencies yet._")
                lang = gr.Radio(["Nepali", "English"], label="Preferred language",
                                value="English", interactive=True)
                district_in = gr.Textbox(label="District (for routing)", value=None,
                                         placeholder="e.g. Kathmandu", interactive=True)
                geolocate = gr.Button("📍 Use my location", variant="secondary")
                geo_status = gr.Markdown("")

            # ── Middle: live progress + chat ────────────────────────────
            # NOTE: gr.Walkthrough is a layout (BlockContext), NOT a data
            # component — its `selected` cannot be updated from an event
            # handler (verified against Gradio 6.29.1). So the LIVE progress
            # is a gr.Markdown rendered by _progress_md(); a static Walkthrough
            # legend is kept below only as orientation (it never moves).
            with gr.Column(scale=3, elem_classes="jr-panel"):
                # LIVE progress (updateable each turn):
                progress_md = gr.Markdown(_progress_md(completed=0, active=0), elem_id="jr-progress")
                # Static "how this works" legend using the native Walkthrough:
                with gr.Accordion("How this works", open=False):
                    with gr.Walkthrough(selected=0):
                        gr.Step("① Understand the emergency")
                        gr.Markdown("Describe what's happening; I ask the "
                                    "2–3 most critical questions.")
                        gr.Step("② Assess urgency")
                        gr.Markdown("Red-flag rules decide how fast this "
                                    "needs care (stable / urgent / critical).")
                        gr.Step("③ Route you to care")
                        gr.Markdown("Best free-bed facility + an action plan "
                                    "with a call button and directions.")
                # Gradio 6: Chatbot is ALWAYS messages format (no `type` param).
                chatbot = gr.Chatbot(height=480, placeholder="Your conversation will appear here. Start by describing what is happening.")
                gr.Markdown("**Start here:** Tell me who needs help, what happened, and when it started. You can write in English or Nepali.")
                with gr.Row(elem_classes="jr-composer"):
                    msg = gr.MultimodalTextbox(
                        placeholder="Describe the emergency (text; image in Phase 2)…",
                        file_types=["image"], interactive=True)
                    submit = gr.Button("Send securely", variant="primary", elem_classes="jr-send")

            # ── Right: live emergency status ────────────────────────────
            with gr.Column(scale=1, min_width=260, elem_classes="jr-panel jr-status"):
                gr.Markdown("### Emergency status")
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
            new_hist, new_msg, status, progress = _respond(
                history, message, emergency_id, routing_district, new_profile)
            return (new_hist, new_msg, status, progress, new_profile,
                    _show_history(new_profile))

        def _locate(lat_lng=None):
            if not lat_lng or len(lat_lng) < 2:
                return "", "⚠️ Could not get location — type your district instead."
            d, note = get_location(lat_lng[0], lat_lng[1])
            return d, note

        geolocate.click(
            _locate,
            inputs=[],
            outputs=[district_in, geo_status],
            js=GEO_JS)

        _outs = [chatbot, msg, status_md, progress_md, profile, history_md]
        _ins = [msg, chatbot, emergency_id, profile, district_in, lang]
        submit.click(_respond_w, inputs=_ins, outputs=_outs)
        msg.submit(_respond_w, inputs=_ins, outputs=_outs)

    return demo


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    demo = build_ui()
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        css=".card {border:1px solid #ddd; border-radius:12px; padding:12px; margin:6px 0;}",
    )


if __name__ == "__main__":
    main()
