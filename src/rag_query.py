"""
Retrieval + generation layer.

Embeds a query, retrieves the most relevant chunks from ChromaDB
(optionally filtered by entity_type), builds a grounded prompt, and
calls a local Ollama model to generate the answer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from . import config
from .ingest import get_collection, embed_text


def retrieve(query: str, k: int = 5, entity_type: str | None = None) -> dict[str, Any]:
    collection = get_collection()
    vector = embed_text(query)
    where = {"entity_type": entity_type} if entity_type else None
    result = collection.query(query_embeddings=[vector], n_results=k, where=where)
    return dict(result)


def format_context(results: dict[str, Any]) -> str:
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    lines = []
    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        lines.append(f"[{i}] ({meta.get('entity_type')}: {meta.get('title')})\n{doc}")
    return "\n\n".join(lines) if lines else "(no matching context found)"


def generate(prompt: str, system: str | None = None) -> str:
    payload = {
        "model": config.GEN_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": not config.DISABLE_THINKING_MODE,
    }
    if system:
        payload["system"] = system
    try:
        resp = requests.post(
            f"{config.OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(
            f"Could not reach Ollama at {config.OLLAMA_HOST}. Is `ollama serve` running, "
            f"and have you run `ollama pull {config.GEN_MODEL}`?"
        ) from e
    except requests.exceptions.ReadTimeout as e:
        raise SystemExit(
            f"Ollama didn't respond within {config.REQUEST_TIMEOUT_SECONDS}s. This usually "
            "means the model is slower than the timeout on your hardware — try a smaller "
            "model, confirm Ollama is actually using your GPU (`ollama ps` should show "
            "mostly GPU, not CPU), or raise REQUEST_TIMEOUT_SECONDS in src/config.py."
        ) from e
    data = resp.json()
    text = data["response"].strip()
    # Belt-and-suspenders: some Ollama/model version combinations have been
    # known to emit a <think>...</think> block even when think=False is
    # requested (see ollama/ollama#10809). Strip it if present so callers
    # expecting plain text or JSON don't have to deal with it.
    if text.startswith("<think>"):
        end = text.find("</think>")
        if end != -1:
            text = text[end + len("</think>"):].strip()
    return text


SYSTEM_PROMPT = (
    "You are a career assistant. Answer using ONLY the provided context about the "
    "user's skills, work experience, education, projects, and certifications. "
    "Never invent achievements, dates, metrics, or skills that are not in the context. "
    "If the context doesn't contain enough information to answer, say so plainly."
)


def ask(query: str, k: int = 5, entity_type: str | None = None) -> dict:
    results = retrieve(query, k=k, entity_type=entity_type)
    context = format_context(results)
    prompt = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
    answer = generate(prompt, system=SYSTEM_PROMPT)
    return {"answer": answer, "context": context}


def load_job_posting(job_file: str) -> dict:
    """Load a saved job_postings JSON file, by path or by filename under
    data/job_postings/."""
    path = Path(job_file)
    if not path.exists():
        candidate = config.JOB_POSTINGS_DIR / job_file
        if candidate.exists():
            path = candidate
        else:
            raise SystemExit(f"Job posting file not found: {job_file}")
    return json.loads(path.read_text(encoding="utf-8"))


# kept for any external code written against the old private name
_load_job_posting_text = load_job_posting


def tailor_resume(job_file: str) -> str:
    """Thin wrapper kept for the `tailor-resume` CLI command — delegates
    to agents.resume_fixer.fix_resume so this command benefits from the
    same full-context + format-preserving logic as `apply`."""
    from .agents.resume_fixer import fix_resume  # local import: fix_resume imports generate from this module
    job = load_job_posting(job_file)
    return fix_resume(job)


def gap_analysis(job_file: str) -> str:
    """Thin wrapper kept for the `gap-analysis` CLI command — delegates
    to agents.matcher.match_job so this command benefits from the same
    full-context matching as `apply`."""
    from .agents.matcher import match_job  # local import: avoids a circular import with agents.matcher
    job = load_job_posting(job_file)
    return match_job(job)["report"]
