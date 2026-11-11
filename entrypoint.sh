#!/usr/bin/env bash
set -euo pipefail

[[ -r /vpn/client.ovpn ]] || { echo 'Mount your OpenVPN profile at /vpn/client.ovpn' >&2; exit 1; }

# Use the VPN host DNS so private VPN names resolve inside the tunnel.
# Microsocks resolves SOCKS5 hostnames here; its DNS packets must exit via tun0.
printf 'nameserver %s\n' "${VPN_DNS:-10.8.0.1}" > /etc/resolv.conf

# Only the proxy is restricted; OpenVPN must reach its server over eth0.
# Allow replies to incoming SOCKS connections, then require tun0 for egress.
iptables -A OUTPUT -m owner --uid-owner socks -p tcp --sport 1080 \
    -m conntrack --ctstate ESTABLISHED --ctdir REPLY -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner socks -o tun0 -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner socks -j REJECT
# Optional LAN allowlist: Docker preserves LAN client addresses; the host
# itself (loopback publishing) arrives from the bridge gateway.
if [[ -n "${PROXY_ALLOW:-}" ]]; then
    gateway=$(ip -4 route show default | awk '{print $3; exit}')
    [[ -n "$gateway" ]] || { echo 'Cannot find the Docker gateway for PROXY_ALLOW.' >&2; exit 1; }
    for source in "$gateway" ${PROXY_ALLOW//,/ }; do
        iptables -A INPUT -p tcp --dport 1080 -s "$source" -j ACCEPT
    done
    iptables -A INPUT -p tcp --dport 1080 -j REJECT --reject-with tcp-reset
fi
# This minimal setup tunnels IPv4 only. Fail closed for IPv6 proxy egress.
ip6tables -A OUTPUT -m owner --uid-owner socks -j REJECT

vpn_pid=
socks_pid=
cleanup() {
    trap - EXIT
    [[ -z "$socks_pid" ]] || kill "$socks_pid" 2>/dev/null || true
    [[ -z "$vpn_pid" ]] || kill "$vpn_pid" 2>/dev/null || true
    wait || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT

openvpn --cd /vpn --config client.ovpn --dev tun0 --dev-type tun \
    --redirect-gateway def1 --auth-nocache "$@" &
vpn_pid=$!
su-exec socks microsocks -i 0.0.0.0 -p 1080 &
socks_pid=$!

# Stop the container (and the other process) if either service exits.
wait -n "$vpn_pid" "$socks_pid"
