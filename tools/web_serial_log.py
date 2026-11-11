"""Bounded, read-only serial log tailing for independently polling clients.

The path is trusted server configuration, never a path supplied by a request.
Cursors are opaque continuity hints, not authentication or authorization tokens.
"""

import codecs
import hashlib
import os
import re
import stat

MAX_LIMIT = 65536
_CURSOR = re.compile(r"v1:([0-9a-f]{1,16}):([0-9a-f]{1,16}):([0-9a-f]{1,16}):([0-9a-f]{0,6}):([0-9a-f]{16})\Z")


def _anchor(fd, offset):
    """Fingerprint a small window immediately before the cursor."""
    os.lseek(fd, max(0, offset - 64), os.SEEK_SET)
    return hashlib.blake2s(os.read(fd, min(offset, 64)), digest_size=8).hexdigest()


def _parse_cursor(cursor):
    if not isinstance(cursor, str) or len(cursor) > 128:
        return None
    match = _CURSOR.fullmatch(cursor)
    if not match:
        return None
    dev, ino, offset = (int(part, 16) for part in match.group(1, 2, 3))
    try:
        pending = bytes.fromhex(match.group(4))
    except ValueError:
        return None
    decoder = codecs.getincrementaldecoder("utf-8")("surrogateescape")
    if decoder.decode(pending, final=False) or decoder.getstate()[0] != pending:
        return None
    if len(pending) > offset:
        return None
    return dev, ino, offset, pending, match.group(5)


def _visible(text):
    result = []
    for char in text:
        n = ord(char)
        if 0xDC80 <= n <= 0xDCFF:
            result.append("\\x%02x" % (n - 0xDC00))
        elif (n < 32 and char not in "\r\n\t") or 0x7F <= n <= 0x9F:
            result.append("\\x%02x" % n)
        else:
            result.append(char)
    return "".join(result)


class SerialLogTail:
    def __init__(self, path):
        self.path = os.fspath(path)

    def read(self, cursor=None, limit=65536):
        """Return cursor, text, reset, available; limit counts input bytes.

        Initial reads and resets return the last <= limit bytes; subsequent reads
        consume up to limit bytes from the cursor. Limits must be positive ints;
        values above MAX_LIMIT are clamped. Incomplete UTF-8 is held in the
        cursor until another poll. An unavailable file preserves a valid cursor.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        limit = min(limit, MAX_LIMIT)
        previous = _parse_cursor(cursor) if cursor is not None else None
        reset = cursor is not None and previous is None
        unavailable = {"cursor": cursor if previous else None, "text": "",
                       "reset": reset, "available": False}
        fd = None
        try:
            # Avoid opening known special files. O_NONBLOCK closes the FIFO race
            # between stat and open; fstat validates the actual opened object.
            if not stat.S_ISREG(os.stat(self.path).st_mode):
                return unavailable
            flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
            fd = os.open(self.path, flags)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                return unavailable
            if previous:
                dev, ino, offset, pending, anchor = previous
                if ((dev, ino) != (info.st_dev, info.st_ino) or offset > info.st_size
                        or _anchor(fd, offset) != anchor):
                    previous = None
                    reset = True
            if previous:
                offset, pending = previous[2], previous[3]
            else:
                offset, pending = max(0, info.st_size - limit), b""
            os.lseek(fd, offset, os.SEEK_SET)
            data = os.read(fd, min(limit, max(0, info.st_size - offset)))
            offset += len(data)
            decoder = codecs.getincrementaldecoder("utf-8")("surrogateescape")
            text = decoder.decode(pending + data, final=False)
            pending = decoder.getstate()[0]
            anchor = _anchor(fd, offset)
            token = "v1:%x:%x:%x:%s:%s" % (info.st_dev, info.st_ino, offset, pending.hex(), anchor)
            return {"cursor": token, "text": _visible(text), "reset": reset, "available": True}
        except OSError:
            return unavailable
        finally:
            if fd is not None:
                os.close(fd)
