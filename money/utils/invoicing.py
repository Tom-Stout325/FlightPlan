# money/utils/invoicing.py
from __future__ import annotations

import re
from typing import Optional

from django.db.models import Q

from money.models import InvoiceV2, Event


_SUFFIX_RE = re.compile(r"^(?P<base>\d{6})(?:-(?P<seq>\d{2}))?$")


def next_invoice_number_for_job(*, user_id: int, job: Event) -> str:
    """
    Returns the next invoice number for a given job.
    Convention: <job_number>-NN (NN is 2-digit sequence).
    If legacy invoice_number == <job_number> exists, treat it as seq=1.
    """
    base = (job.job_number or "").strip()
    if not base:
        raise ValueError("Job has no job_number; cannot suggest invoice number.")

    # Find any invoice numbers that start with base (either exact or base-xx)
    existing = (
        InvoiceV2.objects
        .filter(user_id=user_id, event_id=job.id)
        .filter(Q(invoice_number=base) | Q(invoice_number__startswith=f"{base}-"))
        .values_list("invoice_number", flat=True)
    )

    max_seq = 0
    for inv_no in existing:
        s = (inv_no or "").strip()
        m = _SUFFIX_RE.match(s)
        if not m:
            continue

        # invoice_number == base (no suffix) counts as seq=1
        if m.group("seq") is None:
            max_seq = max(max_seq, 1)
        else:
            try:
                max_seq = max(max_seq, int(m.group("seq")))
            except ValueError:
                pass

    next_seq = max_seq + 1 if max_seq else 1
    return f"{base}-{next_seq:02d}"
