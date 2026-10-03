"""JeevanRoute — public Gradio chat UI for the triage + routing agents.

Architecture (API key stays server-side):
    Browser -> Gradio UI -> triage_turn() -> SimulaChat API
                                 |
                                 +-> route() -> freehealth.mohp.gov.np (live beds)

Run:
    cp .env.example .env   # then put your real key in .env
    pip install -r requirements.txt
    python app.py
Then open http://localhost:7860
"""
import gradio as gr
from dotenv import load_dotenv

load_dotenv()  # loads SIMULACHAT_API_KEY from .env

from triage_agent import triage_turn
from routing_agent import route


def render_card(t):
    """Format the structured triage as a clean emergency card."""
    emoji = {"critical": "🔴", "urgent": "🟠", "stable": "🟢"}.get(t["urgency"], "⚪")
    lines = [
        f"{emoji} **EMERGENCY — suspected {t['suspected_pathway']}**",
        f"Urgency: **{t['urgency'].upper()}**   |   "
        f"Ambulance: **{'Yes' if t['needs_ambulance'] else 'No'}**",
        "",
        "**Symptoms:** " + ", ".join(t["symptoms"]),
        "**Needs:** " + ", ".join(t["requirements"]),
        "",
        "**Do now:**",
    ]
    lines += [f"- {a}" for a in t["immediate_actions"]]
    lines += ["", "**Do NOT:**"]
    lines += [f"- {d}" for d in t["do_not"]]
    return "\n".join(lines)


def chat(message, history, district):
    """Run one turn: triage, then (if complete) route to a hospital.

    `history` is the OpenAI-style list of prior turns (does NOT include `message`).
    `district` comes from the textbox above the chat.
    """
    agent_history = history + [{"role": "user", "content": message}]
    text, triage = triage_turn(agent_history)
    if not triage:
        return text

    reply = (text or "Emergency assessment completed.") + "\n\n" + render_card(triage)

    # Triage -> Routing: recommend a hospital using live bed data.
    try:
        reply += route(triage, district=district or "")["block"]
    except Exception as e:  # never let routing break the emergency card
        reply += f"\n\n🏥 _Hospital routing unavailable ({e}). Call **102**._"
    return reply


demo = gr.ChatInterface(
    fn=chat,
    title="🚑 JeevanRoute — AI Emergency Commander",
    description="Describe what's happening (Nepali or English). Set your district, "
                "and we'll triage and route you to the right hospital.",
    additional_inputs=[
        gr.Textbox(
            label="Your district (e.g. KATHMANDU, LALITPUR, CHITWAN)",
            value="",
            placeholder="KATHMANDU",
        ),
    ],
    examples=[
        ["मेरो बुबा अचानक लड्नुभयो र बोल्न सक्नु भएको छैन", "KATHMANDU"],
        ["I have severe chest pain and difficulty breathing", "KATHMANDU"],
    ],
    save_history=False,
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
