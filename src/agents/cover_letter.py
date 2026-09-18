"""
Cover letter agent — stage 4 of the orchestrator pipeline.

Drafts a short, specific cover letter using the candidate's COMPLETE
profile/skills/experience history (not a retrieved subset — see
full_context.py for why). The matcher's strong and moderate findings are
treated as an approved evidence set, so unrelated career history does not
crowd out the reasons this candidate fits this particular posting.

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
    "with exactly 3 short body paragraphs, using ONLY the candidate facts "
    "provided.\n\n"
    "Rules:\n"
    "1. Return only the letter itself: begin with 'Dear Hiring Team,' and end "
    "with 'Sincerely,' followed by the real candidate name. Do not include "
    "an address block, date, subject line, company address, bracket "
    "placeholders, notes, markdown, bullets, or headers.\n"
    "2. Before writing, choose 2-3 requirements from the focused job posting "
    "and map each one to the APPROVED MATCH EVIDENCE. Lead with that mapping; "
    "do not write a general career chronology.\n"
    "3. Treat APPROVED MATCH EVIDENCE as the relevance boundary. Do not mention "
    "a technology, domain, or achievement that appears only under weak/no "
    "matches or is otherwise unrelated to the target role. If evidence is "
    "missing, omit it rather than filling space with another career domain.\n"
    "4. Never invent achievements, employers, metrics, methodologies, or "
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

_SECTION_HEADER = re.compile(
    r"^\s*(?:\*\*)?\s*(strong|moderate|partial|weak|no|gaps?|conclusion)"
    r"(?:\s+(?:or\s+no\s+)?matches?)?\s*(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
_ROLE_START_MARKERS = ("about the role", "key responsibilities", "responsibilities")
_ROLE_END_MARKERS = ("employer questions", "how to apply", "report this job", "featured jobs")


def _focused_job_description(raw_description: str) -> str:
    """Keep the substantive role content and drop common job-board chrome."""
    text = " ".join(raw_description.split())
    lower = text.lower()
    start_positions = [lower.find(marker) for marker in _ROLE_START_MARKERS if lower.find(marker) >= 0]
    if start_positions:
        text = text[min(start_positions):]
        lower = text.lower()
    end_positions = [lower.find(marker) for marker in _ROLE_END_MARKERS if lower.find(marker) >= 0]
    if end_positions:
        text = text[:min(end_positions)]
    return text[:5000]


def _approved_match_evidence(match_report: str) -> str:
    """Return only strong/moderate evidence from the matcher report."""
    if not match_report.strip():
        return "(No match report was available. Use only clearly relevant candidate facts.)"

    accepted_sections = {"strong", "moderate", "partial"}
    current_section = None
    kept: list[str] = []
    saw_header = False
    for line in match_report.splitlines():
        header = _SECTION_HEADER.match(line)
        if header:
            current_section = header.group(1).lower()
            saw_header = True
            continue
        if current_section in accepted_sections:
            kept.append(line)

    evidence = "\n".join(line for line in kept if line.strip()).strip()
    if evidence:
        return evidence
    if not saw_header:
        return match_report.strip()
    return "(The match report did not identify strong or moderate evidence.)"


def _fix_stray_placeholders(text: str, title: str, company: str, name: str) -> str:
    values = {"title": title, "company": company, "name": name, "greeting_fallback": "Hiring Team"}
    for pattern, key in _PLACEHOLDER_FIXES:
        replacement = values.get(key)
        if replacement:
            text = pattern.sub(replacement, text)
    return text


def _clean_template_scaffolding(text: str, name: str) -> str:
    """Remove common template residue and Markdown emphasis from a letter."""
    text = text.replace("\r\n", "\n").strip()
    greeting = re.search(r"(?im)^dear\s+[^\n,]+,\s*$", text)
    if greeting:
        text = text[greeting.start():]
    else:
        text = f"Dear Hiring Team,\n\n{text}"

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\*?note\s*:", stripped, re.IGNORECASE):
            break
        if re.fullmatch(r"\[[^\]]+\]", stripped):
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    text = re.sub(r"\[[^\]\n]+\]", "", text)
    # Models occasionally wrap achievements in Markdown bold despite the
    # prompt. A plain-text letter should never expose its formatting tokens.
    text = text.replace("**", "")

    if name and not re.search(rf"(?im)^\s*{re.escape(name)}\s*$", text):
        if not re.search(r"(?im)^sincerely,?\s*$", text):
            text = f"{text}\n\nSincerely,"
        text = f"{text}\n{name}"
    return text.strip()


def write_cover_letter(job: dict, match_report: str = "") -> str:
    context = load_full_context()
    title = job.get("title") or "the open role"
    company = job.get("company") or "your company"
    name = get_candidate_name()

    prompt = (
        f"Target job title: {title}\n"
        f"Target company: {company}\n"
        f"Focused job posting:\n{_focused_job_description(job.get('raw_description', ''))}\n\n"
        f"APPROVED MATCH EVIDENCE (use this to choose what to mention):\n"
        f"{_approved_match_evidence(match_report)}\n\n"
        f"Candidate facts (use only to accurately elaborate approved evidence):\n{context}\n\n"
        "Write the cover letter now."
    )
    result = generate(prompt, system=SYSTEM_PROMPT)
    result = _fix_stray_placeholders(result, title, company, name)
    return _clean_template_scaffolding(result, name)
