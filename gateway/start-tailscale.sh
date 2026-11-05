#!/bin/sh
# Keep interactive registration alive: containerboot limits startup to 60 s.
set -eu
mkdir -p /var/run/tailscale /var/lib/tailscale
tailscaled --tun=userspace-networking \
    --state=/var/lib/tailscale/tailscaled.state \
    --socket=/var/run/tailscale/tailscaled.sock &
mochi_vpn_pid=$!
trap 'kill "$mochi_vpn_pid" 2>/dev/null || true; wait "$mochi_vpn_pid" 2>/dev/null || true' EXIT
trap 'exit 0' TERM INT
while ! tailscale status --json >/dev/null 2>&1; do
    kill -0 "$mochi_vpn_pid"
    sleep 1
done
(
    tailscale up --hostname=mochi --accept-dns=false --timeout=0
    # Userspace networking needs an explicit private inbound TCP forward.
    # This is tailnet-only Serve, protected again by the gateway's device key.
    tailscale serve --bg --tcp=8765 tcp://127.0.0.1:8765
) &
wait "$mochi_vpn_pid"
