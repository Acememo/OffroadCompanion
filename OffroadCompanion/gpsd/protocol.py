"""Framing shared with the game: 4-byte little-endian uint32 length + UTF-8 JSON object with a "type".

Same wire format as BeamNG.Earth's own server (server/protocol.py), so the game side can use one tiny decoder.
"""
import asyncio
import json
import struct

HEADER = struct.Struct("<I")
MAX_FRAME = 32 * 1024 * 1024


class ProtocolError(Exception):
    pass


def encode(msg):
    # real UTF-8, never \u escapes: the game's jsonDecode leaves those as literal text ("Revolución")
    payload = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return HEADER.pack(len(payload)) + payload


def decode_payload(payload):
    try:
        msg = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ProtocolError(f"bad JSON frame: {e}") from None
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise ProtocolError("frame is not an object with a 'type'")
    return msg


async def read_message(reader):
    """Next message from an asyncio StreamReader, or None on a clean EOF."""
    try:
        head = await reader.readexactly(HEADER.size)
    except asyncio.IncompleteReadError as e:
        if not e.partial:
            return None
        raise ProtocolError("connection closed inside a frame header") from None
    n = HEADER.unpack(head)[0]
    if n > MAX_FRAME:
        raise ProtocolError(f"frame too large: {n} bytes")
    try:
        payload = await reader.readexactly(n)
    except asyncio.IncompleteReadError:
        raise ProtocolError("connection closed inside a frame") from None
    return decode_payload(payload)


class Decoder:
    """Incremental decoder for blocking clients (tests): feed() bytes, get messages."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        out = []
        while len(self.buf) >= HEADER.size:
            n = HEADER.unpack_from(self.buf)[0]
            if n > MAX_FRAME:
                raise ProtocolError(f"frame too large: {n} bytes")
            if len(self.buf) < HEADER.size + n:
                break
            out.append(decode_payload(bytes(self.buf[HEADER.size:HEADER.size + n])))
            del self.buf[:HEADER.size + n]
        return out
