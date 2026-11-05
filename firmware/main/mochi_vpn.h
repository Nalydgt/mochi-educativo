#pragma once
#include <stdbool.h>
struct ifreq;

/* Call before starting any tasks that use cJSON. */
void mochi_vpn_prepare(void);
/* Nonblocking; call after Wi-Fi obtains an IP. Reuses the existing instance. */
void mochi_vpn_start(void);
/* Persists configuration for the next boot. Does not alter a live session. */
bool mochi_vpn_configure(const char *auth_key, const char *priority_peer_ip);
bool mochi_vpn_configured(void);
bool mochi_vpn_ready(void);
const char *mochi_vpn_status_text(void);
bool mochi_vpn_bind_interface(const char *peer_ip, struct ifreq *out);
bool mochi_vpn_self_test(void);
void mochi_vpn_diagnose(void);
