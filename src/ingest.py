"""
Ingestion pipeline.

Scans data/*.json, renders each entity into a natural-language chunk,
embeds changed/new chunks with a local Ollama embedding model, and
upserts them into a local ChromaDB collection. A small SQLite manifest
tracks a content hash per entity so re-running this script only does
work for what actually changed (including deleting vectors for
entities you removed from the JSON files).

Job postings (data/job_postings/*.json) are intentionally NOT embedded
here. They describe a role you're applying to, not a fact about you —
embedding them into the same collection as your real skills/experience
risks a retrieval later surfacing a past job posting as if it were
your own work history, which the LLM can then mistake for a genuine
achievement. The fetcher/matcher/resume-fixer/cover-letter agents all
read a job posting's JSON file directly (see rag_query.load_job_posting)
rather than via retrieval, so nothing is lost by excluding them here.

Usage:
    python -m src.ingest
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

import requests

try:
    import chromadb
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "chromadb is not installed. Run: pip install -r requirements.txt"
    ) from e

from . import config
from .schemas import ENTITY_MODELS


# ---------------------------------------------------------------------------
# Manifest (tracks what's already indexed, so re-runs are incremental)
# ---------------------------------------------------------------------------
class Manifest:
    def __init__(self, path: Path = config.MANIFEST_DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_entities (
                doc_id       TEXT PRIMARY KEY,
                entity_type  TEXT NOT NULL,
                entity_id    TEXT NOT NULL,
                source_file  TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                last_indexed TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def get_hash(self, doc_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM indexed_entities WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return row[0] if row else None

    def upsert(self, doc_id: str, entity_type: str, entity_id: str,
               source_file: str, content_hash: str) -> None:
        self.conn.execute(
            """
            INSERT INTO indexed_entities
                (doc_id, entity_type, entity_id, source_file, content_hash, last_indexed)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(doc_id) DO UPDATE SET
                content_hash = excluded.content_hash,
                last_indexed = excluded.last_indexed
            """,
            (doc_id, entity_type, entity_id, source_file, content_hash),
        )
        self.conn.commit()

    def doc_ids_for_type(self, entity_type: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT doc_id FROM indexed_entities WHERE entity_type = ?", (entity_type,)
        ).fetchall()
        return {r[0] for r in rows}

    def delete(self, doc_id: str) -> None:
        self.conn.execute("DELETE FROM indexed_entities WHERE doc_id = ?", (doc_id,))
        self.conn.commit()

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT entity_type, COUNT(*) FROM indexed_entities GROUP BY entity_type"
        ).fetchall()
        return dict(rows)


# ---------------------------------------------------------------------------
# Embedding (local Ollama)
# ---------------------------------------------------------------------------
def embed_text(text: str) -> list[float]:
    try:
        resp = requests.post(
            f"{config.OLLAMA_HOST}/api/embeddings",
            json={"model": config.EMBED_MODEL, "prompt": text},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(
            "Could not reach Ollama at "
            f"{config.OLLAMA_HOST}. Is `ollama serve` running, and have you run "
            f"`ollama pull {config.EMBED_MODEL}`?"
        ) from e
    return resp.json()["embedding"]


# ---------------------------------------------------------------------------
# Rendering: entity dict -> natural-language text for embedding
# ---------------------------------------------------------------------------
def render_skill(e: dict) -> str:
    parts = [f"Skill: {e['name']} ({e.get('category', 'general')})."]
    if e.get("proficiency"):
        parts.append(f"Proficiency: {e['proficiency']}.")
    if e.get("years_experience") is not None:
        parts.append(f"Years of experience: {e['years_experience']}.")
    if e.get("last_used"):
        parts.append(f"Last used: {e['last_used']}.")
    if e.get("tags"):
        parts.append(f"Tags: {', '.join(e['tags'])}.")
    if e.get("notes"):
        parts.append(e["notes"])
    return " ".join(parts)


def render_experience(e: dict) -> str:
    parts = [
        f"Job: {e['title']} at {e['company']} "
        f"({e.get('start_date', '?')} to {e.get('end_date', '?')})."
    ]
    if e.get("summary"):
        parts.append(e["summary"])
    if e.get("responsibilities"):
        parts.append("Responsibilities: " + "; ".join(e["responsibilities"]) + ".")
    for a in e.get("achievements", []):
        line = a["description"]
        if a.get("metric"):
            line += f" (Metric: {a['metric']})"
        parts.append("Achievement: " + line)
    if e.get("skills_used"):
        parts.append("Skills used: " + ", ".join(e["skills_used"]) + ".")
    if e.get("tags"):
        parts.append("Tags: " + ", ".join(e["tags"]) + ".")
    return " ".join(parts)


def render_education(e: dict) -> str:
    parts = [
        f"Education: {e['degree']} in {e.get('field_of_study', 'N/A')} "
        f"from {e['institution']} ({e.get('start_date', '?')} to {e.get('end_date', '?')})."
    ]
    if e.get("honors"):
        parts.append("Honors: " + ", ".join(e["honors"]) + ".")
    if e.get("relevant_coursework"):
        parts.append("Relevant coursework: " + ", ".join(e["relevant_coursework"]) + ".")
    return " ".join(parts)


def render_project(e: dict) -> str:
    parts = [f"Project: {e['name']}."]
    if e.get("role"):
        parts.append(f"Role: {e['role']}.")
    if e.get("description"):
        parts.append(e["description"])
    if e.get("tech_stack"):
        parts.append("Tech stack: " + ", ".join(e["tech_stack"]) + ".")
    if e.get("outcomes"):
        parts.append("Outcomes: " + "; ".join(e["outcomes"]) + ".")
    return " ".join(parts)


def render_certification(e: dict) -> str:
    parts = [f"Certification: {e['name']}"]
    if e.get("issuer"):
        parts[-1] += f", issued by {e['issuer']}"
    parts[-1] += "."
    if e.get("date_earned"):
        parts.append(f"Earned: {e['date_earned']}.")
    if e.get("expiry_date"):
        parts.append(f"Expires: {e['expiry_date']}.")
    return " ".join(parts)


def render_job_posting(e: dict) -> str:
    parts = [f"Target job posting: {e['title']} at {e['company']}."]
    if e.get("required_skills"):
        parts.append("Required skills: " + ", ".join(e["required_skills"]) + ".")
    parts.append(e["raw_description"])
    return " ".join(parts)


RENDERERS = {
    "skill": render_skill,
    "experience": render_experience,
    "education": render_education,
    "project": render_project,
    "certification": render_certification,
    "job_posting": render_job_posting,
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_entities(entity_type: str, path: Path) -> list[dict]:
    """Load + validate a JSON file that contains a list of entities of one type."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = [raw]
    model = ENTITY_MODELS[entity_type]
    validated = []
    for item in raw:
        obj = model(**item)  # raises pydantic.ValidationError on bad data
        validated.append(obj.model_dump())
    return validated


def content_hash(entity: dict) -> str:
    canonical = json.dumps(entity, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Main ingestion routine
# ---------------------------------------------------------------------------
def get_collection():
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(config.COLLECTION_NAME)


def ingest_all(verbose: bool = True) -> dict[str, int]:
    manifest = Manifest()
    collection = get_collection()

    stats = {"added": 0, "updated": 0, "unchanged": 0, "deleted": 0}

    def process(entity_type: str, entities: Iterable[dict], source_file: str):
        current_doc_ids = set()
        for entity in entities:
            doc_id = f"{entity_type}:{entity['id']}"
            current_doc_ids.add(doc_id)
            new_hash = content_hash(entity)
            old_hash = manifest.get_hash(doc_id)

            if old_hash == new_hash:
                stats["unchanged"] += 1
                continue

            text = RENDERERS[entity_type](entity)
            vector = embed_text(text)
            metadata = {
                "entity_type": entity_type,
                "entity_id": entity["id"],
                "source_file": source_file,
                "title": entity.get("name") or entity.get("title") or entity.get("degree") or entity["id"],
                "tags": ",".join(entity.get("tags", [])) if entity.get("tags") else "",
            }
            collection.upsert(ids=[doc_id], embeddings=[vector], documents=[text], metadatas=[metadata])
            manifest.upsert(doc_id, entity_type, entity["id"], source_file, new_hash)

            stats["added" if old_hash is None else "updated"] += 1

        # delete vectors for entities removed from the source file
        stale = manifest.doc_ids_for_type(entity_type) - current_doc_ids
        for doc_id in stale:
            collection.delete(ids=[doc_id])
            manifest.delete(doc_id)
            stats["deleted"] += 1

    for entity_type, path in config.ENTITY_FILES.items():
        process(entity_type, load_entities(entity_type, path), path.name)

    # Job postings are never embedded (see module docstring) — clean up any
    # that were indexed by an earlier version of this script.
    stale_job_postings = manifest.doc_ids_for_type("job_posting")
    for doc_id in stale_job_postings:
        collection.delete(ids=[doc_id])
        manifest.delete(doc_id)
        stats["deleted"] += 1

    if verbose:
        print("Ingestion complete:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print("Indexed totals by type:", manifest.counts())

    return stats


if __name__ == "__main__":
    ingest_all()
