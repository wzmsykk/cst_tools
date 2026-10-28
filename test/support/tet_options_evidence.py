"""Bounded CBOR subset reader for V05 mesher-input evidence, not production ABI.

Encoding reference: RFC 8949 sections 3.1 and 3.3. Unknown forms are rejected.
"""
import struct


def decode_options(data):
    if len(data) > 1024 * 1024:
        raise ValueError('options evidence too large')
    offset = 0

    def take(n):
        nonlocal offset
        if offset + n > len(data):
            raise ValueError('truncated CBOR')
        value = data[offset:offset + n]
        offset += n
        return value

    def item(depth=0):
        if depth > 12:
            raise ValueError('CBOR nesting limit')
        head = take(1)[0]
        major, ai = head >> 5, head & 31
        if major == 7:
            if ai in (20, 21, 22):
                return {20: False, 21: True, 22: None}[ai]
            if ai in (25, 26, 27):
                size, fmt = {25: (2, '>e'), 26: (4, '>f'), 27: (8, '>d')}[ai]
                return struct.unpack(fmt, take(size))[0]
            raise ValueError('unsupported CBOR simple value')
        if ai < 24:
            n = ai
        elif ai in (24, 25, 26, 27):
            n = int.from_bytes(take({24: 1, 25: 2, 26: 4, 27: 8}[ai]), 'big')
        else:
            raise ValueError('unsupported CBOR argument')
        if major in (0, 1):
            return n if major == 0 else -1 - n
        if major == 3:
            return take(n).decode('utf-8', errors='strict')
        if major == 4:
            if n > len(data):
                raise ValueError('CBOR array budget')
            return [item(depth + 1) for _ in range(n)]
        if major == 5:
            if n > len(data):
                raise ValueError('CBOR map budget')
            result = {}
            for _ in range(n):
                key = item(depth + 1)
                if not isinstance(key, str) or key in result:
                    raise ValueError('invalid or duplicate options key')
                result[key] = item(depth + 1)
            return result
        raise ValueError('unsupported CBOR major type')

    result = item()
    if offset != len(data) or not isinstance(result, dict):
        raise ValueError('invalid options document boundary')
    return result
