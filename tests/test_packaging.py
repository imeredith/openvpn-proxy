import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_extension", ROOT / "packaging/build-extension.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def parse_fields(data):
    stream = io.BytesIO(data)

    def number():
        value = shift = 0
        while True:
            byte = stream.read(1)[0]
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7

    fields = {}
    while stream.tell() < len(data):
        tag = number()
        if tag & 7 != 2:
            raise ValueError("Expected a length-delimited field")
        fields[tag >> 3] = stream.read(number())
    return fields


class PackagingTests(unittest.TestCase):
    def test_signed_archive_identity_and_registrations(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            key = temp / "private.pem"
            output = temp / "output"
            builder.build(ROOT / "extension", key, output)
            original_key = key.read_bytes()
            original_crx = (output / "extension.crx").read_bytes()
            builder.build(ROOT / "extension", key, output)
            self.assertEqual(key.read_bytes(), original_key)
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual((output / "extension.crx").read_bytes(), original_crx)
            self.assertEqual(original_crx[:4], b"Cr24")
            version, header_length = struct.unpack("<II", original_crx[4:12])
            self.assertEqual(version, 3)
            header = parse_fields(original_crx[12:12 + header_length])
            proof = parse_fields(header[2])
            identity = parse_fields(header[10000])[1]
            self.assertEqual(identity, hashlib.sha256(proof[1]).digest()[:16])
            archive = original_crx[12 + header_length:]
            signed_data = b"CRX3 SignedData\0" + struct.pack("<I", len(header[10000])) + header[10000] + archive
            public = temp / "public.der"
            public.write_bytes(proof[1])
            signature = temp / "signature"
            signature.write_bytes(proof[2])
            command = ["openssl", "dgst", "-sha256", "-verify", str(public), "-keyform", "DER", "-signature", str(signature)]
            subprocess.run(command, input=signed_data, check=True, capture_output=True)
            self.assertNotEqual(subprocess.run(command, input=signed_data + b"tampered", capture_output=True).returncode, 0)
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                manifest = json.loads(zipped.read("manifest.json"))
                self.assertEqual(base64.b64decode(manifest["key"]), proof[1])
                self.assertIn(b"org.openvpn_socks.packaged_check", zipped.read("background.js"))
                self.assertFalse(any(name.endswith(".pem") or name.startswith("vpn/") for name in zipped.namelist()))
            extension_id = "".join(chr(97 + int(char, 16)) for char in identity.hex())
            external = json.loads((output / f"{extension_id}.json").read_text())
            self.assertEqual(external["external_version"], manifest["version"])
            self.assertEqual(external["external_crx"], "/usr/share/openvpn-proxy/extension.crx")
            native = json.loads((output / "org.openvpn_socks.packaged_check.json").read_text())
            self.assertEqual(native["allowed_origins"], [f"chrome-extension://{extension_id}/"])


if __name__ == "__main__":
    unittest.main()
