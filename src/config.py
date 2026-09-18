"""
Central configuration for the local job-hunt RAG agent.
Everything here is local / free — no API keys required.
"""
import os
from pathlib import Path

# --- Project layout -----------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOB_POSTINGS_DIR = DATA_DIR / "job_postings"
INDEX_DIR = PROJECT_ROOT / "index"
CHROMA_DIR = INDEX_DIR / "chroma_db"
MANIFEST_DB_PATH = INDEX_DIR / "manifest.sqlite"

# --- Ollama ---------------------------------------------------------------
# The local default keeps the existing non-Docker workflow unchanged. Docker
# Compose overrides this with host.docker.internal so the API container can
# reach Ollama running on the Windows host.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
GEN_MODEL = "qwen3:8b"          # `ollama pull qwen3:8b`
EMBED_MODEL = "nomic-embed-text"   # `ollama pull nomic-embed-text`

# How long to wait for a single Ollama response before giving up. Local
# inference speed varies a lot by hardware — raise this if you're on a
# modest GPU/CPU and see ReadTimeoutError, especially for multi-field
# tasks (fill-resume-docx / fill-resume-xlsx) which generate more output
# in one call than a simple question does.
REQUEST_TIMEOUT_SECONDS = 300

# Some models (the Qwen3 family) default to a "thinking" mode that
# generates a hidden chain-of-thought reasoning block before the actual
# answer — often doubling or tripling response time, which matters a lot
# for structured extraction/fill tasks that don't need deep reasoning.
# This is passed on every request; models that don't support thinking
# (Llama, Mistral, etc.) simply ignore the field.
DISABLE_THINKING_MODE = True

# --- Chroma -----------------------------------------------------------
COLLECTION_NAME = "career_profile"

# --- Data files (single-object or list-of-objects JSON) ------------------
ENTITY_FILES = {
    "skill": DATA_DIR / "skills.json",
    "experience": DATA_DIR / "experience.json",
    "education": DATA_DIR / "education.json",
    "project": DATA_DIR / "projects.json",
    "certification": DATA_DIR / "certifications.json",
}
PROFILE_FILE = DATA_DIR / "profile.json"

# The candidate's actual resume, used as a structural template: resume
# tailoring rewrites content WITHIN this format (summary, skills line,
# bullets per job) rather than collapsing to a bare bullet list. Optional —
# if this file doesn't exist, fix_resume() falls back to writing plain
# tailored bullets instead of a full formatted resume.
CURRENT_RESUME_PATH = DATA_DIR / "resume" / "current_resume.txt"

INDEX_DIR.mkdir(parents=True, exist_ok=True)
