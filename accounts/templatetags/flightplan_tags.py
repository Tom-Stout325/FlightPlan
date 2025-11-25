from django import template
from django.utils.safestring import mark_safe
from datetime import timedelta
import os

register = template.Library()

# -----------------------------
# Durations / Time Formatting
# -----------------------------

@register.filter
def duration_display(value):
    """
    Format a timedelta like '3h 07m' or '7m' if under an hour.
    Falls back to '0 minutes' on non-timedelta input.
    """
    if not isinstance(value, timedelta):
        return "0 minutes"

    total_seconds = int(value.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60

    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


@register.filter
def duration(value):
    """
    Format a timedelta as HH:MM:SS (zero-padded).
    """
    if not value:
        return "00:00:00"
    try:
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    except (AttributeError, ValueError):
        return "00:00:00"


@register.filter
def minutes_to_hm(value):
    """
    Convert integer minutes to 'Hh Mm' (e.g., 187 -> '3h 7m').
    Accepts int/str; returns '0m' if empty/invalid.
    """
    if value in (None, ""):
        return "0m"
    try:
        total_minutes = int(value)
    except (TypeError, ValueError):
        return "0m"

    h, m = divmod(total_minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"



@register.filter
def seconds_to_hms(value):
    """
    Convert seconds (int) to 'HH:MM:SS'.
    Accepts int/str; returns '00:00:00' if empty/invalid.
    """
    if value in (None, ""):
        return "00:00:00"

    try:
        total_seconds = int(value)
    except (TypeError, ValueError):
        return "00:00:00"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


# -----------------------------
# Files / Icons
# -----------------------------

def _ext(url_or_path: str) -> str:
    """Return lowercase file extension (including dot), or ''."""
    if not url_or_path:
        return ""
    _, ext = os.path.splitext(str(url_or_path).lower())
    return ext


@register.filter
def is_pdf(url):
    """
    True if the URL/path ends with .pdf (case-insensitive).
    """
    return _ext(url) == ".pdf"


@register.filter
def file_icon_class(url):
    """
    Return a Font Awesome class string for the given file URL/filename.
    Example use:
      <i class="{{ some_url|file_icon_class }}"></i>
    """
    ext = _ext(url)
    mapping = {
        ".pdf":  "fa-solid fa-file-pdf text-danger",
        ".doc":  "fa-solid fa-file-word text-primary",
        ".docx": "fa-solid fa-file-word text-primary",
        ".xls":  "fa-solid fa-file-excel text-success",
        ".xlsx": "fa-solid fa-file-excel text-success",
        ".csv":  "fa-solid fa-file-csv text-success",
        ".jpg":  "fa-solid fa-file-image text-info",
        ".jpeg": "fa-solid fa-file-image text-info",
        ".png":  "fa-solid fa-file-image text-info",
        ".gif":  "fa-solid fa-file-image text-info",
        ".zip":  "fa-solid fa-file-zipper text-warning",
        ".txt":  "fa-regular fa-file-lines text-muted",
    }
    return mapping.get(ext, "fa-regular fa-file")


@register.filter
def file_badge(url):
    """
    Return a small HTML badge with an icon for the file type (Font Awesome).
    Marked safe for direct rendering.
    Example:
      {{ item.receipt.url|file_badge|safe }}
    """
    ext = _ext(url)
    config = {
        ".pdf":  ("bg-danger text-white",  "fa-solid fa-file-pdf",   "PDF"),
        ".doc":  ("bg-primary text-white", "fa-solid fa-file-word",  "DOC"),
        ".docx": ("bg-primary text-white", "fa-solid fa-file-word",  "DOC"),
        ".xls":  ("bg-success text-white", "fa-solid fa-file-excel", "XLS"),
        ".xlsx": ("bg-success text-white", "fa-solid fa-file-excel", "XLSX"),
        ".csv":  ("bg-success text-white", "fa-solid fa-file-csv",   "CSV"),
        ".jpg":  ("bg-info text-dark",     "fa-solid fa-file-image", "JPG"),
        ".jpeg": ("bg-info text-dark",     "fa-solid fa-file-image", "JPEG"),
        ".png":  ("bg-info text-dark",     "fa-solid fa-file-image", "PNG"),
        ".gif":  ("bg-info text-dark",     "fa-solid fa-file-image", "GIF"),
        ".zip":  ("bg-warning text-dark",  "fa-solid fa-file-zipper","ZIP"),
        ".txt":  ("bg-secondary text-white","fa-regular fa-file-lines","TXT"),
    }
    css, icon, label = config.get(ext, ("bg-secondary text-white", "fa-regular fa-file", ext[1:].upper() or "FILE"))
    html = f'<span class="badge {css}"><i class="{icon}"></i> {label}</span>'
    return mark_safe(html)


# -----------------------------
# Form Helpers
# -----------------------------

@register.filter(name="add_class")
def add_class(field, css_class):
    """
    Add CSS classes to a Django form field widget.
    Usage: {{ form.field|add_class:"form-control form-control-sm" }}
    """
    return field.as_widget(attrs={"class": css_class})
