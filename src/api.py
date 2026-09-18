"""
Local REST API wrapping the job-hunt agent, so a browser-based frontend
(or, later, an automation tool) can call it over HTTP instead of the CLI.
No logic is reimplemented here — every endpoint just calls the same
functions the CLI uses (src/orchestrator.py, src/agents/, src/ingest.py).

Run with:
    uvicorn src.api:app --reload --port 8000

This is a single-user local tool, not a public service — CORS is left
wide open (allow_origins=["*"]) so a frontend opened as a local HTML
file, or served from a different local port, can call it freely.
"""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .orchestrator import run_matching, run_matching_parsed, CONFIDENCE_THRESHOLD
from .agents.matcher import match_job
from .agents.resume_fixer import fix_resume
from .agents.cover_letter import write_cover_letter
from .ingest import ingest_all, Manifest
from .rag_query import ask as rag_ask

app = FastAPI(title="Job Hunt Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MatchRequest(BaseModel):
    job_source: str | None = None  # raw pasted job description text, or a URL
    job: dict | None = None        # an already-parsed or saved job
    save_job: bool = False         # true for a newly imported structured posting


class ResumeRequest(BaseModel):
    job: dict
    match_report: str = ""


class CoverLetterRequest(BaseModel):
    job: dict
    match_report: str = ""


class AskRequest(BaseModel):
    query: str
    entity_type: str | None = None


class JobPostingUpdateRequest(BaseModel):
    status: str | None = None
    resume_text: str | None = None
    cover_letter_text: str | None = None


def _as_http_error(e: Exception) -> HTTPException:
    """Local Ollama/model errors (SystemExit, ValueError from bad JSON,
    etc.) become a 502 with the original message intact, rather than a
    generic 500 that hides what actually went wrong."""
    return HTTPException(status_code=502, detail=str(e))


@app.get("/api/health")
def health():
    """The frontend polls this to show a connected/not-connected indicator."""
    return {"status": "ok"}


@app.post("/api/match")
def match(req: MatchRequest):
    """
    Either parses a job (req.job_source: text or URL), imports a structured
    job (req.job with save_job=true), or re-matches an existing saved job
    (req.job with save_job=false) without spending an extra LLM call.

    Returns job, match_report, confidence, confidence_detected,
    below_threshold, confidence_threshold — the frontend decides how to
    react to below_threshold (e.g. show a warning) rather than the API
    blocking anything; a GUI's buttons are already the "ask before
    generating" step the CLI needs input() for.
    """
    try:
        if req.job:
            if req.save_job:
                result = run_matching_parsed(req.job)
            else:
                match_result = match_job(req.job)
                result = {
                    "job": req.job,
                    "match_report": match_result["report"],
                    "confidence": match_result["confidence"],
                    "confidence_detected": match_result["confidence_detected"],
                    "below_threshold": (
                        match_result["confidence"] is None
                        or match_result["confidence"] < CONFIDENCE_THRESHOLD
                    ),
                    "saved": True,  # re-matching a job from /api/job-postings
                }
        elif req.job_source:
            result = run_matching(req.job_source)
        else:
            raise HTTPException(status_code=400, detail="Provide either job_source or job.")
    except (SystemExit, ValueError) as e:
        raise _as_http_error(e)
    result["confidence_threshold"] = CONFIDENCE_THRESHOLD
    return result


@app.post("/api/resume")
def resume(req: ResumeRequest):
    try:
        text = fix_resume(req.job, match_report=req.match_report)
    except (SystemExit, ValueError) as e:
        raise _as_http_error(e)
    return {"resume": text}


@app.post("/api/cover-letter")
def cover_letter(req: CoverLetterRequest):
    try:
        text = write_cover_letter(req.job, match_report=req.match_report)
    except (SystemExit, ValueError) as e:
        raise _as_http_error(e)
    return {"cover_letter": text}


@app.post("/api/ask")
def ask_endpoint(req: AskRequest):
    """Free-form Q&A against your indexed career data (still
    retrieval-based — see rag_query.ask)."""
    try:
        result = rag_ask(req.query, entity_type=req.entity_type)
    except (SystemExit, ValueError) as e:
        raise _as_http_error(e)
    return result


@app.get("/api/status")
def status():
    """Indexed entity counts, for a knowledge-base dashboard panel."""
    return {"indexed": Manifest().counts()}


@app.post("/api/ingest")
def ingest():
    """Re-runs ingestion (only affects `ask`'s vector store — match/resume/
    cover-letter read data/*.json directly and don't need this)."""
    try:
        stats = ingest_all(verbose=False)
    except (SystemExit, ValueError) as e:
        raise _as_http_error(e)
    return {"stats": stats, "indexed": Manifest().counts()}


@app.get("/api/job-postings")
def list_job_postings():
    """Every previously saved job posting (data/job_postings/*.json),
    newest first — lets the frontend show a history and re-match one
    without re-pasting it."""
    postings = []
    if config.JOB_POSTINGS_DIR.exists():
        for f in sorted(config.JOB_POSTINGS_DIR.glob("*.json"), reverse=True):
            try:
                postings.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
    return {"postings": postings}


@app.patch("/api/job-postings/{job_id}")
def update_job_posting(job_id: str, req: JobPostingUpdateRequest):
    """
    Partial update of a saved posting — used for two things: moving a
    Kanban card between status columns, and persisting a generated
    resume/cover letter onto the posting so reopening it later (the
    card's detail view) shows what was actually produced for it. Only
    the fields provided are changed; everything else in the saved JSON
    is left untouched.
    """
    path = config.JOB_POSTINGS_DIR / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No saved job posting with id '{job_id}'.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Saved posting file is corrupted: {e}")

    if req.status is not None:
        data["status"] = req.status
    if req.resume_text is not None:
        data["resume_text"] = req.resume_text
    if req.cover_letter_text is not None:
        data["cover_letter_text"] = req.cover_letter_text

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@app.get("/api/profile-data")
def profile_data():
    """Read-only: your skill names and job titles/companies, straight from
    data/skills.json and data/experience.json — no LLM call, nothing
    generated. Lets the frontend tell a 'skill' mention in a match report
    apart from an 'experience' mention, for the two match-map charts."""
    from .ingest import load_entities

    skills = load_entities("skill", config.ENTITY_FILES["skill"])
    experience = load_entities("experience", config.ENTITY_FILES["experience"])
    return {
        "skills": [
            {
                "id": s["id"],
                "name": s["name"],
                "related_experience_ids": s.get("related_experience_ids", []),
            }
            for s in skills
        ],
        "experience": [
            {
                "id": e["id"],
                "title": e["title"],
                "company": e["company"],
                "skills_used": e.get("skills_used", []),
                "tags": e.get("tags", []),
            }
            for e in experience
        ],
    }
