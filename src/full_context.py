"""
Full-context alternative to RAG retrieval, for tasks that should see your
COMPLETE profile — identity, skills, experience, education, projects, and
certifications — rather than a fuzzy top-k semantic sample.

Why: semantic top-k retrieval is built for knowledge bases too large to
fit in a prompt. Yours isn't — a few dozen skills and half a dozen jobs
renders to a few thousand words, comfortably inside any local model's
context window. For job MATCHING and resume/cover-letter TAILORING
specifically, seeing everything is strictly better than seeing a
similarity-ranked sample: a top-k search can under-represent a skill or
job that's genuinely relevant but not textually similar to the job
description (e.g. an adaptability angle spanning several roles), and
that's exactly the kind of thing these tasks need to catch.

`ask()` (free-form Q&A) in rag_query.py still uses retrieval — that's a
different use case where scoping to the most relevant few facts is
actually what you want, and stays useful as your data grows.
"""
from __future__ import annotations

import json

from . import config
from .ingest import load_entities, RENDERERS


def _load_profile() -> dict:
    if not config.PROFILE_FILE.exists():
        return {}
    return json.loads(config.PROFILE_FILE.read_text(encoding="utf-8"))


def get_candidate_name() -> str:
    """Just the bare name, for code-level fixes (e.g. substituting a stray
    '[Your Name]' the model didn't replace) — separate from
    _render_profile()'s full-sentence form, which isn't useful for that."""
    return _load_profile().get("name", "")


def _render_profile() -> str:
    """Your name, headline, and summary — without this, nothing downstream
    (cover letters especially) has any way to know your actual name, and
    ends up writing '[Your Name]' instead. profile.json isn't ingested as
    an entity like skills/experience are (it's a single object, not a
    list), so it needs its own small renderer here rather than going
    through ingest.py's RENDERERS."""
    profile = _load_profile()
    if not profile:
        return ""
    parts = [f"Candidate name: {profile.get('name', '(not given)')}."]
    if profile.get("headline"):
        parts.append(f"Current headline/title: {profile['headline']}.")
    if profile.get("summary"):
        parts.append(f"Professional summary: {profile['summary']}")
    return " ".join(parts)


def load_full_context() -> str:
    """Render the candidate's profile plus every skill, experience,
    education, project, and certification entry as text and concatenate
    them. This is what matcher.py, resume_fixer.py, cover_letter.py, and
    field_filler.py send to the LLM instead of a retrieved subset."""
    sections = []
    profile_text = _render_profile()
    if profile_text:
        sections.append(profile_text)
    for entity_type, path in config.ENTITY_FILES.items():
        entities = load_entities(entity_type, path)
        renderer = RENDERERS[entity_type]
        for entity in entities:
            sections.append(renderer(entity))
    return "\n\n".join(sections)
