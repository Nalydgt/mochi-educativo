# MicroLink source used by Mochi

Source: <https://github.com/Csontikka/esphome-tailscale>, tag `v0.5.28`,
commit `0a34e85f1a0483e8bf4cb9951dbf1ac531f9fcf0` (20 October 2026).
Vendored from `microlink/components/microlink`; its `wireguard_lwip` dependency
is registered as the sibling component `../wireguard_lwip`.

MicroLink's MIT license, X25519 notice and the ESPHome wrapper's MIT notice are
preserved as `LICENSE`, `x25519-license.txt` and `ESPHOME-LICENSE`. The dependency
has its own `LICENSE`. This is an independent Tailscale-compatible client.

Local integration changes:

- Native ESP-IDF 6 dependency names (`espressif__cjson`), with cellular drivers
  and the HTTP configuration server excluded from this application build.
- Noise ChaCha20-Poly1305 uses the public PSA API required by mbedTLS 4.
  Noise message construction checks AEAD errors. `microlink_crypto_self_test`
  checks independently generated OpenSSL vectors, tag tampering and empty
  handshake payloads. The device must run this check before connecting.
- DERP uses mbedTLS 4's PSA randomness, mandatory certificate-bundle checking
  and hostname verification. The Mochi wrapper also requires a verified HTTPS
  connection to the Tailscale control plane for fetching its Noise key.
- Global cJSON allocation hooks are installed by `mochi_vpn_prepare` before
  concurrent application tasks, rather than changed during VPN startup.
- WireGuard registers its interface using `netif_add` on the lwIP thread,
  assigning a unique interface index for binding private HTTP sockets.
- ESP-IDF's separate ESP-NETIF client-data slot is enabled by PPP support in
  the project configuration; no PPP link is started. Otherwise the SDK's
  global netif callback miscasts WireGuard's private state and crashes.
  A compile-time guard prevents that unsupported configuration.
- TLS/PSA allocations use PSRAM. The control connection and the verified
  Noise-key fetch can overlap; internal-only allocation ran out of RAM while
  verifying certificates on the board. Certificate checks remain mandatory.
- WireGuard RX, periodic maintenance and peer/key updates execute on that same
  lwIP thread as packet output. This serializes key rotation and counter use;
  a transmit-only mutex cannot protect a keypair being replaced by RX.
- Protocol constants retain their exact byte lengths without NUL terminators,
  annotated as nonstring for the ESP-IDF 6 compiler. Peer hostname copies use
  the full fixed-size source array and explicitly terminate the destination.
- The peer-update queue holds eight entries for Mochi's two-peer configuration.
  Map buffers are 128 KiB in PSRAM; the NVS cache is limited to sixteen peers.
- Optional `follow_priority_derp` uses the priority server's authenticated
  HomeDERP, including NodeID-based incremental changes, and validates the
  region against the DERPMap. The coordinator reconnects the single relay and
  publishes the new PreferredDERP. This avoids depending on an incoming ping
  when the server and device would otherwise choose different home relays.
  Unused latency sweeps are skipped in this single-server mode.
- Binding private HTTP permits an administratively up WG interface before its
  first session becomes link-up, allowing the first bound SYN to initiate the
  handshake without allowing a Wi-Fi fallback.
- Uplink changes clear stale LAN/NAT endpoints and DISCO probes on the peer
  manager, using the serialized WG APIs without resetting session counters.
  Traffic resumes through DERP while new direct paths are discovered. The
  readiness snapshot also checks registration/relay event bits, which rebind
  clears immediately, instead of reporting a stale connection during a roam.
- DERP TX/RX task stacks use 8 KiB each. On the board, the TX high-water mark
  after TLS enrollment and a private HTTP request leaves 3.5 KiB unused; RX
  leaves 5.7 KiB. The application exposes these measurements via `@audio`.
  Wi-Fi/lwIP allocations prefer PSRAM using the ESP-IDF configuration option,
  preserving internal memory for audio/display DMA during VPN transfers.
  This option requires static Wi-Fi TX buffers on ESP32-S3: Mochi uses four,
  with a 32-packet PSRAM cache. Six static RX buffers match the RX BA window.
  Leaving the SDK's sixteen static TX buffers exhausts memory before WG starts.

Machine/node/discovery identity is retained in MicroLink's NVS namespaces.
The application separately stores its enrollment key and priority peer in
`mochi_vpn`; Wi-Fi, volume and GPS namespaces are preserved. The wrapper does
not advertise routes, select an exit node, enable Funnel or run a web server.

This remains a community-client integration. On the Mochi board, enrollment,
cold reconnection, iPhone hotspot access, private TCP audio and concurrent
display/audio operation have been verified. Firmware 0.6.2 received two real
voice replies over WireGuard/DERP, returned to idle without resetting, and the
user confirmed audible replies. A successful build alone is not a runtime or
cryptographic test result; these checks do not establish long-term reliability.
