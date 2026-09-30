"""Small WinWrap/VBA source encoding helpers shared by runtime macros."""

from __future__ import annotations


def quote_vb_string(value: object) -> str:
    """Escape a value for inclusion inside a VB string literal."""

    return str(value).replace('"', '""')
