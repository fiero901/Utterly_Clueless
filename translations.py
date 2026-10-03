"""Centralized UI translations for JeevanRoute (en / ne).

Gradio 6.29.1 has no built-in localization, so the UI strings live here and the
`lang` radio re-renders every visible string live (no reload). `t(key, lang)`
returns the translated string for a lang code ("en" | "ne"), falling back to
English for anything missing.

This is the pragmatic replacement for a gettext (.po/.mo) setup: all UI copy is
centralized in one module with a single lookup entry point, so it can be swapped
to real gettext later without touching the call sites.
"""
from __future__ import annotations

EN: dict = {
    # Hero
    "hero_title": "# 🏥 JeevanRoute",
    "hero_sub": "### Stay calm. Get the next right step.",
    "alert": ("**Immediate danger?** Call **102** for Ambulance Nepal where available. "
              "For police call **100**; outside supported areas, use your local "
              "emergency service. Otherwise, describe what’s happening and we’ll "
              "guide you to the right care."),
    # Details panel
    "details_title": "### Your details",
    "details_sub": "Set these once to get a more relevant hospital recommendation.",
    "history_empty": "_No past emergencies yet._",
    "lang_label": "Preferred language",
    "district_label": "District (for routing)",
    "district_ph": "e.g. Kathmandu",
    "geolocate": "📍 Use my location",
    "locate_fail": "⚠️ Could not get location — type your district instead.",
    # Progress steps
    "prog_1": "Understand the emergency",
    "prog_2": "Assess urgency",
    "prog_3": "Route you to care",
    # How it works
    "how_title": "How this works",
    "how_1_t": "### 1 · Understand",
    "how_1": "Tell me what happened and when. I’ll ask only the key questions.",
    "how_2_t": "### 2 · Assess",
    "how_2": "Safety rules identify red flags and how quickly help is needed.",
    "how_3_t": "### 3 · Route",
    "how_3": "Get an action plan and the best available nearby facility.",
    # Chat
    "chat_ph": "Your conversation will appear here. Start by describing what is happening.",
    "start_here": ("**Start here:** Tell me who needs help, what happened, and when "
                   "it started. You can write in English or Nepali."),
    "input_label": "Type what’s happening here",
    "input_ph": "Describe what’s happening…",
    "voice_status": "Browser speech-to-text • review before sending",
    "voice_unavailable": (
        "Voice typing is unavailable in this browser. You can still type or upload audio."
    ),
    "examples_label": "Try an example",
    # Status panel
    "status_title": "### Emergency status",
    "status_ready": (
        "🔵 **Ready when you are**\n\nI’ll ask only the questions needed to assess urgency "
        "and find nearby care."
    ),
    # Dynamic status states
    "st_error": "⚪ **Service temporarily unavailable**\n\nPlease try again.",
    "st_gathering": "🔵 Gathering symptoms…",
    "red_flags": "Red flags:",
    "none": "none",
    "urgent_upper": "URGENT",
    "critical_upper": "CRITICAL",
    "stable_upper": "STABLE",
    # Card
    "card_triage": "Triage",
    "b_critical": "🔴 Critical",
    "b_urgent": "🟠 Urgent",
    "b_stable": "🟢 Stable",
    "card_call102": "### 🚨 CALL 102 (Ambulance) / 112 NOW",
    "card_emergency_line": "This is a medical emergency. Keep the line open until help arrives.",
    "card_why": "**Why this is serious:**",
    "card_rec": "### 🏥 Recommended",
    "card_district": "District",
    "card_beds": "Free beds now",
    "card_reason": "Reason",
    "card_call": "📞 Call",
    "card_alternates": "**Alternates:**",
    "card_freebeds": "free beds",
    "card_context": "### 📍 Context",
    "card_footer": ("_Do not leave your phone. Stay on the line until a dispatcher or "
                    "medic takes over. If a family member can drive, keep the route clear._"),
    # Stream / transient milestones
    "ms_reading": "Reading your message",
    "ms_reading_body": "I’m identifying the key details so I can ask only what matters.",
    "ms_working": "🔵 **Working on it…**\n\nReading the emergency description.",
    "ms_gathering2": (
        "🔵 **Gathering symptoms…**\n\nI need one more detail before assessing urgency."
    ),
    "ms_checking": "Applying safety checks to the information you shared.",
    "ms_checking_urgency": (
        "🧭 **Checking urgency…**\n\nApplying safety checks to the information you shared."
    ),
    "ms_finding": "Checking facilities and live bed availability.",
    "ms_finding_care": (
        "🏥 **Finding available care…**\nChecking facilities and live bed availability."
    ),
    "ms_plan_ready": "✅ **Action plan ready**",
    "err_retry": ("⚠️ I couldn't reach the emergency service just now — "
                  "please tap **Send** once more. If it persists, call "
                  "**102** (ambulance) or **112** directly."),
}


# NOTE: Nepali strings below are careful translations of the EN strings above.
NE: dict = {
    "hero_title": "# 🏥 जीवनराउट",
    "hero_sub": "### शान्त रहनुहोस्। अर्को सही कदम चाल्नुहोस्।",
    "alert": ("**तत्काल खतरा छ?** उपलब्ध भएमा एम्बुलेन्स नेपालका लागि **१०२** मा फोन गर्नुहोस्। "
              "पুলिसका लागि **१००** मा कल गर्नुहोस्; समर्थित क्षेत्रबाहिर, तपाईंको स्थानीय "
              "आपत्कालीन सेवामा सम्पर्क गर्नुहोस्। अन्यथा, के भइरहेको छ भनेर बताउनुहोस् र हामी "
              "तपाईंलाई उचित उपचारतिर निर्देशन दिन्छौं।"),
    "details_title": "### तपाईंको विवरण",
    "details_sub": "अस्पतालको अझ सान्दर्भिक सिफारिस पाउन यी विवरण एकपटक सेट गर्नुहोस्।",
    "history_empty": "_अहिलेसम्म कुनै आपत्कालीन घटना छैन।_",
    "lang_label": "प्राथमिक भाषा",
    "district_label": "जिल्ला (मार्ग निर्देशनको लागि)",
    "district_ph": "उदाहरण: काठमाडौं",
    "geolocate": "📍 मेरो स्थान प्रयोग गर्नुहोस्",
    "locate_fail": "⚠️ स्थान प्राप्त गर्न सकिएन — कृपया आफ्नो जिल्ला टाइप गर्नुहोस्।",
    "prog_1": "आपत्कालीन अवस्था बुझ्नुहोस्",
    "prog_2": "गम्भीरता मूल्याङ्कन गर्नुहोस्",
    "prog_3": "उपचारतर्फ मार्गदर्शन गर्नुहोस्",
    "how_title": "यसले कसरी काम गर्छ",
    "how_1_t": "### १ · बुझ्नुहोस्",
    "how_1": "के भयो र कहिले भयो भनेर भन्नुहोस्। म आवश्यक प्रश्नहरू मात्र सोध्नेछु।",
    "how_2_t": "### २ · मूल्याङ्कन",
    "how_2": "सुरक्षा नियमले खतराका संकेत पहिचान गर्छ र सहायता कति छिटो आवश्यक छ भनी बताउँछ।",
    "how_3_t": "### ३ · मार्ग",
    "how_3": "कार्ययोजना र नजिकै उपलब्ध सबैभन्दा उपयुक्त स्वास्थ्य संस्था पाउनुहोस्।",
    "chat_ph": "तपाईंको कुराकानी यहाँ देखिनेछ। के भइरहेको छ भनेर बताएर सुरु गर्नुहोस्।",
    "start_here": ("**यहाँबाट सुरु गर्नुहोस्:** कसलाई मद्दत चाहिएको छ, के भयो, र यो कहिले सुरु भयो भनेर "
                   "भन्नुहोस्। तपाईंले अंग्रेजी वा नेपालीमा लेख्न सक्नुहुन्छ।"),
    "input_label": "के भन्दैछ भनेर यहाँ टाइप गर्नुहोस्",
    "input_ph": "के भन्दैछ भनेर वर्णन गर्नुहोस्…",
    "voice_status": "ब्राउजर स्पिच-टु-टेक्स्ट • पठाउनुअघि जाँच गर्नुहोस्",
    "voice_unavailable": "यस ब्राउजरमा भ्वाइस टाइपिङ उपलब्ध छैन। तपाईंले टाइप वा ध्वनि अपलोड गर्न सक्नुहुन्छ।",
    "examples_label": "एउटा उदाहरण प्रयास गर्नुहोस्",
    "status_title": "### आपत्कालीन अवस्था",
    "status_ready": (
        "🔵 **तपाईं तयार हुँदा सुरु गर्नुहोस्**\n\nगम्भीरता मूल्याङ्कन गर्न र नजिकैको उपचार "
        "खोज्न आवश्यक प्रश्नहरू मात्र सोध्नेछु।"
    ),
    "st_error": "⚪ **सेवा अस्थायी रूपमा उपलब्ध छैन**\n\nकृपया फेरि प्रयास गर्नुहोस्।",
    "st_gathering": "🔵 लक्षणहरू जम्मा गर्दै…",
    "red_flags": "खतराका संकेत:",
    "none": "कुनै छैन",
    "urgent_upper": "तत्कालीन",
    "critical_upper": "तत्काल आवश्यक",
    "stable_upper": "स्थिर",
    "card_triage": "ट्रियाज",
    "b_critical": "🔴 तत्काल आवश्यक",
    "b_urgent": "🟠 तत्कालीन",
    "b_stable": "🟢 स्थिर",
    "card_call102": "### 🚨 अहिले **१०२** मा एम्बुलेन्स फोन गर्नुहोस्",
    "card_emergency_line": "यो चिकित्सकीय आपत्काल हो। सहायता नआउन्जेल फोनमा सम्पर्क कायम राख्नुहोस्।",
    "card_why": "**यो किन गम्भीर छ:**",
    "card_rec": "### 🏥 सिफारिस",
    "card_district": "जिल्ला",
    "card_beds": "अहिले खाली बिस्तर",
    "card_reason": "कारण",
    "card_call": "📞 कल गर्नुहोस्",
    "card_alternates": "**विकल्पहरू:**",
    "card_freebeds": "खाली बिस्तर",
    "card_context": "### 📍 सन्दर्भ",
    "card_footer": ("_फोन नछाड्नुहोस्। डिस्पेचर वा मेडिकले लिइन्जेलसम्म लाइनमा रहनुहोस्। "
                    "कुनै परिवारको सदस्यले गाडी चलाउन सक्छ भने, बाटो खुला राख्नुहोस्।_"),
    "ms_reading": "तपाईंको सन्देश पढ्दै",
    "ms_reading_body": "म आवश्यक विवरण पहिचान गर्दैछु ताकि महत्त्वपूर्ण कुरा मात्र सोध्न सकूँ।",
    "ms_working": "🔵 **काम गर्दै…**\n\nआपत्कालीन अवस्थाको विवरण पढ्दैछु।",
    "ms_gathering2": "🔵 **लक्षणहरू सङ्कलन गर्दै…**\n\nगम्भीरता मूल्याङ्कन गर्नुअघि थप एउटा विवरण चाहिन्छ।",
    "ms_checking": "तपाईंले साझा गरेको जानकारीमा सुरक्षा जाँच लागू गरिँदैछ।",
    "ms_checking_urgency": (
        "🧭 **गम्भीरता जाँच गर्दै…**\n\nतपाईंले साझा गरेको जानकारीमा सुरक्षा जाँच लागू गर्दैछु।"
    ),
    "ms_finding": "सुविधा र लाइभ बिस्तर उपलब्धता जाँच गरिँदैछ।",
    "ms_finding_care": "🏥 **उपलब्ध उपचार खोजिँदै…**\nसुविधा र लाइभ बिस्तर उपलब्धता जाँच गरिँदैछ।",
    "ms_plan_ready": "✅ **कार्ययोजना तयार छ**",
    "err_retry": ("⚠️ आपत्कालीन सेवासँग अहिले सम्पर्क हुन सकेन — कृपया **Send** फेरि थिच्नुहोस्। "
                  "समस्या रहिरहेमा **१०२** (एम्बुलेन्स) वा **१००** (प्रहरी) मा सिधै फोन गर्नुहोस्।"),
}


# Urgency-key -> badge-key mapping (used by _status_md / _render_card).
_BADGE = {"critical": "b_critical", "urgent": "b_urgent", "stable": "b_stable"}
_URGENT_UPPER = {"critical": "critical_upper", "urgent": "urgent_upper", "stable": "stable_upper"}


def t(key: str, lang: str | None) -> str:
    """Return the translated string for `key` in `lang` ('en'|'ne'), else English."""
    table = NE if str(lang or "").lower().startswith("ne") else EN
    return table.get(key) or EN.get(key, key)


def badge(urgency: str, lang: str | None) -> str:
    return t(_BADGE.get(urgency, urgency), lang)


def urgency_upper(urgency: str, lang: str | None) -> str:
    return t(_URGENT_UPPER.get(urgency, urgency), lang)


# Keep the unused helper referenced so linters don't flag it as dead in some configs.
__all__ = ["t", "badge", "urgency_upper", "EN", "NE"]
