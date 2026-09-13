# OpenVPN SOCKS5 proxy

## Arch Linux package

From this checkout, as your normal user:

```sh
makepkg -si
```

This installs `openvpn-proxy` and `pssh` into `/usr/bin`, declares their runtime
dependencies, and installs a signed Chrome/Chromium extension plus its native
proxy checker system-wide. It does not start Docker or the VPN during package
installation. This is a local-checkout PKGBUILD; keep the complete repository
when building it.

Put your VPN files in `~/.config/openvpn-proxy/` (respects `XDG_CONFIG_HOME`):

```sh
mkdir -p ~/.config/openvpn-proxy
# Copy client.ovpn and its certificates/keys into that directory.
openvpn-proxy
pssh user@example.com
```

Alternatively, keep the existing `vpn/` directory and launch with
`VPN_DIR="$PWD/vpn" openvpn-proxy`. No VPN profiles, credentials, or signing
keys are included in the Arch package or Docker image.

Fully quit and reopen Chrome/Chromium after installation. Linux's
[external extension installation](https://developer.chrome.com/docs/extensions/how-to/distribute/install-extensions)
loads the bundled CRX automatically; find **OpenVPN Site Proxy** in
`chrome://extensions` and pin it. Browser policies and previously uninstalling
this extension through Chrome can prevent automatic installation. This
integration targets native Linux Chrome/Chromium, not Snap/Flatpak browsers.

If you previously used the unpacked extension, remove that copy to avoid two
extensions competing for proxy settings. The package has a separate extension
ID and whitelist, so re-add your sites. Its checker uses a separate registration
to coexist with files left by the standalone installer.

The first build generates `.extension-signing-key.pem` in this checkout.
Keep that private file for future builds: it preserves the extension ID and
whitelist through updates. It is ignored by Git and excluded from the package.
When changing extension code, bump `extension/manifest.json`'s version and the
PKGBUILD `pkgver`, rebuild with `makepkg -sif`, then restart the browser.
Rebuilding the same version does not update Chrome's installed extension.

Package assets live under `/usr/share/openvpn-proxy/`; the native helper lives
under `/usr/lib/openvpn-proxy/`. Remove everything owned by the package with
`sudo pacman -Rns openvpn-proxy`, then restart Chrome. Your VPN configuration
and Docker image/container are managed separately and remain in place.

## Run from the checkout

Runs microsocks through an OpenVPN connection in a container. Requires Docker
with `/dev/net/tun` and IPv4/IPv6 iptables support (typically a Linux host).
The Docker build compiles microsocks 1.0.5 from its checksum-verified
[upstream release](https://github.com/rofl0r/microsocks/releases/tag/v1.0.5)
in a separate stage; the final image contains the binary without build tools.

1. Put your VPN provider's profile at `vpn/client.ovpn`, with any referenced
   certificates/keys alongside it. Relative profile paths resolve from `/vpn`.
   Use a foreground client profile: remove `daemon` if present.
2. Build and run:

   ```sh
   docker build -t openvpn-socks .
   docker run --restart unless-stopped --init --name openvpn-socks \
     --cap-add=NET_ADMIN --device=/dev/net/tun \
     -p 127.0.0.1:1080:1080 \
     -v "$PWD/vpn:/vpn:ro" \
     openvpn-socks
   ```

   If the provider requires a username/password, create `vpn/auth.txt` with the
   username on line 1 and password on line 2 (`chmod 600 vpn/auth.txt`). Append
   `--auth-user-pass /vpn/auth.txt` after `openvpn-socks` in the run command.

3. Wait for `Initialization Sequence Completed` in the logs. In Firefox's
   Network Settings, select manual proxy configuration, set **SOCKS Host** to
   `127.0.0.1`, **Port** to `1080`, choose **SOCKS v5**, and enable **Proxy DNS
   when using SOCKS v5**. Leave HTTP/HTTPS proxy fields empty. Remote DNS is
   required: the browser sends hostnames to microsocks, which resolves them
   inside the container over the OpenVPN tunnel.

Check using remote DNS resolution:

```sh
curl --proxy socks5h://127.0.0.1:1080 https://api.ipify.org
```

The result should be your VPN's exit IP. Only applications configured to use
the SOCKS proxy use this connection. Microsocks proxies TCP; browser UDP/WebRTC
traffic is outside its scope.

The proxy's outbound connections and DNS are restricted to `tun0`; while the
VPN is unavailable, requests fail. IPv6 proxy egress is blocked. DNS defaults
to `1.1.1.1`, reached **through the VPN**, not directly through the host's
connection. Add `-e VPN_DNS=<VPN-DNS-IP>` before the image name if your provider
requires its own IPv4 resolver. OpenVPN's pushed DNS settings are not applied.
Resolving the VPN server's own hostname happens before the tunnel connects.

The proxy has no authentication and is published only on localhost. VPN
credentials are mounted at runtime and excluded from the image build context.

References: [microsocks](https://github.com/rofl0r/microsocks) and
[OpenVPN routing documentation](https://openvpn.net/community-docs/routing-all-client-traffic--including-web-traffic--through-the-vpn.html).

## Launcher and SSH

Start the container in the background:

```sh
./openvpn-proxy
```

The launcher uses the local system Docker socket, starts `docker.service` if
needed, and uses sudo when your user cannot access Docker. It builds the image
on first use. Put your profile at `vpn/client.ovpn`; `vpn/auth.txt` is detected
automatically. Relative paths work even when you launch from another directory.
Use `VPN_DIR=/path/to/vpn ./openvpn-proxy` for another profile directory and
`VPN_DNS=10.8.0.1 ./openvpn-proxy` for a provider-specific DNS server.

An existing `openvpn-socks` container is reused with its original settings.
To apply changes, use `./openvpn-proxy --recreate`. This stops and replaces the
container using the current profile directory, DNS, and arguments; your mounted
VPN files are preserved. Containers remain on disk when stopped.
Use `./openvpn-proxy --recreate --build` to rebuild, or pass additional OpenVPN arguments
after `--`, for example `./openvpn-proxy -- --verb 4`. Check the logs using
the command printed by the launcher and wait for `Initialization Sequence
Completed` before connecting. The launcher does not verify VPN readiness.

For automatic startup after a reboot, install the current package, enable
Docker at boot, and recreate any container made by the old `--rm` launcher:

```sh
makepkg -si
sudo systemctl enable --now docker.service
openvpn-proxy --recreate
```

Pass your usual `VPN_DIR`, `VPN_DNS`, and any extra OpenVPN arguments when
recreating. The container remembers those settings for subsequent boots.
Docker's [unless-stopped restart policy](https://docs.docker.com/engine/containers/start-containers-automatically/)
restarts it after Docker starts and after process exits. If you manually run
`docker stop openvpn-socks`, it stays stopped across reboots until you run
`openvpn-proxy` again. The VPN profile directory must be available at boot.

After reboot, check both the container and actual VPN connectivity:

```sh
systemctl is-enabled docker.service
sudo docker inspect --format '{{.State.Status}} {{.HostConfig.RestartPolicy.Name}}' openvpn-socks
sudo docker logs --tail 50 openvpn-socks
curl --connect-timeout 10 --max-time 20 --proxy socks5h://127.0.0.1:1080 https://api.ipify.org
```

Expect `enabled`, `running unless-stopped`, a VPN connection in the logs, and
your VPN exit IP from curl. The Chrome badge only checks the SOCKS listener.

Proxy SSH connections through the same local SOCKS5 endpoint:

```sh
./pssh user@example.com
./pssh -p 2222 -i ~/.ssh/id_ed25519 user@example.com
./pssh my-ssh-config-alias 'uname -a'
```

`pssh` requires OpenSSH and a version of socat that supports `SOCKS5-CONNECT`.
It preserves SSH arguments, host aliases, keys, and host-key checking, while
forcing the connection through the proxy. Destination DNS is resolved by
microsocks over OpenVPN. It disables local hostname canonicalization, DNS
host-key lookups, and SSH connection sharing to avoid reusing a direct session.
There is no direct fallback if the proxy is unavailable. Browser whitelist
entries do not affect `pssh`; every SSH destination uses the proxy.
Custom proxy/jump-host and connection-sharing options are outside this wrapper's
intended usage. See OpenSSH's [ProxyCommand documentation](https://man.openbsd.org/ssh_config.5).

For commands without `./`, add this repository directory to your `PATH`.

## Chrome extension

With the container running, install the extension files and local port checker:

```sh
python3 install-extension.py
```

The installer supports Linux Chrome and Chromium with Python 3, without sudo.
It copies the extension to `~/.local/share/openvpn-socks-extension/extension`
and registers a native messaging helper under each browser's
`~/.config/<browser>/NativeMessagingHosts/` directory. XDG data/config locations
are respected. Custom browser configurations can use `--config-home PATH`.
Snap/Flatpak browsers may need separate native messaging integration.

Chrome requires a one-time manual step for this unpublished extension:
open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**,
and select the extension directory printed by the installer. Pin **OpenVPN
Site Proxy** from the Extensions menu. The installer opens the extensions page
when it finds Chrome/Chromium; use `--no-open` to skip opening the browser.

Visit a site, open the extension, and click **Add this site to whitelist**.
Reload the page to use the new route. The popup also accepts manually entered
hostnames and lets you remove entries. An entry includes its subdomains:
`example.com` includes `www.example.com`, but adding `www.example.com` alone
does not include `example.com`. The whitelist persists across browser restarts.

Whitelisted destinations use `SOCKS5 127.0.0.1:1080` with **no direct fallback**.
Other destinations use a direct connection while the whitelist is active.
This operates per destination hostname, not per tab: third-party assets,
sign-in hosts, and redirect destinations need their own entries. Chrome's
built-in loopback bypass still applies to localhost destinations. Incognito
is not supported. Removing the last entry releases this extension's proxy
settings, restoring the browser's previous configuration.

Chrome resolves SOCKS5 destination hostnames at the proxy, so those DNS queries
travel through OpenVPN. While the whitelist is nonempty, the extension also
disables browser-wide network prediction (including DNS prefetching) and
non-proxied WebRTC UDP; those overrides are released when the list becomes
empty. These settings can affect other tabs, including WebRTC calls.

The popup and a once-per-minute badge check confirm that port 1080 answers a
SOCKS5 handshake. A green **ON** badge means the proxy is listening and rules
are active; **!** means there is a problem. This does **not** verify VPN tunnel
health. A stopped VPN can leave microsocks listening while its firewall blocks
outbound traffic. Unavailable proxies never cause the extension to remove the
whitelist or add a direct fallback. The helper only checks `127.0.0.1:1080`;
it does not start Docker or accept commands to run programs.

To update, rerun the installer and click **Reload** on the extension card.
To uninstall, remove the extension in Chrome, delete
`~/.local/share/openvpn-socks-extension`, and delete
`org.openvpn_socks.check.json` from the browser `NativeMessagingHosts`
directories listed above (adjust for custom/XDG paths).

Run the automated checks:

```sh
node --test tests/extension.test.mjs
python3 -m unittest discover -s tests -p 'test_*.py'
```

An optional integration test launches headless Chromium in a disposable profile
and checks the popup, native helper, and real browser proxy settings:

```sh
node tests/browser-smoke.mjs
```

After building the Arch package, verify automatic CRX installation and the
system-wide native helper in temporary Bubblewrap overlays (requires `bubblewrap`
with overlay support and Chromium):

```sh
PACKAGE_ROOT="$PWD/pkg/openvpn-proxy" node tests/browser-smoke.mjs
```

This uses a disposable browser profile and does not install the package onto
your system. Set `CHROMIUM_PATH=/usr/bin/google-chrome-stable` to test Chrome.

Chrome references: [proxy API](https://developer.chrome.com/docs/extensions/reference/api/proxy),
[SOCKS5 DNS behavior](https://github.com/chromium/chromium/blob/main/net/docs/proxy.md),
[native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging),
and [loading a personal extension](https://developer.chrome.com/docs/extensions/how-to/distribute).
