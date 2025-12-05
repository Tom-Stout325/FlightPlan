# airspace/utils.py

from __future__ import annotations
from decimal import Decimal


def dms_to_decimal(
    degrees: int | Decimal | float,
    minutes: int | Decimal | float,
    seconds: int | Decimal | float,
    direction: str,
) -> Decimal:
    """
    Convert Degrees / Minutes / Seconds + direction (N/S/E/W) to decimal degrees.

    N/E => positive, S/W => negative.
    """
    deg = Decimal(str(degrees))
    mins = Decimal(str(minutes))
    secs = Decimal(str(seconds))

    decimal = deg + (mins / Decimal("60")) + (secs / Decimal("3600"))

    direction = (direction or "").upper()
    if direction in ("S", "W"):
        decimal = -decimal

    return decimal
