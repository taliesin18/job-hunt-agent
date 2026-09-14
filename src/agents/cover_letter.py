"""
Cover letter agent — stage 4 of the orchestrator pipeline.

Drafts a short, specific cover letter using the candidate's COMPLETE
profile/skills/experience history (not a retrieved subset — see
full_context.py for why), optionally informed by the matcher's report
so it can lead with genuine strengths for this particular job.

The system prompt tells the model never to leave a bracket placeholder
like [Job Title] — but that's a soft, probabilistic instruction, and
small local models have a strong training-data prior toward literal
cover-letter templates that can override it anyway. _fix_stray_placeholders()
is the hard backstop: a regex pass after generation that catches common
placeholder patterns and substitutes the real value in code, which
doesn't depend on the model complying with anything.
"""
from __future__ import annotations

import re

from ..full_context import load_full_context, get_candidate_name
from ..rag_query import generate

SYSTEM_PROMPT = (
    "You are a cover letter writer. Write a concise, specific cover letter "
    "(3-4 short paragraphs, plain prose — no markdown, bold, bullets, or "
    "headers) using ONLY the candidate facts provided.\n\n"
    "Rules:\n"
    "1. Use the real name, job title, and company given below — never a "
    "bracket like [Your Name] or [Job Title]. If no hiring manager name is "
    "known, greet with 'Dear Hiring Team,' — still no bracket. Any square-"
    "bracket placeholder is a failure, even if the rest is good.\n"
    "2. Tailor to THIS job: lead with the 2-3 facts most relevant to what "
    "the posting asks for, and reference something concrete from it — not "
    "a generic letter with the job title swapped in.\n"
    "3. Never invent achievements, employers, metrics, methodologies, or "
    "certifications not in the facts — e.g. don't say 'Lean Six Sigma' "
    "just because the facts mention general continuous-improvement work."
)

# Each pattern matches a bracket containing any of these key words, so it
# catches variants like "[Job Title]", "[Insert Job Title Here]", or
# "[Position]" with one rule rather than an exact-string list.
_PLACEHOLDER_FIXES = [
    (re.compile(r"\[[^\]]*\b(job\s*title|position\s*title|position|role)\b[^\]]*\]", re.IGNORECASE), "title"),
    (re.compile(r"\[[^\]]*\bcompany(\s*name)?\b[^\]]*\]", re.IGNORECASE), "company"),
    (re.compile(r"\[[^\]]*\b(your\s+name|full\s+name|candidate\s+name)\b[^\]]*\]", re.IGNORECASE), "name"),
    (re.compile(r"\[[^\]]*\b(hiring\s+manager|recipient)\b[^\]]*\]", re.IGNORECASE), "greeting_fallback"),
]


def _fix_stray_placeholders(text: str, title: str, company: str, name: str) -> str:
    values = {"title": title, "company": company, "name": name, "greeting_fallback": "Hiring Team"}
    for pattern, key in _PLACEHOLDER_FIXES:
        replacement = values.get(key)
        if replacement:
            text = pattern.sub(replacement, text)
    return text


def write_cover_letter(job: dict, match_report: str = "") -> str:
    context = load_full_context()
    title = job.get("title") or "the open role"
    company = job.get("company") or "your company"
    name = get_candidate_name()

    prompt = (
        f"Target job title (use this exact text in the letter, not a placeholder): {title}\n"
        f"Target company (use this exact text in the letter, not a placeholder): {company}\n"
        f"Job description: {job.get('raw_description', '')[:2000]}\n\n"
        + (f"Match analysis (for emphasis):\n{match_report}\n\n" if match_report else "")
        + f"Candidate's complete profile, skills, and experience history:\n{context}\n\n"
        "Write the cover letter now."
    )
    result = generate(prompt, system=SYSTEM_PROMPT)
    return _fix_stray_placeholders(result, title, company, name)
