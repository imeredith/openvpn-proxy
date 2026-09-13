#!/usr/bin/env python3
"""Native messaging helper: only checks the fixed local SOCKS5 endpoint."""
import json
import socket
import struct
import sys


def read_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise EOFError("Incomplete message")
        data.extend(chunk)
    return bytes(data)


def check_proxy():
    try:
        with socket.create_connection(("127.0.0.1", 1080), timeout=2) as connection:
            connection.sendall(b"\x05\x01\x00")
            with connection.makefile("rb") as stream:
                response = read_exact(stream, 2)
            if response != b"\x05\x00":
                return {"ok": False, "message": "Port 1080 is open, but is not a SOCKS5 proxy accepting unauthenticated connections."}
        return {"ok": True, "message": "SOCKS5 ready at 127.0.0.1:1080"}
    except (OSError, EOFError) as error:
        return {"ok": False, "message": f"Proxy unavailable on 127.0.0.1:1080. Start the Docker container. ({error})"}


def main():
    try:
        length = struct.unpack("=I", read_exact(sys.stdin.buffer, 4))[0]
        if length > 4096:
            raise ValueError("Message too large")
        message = json.loads(read_exact(sys.stdin.buffer, length))
        result = check_proxy() if isinstance(message, dict) and message.get("command") == "check" else {"ok": False, "message": "Unknown command"}
    except (EOFError, ValueError) as error:
        result = {"ok": False, "message": str(error)}
    payload = json.dumps(result).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(payload)) + payload)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
