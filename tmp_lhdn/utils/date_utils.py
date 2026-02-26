"""Date utilities for LHDN payroll integration."""
from datetime import date, datetime


def to_lhdn_date(value):
    """Convert a date value to LHDN-compatible YYYY-MM-DD string.

    Args:
        value: A date object or YYYY-MM-DD string.

    Returns:
        str: The date in YYYY-MM-DD format.

    Raises:
        ValueError: If value is invalid, empty, or cannot be parsed.
    """
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    if not isinstance(value, str) or not value or not value.strip():
        raise ValueError(f"Invalid date value: {value!r}")

    value = value.strip()

    # Validate YYYY-MM-DD format
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise ValueError(f"Invalid date value: {value!r}")


def to_lhdn_datetime():
    """Get the current UTC datetime in LHDN-compatible format.

    Returns:
        str: Current UTC time as YYYY-MM-DDTHH:MM:SSZ.
    """
    now = datetime.utcnow()
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")
