"""
Docx resume writer agent.

Fills a placeholder-tagged Word resume template (e.g. {{SUMMARY}},
{{EXP1_BULLET1}}) with content grounded in the candidate's indexed
facts, tailored to a specific job — without touching the document's
existing fonts, bullets, tables, or layout.

You tag your real resume once with tokens for the parts you want
tailored per job; this agent only ever changes the text inside those
tokens (via docx_tools.fill_template). The actual "ask the LLM to fill
these field names" logic lives in field_filler.py, shared with the
xlsx resume writer.
"""
from __future__ import annotations

from ..field_filler import generate_field_values
from ..docx_tools import find_placeholders, fill_template


def fill_resume_docx(
    template_path: str,
    output_path: str,
    job: dict,
    match_report: str = "",
) -> dict:
    """
    Reads {{PLACEHOLDER}} tokens out of template_path, asks the LLM to
    fill each one using the candidate's complete history tailored to
    `job`, then writes a new document to output_path with only those
    tokens' text replaced — formatting untouched.

    Returns the report from docx_tools.fill_template, plus output_path.
    """
    tokens = find_placeholders(template_path)
    plain_fields = [t.strip("{}") for t in tokens]
    if not plain_fields:
        raise ValueError(
            f"No {{{{PLACEHOLDER}}}} tokens found in {template_path}. "
            "Tag the parts of your resume you want tailored per job, "
            "e.g. {{SUMMARY}}, {{EXP1_BULLET1}}."
        )

    replacements, warnings = generate_field_values(plain_fields, job, match_report=match_report)

    result = fill_template(template_path, replacements, output_path)
    result["output_path"] = output_path
    result["warnings"] = warnings
    return result
