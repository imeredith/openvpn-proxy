#!/usr/bin/env python3
"""Install the extension files and native messaging checker for Chrome on Linux or macOS."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Per-user NativeMessagingHosts parent directories, relative to --config-home.
BROWSERS = {
    "linux": ("google-chrome", "google-chrome-beta", "google-chrome-unstable", "chromium"),
    "darwin": ("Google/Chrome", "Google/Chrome Beta", "Google/Chrome Canary", "Chromium"),
}


def main():
    platform = "linux" if sys.platform.startswith("linux") else sys.platform
    mac = platform == "darwin"
    config_home = Path.home() / "Library/Application Support" if mac else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "openvpn-socks-extension")
    parser.add_argument("--config-home", type=Path, default=config_home)
    parser.add_argument("--no-open", action="store_true", help="Do not open Chrome's extensions page")
    args = parser.parse_args()
    if platform not in BROWSERS:
        parser.error("This installer supports Chrome and Chromium on Linux and macOS.")
    source = Path(__file__).resolve().parent
    destination = args.prefix.expanduser().resolve()
    extension = destination / "extension"
    extension.mkdir(parents=True, exist_ok=True)
    for path in (source / "extension").iterdir():
        if path.is_file() and path.resolve() != (extension / path.name).resolve():
            shutil.copy2(path, extension / path.name)
    helper = destination / "proxy_check.py"
    shutil.copy2(source / "native/proxy_check.py", helper)
    if mac:
        # Chrome starts the helper with launchd's PATH, where python3 may be
        # missing or the Xcode stub; pin the interpreter running this installer.
        lines = helper.read_text().splitlines(keepends=True)
        helper.write_text(f"#!{sys.executable}\n" + "".join(lines[1:]))
    helper.chmod(0o755)
    manifest = json.loads((extension / "manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
    host = {
        "name": "org.openvpn_socks.check",
        "description": "Check the local OpenVPN SOCKS5 proxy",
        "path": str(helper),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    for browser in BROWSERS[platform]:
        directory = args.config_home.expanduser().resolve() / browser / "NativeMessagingHosts"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "org.openvpn_socks.check.json").write_text(json.dumps(host, indent=2) + "\n")
    print(f"Installed extension and proxy checker.\nExtension ID: {extension_id}\n\n"
          f"1. Open chrome://extensions\n2. Enable Developer mode\n"
          f"3. Click Load unpacked and select:\n   {extension}\n"
          "4. Pin OpenVPN Site Proxy from Chrome's Extensions menu.\n\n"
          "After updates, run this installer again and click Reload in chrome://extensions.")
    if not args.no_open and not mac:
        for browser in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"):
            executable = shutil.which(browser)
            if executable:
                subprocess.Popen([executable, "chrome://extensions"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                break


if __name__ == "__main__":
    main()
