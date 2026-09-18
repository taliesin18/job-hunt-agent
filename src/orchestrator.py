"""
Orchestrator — chains the fetcher, matcher, resume-fixer, and
cover-letter agents for a single job posting.

This is deliberately a plain sequential pipeline (no agent framework):
each stage is a function with its own system prompt.

Split into two composable steps rather than one all-or-nothing
pipeline, so a caller (e.g. the CLI's `apply` command) can run the
match first, show it to the person, and only generate a resume and/or
cover letter if they actually want one:

  1. run_matching()               — fetch/parse + save + match
  2. generate_resume_and_cover_letter() — resume and/or cover letter,
                                     each independently optional

run_pipeline() is kept as a non-interactive convenience wrapper around
both, for scripts/automation that want the old always-generate-both
behavior in one call.

Gating: the matcher agent returns a 0-100 confidence score for how
strong a fit the candidate is. If it's below CONFIDENCE_THRESHOLD,
callers should treat that as "don't bother generating a resume/cover
letter" by default — there's no point drafting either for a role the
data says is a weak fit. Set confidence_skip=True (run_pipeline) or
just proceed anyway (interactive callers can ask the person directly)
to bypass this.

Saving: a job posting is only written to data/job_postings/ when its
match confidence meets CONFIDENCE_THRESHOLD — a low-confidence match is
computed and reported, but not persisted, so the Job Postings board
only fills up with roles actually worth tracking. Re-matching an
already-saved posting (passing a pre-parsed `job` dict rather than raw
text) never re-triggers this decision; it's already saved.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .agents.fetcher import parse_job_posting
from .agents.matcher import match_job
from .agents.resume_fixer import fix_resume
from .agents.cover_letter import write_cover_letter
from .schemas import JobPosting

CONFIDENCE_THRESHOLD = 50


def _match_and_maybe_save(job: dict, save_job: bool = True) -> dict:
    """Match a normalized posting, saving only when it clears the threshold."""
    match_result = match_job(job)
    confidence = match_result["confidence"]
    # A missing score is not evidence of a good fit. Do not save or
    # automatically prioritize a posting until the model provides one.
    below_threshold = confidence is None or confidence < CONFIDENCE_THRESHOLD

    saved = False
    if save_job and not below_threshold:
        job["last_match_confidence"] = confidence
        config.JOB_POSTINGS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = config.JOB_POSTINGS_DIR / f"{job['id']}.json"
        out_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        saved = True

    return {
        "job": job,
        "match_report": match_result["report"],
        "confidence": match_result["confidence"],
        "confidence_detected": match_result["confidence_detected"],
        "below_threshold": below_threshold,
        "saved": saved,
    }


def run_matching(source: str, save_job: bool = True) -> dict:
    """
    source: raw job description text OR a URL to fetch it from.

    Fetches/parses the job and runs the matcher first, THEN saves to
    data/job_postings/ only if save_job is True and the match confidence
    meets CONFIDENCE_THRESHOLD — see module docstring. Returns:
        job, match_report, confidence, confidence_detected,
        below_threshold, saved
    """
    return _match_and_maybe_save(parse_job_posting(source), save_job=save_job)


def run_matching_parsed(job: dict, save_job: bool = True) -> dict:
    """Match a structured JobPosting payload captured outside the application.

    The browser extension supplies this form. Validate and normalize it before
    use so downstream agents always receive the same shape as postings parsed
    from raw text. This avoids a second local-LLM extraction pass while the
    original description is still retained in ``raw_description``.
    """
    try:
        normalized_job = JobPosting.model_validate(job).model_dump()
    except Exception as e:
        raise ValueError(f"Invalid structured job posting: {e}") from e
    return _match_and_maybe_save(normalized_job, save_job=save_job)


def generate_resume_and_cover_letter(
    job: dict,
    match_report: str = "",
    want_resume: bool = True,
    want_cover_letter: bool = True,
    existing_resume_path: str | None = None,
) -> dict:
    """
    Generates whichever of (resume, cover letter) is requested. Either
    can be skipped independently — the one not requested comes back as
    None rather than being generated and discarded, since each is its
    own (slow, local-inference) LLM call.
    """
    resume = None
    if want_resume:
        existing_resume_text = None
        if existing_resume_path:
            existing_resume_text = Path(existing_resume_path).read_text(encoding="utf-8")
        resume = fix_resume(job, match_report=match_report, existing_resume_text=existing_resume_text)

    cover_letter = None
    if want_cover_letter:
        cover_letter = write_cover_letter(job, match_report=match_report)

    return {"resume": resume, "cover_letter": cover_letter}


def run_pipeline(
    source: str,
    existing_resume_path: str | None = None,
    save_job: bool = True,
    confidence_skip: bool = False,
) -> dict:
    """
    Non-interactive convenience wrapper: runs the match, then — unless
    confidence is below threshold and confidence_skip is False —
    generates BOTH a resume and a cover letter automatically. For an
    interactive flow that asks before generating each artifact, call
    run_matching() and generate_resume_and_cover_letter() directly
    instead (see the CLI's `apply` command).

    Returns a dict with keys: job, match_report, confidence,
    confidence_detected, skipped, resume, cover_letter. When skipped is
    True, resume and cover_letter are None.
    """
    match_result = run_matching(source, save_job=save_job)
    job = match_result["job"]

    skipped = match_result["below_threshold"] and not confidence_skip
    if skipped:
        return {**match_result, "skipped": True, "resume": None, "cover_letter": None}

    generated = generate_resume_and_cover_letter(
        job,
        match_report=match_result["match_report"],
        want_resume=True,
        want_cover_letter=True,
        existing_resume_path=existing_resume_path,
    )
    return {**match_result, "skipped": False, **generated}
