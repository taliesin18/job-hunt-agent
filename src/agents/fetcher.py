"""
Fetcher / parser agent — stage 1 of the orchestrator pipeline.

Takes a job description as either raw pasted text or a URL, uses the
local LLM to extract it into the JobPosting schema (company, title,
required_skills), and returns a dict ready to save as a job_postings
JSON file.

This agent has its own system prompt, separate from the other agents,
because its job is narrow and mechanical: extract fields, don't
analyze or advise.
"""
from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser

import requests

from ..schemas import JobPosting
from ..rag_query import generate
from ..json_utils import extract_json

SYSTEM_PROMPT = (
    "You are a job-posting parser. Extract structured fields from the raw job "
    "posting text you are given. Respond with ONLY a single JSON object, no "
    'markdown fences, no commentary, with exactly these keys: "company" '
    '(string), "title" (string), "required_skills" (array of short skill '
    "strings). If a field cannot be determined, use an empty string or empty "
    "array. Never invent a company or title that isn't clearly present in the "
    "text."
)


class _TextExtractor(HTMLParser):
    """Minimal HTML-to-text stripper — avoids adding a new dependency
    just for this one step."""

    def __init__(self):
        super().__init__()
        self._skip = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.chunks.append(text)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.chunks)


def fetch_raw_text(source: str) -> str:
    """`source` is either raw pasted text or an http(s) URL."""
    if source.strip().startswith(("http://", "https://")):
        resp = requests.get(source, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return _html_to_text(resp.text)
    return source


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unknown"


def parse_job_posting(source: str, job_id: str | None = None) -> dict:
    """
    source: raw job description text OR a URL to fetch it from.
    Returns a dict matching the JobPosting schema.
    """
    raw_text = fetch_raw_text(source)
    prompt = f"Job posting text:\n{raw_text[:6000]}\n\nExtract the JSON now."
    response = generate(prompt, system=SYSTEM_PROMPT)

    try:
        extracted = extract_json(response)
    except ValueError:
        # Don't let a malformed model response crash the whole pipeline —
        # fall back to empty fields; raw_description still has everything.
        extracted = {"company": "", "title": "", "required_skills": []}

    company = extracted.get("company") or "Unknown"
    is_url = source.strip().startswith(("http://", "https://"))
    job_id = job_id or f"job_{date.today().isoformat()}_{_slugify(company)}"

    job = JobPosting(
        id=job_id,
        company=company,
        title=extracted.get("title") or "Unknown",
        url=source if is_url else None,
        date_saved=date.today().isoformat(),
        raw_description=raw_text,
        required_skills=extracted.get("required_skills") or [],
        status="saved",
    )
    return job.model_dump()
