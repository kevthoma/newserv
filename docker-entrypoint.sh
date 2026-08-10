#!/usr/bin/env bash
# docker-entrypoint.sh -- make an empty bind-mounted system/ dir "just work".
#
# WHY: the image declares VOLUME /newserv/system and bakes the default config + game data there.
# When Unraid (or any `-v host:/newserv/system`) bind-mounts an EMPTY host dir, it SHADOWS those
# baked defaults, so newserv has no config and can't start. To avoid a manual seeding step, we keep
# a pristine copy at /newserv/system-default (created in the Dockerfile, OUTSIDE the volume) and, on
# first boot only, copy it into the mounted dir. After that the mount owns the data.
#
# On seed we also stamp the server's LocalAddress/ExternalAddress so it advertises the right IP to
# clients. LocalAddress is always the container's own LAN IP; ExternalAddress is $NEWSERV_EXTERNAL_ADDRESS
# if set (use this for a WAN/DDNS deploy), otherwise the same LAN IP (correct for a LAN-only canary).
#
# Idempotent + backward-compatible: if system/config.json already exists (e.g. Agrilat's existing
# appdata, or a second boot), we DON'T seed and DON'T rewrite addresses -- so a portal/operator's
# later live edits are never clobbered. The one exception: if $NEWSERV_EXTERNAL_ADDRESS is explicitly
# set, we refresh ExternalAddress on every boot (the DDNS knob: change the env, restart the container).
set -euo pipefail

SYS=/newserv/system
DEFAULT=/newserv/system-default
CFG="$SYS/config.json"

# Best-effort detection of this container's primary IPv4 (its br0 LAN address).
detect_ip() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    # source address newserv would use to reach the LAN/gateway
    ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')
  fi
  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then
    ip=$(hostname -i 2>/dev/null | awk '{print $1}')
  fi
  printf '%s' "$ip"
}

# In-place set of a "Key": "value" string field in the relaxed-JSON config (same approach as the
# legacy seed script; preserves the rest of the file).
set_addr() {
  local key="$1" val="$2"
  [ -n "$val" ] || return 0
  sed -i "s/\"$key\": \"[^\"]*\"/\"$key\": \"$val\"/" "$CFG"
}

if [ ! -f "$CFG" ]; then
  echo "[entrypoint] $CFG not found -- seeding from $DEFAULT (first boot)."
  mkdir -p "$SYS"
  cp -a "$DEFAULT/." "$SYS/"

  LAN_IP=$(detect_ip)
  EXT_IP="${NEWSERV_EXTERNAL_ADDRESS:-$LAN_IP}"
  echo "[entrypoint] stamping LocalAddress=${LAN_IP:-<unset>} ExternalAddress=${EXT_IP:-<unset>}"
  # Stamp each independently so an explicit NEWSERV_EXTERNAL_ADDRESS still applies even if LAN-IP
  # auto-detection came up empty.
  [ -n "$LAN_IP" ] && set_addr LocalAddress "$LAN_IP"
  [ -n "$EXT_IP" ] && set_addr ExternalAddress "$EXT_IP"
  if [ -z "$LAN_IP" ] && [ -z "$EXT_IP" ]; then
    echo "[entrypoint] WARNING: could not detect the container IP and no NEWSERV_EXTERNAL_ADDRESS set;" \
         "leaving LocalAddress/ExternalAddress at config defaults. Set them via the portal Game settings" \
         "page or NEWSERV_EXTERNAL_ADDRESS."
  fi
else
  echo "[entrypoint] $CFG already present -- not seeding."
  # DDNS/WAN knob: only touch ExternalAddress when the operator explicitly opted in via the env var.
  if [ -n "${NEWSERV_EXTERNAL_ADDRESS:-}" ]; then
    echo "[entrypoint] NEWSERV_EXTERNAL_ADDRESS set -- refreshing ExternalAddress=$NEWSERV_EXTERNAL_ADDRESS"
    set_addr ExternalAddress "$NEWSERV_EXTERNAL_ADDRESS"
  fi
fi

exec "$@"
