from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject


def fill_1099nec_copy_b(*, template_path: Path, field_values: dict[str, Any]) -> bytes:
    """
    Fill AcroForm fields and force appearance generation so Ghostscript can rasterize them.
    """
    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    # Preserve the template's AcroForm in the output (important for some IRS PDFs)
    acro_ref = reader.trailer["/Root"].get("/AcroForm")
    if acro_ref:
        writer._root_object.update({NameObject("/AcroForm"): acro_ref})

    # Ask renderers to use (or regenerate) appearances
    writer.set_need_appearances_writer()

    # CRITICAL: generates /AP appearance streams when auto_regenerate=True
    for page in writer.pages:
        writer.update_page_form_field_values(page, field_values, auto_regenerate=True)

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()
