"""
Job matcher agent — stage 2 of the orchestrator pipeline.

Compares the target job against the candidate's COMPLETE skills and
experience history (not a retrieved subset — see full_context.py for
why) and produces an honest match report, plus a 0-100 confidence
score the orchestrator uses to decide whether it's worth generating a
resume and cover letter at all.
"""
from __future__ import annotations

import re

from ..full_context import load_full_context
from ..rag_query import generate

SYSTEM_PROMPT = (
    "You are a skills-matching analyst helping a job seeker understand their "
    "fit for a role. You are given the candidate's COMPLETE skills and "
    "experience history below — use it, not just the most obviously similar "
    "parts of it, since a genuinely relevant skill or achievement may not use "
    "the same words as the job posting. Use ONLY the provided candidate "
    "facts. Be honest and specific — do not soften real gaps, and do not "
    "invent matches that aren't supported by the facts. Structure your "
    "answer with three headed sections: 'Strong matches', 'Partial "
    "matches', and 'Gaps'. "
    "After those three sections, add one final line, exactly in this format "
    "and nothing else on that line: 'Confidence: NN' — where NN is a whole "
    "number from 0 to 100 representing your honest estimate of how strong "
    "an overall fit the candidate is for this specific role, based solely "
    "on the facts provided. Do not add a percent sign or any other text on "
    "that line."
)

_CONFIDENCE_PATTERN = re.compile(r"confidence:\s*(\d{1,3})", re.IGNORECASE)
DEFAULT_CONFIDENCE_WHEN_UNPARSEABLE = 100  # fail open so a parsing miss never blocks the pipeline


def _parse_confidence(text: str) -> tuple[str, int, bool]:
    """Pull the trailing 'Confidence: NN' line out of the report.

    Returns (report_without_confidence_line, confidence_0_to_100, was_detected).
    """
    match = _CONFIDENCE_PATTERN.search(text)
    if not match:
        return text.strip(), DEFAULT_CONFIDENCE_WHEN_UNPARSEABLE, False
    confidence = max(0, min(100, int(match.group(1))))
    cleaned = _CONFIDENCE_PATTERN.sub("", text).strip()
    return cleaned, confidence, True


def match_job(job: dict) -> dict:
    context = load_full_context()
    prompt = (
        f"Job: {job.get('title')} at {job.get('company')}\n"
        f"Required skills listed: {', '.join(job.get('required_skills', [])) or '(not specified)'}\n"
        f"Full description: {job.get('raw_description', '')[:4000]}\n\n"
        f"Candidate's complete skills and experience history:\n{context}\n\n"
        "Produce the match report now."
    )
    raw_response = generate(prompt, system=SYSTEM_PROMPT)
    report, confidence, detected = _parse_confidence(raw_response)

    return {
        "report": report,
        "confidence": confidence,
        "confidence_detected": detected,
    }
