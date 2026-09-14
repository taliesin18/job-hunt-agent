"""
Resume fixer agent — stage 3 of the orchestrator pipeline.

Given a job posting and (optionally) the matcher's report, rewrites the
candidate's actual resume (data/current_resume.txt, if present) for
this specific job — preserving its exact structure (sections, job
titles, companies, dates, education) and only rewriting the tailorable
prose within it: headline, summary, skills line, and bullets per job.
If no base resume file exists, falls back to writing plain tailored
bullets instead.

Uses the candidate's COMPLETE skills/experience history (full_context.py)
rather than a retrieved subset — see that module's docstring for why.
"""
from __future__ import annotations

from ..full_context import load_full_context
from ..rag_query import generate
from .. import config

SYSTEM_PROMPT = (
    "You are a resume editor specializing in tailoring a resume to ONE specific "
    "job posting. Your job is NOT to summarize or transcribe the candidate's work "
    "history — it is to select and reframe the facts so a recruiter sees the fit "
    "for THIS job. Copying or lightly rewording the candidate facts as given is a "
    "failure; you must actively decide what to lead with, what to compress, and "
    "what to leave out.\n\n"
    "Follow this priority order:\n"
    "1. First, work out what this job actually requires (skills, responsibilities, "
    "domain, seniority) from the job description.\n"
    "2. Reframe wording around the job's own terms where the underlying fact "
    "genuinely supports it — do not just restate the candidate facts verbatim, "
    "and do not just restate the job description back at the reader.\n"
    "3. Where the candidate's background only partially overlaps with the role "
    "(different tech stack, different industry), phrase it around the "
    "transferable capability, not the mismatched detail — e.g. lead with 'led "
    "production incident response across distributed systems' rather than "
    "naming an unrelated legacy platform, so the relevance is explicit rather "
    "than left for the reader to infer.\n"
    "4. This candidate has moved across several distinct technical domains over "
    "their career (for example: embedded systems, security/smartcards, SaaS "
    "backend support, IT operations, identity & access management, AI "
    "automation). Where the facts support it, work in a line that explicitly "
    "frames this range as adaptability — the ability to ramp up quickly in a "
    "new technical domain — rather than letting it read as an unfocused job "
    "history.\n\n"
    "Write in plain text only — no markdown emphasis syntax like **bold** "
    "or _italic_ anywhere, even for a job title or company name you want "
    "to stand out. This text is inserted as-is into a plain-text or Word "
    "document; markdown characters would appear as literal asterisks/"
    "underscores, not formatting. Bullet points themselves are fine — "
    "those are real resume structure, not markdown you need to avoid.\n\n"
    "Never invent achievements, employers, dates, metrics, methodologies, "
    "or frameworks that are not present in the candidate facts — if a "
    "specific named term (e.g. a methodology like 'Lean Six Sigma') is not "
    "stated there, do not use that term even if something similar (e.g. "
    "general continuous-improvement or kaizen work) is. Each bullet starts "
    "with an action verb, stays to one line, and includes a metric only "
    "where one exists in the facts."
)

_REVISE_INSTRUCTION = (
    "Above is the candidate's actual current resume. Produce a REVISED version "
    "of this exact resume, tailored to the target job, in the SAME overall "
    "format — output a complete resume, not a bare bullet list. Structural "
    "rules, followed strictly:\n"
    "- Keep every section header, job title, company name, employment date "
    "range, and education entry EXACTLY as written. Do not add, remove, "
    "reorder, or rename any of these.\n"
    "- Keep the same jobs in the same order. Never move a bullet from one job "
    "to a different job — each bullet must stay attributed to the job it "
    "already belongs to.\n"
    "- You MAY rewrite: the headline line under the name, the Professional "
    "Summary paragraph, the Core Skills line, and the bullet text within each "
    "job (reword, reprioritize, swap emphasis) — grounded only in that job's "
    "existing bullets or the candidate facts below.\n"
    "- You may trim one clearly irrelevant bullet or add one clearly relevant "
    "one per job, but never leave a job with zero bullets or gut its content.\n"
    "Never invent achievements, employers, dates, or metrics not present in "
    "the original resume or the candidate facts below."
)

_FRESH_BULLETS_INSTRUCTION = (
    "No base resume file was found, so write 5-8 tailored resume bullet "
    "points for this job instead of a full resume. Prioritize facts that "
    "directly align with the job's requirements — lead with those. Include "
    "at most 1-2 minor bullets for less-aligned experience, and only if "
    "still IT/technical. Reframe rather than transcribe the facts, and "
    "include a bullet highlighting adaptability across technical domains if "
    "the facts support it."
)


def _load_canonical_resume_text() -> str | None:
    if config.CURRENT_RESUME_PATH.exists():
        return config.CURRENT_RESUME_PATH.read_text(encoding="utf-8")
    return None


def fix_resume(
    job: dict,
    match_report: str = "",
    existing_resume_text: str | None = None,
) -> str:
    """
    If existing_resume_text isn't given, auto-loads
    data/current_resume.txt (if present) as the base resume to revise
    in place, preserving its structure. Falls back to plain tailored
    bullets only if no base resume is available either way.
    """
    if existing_resume_text is None:
        existing_resume_text = _load_canonical_resume_text()

    context = load_full_context()

    parts = [
        f"Target job: {job.get('title')} at {job.get('company')}",
        f"Job description: {job.get('raw_description', '')[:2000]}",
    ]
    if match_report:
        parts.append(f"Match analysis (for emphasis, not a source of new facts):\n{match_report}")
    parts.append(f"Candidate's complete skills and experience history:\n{context}")

    if existing_resume_text:
        parts.append(f"Candidate's current resume:\n{existing_resume_text}")
        instruction = _REVISE_INSTRUCTION
    else:
        instruction = _FRESH_BULLETS_INSTRUCTION

    prompt = "\n\n".join(parts) + f"\n\n{instruction}"
    return generate(prompt, system=SYSTEM_PROMPT)
