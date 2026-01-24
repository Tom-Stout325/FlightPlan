# money/utils_tokens.py

from __future__ import annotations

from django.core import signing


W9_SALT = "money.contractor.w9"
W9_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days


def make_contractor_w9_token(contractor_id: int) -> str:
    signer = signing.TimestampSigner(salt=W9_SALT)
    return signer.sign(str(contractor_id))


def parse_contractor_w9_token(token: str) -> int:
    signer = signing.TimestampSigner(salt=W9_SALT)
    raw = signer.unsign(token, max_age=W9_MAX_AGE_SECONDS)
    return int(raw)
