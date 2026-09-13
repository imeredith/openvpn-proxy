import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name)
        self.vpn = self.temp / "vpn with spaces"
        self.vpn.mkdir()
        (self.vpn / "client.ovpn").write_text("client\n")
        self.log = self.temp / "docker.jsonl"
        docker = self.temp / "docker"
        docker.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["DOCKER_TEST_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
args = args[2:]  # --host unix:///var/run/docker.sock
if args[:2] == ["container", "inspect"]:
    if "--format" in args:
        print("true" if os.environ.get("DOCKER_TEST_AUTO_REMOVE") else "false")
    sys.exit(0 if os.environ.get("DOCKER_TEST_EXISTS") else 1)
if args[:2] == ["image", "inspect"]:
    sys.exit(1)
if args[0] == "build" and os.environ.get("DOCKER_TEST_BUILD_FAIL"):
    sys.exit(1)
''')
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.temp}:{os.environ['PATH']}", VPN_DIR=str(self.vpn), DOCKER_TEST_LOG=str(self.log))

    def run_launcher(self, *args):
        return subprocess.run([str(ROOT / "openvpn-proxy"), *args], cwd=self.temp, env=self.env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line)[2:] for line in self.log.read_text().splitlines()]

    def test_first_start_builds_and_mounts_credentials_without_copying(self):
        (self.vpn / "auth.txt").write_text("user\npassword\n")
        self.env["VPN_DNS"] = "10.8.0.1"
        result = self.run_launcher("--", "--verb", "4")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertIn(["build", "-t", "openvpn-socks", str(ROOT)], calls)
        run = next(call for call in calls if call[0] == "run")
        self.assertIn(f"{self.vpn}:/vpn:ro", run)
        self.assertIn("VPN_DNS=10.8.0.1", run)
        self.assertIn("127.0.0.1:1080:1080", run)
        self.assertIn("--restart", run)
        self.assertIn("unless-stopped", run)
        self.assertNotIn("--rm", run)
        self.assertEqual(run[-5:], ["openvpn-socks", "--auth-user-pass", "/vpn/auth.txt", "--verb", "4"])

    def test_existing_container_is_reused(self):
        self.env["DOCKER_TEST_EXISTS"] = "1"
        self.assertEqual(self.run_launcher().returncode, 0)
        self.assertIn(["start", "openvpn-socks"], self.calls())
        self.assertIn(["update", "--restart", "unless-stopped", "openvpn-socks"], self.calls())
        self.assertFalse(any(call[0] in ("run", "build", "rm") for call in self.calls()))

    def test_rebuild_does_not_replace_existing_container(self):
        self.env["DOCKER_TEST_EXISTS"] = "1"
        self.assertNotEqual(self.run_launcher("--build").returncode, 0)
        self.assertFalse(any(call[0] in ("start", "run", "build", "rm") for call in self.calls()))

    def test_build_failure_does_not_start_container(self):
        self.env["DOCKER_TEST_BUILD_FAIL"] = "1"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse(any(call[0] == "run" for call in self.calls()))

    def test_old_auto_removing_container_requires_explicit_recreation(self):
        self.env.update(DOCKER_TEST_EXISTS="1", DOCKER_TEST_AUTO_REMOVE="1")
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--recreate", result.stderr)
        self.assertFalse(any(call[0] in ("stop", "rm", "update", "run") for call in self.calls()))

    def test_recreate_builds_before_replacing_existing_container(self):
        self.env["DOCKER_TEST_EXISTS"] = "1"
        self.assertEqual(self.run_launcher("--recreate", "--build").returncode, 0)
        operations = [call[0] for call in self.calls()]
        self.assertLess(operations.index("build"), operations.index("stop"))
        self.assertLess(operations.index("stop"), operations.index("rm"))
        self.assertLess(operations.index("rm"), operations.index("run"))

    def test_failed_recreate_build_leaves_existing_container_running(self):
        self.env.update(DOCKER_TEST_EXISTS="1", DOCKER_TEST_BUILD_FAIL="1")
        self.assertNotEqual(self.run_launcher("--recreate", "--build").returncode, 0)
        self.assertFalse(any(call[0] in ("stop", "rm", "run") for call in self.calls()))

    def test_missing_profile_fails_before_docker(self):
        (self.vpn / "client.ovpn").unlink()
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_packaged_launcher_uses_system_assets_and_user_config(self):
        binary = self.temp / "openvpn-proxy"
        shutil.copy2(ROOT / "openvpn-proxy", binary)
        config = self.temp / "config/openvpn-proxy"
        config.mkdir(parents=True)
        (config / "client.ovpn").write_text("client\n")
        self.env.pop("VPN_DIR")
        self.env["XDG_CONFIG_HOME"] = str(self.temp / "config")
        result = subprocess.run([str(binary)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["build", "-t", "openvpn-socks", "/usr/share/openvpn-proxy/docker"], self.calls())
        run = next(call for call in self.calls() if call[0] == "run")
        self.assertIn(f"{config}:/vpn:ro", run)

    @unittest.skipUnless(shutil.which("ssh") and shutil.which("socat"), "requires OpenSSH and socat")
    def test_pssh_overrides_direct_config_and_preserves_alias(self):
        config = self.temp / "ssh config"
        config.write_text("Host testalias\n HostName destination.invalid\n Port 2222\n ProxyCommand none\n CanonicalizeHostname always\n VerifyHostKeyDNS yes\n ControlMaster auto\n ControlPath /tmp/direct-ssh-socket\n")
        result = subprocess.run([str(ROOT / "pssh"), "-G", "-F", str(config), "user@testalias"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = dict(line.split(" ", 1) for line in result.stdout.splitlines())
        self.assertEqual(settings["hostname"], "destination.invalid")
        self.assertEqual(settings["user"], "user")
        self.assertEqual(settings["port"], "2222")
        self.assertIn("SOCKS5-CONNECT:127.0.0.1:1080:%h:%p", settings["proxycommand"])
        self.assertEqual(settings["canonicalizehostname"], "false")
        self.assertEqual(settings["verifyhostkeydns"], "false")
        self.assertEqual(settings["controlmaster"], "false")
        self.assertIn(settings.get("controlpath"), (None, "none"))


if __name__ == "__main__":
    unittest.main()
