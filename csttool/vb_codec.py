"""Small WinWrap/VBA source encoding helpers shared by runtime macros."""

from __future__ import annotations


def quote_vb_string(value: object) -> str:
    """Escape a value for inclusion inside a VB string literal."""

    escaped = str(value).replace('"', '""')
    parts = []
    for character in escaped:
        if ord(character) < 128:
            parts.append(character)
        else:
            units = character.encode('utf-16-le')
            for index in range(0, len(units), 2):
                code = int.from_bytes(units[index:index + 2], 'little')
                parts.append('" & ChrW(' + str(code if code < 32768 else code - 65536) + ') & "')
    return ''.join(parts)
