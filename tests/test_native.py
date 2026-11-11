import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("proxy_check", ROOT / "native/proxy_check.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class NativeTests(unittest.TestCase):
    def test_socks_handshake(self):
        for reply, expected in [(b"\x05\x00", True), (b"\x05\xff", False), (b"HTTP", False), (b"\x05", False)]:
            connection = MagicMock()
            connection.makefile.return_value = contextlib.closing(io.BytesIO(reply))
            with patch.object(helper.socket, "create_connection", return_value=contextlib.nullcontext(connection)) as connect:
                self.assertEqual(helper.check_proxy()["ok"], expected)
                connect.assert_called_once_with(("127.0.0.1", 1080), timeout=2)
                connection.sendall.assert_called_once_with(b"\x05\x01\x00")

    def test_configured_endpoint(self):
        with patch.object(helper.socket, "create_connection", side_effect=ConnectionRefusedError("refused")) as connect:
            result = helper.check_proxy("192.168.1.5", 1081)
        connect.assert_called_once_with(("192.168.1.5", 1081), timeout=2)
        self.assertIn("192.168.1.5:1081", result["message"])

    def test_closed_port(self):
        with patch.object(helper.socket, "create_connection", side_effect=ConnectionRefusedError("refused")):
            self.assertFalse(helper.check_proxy()["ok"])

    def test_native_framing_and_command_restriction(self):
        payload = json.dumps({"command": "execute", "host": "example.com"}).encode()
        result = subprocess.run(["python3", str(ROOT / "native/proxy_check.py")], input=struct.pack("=I", len(payload)) + payload, capture_output=True, check=True)
        length = struct.unpack("=I", result.stdout[:4])[0]
        self.assertEqual(length, len(result.stdout[4:]))
        self.assertEqual(json.loads(result.stdout[4:]), {"ok": False, "message": "Unknown command"})

    def test_rejects_invalid_endpoint(self):
        for host, port in [("bad host", 1080), ("ok\n", 1080), ("ok", 0), ("ok", 65536), ("ok", "1080"), (1, 1080)]:
            payload = json.dumps({"command": "check", "host": host, "port": port}).encode()
            result = subprocess.run(["python3", str(ROOT / "native/proxy_check.py")], input=struct.pack("=I", len(payload)) + payload, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout[4:]), {"ok": False, "message": "Invalid proxy host or port"})

    def test_installer_and_reinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "data with spaces"
            config = Path(directory) / "config"
            command = ["python3", str(ROOT / "install-extension.py"), "--prefix", str(prefix), "--config-home", str(config), "--no-open"]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            host = json.loads((config / "google-chrome/NativeMessagingHosts/org.openvpn_socks.check.json").read_text())
            self.assertTrue(Path(host["path"]).is_file())
            self.assertRegex(host["allowed_origins"][0], r"^chrome-extension://[a-p]{32}/$")
            self.assertTrue((prefix / "extension/manifest.json").is_file())
            self.assertEqual(Path(host["path"]).stat().st_mode & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()
