"""
Shared logic for "fill these named fields from candidate facts" — used by
both the docx resume writer and the xlsx resume writer, so both templating
approaches (Word placeholder tokens, Excel Data-sheet rows) go through the
exact same prompting + JSON-parsing path instead of two near-duplicate
implementations.
"""
from __future__ import annotations

import re

from .full_context import load_full_context
from .rag_query import generate
from .json_utils import extract_json

SYSTEM_PROMPT = (
    "You are a resume editor filling in named fields of a resume template. "
    "You will be given a list of fields — each with its CURRENT text — and "
    "the candidate's complete skills and experience history. Respond with "
    "ONLY a single JSON object, no markdown fences, no commentary, mapping "
    "each field name exactly as given to its new plain text content.\n\n"
    "CRITICAL — do not swap content between fields: each field's current "
    "text tells you which job, employer, or time period that field belongs "
    "to. Your new text for that field MUST stay about the SAME job/period "
    "as its current text — you are re-wording and re-emphasizing for the "
    "target role, not moving facts to a different field. Two fields with "
    "related name prefixes (e.g. EXP2_BULLET1 and EXP2_BULLET3) belong to "
    "the same job and must all describe that one job, never a mix of "
    "several jobs.\n\n"
    "Do not use markdown formatting, bullet characters, or asterisks in the "
    "values — the template's own styling will display the text as plain "
    "sentences. Use ONLY the candidate facts provided. Never invent "
    "achievements, employers, dates, or metrics — if the current text and "
    "the candidate facts for that job contain no number, your new text must "
    "not contain one either; do not add a percentage or statistic that "
    "isn't explicitly present in the facts. If a field gives you no clear "
    "indication of what belongs there, leave its value as an empty string "
    "rather than guessing."
)

_PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*%")


def generate_field_values(
    fields: list[str],
    job: dict,
    match_report: str = "",
    field_context: dict | None = None,
) -> tuple[dict, list[str]]:
    """
    Asks the LLM to fill each name in `fields` using the candidate's
    complete skills/experience history.

    field_context: optional {field_name: current_text} — when provided,
    each field is shown to the model together with its existing content so
    the model has a concrete anchor for which job/topic that field is
    about, instead of guessing from the bare name alone. Strongly
    recommended whenever the template still has real content in it (e.g.
    the xlsx Data sheet, which is never blanked out); for a fully-blanked
    docx template ({{TOKEN}} already replaced the original text) this
    isn't available, so omit it or pass a synthetic description per field.

    Returns (values, warnings): values is {field_name: text}; warnings is
    a list of human-readable strings for any value that looks like it may
    contain a fabricated number — not blocked, just surfaced for review.
    Raises ValueError (with the raw response attached to the message) if
    the model's response isn't valid JSON.
    """
    if not fields:
        raise ValueError("No fields given to fill.")

    context = load_full_context()

    if field_context:
        fields_block = "\n".join(
            f"- {f} (current text: {field_context.get(f, '(none)')!r})" for f in fields
        )
    else:
        fields_block = "\n".join(f"- {f}" for f in fields)

    prompt = (
        f"Target job: {job.get('title')} at {job.get('company')}\n"
        f"Job description: {job.get('raw_description', '')[:2000]}\n\n"
        + (f"Match analysis (for emphasis):\n{match_report}\n\n" if match_report else "")
        + f"Candidate's complete skills and experience history:\n{context}\n\n"
        f"Fields to fill:\n{fields_block}\n\n"
        "Return the JSON now."
    )
    response = generate(prompt, system=SYSTEM_PROMPT)

    try:
        values = extract_json(response)
    except ValueError as e:
        raise ValueError(
            "The model's response wasn't valid JSON, so nothing was "
            f"modified. Raw response:\n{response}"
        ) from e

    # Best-effort check: flag any percentage in the new text that wasn't
    # already present in that field's current text or in the candidate's
    # history — a strong signal (not a certainty) of a fabricated metric.
    warnings = []
    for field, new_text in values.items():
        if not isinstance(new_text, str):
            continue
        old_text = (field_context or {}).get(field, "")
        for match in _PERCENT_PATTERN.findall(new_text):
            if match not in old_text and match not in context:
                warnings.append(
                    f"{field}: contains '{match}' which doesn't appear in the "
                    "original field text or candidate history — possibly fabricated."
                )
    return values, warnings
