#!/usr/bin/env python3
"""Build a locally signed CRX3 and Linux external-install registrations.

Format: chromium/src/components/crx_file/crx3.proto.
The signing key stays in the checkout and is never included in the package.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import zipfile


def varint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def field(number, value):
    return varint((number << 3) | 2) + varint(len(value)) + value


def build(source, key, output):
    output.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        # Exclusive creation prevents overwriting the identity used by prior builds.
        with key.open("xb") as stream:
            key.chmod(0o600)
            try:
                subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"], stdout=stream, stderr=subprocess.PIPE, check=True)
            except Exception:
                key.unlink()
                raise
    public = subprocess.check_output(["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"])
    identity = hashlib.sha256(public).digest()[:16]
    extension_id = "".join(chr(97 + int(char, 16)) for char in identity.hex())
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["key"] = base64.b64encode(public).decode()
    # Avoid user-level registrations left by the standalone installer masking
    # the system-wide checker for the separately signed package extension.
    host_name = "org.openvpn_socks.packaged_check"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(source.iterdir()):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if path.name == "manifest.json":
                data = (json.dumps(manifest, indent=2) + "\n").encode()
            elif path.name == "background.js":
                data = data.replace(b"org.openvpn_socks.check", host_name.encode())
            info = zipfile.ZipInfo(path.name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zipped.writestr(info, data)
    archive = archive.getvalue()
    signed_header = field(1, identity)
    signed_data = b"CRX3 SignedData\0" + struct.pack("<I", len(signed_header)) + signed_header + archive
    signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key)], input=signed_data, capture_output=True, check=True).stdout
    header = field(2, field(1, public) + field(2, signature)) + field(10000, signed_header)
    (output / "extension.crx").write_bytes(b"Cr24" + struct.pack("<II", 3, len(header)) + header + archive)
    (output / "extension-id").write_text(extension_id + "\n")
    external = {"external_crx": "/usr/share/openvpn-proxy/extension.crx", "external_version": manifest["version"]}
    (output / f"{extension_id}.json").write_text(json.dumps(external, indent=2) + "\n")
    native = {
        "name": host_name,
        "description": "Check the local OpenVPN SOCKS5 proxy",
        "path": "/usr/lib/openvpn-proxy/proxy-check",
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    (output / f"{host_name}.json").write_text(json.dumps(native, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("key", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.key, args.output)
