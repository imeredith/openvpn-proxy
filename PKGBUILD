# Local package: run makepkg -si from this checkout.
pkgname=openvpn-proxy
pkgver=1.1.0
pkgrel=1
pkgdesc='OpenVPN SOCKS5 container launcher, proxied SSH, and Chrome site whitelist'
arch=('any')
depends=('bash' 'coreutils' 'docker' 'openssh' 'socat>=1.8.0.0' 'python' 'sudo' 'systemd')
makedepends=('openssl')
optdepends=('chromium: browser for the bundled extension' 'google-chrome: browser for the bundled extension')
conflicts=('pssh')
options=('!debug' '!strip')
install=packaging/openvpn-proxy.install
source=(
  'openvpn-proxy' 'pssh' 'Dockerfile' 'entrypoint.sh' '.dockerignore' 'README.md'
)
# This is a checkout-local package, not an AUR/source-archive recipe.
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP' 'SKIP' 'SKIP')

prepare() {
  # makepkg's local source resolver does not support subdirectories.
  cp "$startdir/native/proxy_check.py" "$srcdir/proxy_check.py"
  cp "$startdir/packaging/build-extension.py" "$srcdir/build-extension.py"
  mkdir -p "$srcdir/extension"
  local file
  for file in manifest.json background.js rules.mjs popup.html popup.css popup.js; do
    cp "$startdir/extension/$file" "$srcdir/extension/$file"
  done
}

build() {
  # Keep this key outside src/ so makepkg --cleanbuild preserves extension identity.
  python "$srcdir/build-extension.py" "$srcdir/extension" \
    "$startdir/.extension-signing-key.pem" "$srcdir/chrome-package"
}

check() {
  bash -n "$srcdir/openvpn-proxy" "$srcdir/pssh" "$srcdir/entrypoint.sh"
  python -m json.tool "$srcdir/extension/manifest.json" >/dev/null
}

package() {
  install -Dm755 "$srcdir/openvpn-proxy" "$pkgdir/usr/bin/openvpn-proxy"
  install -Dm755 "$srcdir/pssh" "$pkgdir/usr/bin/pssh"
  local file
  for file in Dockerfile entrypoint.sh .dockerignore; do
    install -Dm644 "$srcdir/$file" "$pkgdir/usr/share/$pkgname/docker/$file"
  done
  install -Dm644 "$srcdir/README.md" "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm755 "$srcdir/proxy_check.py" "$pkgdir/usr/lib/$pkgname/proxy-check"
  install -Dm644 "$srcdir/chrome-package/extension.crx" "$pkgdir/usr/share/$pkgname/extension.crx"
  local extension_id
  extension_id=$(cat "$srcdir/chrome-package/extension-id")
  for file in google-chrome chromium; do
    install -Dm644 "$srcdir/chrome-package/$extension_id.json" \
      "$pkgdir/usr/share/$file/extensions/$extension_id.json"
  done
  for file in opt/chrome chromium; do
    install -Dm644 "$srcdir/chrome-package/org.openvpn_socks.packaged_check.json" \
      "$pkgdir/etc/$file/native-messaging-hosts/org.openvpn_socks.packaged_check.json"
  done
}
