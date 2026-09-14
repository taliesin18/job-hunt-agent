"""
Xlsx resume writer agent.

Simpler alternative to the docx placeholder approach: fills the "Data"
sheet of an Excel workbook (one row per field) with content grounded
in the candidate's indexed facts, tailored to a specific job. A
"Resume" sheet holds a printable layout whose cells are formulas
referencing the Data sheet — Excel's own formula engine handles
"don't break the formatting," so there's no run-splitting logic here
at all, unlike docx_tools.py.

Each field is sent to the LLM together with its CURRENT text (still
sitting in the Data sheet, never blanked out) so the model has a
concrete anchor for which job/topic that field belongs to — this is
what prevents content from one job getting swapped into another job's
field, which bare field names alone don't protect against.

Also writes a plain field,value CSV alongside the workbook, and can
export the workbook straight to PDF via LibreOffice, which respects
the Resume sheet's print area.
"""
from __future__ import annotations

from pathlib import Path

from ..field_filler import generate_field_values
from ..xlsx_tools import read_data_fields, read_data_field_values, write_data_values, export_to_csv, convert_to_pdf


def fill_resume_xlsx(
    template_path: str,
    output_path: str,
    job: dict,
    match_report: str = "",
    csv_path: str | None = None,
    export_pdf: bool = False,
) -> dict:
    """
    Reads field names (and their current text) from the Data sheet, asks
    the LLM to fill each one using the candidate's complete history
    tailored to `job`, writes a new workbook to output_path with only
    the Data sheet's values changed, and optionally writes a CSV /
    exports a PDF.

    Returns the report from xlsx_tools.write_data_values, plus
    output_path, csv_path (if written), pdf_path (if exported), and
    warnings (list[str] — any values that may contain a fabricated
    number, worth a manual look before you send the resume anywhere).
    """
    fields = read_data_fields(template_path)
    if not fields:
        raise ValueError(
            f"No fields found in the Data sheet of {template_path}. "
            "Column A (below the header row) should list one field name per row."
        )
    current_values = read_data_field_values(template_path)

    values, warnings = generate_field_values(
        fields, job, match_report=match_report, field_context=current_values
    )

    result = write_data_values(template_path, values, output_path)
    result["output_path"] = output_path
    result["warnings"] = warnings

    if csv_path:
        export_to_csv(values, csv_path)
        result["csv_path"] = csv_path

    if export_pdf:
        pdf_path = convert_to_pdf(output_path, output_dir=str(Path(output_path).parent))
        result["pdf_path"] = pdf_path

    return result
