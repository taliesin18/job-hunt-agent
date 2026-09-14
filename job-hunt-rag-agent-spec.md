# Local Job-Hunting RAG Agent — Architecture & Data Specification

## 1. Goal

A fully local, zero-cost AI agent that:
- Stores your skills, work history, education, projects, and certifications as structured data
- Automatically ingests new/updated data into a vector store (embeddings) with no manual re-indexing step
- Uses RAG to answer questions like "which experiences show leadership?", tailor a resume/cover letter to a job posting, do gap analysis against a job description, or prep interview answers
- Runs entirely offline — no API keys, no cloud cost

---

## 2. Component Choices

| Layer | Choice | Why |
|---|---|---|
| LLM (generation) | **Ollama** — `llama3.1:8b` or `qwen2.5:7b-instruct` | Free, local, good instruction-following at 8B scale, runs on modest hardware (CPU or small GPU) |
| Embedding model | **Ollama** — `nomic-embed-text` (or `mxbai-embed-large`) | Free, local, purpose-built embedding model, no separate framework needed — one Ollama server handles both generation and embeddings |
| Vector DB | **ChromaDB** | See comparison below |
| Language | **Python 3.11+** | ecosystem fit for both |
| Structured data store | **JSON files** (source of truth) + a lightweight **SQLite manifest** for index tracking | See section 4 |

### ChromaDB vs FAISS — recommendation: **ChromaDB**

Both are free/open-source (Chroma: Apache-2.0, FAISS: MIT), so cost isn't the deciding factor. The difference is what you get out of the box:

- **FAISS** is just a similarity-search *index library*. It has no built-in persistence format for metadata, no filtering-by-field, no document storage — you'd have to hand-build a layer to map vector IDs back to your skills/jobs and to filter by, e.g., "only experience entries" or "only skills tagged Python." That's real work for a personal project.
- **ChromaDB** is a full embedded vector database: it persists to disk automatically, stores documents + metadata + embeddings together, supports metadata filtering (`where={"entity_type": "experience"}`), and upserts (update-if-exists) natively — which you need for automatic re-ingestion. It runs embedded (no server process) for a single-user local setup, exactly like SQLite does for relational data.

FAISS would make sense if you had millions of vectors and needed raw ANN speed. For a personal career-history knowledge base (likely a few hundred to a few thousand chunks), ChromaDB's convenience wins and costs nothing in performance you'd notice.

---

## 3. High-Level Architecture

```
                     ┌─────────────────────────┐
                     │   data/ (JSON files)     │   ← you edit these directly
                     │  profile.json            │
                     │  skills.json             │
                     │  experience.json         │
                     │  education.json          │
                     │  projects.json           │
                     │  certifications.json     │
                     │  job_postings/*.json     │
                     └────────────┬─────────────┘
                                  │ watch / scan
                                  ▼
                     ┌─────────────────────────┐
                     │   Ingestion Pipeline      │
                     │  1. Load & validate JSON  │
                     │  2. Render entity → text  │
                     │  3. Hash content           │
                     │  4. Diff vs manifest.db    │
                     │  5. Embed changed chunks   │
                     │     (Ollama nomic-embed)   │
                     │  6. Upsert into ChromaDB   │
                     └────────────┬─────────────┘
                                  ▼
                     ┌─────────────────────────┐
                     │  ChromaDB (persisted      │
                     │  local dir: ./chroma_db)  │
                     └────────────┬─────────────┘
                                  ▼
                     ┌─────────────────────────┐
                     │   RAG Query Layer         │
                     │  - embed the query         │
                     │  - similarity search       │
                     │    (+ metadata filters)    │
                     │  - build prompt w/ context │
                     │  - Ollama LLM generates    │
                     └────────────┬─────────────┘
                                  ▼
                     Resume tailoring / cover letters /
                     interview prep / job-fit gap analysis
```

---

## 4. Data Specification

### Why JSON files (not a full RDBMS)

You asked for whichever is simpler and scales easily. For this use case:
- Your data volume is small (one person's career) — an RDBMS's main strengths (joins across huge tables, concurrent multi-user writes, complex transactions) aren't needed.
- JSON files are human-editable, diff-friendly in git, and trivial to add new fields to without migrations.
- "Auto-read any input and add it to embeddings" is much simpler against a folder of JSON files than against DB tables — the ingestion script just scans a directory.
- For scale/integrity later, add a **SQLite manifest** (still zero setup, zero cost, single file) that just tracks *what's already been indexed* (content hashes), not your actual career data. This gives you RDBMS-style tracking without giving up JSON's editability for the real content.

If your data ever grows large (e.g., you start batch-importing hundreds of scraped job postings), migrate `job_postings/` into SQLite while keeping your personal profile/skills/experience as JSON — that's the natural scaling path.

### Folder structure

```
job-hunt-agent/
├── data/
│   ├── profile.json
│   ├── skills.json
│   ├── experience.json
│   ├── education.json
│   ├── projects.json
│   ├── certifications.json
│   └── job_postings/
│       ├── 2026-08-28_acme-corp-backend-eng.json
│       └── ...
├── index/
│   ├── manifest.sqlite          # tracks content hashes → indexed/not
│   └── chroma_db/                # ChromaDB persistent store
├── src/
│   ├── ingest.py
│   ├── schemas.py                # pydantic models mirroring this spec
│   ├── rag_query.py
│   └── cli.py
└── requirements.txt
```

### 4.1 `profile.json`

```json
{
  "name": "string",
  "headline": "string (e.g. 'Backend Engineer | Distributed Systems')",
  "location": "string",
  "email": "string",
  "phone": "string",
  "links": {"linkedin": "url", "github": "url", "portfolio": "url"},
  "summary": "string — 2-4 sentence professional summary",
  "target_roles": ["string", "..."],
  "target_industries": ["string", "..."],
  "work_preferences": {"remote": "bool", "relocation": "bool", "salary_range": "string"}
}
```

### 4.2 `skills.json`

```json
[
  {
    "id": "skl_001",
    "name": "Python",
    "category": "technical | soft | tool | language | domain",
    "subcategory": "e.g. 'programming language', 'cloud', 'communication'",
    "proficiency": "beginner | intermediate | advanced | expert",
    "years_experience": 4.5,
    "last_used": "2026-08",
    "related_experience_ids": ["exp_002", "exp_004"],
    "related_project_ids": ["prj_001"],
    "tags": ["backend", "data-processing"],
    "notes": "optional free text — e.g. specific libraries, context of use"
  }
]
```

### 4.3 `experience.json`

```json
[
  {
    "id": "exp_001",
    "company": "string",
    "title": "string",
    "location": "string",
    "employment_type": "full-time | part-time | contract | freelance | internship",
    "start_date": "YYYY-MM",
    "end_date": "YYYY-MM | present",
    "summary": "1-2 sentence role overview",
    "responsibilities": ["string", "..."],
    "achievements": [
      {"description": "string", "metric": "e.g. 'reduced latency 35%'", "skills_used": ["skl_001"]}
    ],
    "skills_used": ["skl_001", "skl_003"],
    "tags": ["leadership", "greenfield", "migration"]
  }
]
```

### 4.4 `education.json`

```json
[
  {
    "id": "edu_001",
    "institution": "string",
    "degree": "string",
    "field_of_study": "string",
    "start_date": "YYYY-MM",
    "end_date": "YYYY-MM",
    "gpa": "optional string/number",
    "honors": ["string"],
    "relevant_coursework": ["string"]
  }
]
```

### 4.5 `projects.json`

```json
[
  {
    "id": "prj_001",
    "name": "string",
    "description": "string",
    "role": "string",
    "start_date": "YYYY-MM",
    "end_date": "YYYY-MM | ongoing",
    "tech_stack": ["string"],
    "outcomes": ["string — quantify where possible"],
    "links": {"repo": "url", "demo": "url"},
    "related_skills": ["skl_001"]
  }
]
```

### 4.6 `certifications.json`

```json
[
  {
    "id": "cert_001",
    "name": "string",
    "issuer": "string",
    "date_earned": "YYYY-MM",
    "expiry_date": "YYYY-MM | null",
    "credential_id": "string",
    "credential_url": "url",
    "related_skills": ["skl_001"]
  }
]
```

### 4.7 `job_postings/*.json` (one file per posting you're targeting)

```json
{
  "id": "job_2026-08-28_acme",
  "company": "string",
  "title": "string",
  "url": "string",
  "date_saved": "YYYY-MM-DD",
  "raw_description": "full pasted job description text",
  "required_skills": ["string, extracted or manual"],
  "status": "saved | applied | interviewing | rejected | offer"
}
```

---

## 5. Ingestion Pipeline Design

**Chunking strategy:** one chunk per entity (one skill = one chunk, one job = one chunk, one achievement can optionally be its own chunk if long). Personal career data is naturally short and self-contained, so entity-level chunking beats arbitrary text splitting — it keeps retrieval results meaningful (e.g., a whole job entry, not half of one).

**Text rendering:** each entity type has a template that turns its JSON into a natural-language paragraph before embedding (embeddings work better on prose than raw JSON keys). Example for an experience entry:

> "Backend Engineer at Acme Corp (2023-01 to present). Led migration of monolith to microservices, reducing deploy time 60%. Responsibilities: designed API contracts, mentored 2 junior engineers. Skills used: Python, Kubernetes, PostgreSQL."

**Change detection (no full re-embedding on every run):**
1. Compute a SHA-256 hash of each entity's canonical JSON.
2. Look up the entity's `id` in `manifest.sqlite` (columns: `entity_id`, `entity_type`, `content_hash`, `chroma_doc_id`, `last_indexed`).
3. If hash matches → skip. If new or changed → render text, embed, upsert into Chroma, update manifest. If an entity's `id` disappears from the JSON file → delete its vector from Chroma and its manifest row.

**Embedding call (Ollama):**
```python
import requests
resp = requests.post("http://localhost:11434/api/embeddings",
    json={"model": "nomic-embed-text", "prompt": rendered_text})
vector = resp.json()["embedding"]
```

**ChromaDB storage:** a single collection, e.g. `career_profile`, with metadata per chunk:

```json
{
  "entity_type": "skill | experience | education | project | certification | job_posting",
  "entity_id": "exp_001",
  "source_file": "experience.json",
  "title": "Backend Engineer @ Acme Corp",
  "start_date": "2023-01",
  "end_date": "present",
  "tags": "leadership,migration"
}
```
(A single collection with `entity_type` metadata filtering is simpler to query than one collection per entity type, and is plenty fast at personal-data scale.)

**Trigger options** (pick one to start; simplest first):
- Manual: run `python src/ingest.py` after editing a JSON file.
- Automatic: watch the `data/` folder with `watchdog` and re-run ingestion on file save.
- Scheduled: cron/task-scheduler re-run daily — useful once you're also dropping in scraped job postings regularly.

---

## 6. Retrieval & Use Cases

| Use case | Retrieval approach |
|---|---|
| Tailor resume bullet points to a job posting | Embed the job posting text → retrieve top-k skills/experience/project chunks → prompt LLM to draft bullets using only retrieved facts |
| Gap analysis ("what am I missing for this role?") | Compare `required_skills` in the job posting against your `skills.json` semantically, not just exact string match |
| Interview prep | Retrieve experience/achievement chunks matching a question topic (e.g., "tell me about a time you led a project") |
| Cover letter draft | Retrieve profile summary + 2-3 most relevant experience/project chunks for the target role |

Always instruct the LLM (in the prompt) to only use retrieved context and not invent achievements/metrics you didn't provide — important for factual accuracy in job applications.

---

## 7. Setup Requirements (all free)

```bash
# Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Python deps
pip install chromadb pydantic requests watchdog
```

---

## 8. Next Steps

This document is the spec/context file. Once you confirm the schema fits how you think about your own career data (feel free to add/rename fields), the next step is the actual code:
- `schemas.py` — pydantic models enforcing this spec
- `ingest.py` — the pipeline in section 5
- `rag_query.py` — retrieval + prompt construction + Ollama generation call
- `cli.py` — simple command-line interface (`ingest`, `ask "..."`, `tailor-resume <job_file>`)

Let me know if you want me to write that code next, and whether you'd like a CLI, a simple local web UI, or both.
