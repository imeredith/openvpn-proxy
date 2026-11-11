#!/usr/bin/env python3
"""Native messaging helper: only checks whether a SOCKS5 endpoint answers."""
import json
import re
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


HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")


def check_proxy(host="127.0.0.1", port=1080):
    endpoint = f"{host}:{port}"
    try:
        with socket.create_connection((host, port), timeout=2) as connection:
            connection.sendall(b"\x05\x01\x00")
            with connection.makefile("rb") as stream:
                response = read_exact(stream, 2)
            if response != b"\x05\x00":
                return {"ok": False, "message": f"{endpoint} is open, but is not a SOCKS5 proxy accepting unauthenticated connections."}
        return {"ok": True, "message": f"SOCKS5 ready at {endpoint}"}
    except (OSError, EOFError) as error:
        return {"ok": False, "message": f"Proxy unavailable on {endpoint}. Start the Docker container. ({error})"}


def main():
    try:
        length = struct.unpack("=I", read_exact(sys.stdin.buffer, 4))[0]
        if length > 4096:
            raise ValueError("Message too large")
        message = json.loads(read_exact(sys.stdin.buffer, length))
        if not isinstance(message, dict) or message.get("command") != "check":
            result = {"ok": False, "message": "Unknown command"}
        else:
            host, port = message.get("host", "127.0.0.1"), message.get("port", 1080)
            if not isinstance(host, str) or not HOST.fullmatch(host) or type(port) is not int or not 0 < port < 65536:
                raise ValueError("Invalid proxy host or port")
            result = check_proxy(host, port)
    except (EOFError, ValueError) as error:
        result = {"ok": False, "message": str(error)}
    payload = json.dumps(result).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(payload)) + payload)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
