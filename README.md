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
and a browser frontend that calls it. No logic is reimplemented — every
endpoint just calls a function the CLI already uses.

**Frontend files** — split by concern so each is easy to edit on its own:
- `job-hunt-frontend.html` — structure/markup only
- `job-hunt-frontend.css` — all styling (the glass theme, light/dark tokens)
- `job-hunt-frontend.js` — all behavior (tab switching, API calls, the
  match-map charts, the markdown renderer)

**Color palettes.** A dropdown in the header (next to the light/dark toggle)
switches between three glass palettes, each with its own light and dark
variant:
- **Aurora** (default) — indigo/pink/green/blue pastel gradient
- **Noir Green** — black/gray/green
- **Cyber Teal** — teal/gray/black

Every palette's muted text color was chosen by actually computing WCAG
contrast ratios against the translucent panel composited over each gradient
stop (not just eyeballing it) — worst case across all three palettes and
both light/dark modes is 5.02:1, comfortably above the 4.5:1 minimum for
body text. The original Aurora palette's `--fg-muted` was corrected the same
way after review — it was measured at 3.30:1 in dark mode in one gradient
position, a real WCAG 1.4.3 failure, not just a theoretical one.

**Accessibility.** The Kanban board, modal, and tab navigation were rebuilt
for keyboard and screen-reader use, following an accessibility review:
- Kanban cards are keyboard-focusable (`tabindex`, `role="button"`,
  Enter/Space to open) and each also has its own status `<select>` — a
  non-drag way to change status, needed both for keyboard users and anyone
  who finds dragging error-prone (WCAG 2.5.7).
- The job detail modal traps Tab within itself while open, moves focus in
  on open and back to the triggering card on close, and closes on Escape
  (`role="dialog"`, `aria-modal="true"`).
- Tabs use the real ARIA tabs pattern (`role="tablist"/"tab"/"tabpanel"`,
  `aria-selected`), and switching tabs moves focus to the new panel's
  heading so a screen reader announces the change.
- Status/error messages are in `aria-live="polite"` regions, with
  `role="alert"` added specifically for errors.
- `jobInput`, `askInput`, `apiUrlInput`, and `askType` all have real
  (visually-hidden where not wanted visibly) `<label>`s instead of relying
  on placeholder text alone.
- The two match-map scatter charts have distinct `aria-label`s (previously
  one generic label shared by both) plus a visually-hidden data table
  listing the same strong/partial/gap items the dots represent, since a
  hover-only `<title>` reaches mouse users only.

Not fully covered: color contrast could only be verified by computing exact
composite colors mathematically (see above), not by rendering — if you
customize a palette's gradient or panel opacity, re-check contrast rather
than assuming it still passes. Touch target sizes look fine from the CSS
but weren't confirmed against a live render either.

**Run the API:**

```bash
uvicorn src.api:app --reload --port 8000
```

### Run with Docker Desktop

Docker Desktop can run the API and browser frontend together, without
activating the Python virtual environment. This first containerized setup
continues to use Ollama installed on your Windows host, so start Ollama and
make sure the configured models are already available before starting the
stack.

```bash
docker compose up --build -d
```

Then open [http://localhost:8080](http://localhost:8080). The dashboard
proxies its API calls privately to the API container, so Docker does not use
or expose host port 8000. Stop any locally running Uvicorn instance before
using this Docker stack: both instances can access the same mounted `data/`
and `index/` folders, and should not write to them concurrently.

Your private `data/`, `index/`, and `out/` folders are mounted from the
project directory rather than copied into an image. Rebuilding or removing
the containers therefore does not remove your profile, saved postings, RAG
index, or generated materials.

Useful commands:

```bash
# See API startup errors or Ollama connection failures
docker compose logs --follow job-hunt-api

# Stop the containers; your mounted data remains intact
docker compose down
```

By default the Docker API uses `http://host.docker.internal:11434` to reach
Ollama on the Windows host. If you later host Ollama elsewhere, create an
uncommitted `.env` file beside `compose.yaml` with, for example:

```bash
OLLAMA_HOST=http://your-ollama-host:11434
```

The usual local development command above remains supported: outside Docker,
the API still defaults to `http://localhost:11434` for Ollama.

**Open the frontend:** double-click `job-hunt-frontend.html` to open it in
your browser (or drag it into a browser window). No build step, no server
needed for the frontend itself — but keep all three files in the same
folder, since the HTML references the other two by relative filename
(`<link href="job-hunt-frontend.css">`, `<script src="job-hunt-frontend.js">`).
Browsers load sibling files like this fine from a plain `file://` page, same
as when it was one file.

**Important:** this only works when the HTML file is opened directly in
your own browser. If you're viewing it inside Claude's chat preview instead,
the fetch calls will fail — Claude's sandboxed preview (and browsers in
general) block a hosted page from reaching into your local network. Download
all three files (not just the HTML) and open the HTML as a local file for
the live functionality.

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
- **Job postings** — a Kanban board, one column per status: Saved,
  Application Sent / Waiting, Initial Interview, Rejected, Failed. A job
  only lands here at all if its match confidence meets the threshold (50 by
  default) — a weak match is reported on the Match tab but never saved to
  `data/job_postings/`, so this board only fills with roles worth tracking.
  Drag a card to a different column to update its status (persisted
  immediately via `PATCH /api/job-postings/{id}`), or click a card to open
  its detail view: the generated resume and cover letter for that job (if
  you've generated them — see below), a status dropdown as an alternative
  to dragging, and a button to jump back to the Match tab and re-match it
  without re-parsing (it's already structured).
- **Knowledge base** — indexed entity counts and a "Re-index now" button.
  This only affects the Ask tab's retrieval — Match/resume/cover-letter read
  `data/*.json` directly and don't need indexing at all.

**Generated resume/cover letter persistence.** When you click "Generate
resume" or "Generate cover letter" on the Match tab for a job that was
saved (high enough confidence), the result is automatically written onto
that job's JSON file (`resume_text` / `cover_letter_text` fields) via a
`PATCH` call — that's what the Job Postings board's card modal shows when
you open a ticket later. For a match that wasn't saved (below threshold),
generation still works, but nothing is persisted — there's no saved record
to attach it to.

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
