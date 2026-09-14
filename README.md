# Local Job-Hunt RAG Agent

Fully local, zero-cost RAG agent over your own career data. See
`job-hunt-rag-agent-spec.md` for the full architecture/data spec this
code implements.

## 1. One-time setup

```bash
# 1. Install Ollama (if you haven't): https://ollama.com/download
# 2. Pull the models this project uses (both free, run locally)
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 3. Make sure the Ollama server is running (it usually auto-starts;
#    if not, run this in its own terminal):
ollama serve
```

```bash
# 4. Create and activate a virtual environment inside this project folder
cd job-hunt-agent
python3 -m venv venv

# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# 5. Install Python dependencies into the venv
pip install -r requirements.txt
```

## 2. Fill in your real data

Edit the files in `data/`:
- `profile.json`
- `skills.json`
- `experience.json`
- `education.json`
- `projects.json`
- `certifications.json`
- `job_postings/*.json` — one file per job you're targeting (copy `example_job.json`)
- `current_resume.txt` *(optional)* — your actual resume as plain text. When
  present, `fix_resume()` (used by `apply`, `tailor-resume`, and the
  `/api/resume` endpoint) revises THIS resume in place for each job — same
  sections, same job titles/companies/dates, only the summary/skills-line/
  bullets get tailored. Without this file, resume generation falls back to
  writing a plain list of tailored bullets instead of a full resume.

**Note:** files in `job_postings/` are read directly by the agents (fetcher,
matcher, resume-fixer, cover-letter) when you point a command at them — they
are never embedded into the vector store by `ingest`. A job posting describes
a role you're applying to, not a fact about you, so keeping it out of the same
collection as your real skills/experience avoids it ever being retrieved and
mistaken for your own work history.

Each file's shape is documented in `job-hunt-rag-agent-spec.md`. Keep the
`id` fields unique within each file (e.g. `skl_001`, `skl_002`, ...) —
that's how the agent tracks updates and deletions.

## 3. Index your data

Run this after every edit to `data/` (it only re-embeds what changed):

```bash
python -m src.cli ingest
```

Check what's indexed:

```bash
python -m src.cli status
```

## 4. Use it

```bash
# Ask a free-form question grounded in your own data
python -m src.cli ask "What experience do I have leading teams?"

# Restrict retrieval to one entity type
python -m src.cli ask "What Python projects have I built?" --type project --k 3

# See the retrieved chunks alongside the answer
python -m src.cli ask "Tell me about my education" --show-context

# Draft resume bullets tailored to a saved job posting
python -m src.cli tailor-resume data/job_postings/example_job.json

# Compare your skills against a job posting's requirements
python -m src.cli gap-analysis data/job_postings/example_job.json

# Match a job, then get asked before generating a resume and/or cover letter
python -m src.cli apply job_description.txt
python -m src.cli apply "https://example.com/careers/backend-engineer"
python -m src.cli apply job_description.txt --resume my_current_resume.txt --output-dir out/
python -m src.cli apply job_description.txt --yes    # skip prompts, generate both automatically
```

## 5. Multi-agent pipeline (`apply`)

`apply` always runs the fetcher and matcher, then asks before running
either of the two slower generation steps — each with its own system
prompt (`src/agents/`):

1. **Fetcher/parser** (`fetcher.py`) — accepts a path to a text file, a URL,
   or raw pasted text; extracts company, title, and required skills into
   the `JobPosting` schema, and saves it to `data/job_postings/`.
2. **Job matcher** (`matcher.py`) — compares the job against your COMPLETE
   skills/experience history (see `full_context.py` — not a retrieved
   subset) and reports strong matches, partial matches, and real gaps,
   plus a confidence score. Always runs.
3. **Resume fixer** (`resume_fixer.py`) — if `data/current_resume.txt`
   exists, revises it in place for this job (same sections/jobs/dates,
   tailored summary/skills/bullets); otherwise writes plain tailored
   bullets. Pass `--resume <path>` to use a different base resume instead
   of the default. You're asked "Generate a tailored resume for this job?
   [y/n]" before this runs.
4. **Cover letter** (`cover_letter.py`) — drafts a short, specific cover
   letter using the same complete history and the matcher's report. You're
   asked separately, so you can generate just one, both, or neither.

Answering "n" to a step skips that LLM call entirely — it's not generated
and discarded, since local inference is slow enough that you don't want to
pay for output you didn't ask for. Pass `--yes` to skip both prompts and
always generate both, matching the old fully-automatic behavior (useful
for scripting).

`src/orchestrator.py` splits this into `run_matching()` (fetch + match)
and `generate_resume_and_cover_letter()` (independently toggleable) so the
CLI can ask between them; `run_pipeline()` remains as a non-interactive
wrapper around both for any code that wants the old one-call behavior.

**Why full context instead of RAG retrieval for these three agents:**
your entire skills/experience history renders to roughly 2,000 tokens —
small enough to just include all of it in every prompt, rather than
searching for a semantically-similar top-k subset. This avoids a real
failure mode retrieval has at this data size: under-representing a
skill or achievement that's genuinely relevant but doesn't use similar
wording to the job description. `ask()` (free-form Q&A, in `rag_query.py`)
still uses retrieval — that's a different use case where scoping to the
most relevant facts is actually useful, and stays sensible as your data
grows.

Gating: the matcher returns a 0-100 confidence score. If it's below 50,
`apply` stops after the match report without even asking — no point
prompting about a resume/cover letter for a role your own data says is a
weak fit. Pass `--confidence-skip` to be asked anyway.

## 6. Local API + browser frontend

For a GUI instead of the CLI, there's a small FastAPI wrapper (`src/api.py`)
and a standalone HTML frontend (`job-hunt-frontend.html`) that calls it.
No logic is reimplemented — every endpoint just calls a function the CLI
already uses.

**Run the API:**

```bash
uvicorn src.api:app --reload --port 8000
```

**Open the frontend:** double-click `job-hunt-frontend.html` to open it in
your browser (or drag it into a browser window). It's a single self-contained
file — no build step, no server needed for the frontend itself.

**Important:** this only works when the HTML file is opened directly in
your own browser. If you're viewing it inside Claude's chat preview instead,
the fetch calls will fail — Claude's sandboxed preview (and browsers in
general) block a hosted page from reaching into your local network. Download
the file and open it as a local file for the live functionality.

**Layout:** a glass UI (frosted translucent panels over a soft gradient
background) with a light/dark toggle (top right — follows your system
preference by default) and four tabs, styled as a floating glass segmented
control rather than one linear flow — jump to whichever you need:

- **Match** — paste a job description (or a URL) → match report + confidence
  badge → two auto-generated **match maps** (scatter charts, one for skills,
  one for experience — see below) → independent "Generate resume" /
  "Generate cover letter" buttons, each its own request, so you only wait
  for what you actually want (mirroring the CLI's y/n prompts as buttons
  instead of a terminal). If confidence is low, a caution banner appears but
  nothing is blocked — you decide whether to generate anyway. The resume
  button revises `data/current_resume.txt` in place, same as the CLI.
- **Ask** — free-form Q&A against your indexed data, with an optional
  entity-type filter. Built for recruitment-page screening questions
  ("Describe your experience with X") as much as open-ended ones — answers
  come with a "Copy" button and an optional "Show retrieved context" toggle
  so you can sanity-check what it was grounded in before pasting an answer
  somewhere.
- **Job postings** — every job you've matched before (`data/job_postings/`),
  newest first. Clicking "Match" on one re-runs the matcher without
  re-parsing it through the fetcher agent again (it's already structured),
  and jumps you to the Match tab with the result.
- **Knowledge base** — indexed entity counts and a "Re-index now" button.
  This only affects the Ask tab's retrieval — Match/resume/cover-letter read
  `data/*.json` directly and don't need indexing at all.

**Match maps — a real limitation worth knowing.** `/api/match` only returns
prose (the matcher's "Strong matches / Partial matches / Gaps" write-up) —
there's no structured per-skill or per-job score to plot. The two scatter
charts are built entirely client-side: the report text is split into its
three sections, each split further into individual items (bullets if
present, sentence/comma splitting otherwise), then each item is checked for
a literal (word-boundary) match against your actual skill names and job
titles/companies — fetched read-only from the new `/api/profile-data`
endpoint — to decide which chart it belongs on. This works well for items
that name a specific skill or employer, but a bullet describing only a
*responsibility* ("Led AMS operations...") with no literal name match gets
dropped rather than guessed at. The report text above the charts is always
the source of truth; the charts are a visual aid, not a re-analysis.

CORS is wide open on the API (`allow_origins=["*"]`) since this is a
single-user local tool, not a public service.

## 6. Editing your real Word resume (`fill-resume-docx`)

This fills a Word document in place **without breaking its formatting** —
fonts, bold job titles, bullet styles, and tables are all left untouched.
It works by tagging your real resume once with placeholder tokens, then
only ever replacing the text inside those tokens.

**Setup (one time):** open your actual resume `.docx` and replace the
parts you want tailored per job with tokens like:

```
{{SUMMARY}}

Acme Corp — Backend Engineer
• {{EXP1_BULLET1}}
• {{EXP1_BULLET2}}
```

Token names are up to you — the tool auto-detects whatever `{{TOKENS}}`
it finds. Keep them `UPPERCASE_WITH_UNDERSCORES`.

**Run it:**

```bash
python -m src.cli fill-resume-docx my_resume_template.docx tailored_resume.docx data/job_postings/example_job.json

# include the job matcher's report so the LLM knows what to emphasize
python -m src.cli fill-resume-docx my_resume_template.docx tailored_resume.docx data/job_postings/example_job.json --with-match-report
```

This never modifies your template — it always writes a new file at the
output path you give it. If the model returns a field name that doesn't
match a token in your document (or leaves a token unfilled), you'll see
a warning printed so you notice instead of silently getting a half-filled
document.

**Why this is safe:** Word stores each paragraph as a sequence of "runs,"
each with its own formatting. A naive approach (`paragraph.text = ...`)
destroys every run and replaces the whole paragraph with one plain-text
run — that's what breaks formatting. This tool instead finds exactly
which run(s) a token spans and only changes `run.text` on those,
leaving every other character's font, bold, and style untouched — even
when Word has split a single token across multiple runs internally,
which happens more often than you'd expect.

## 7. Editing a resume in Excel instead (`fill-resume-xlsx`) — simpler alternative

If the Word placeholder approach feels fiddly, this does the same job with
far less that can go wrong, because Excel's own formula engine — not
custom run-splitting code — is what keeps the formatting intact.

**How the template works:** the workbook has two sheets:
- **Data** (hidden by default, right-click a sheet tab → Unhide to see it) —
  one row per field: column A is the field name, column B is its current
  text. This is the *only* thing the tool ever writes to.
- **Resume** — the printable layout, with a defined print area sized to fit
  one page. Its cells are formulas like `=Data!B5` — nothing here is ever
  touched by the tool; Excel recalculates the display automatically.

**Run it:**

```bash
python -m src.cli fill-resume-xlsx my_resume_template.xlsx tailored_resume.xlsx data/job_postings/example_job.json --with-match-report

# also write a plain field/value CSV, and export straight to PDF
python -m src.cli fill-resume-xlsx my_resume_template.xlsx tailored_resume.xlsx data/job_postings/example_job.json --csv tailored_resume.csv --pdf
```

`--pdf` shells out to LibreOffice (`soffice`) to export a PDF that respects
the Resume sheet's print area — install LibreOffice (free) for this, or
skip the flag and just open `tailored_resume.xlsx` in Excel and print to
PDF yourself; either way the Data sheet won't appear in the printout since
it's hidden.

**Building your own template:** start from `example_resume_template.xlsx`
(included), or build your own — Data sheet has field names in column A,
Resume sheet has formulas referencing them, print area set on the Resume
sheet. `fill-resume-xlsx` auto-detects whatever field names are in column A,
so add or rename rows freely; no code changes needed.

**Trade-off vs. the Word version:** Excel's formulas make formatting
essentially bulletproof, but you lose Word's richer typography if your
real resume needs it. For a single-page, mostly-plain-text resume, xlsx is
the more robust choice; use docx if you need things Excel can't easily do
(headers/footers, multi-column layouts, embedded images).


## Notes

- Everything runs on your machine — no API keys, no per-token cost.
- `index/chroma_db/` and `index/manifest.sqlite` are generated automatically;
  delete them any time to force a full re-index.
- Every agent is instructed to only use the facts in your `data/` files and
  never invent achievements or metrics — but always review generated
  resume/cover letter text yourself before sending it anywhere.
