# JeevanRoute knowledge base

Add developer-maintained, source-backed guidance as Markdown files in this
folder. The Commander loads every `.md` file except this README at startup and
injects the content into its instructions.

## Editing rules

- Put one topic per file, for example `nepal-emergency.md` or
  `district-referral-rules.md`.
- Include a review date and source URLs for time-sensitive facts.
- Mark location-dependent or uncertain information explicitly.
- Do not add secrets, patient data, diagnoses, medication dosing, or invented
  hospital capabilities.
- Keep safety-critical urgency and hospital ranking in Python's deterministic
  layer; Markdown provides context and operator guidance only.
