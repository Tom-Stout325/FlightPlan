# money/utils/pdf_1099nec.py
from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

from django.conf import settings

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas




# 0-indexed page indexes based on your shell output:
#   Copy 1 = page 2
#   Copy B = page 3
COPY_1_PAGE_INDEX = 2
COPY_B_PAGE_INDEX = 3


@dataclass(frozen=True)
class DrawSpec:
    x: float
    y: float
    size: int = 10


def money_str(v: Optional[Decimal | float | int | str]) -> str:
    """
    Format a number as dollars/cents for printing on the form.
    Returns "" for empty values.
    """
    if v in (None, ""):
        return ""
    d = Decimal(str(v)).quantize(Decimal("0.01"))
    return f"{d:,.2f}"



def make_overlay_pdf(
    *,
    page_width: float,
    page_height: float,
    values: Dict[str, str],
    layout: Dict[str, DrawSpec],
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.setTitle("1099-NEC Overlay")

    for key, spec in layout.items():
        val = (values.get(key) or "").strip()
        if not val:
            continue

        c.setFont("Helvetica", spec.size)

        if "\n" in val:
            lines = [ln.strip() for ln in val.splitlines() if ln.strip()]
            line_gap = spec.size + 1  # slightly tighter leading
            y = spec.y
            for ln in lines:
                c.drawString(spec.x, y, ln[:80])
                y -= line_gap
        else:
            c.drawString(spec.x, spec.y, val[:120])

    c.showPage()
    c.save()
    return buf.getvalue()




def render_1099nec_copy_b_and_1(
    *,
    template_relpath: str = "money/templates/pdf_templates/1099_NEC_full.pdf",
    values: Dict[str, str],
    layout: Dict[str, DrawSpec],
    output_mode: str = "separate",  # "separate" | "combined"
) -> Dict[str, bytes]:
    """
    Render Copy 1 and Copy B from the IRS full PDF template by stamping values
    onto the background pages via a ReportLab overlay.

    Returns:
      - separate: {"1099_nec_copy_1.pdf": bytes, "1099_nec_copy_b.pdf": bytes}
      - combined: {"1099_nec_copy_b_and_1.pdf": bytes}
    """
    template_path = Path(settings.BASE_DIR) / template_relpath
    reader = PdfReader(str(template_path))

    if len(reader.pages) <= max(COPY_1_PAGE_INDEX, COPY_B_PAGE_INDEX):
        raise ValueError("Template PDF does not contain expected Copy 1 / Copy B pages.")

    # Extract pages
    page_copy1 = reader.pages[COPY_1_PAGE_INDEX]
    page_copyb = reader.pages[COPY_B_PAGE_INDEX]

    # Use actual page sizes
    w1, h1 = float(page_copy1.mediabox.width), float(page_copy1.mediabox.height)
    wb, hb = float(page_copyb.mediabox.width), float(page_copyb.mediabox.height)

    # Build overlays
    overlay1_pdf = make_overlay_pdf(page_width=w1, page_height=h1, values=values, layout=layout)
    overlayb_pdf = make_overlay_pdf(page_width=wb, page_height=hb, values=values, layout=layout)

    overlay1 = PdfReader(io.BytesIO(overlay1_pdf)).pages[0]
    overlayb = PdfReader(io.BytesIO(overlayb_pdf)).pages[0]

    # Merge overlays onto background
    page_copy1.merge_page(overlay1)
    page_copyb.merge_page(overlayb)

    if output_mode == "combined":
        writer = PdfWriter()
        writer.add_page(page_copy1)
        writer.add_page(page_copyb)
        out = io.BytesIO()
        writer.write(out)
        return {"1099_nec_copy_b_and_1.pdf": out.getvalue()}

    if output_mode == "separate":
        w_a = PdfWriter()
        w_a.add_page(page_copy1)
        out_a = io.BytesIO()
        w_a.write(out_a)

        w_b = PdfWriter()
        w_b.add_page(page_copyb)
        out_b = io.BytesIO()
        w_b.write(out_b)

        return {
            "1099_nec_copy_1.pdf": out_a.getvalue(),
            "1099_nec_copy_b.pdf": out_b.getvalue(),
        }

    raise ValueError("output_mode must be 'separate' or 'combined'.")



def COPY_B_AND_1_LAYOUT() -> Dict[str, DrawSpec]:
    """
    Copy B layout — add remaining fields.
    Your existing tuned coords are preserved; new fields are starter coords.
    """
    return {
        # --- Already tuned (keep yours) ---
        "payer_block": DrawSpec(x=65, y=725, size=10),
        "payer_tin": DrawSpec(x=65, y=665, size=10),
        "recipient_tin": DrawSpec(x=190, y=665, size=10),
        "box1": DrawSpec(x=310, y=665, size=11),

        # --- NEW fields (starter coords) ---

        # Recipient name line (box directly below TIN row)
        "recipient_name": DrawSpec(x=65, y=635, size=10),

        # Street address (including apt. no.) box
        "recipient_street": DrawSpec(x=65, y=602, size=10),

        # City/town, state, ZIP box
        "recipient_city": DrawSpec(x=65, y=580, size=10),

        # For calendar year (top header, small blank line)
        "tax_year": DrawSpec(x=420, y=690, size=10),

        # Box 7 State income (right-most column bottom)
        "box7": DrawSpec(x=510, y=567, size=11),
    }
