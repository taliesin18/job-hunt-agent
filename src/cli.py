"""
CLI for the local job-hunt RAG agent.

Examples:
    python -m src.cli ingest
    python -m src.cli status
    python -m src.cli ask "What experience do I have leading teams?"
    python -m src.cli ask "What Python projects have I built?" --type project --k 3
    python -m src.cli tailor-resume data/job_postings/example_job.json
    python -m src.cli gap-analysis data/job_postings/example_job.json
    python -m src.cli apply job_description.txt
    python -m src.cli apply "https://example.com/careers/backend-engineer"
    python -m src.cli apply job_description.txt --resume my_current_resume.txt --output-dir out/
    python -m src.cli apply job_description.txt --yes    # skip prompts, generate both automatically
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .ingest import ingest_all, Manifest
from .rag_query import ask, tailor_resume, gap_analysis, load_job_posting
from .orchestrator import run_matching, generate_resume_and_cover_letter, CONFIDENCE_THRESHOLD
from .agents.matcher import match_job
from .agents.docx_resume_writer import fill_resume_docx
from .agents.xlsx_resume_writer import fill_resume_xlsx


def cmd_ingest(args):
    ingest_all(verbose=True)


def cmd_status(args):
    manifest = Manifest()
    counts = manifest.counts()
    if not counts:
        print("Nothing indexed yet. Run: python -m src.cli ingest")
        return
    print("Indexed entities by type:")
    for entity_type, count in counts.items():
        print(f"  {entity_type}: {count}")


def cmd_ask(args):
    result = ask(args.query, k=args.k, entity_type=args.type)
    print("\n=== Answer ===\n")
    print(result["answer"])
    if args.show_context:
        print("\n=== Retrieved context ===\n")
        print(result["context"])


def cmd_tailor_resume(args):
    print(tailor_resume(args.job_file))


def cmd_gap_analysis(args):
    print(gap_analysis(args.job_file))


def _confirm(question: str) -> bool:
    while True:
        answer = input(f"{question} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def cmd_apply(args):
    # job_source can be a path to a text file, an http(s) URL, or raw pasted text
    path = Path(args.job_source)
    source = path.read_text(encoding="utf-8") if path.exists() else args.job_source

    match_result = run_matching(source)
    job = match_result["job"]

    print(f"\n=== Parsed job: {job['title']} at {job['company']} ===")
    if match_result["saved"]:
        print(f"Saved to: {config.JOB_POSTINGS_DIR / (job['id'] + '.json')}")
    else:
        print("Not saved — confidence is below the threshold (see below).")

    print("\n=== Match report ===\n")
    print(match_result["match_report"])
    confidence_note = "" if match_result["confidence_detected"] else " (not detected in model output, defaulted)"
    print(f"\nConfidence: {match_result['confidence']}/100{confidence_note}")

    if match_result["below_threshold"] and not args.confidence_skip:
        print(
            f"\nConfidence is below the threshold ({CONFIDENCE_THRESHOLD}) — stopping here.\n"
            "Re-run with --confidence-skip to be asked about resume/cover letter anyway."
        )
        return

    if args.yes:
        want_resume, want_cover_letter = True, True
    else:
        want_resume = _confirm("\nGenerate a tailored resume for this job?")
        want_cover_letter = _confirm("Generate a cover letter for this job?")

    if not want_resume and not want_cover_letter:
        print("\nNothing else to generate.")
        return

    generated = generate_resume_and_cover_letter(
        job,
        match_report=match_result["match_report"],
        want_resume=want_resume,
        want_cover_letter=want_cover_letter,
        existing_resume_path=args.resume,
    )

    if want_resume:
        print("\n=== Tailored resume ===\n")
        print(generated["resume"])

    if want_cover_letter:
        print("\n=== Cover letter ===\n")
        print(generated["cover_letter"])

    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{job['id']}_match_report.md").write_text(match_result["match_report"], encoding="utf-8")
        if want_resume:
            (out_dir / f"{job['id']}_resume.md").write_text(generated["resume"], encoding="utf-8")
        if want_cover_letter:
            (out_dir / f"{job['id']}_cover_letter.md").write_text(generated["cover_letter"], encoding="utf-8")
        print(f"\nSaved outputs to {out_dir}/")


def cmd_fill_resume_docx(args):
    job = load_job_posting(args.job_file)

    match_report = ""
    if args.with_match_report:
        match_result = match_job(job)
        match_report = match_result["report"]
        note = "" if match_result["confidence_detected"] else " (not detected, defaulted)"
        print(f"Match confidence: {match_result['confidence']}/100{note}\n")

    result = fill_resume_docx(
        args.template, args.output, job, match_report=match_report
    )

    print(f"Filled fields: {', '.join(result['filled']) or '(none)'}")
    if result["not_provided"]:
        print(f"Warning — template tokens the model left unfilled: {', '.join(result['not_provided'])}")
    if result["not_found_in_doc"]:
        print(f"Warning — model returned fields not found in the template: {', '.join(result['not_found_in_doc'])}")
    for w in result.get("warnings", []):
        print(f"Warning — {w}")
    print(f"\nSaved: {result['output_path']}")


def cmd_fill_resume_xlsx(args):
    job = load_job_posting(args.job_file)

    match_report = ""
    if args.with_match_report:
        match_result = match_job(job)
        match_report = match_result["report"]
        note = "" if match_result["confidence_detected"] else " (not detected, defaulted)"
        print(f"Match confidence: {match_result['confidence']}/100{note}\n")

    result = fill_resume_xlsx(
        args.template, args.output, job,
        match_report=match_report,
        csv_path=args.csv, export_pdf=args.pdf,
    )

    print(f"Filled fields: {', '.join(result['filled']) or '(none)'}")
    if result["not_provided"]:
        print(f"Warning — Data sheet fields the model left unfilled: {', '.join(result['not_provided'])}")
    if result["not_found_in_sheet"]:
        print(f"Warning — model returned fields not found in the Data sheet: {', '.join(result['not_found_in_sheet'])}")
    for w in result.get("warnings", []):
        print(f"Warning — {w}")
    print(f"\nSaved: {result['output_path']}")
    if "csv_path" in result:
        print(f"CSV written: {result['csv_path']}")
    if "pdf_path" in result:
        print(f"PDF exported: {result['pdf_path']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-hunt-agent",
        description="Local, offline RAG agent over your career data (Ollama + ChromaDB).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="(Re-)index data/*.json into the vector store")
    p_ingest.set_defaults(func=cmd_ingest)

    p_status = sub.add_parser("status", help="Show how many entities are currently indexed")
    p_status.set_defaults(func=cmd_status)

    p_ask = sub.add_parser("ask", help="Ask a question grounded in your career data")
    p_ask.add_argument("query", type=str)
    p_ask.add_argument("--k", type=int, default=5, help="Number of chunks to retrieve")
    p_ask.add_argument(
        "--type", type=str, default=None,
        choices=["skill", "experience", "education", "project", "certification"],
        help="Restrict retrieval to one entity type",
    )
    p_ask.add_argument("--show-context", action="store_true", help="Print retrieved chunks too")
    p_ask.set_defaults(func=cmd_ask)

    p_tailor = sub.add_parser("tailor-resume", help="Draft tailored resume bullets for a job posting")
    p_tailor.add_argument("job_file", type=str, help="Path, or filename under data/job_postings/")
    p_tailor.set_defaults(func=cmd_tailor_resume)

    p_gap = sub.add_parser("gap-analysis", help="Compare your skills against a job posting")
    p_gap.add_argument("job_file", type=str, help="Path, or filename under data/job_postings/")
    p_gap.set_defaults(func=cmd_gap_analysis)

    p_apply = sub.add_parser(
        "apply",
        help="Fetch/parse -> match a job, then ask before generating a resume and/or cover letter",
    )
    p_apply.add_argument(
        "job_source", type=str,
        help="Path to a text file, an http(s) URL, or raw pasted job description text",
    )
    p_apply.add_argument(
        "--resume", type=str, default=None,
        help="Path to an existing resume draft to fix instead of drafting fresh bullets",
    )
    p_apply.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to save the match report, resume, and cover letter as .md files",
    )
    p_apply.add_argument(
        "--confidence-skip", action="store_true",
        help="Still be asked about resume/cover letter even if match confidence is low "
             "(by default, low confidence stops the pipeline right after the match report)",
    )
    p_apply.add_argument(
        "--yes", action="store_true",
        help="Skip the interactive prompts and generate both a resume and a cover letter "
             "automatically (old always-run-everything behavior — useful for scripting)",
    )
    p_apply.set_defaults(func=cmd_apply)

    p_docx = sub.add_parser(
        "fill-resume-docx",
        help="Fill a placeholder-tagged Word resume template for a specific job, preserving formatting",
    )
    p_docx.add_argument("template", type=str, help="Path to your .docx resume template with {{PLACEHOLDER}} tokens")
    p_docx.add_argument("output", type=str, help="Path to save the filled .docx")
    p_docx.add_argument("job_file", type=str, help="Path, or filename under data/job_postings/")
    p_docx.add_argument(
        "--with-match-report", action="store_true",
        help="Run the job matcher first and use its report to inform which facts to emphasize",
    )
    p_docx.set_defaults(func=cmd_fill_resume_docx)

    p_xlsx = sub.add_parser(
        "fill-resume-xlsx",
        help="Fill the Data sheet of an Excel resume template for a specific job, then optionally export a PDF",
    )
    p_xlsx.add_argument("template", type=str, help="Path to your .xlsx resume template with a 'Data' sheet")
    p_xlsx.add_argument("output", type=str, help="Path to save the filled .xlsx")
    p_xlsx.add_argument("job_file", type=str, help="Path, or filename under data/job_postings/")
    p_xlsx.add_argument(
        "--with-match-report", action="store_true",
        help="Run the job matcher first and use its report to inform which facts to emphasize",
    )
    p_xlsx.add_argument(
        "--csv", type=str, default=None,
        help="Also write the field/value pairs to this CSV path",
    )
    p_xlsx.add_argument(
        "--pdf", action="store_true",
        help="Also export the filled workbook to PDF (via LibreOffice), respecting the Resume sheet's print area",
    )
    p_xlsx.set_defaults(func=cmd_fill_resume_xlsx)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
