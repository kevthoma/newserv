#!/usr/bin/env bash
# docker-entrypoint.sh -- make an empty bind-mounted system/ dir "just work" + keep addresses current.
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
# ExternalAddress dynamic-IP self-heal: newserv parses ExternalAddress with inet_addr (numeric IPv4
# only -- no DNS), so a dynamic WAN IP would go stale on an ISP renumber and break WAN players. Set
# NEWSERV_EXTERNAL_ADDRESS=auto to have this entrypoint resolve the current public IP on boot AND run
# a background poller that, when the public IP changes, rewrites config.json + `reload config` (live,
# no restart). A literal IP (or unset) keeps the old behavior exactly -- the auto path is opt-in.
#
# Idempotent + backward-compatible: if system/config.json already exists we DON'T seed. We refresh
# ExternalAddress on every boot only when NEWSERV_EXTERNAL_ADDRESS is set (to the literal IP, or the
# current public IP in auto mode); other live edits are never clobbered.
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

# Fetch the current public IPv4 from an echo service (validated dotted-quad); empty/return-1 on failure.
fetch_public_ip() {
  local ip svc
  for svc in https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com; do
    ip=$(curl -fsS --max-time 8 "$svc" 2>/dev/null | tr -d '[:space:]')
    if printf '%s' "$ip" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
      printf '%s' "$ip"; return 0
    fi
  done
  return 1
}

# Current ExternalAddress value in the config (empty if unset/absent).
get_cfg_external() { sed -n 's/.*"ExternalAddress": *"\([^"]*\)".*/\1/p' "$CFG" 2>/dev/null | head -n1; }

# auto => track the current public IP (self-heal poller below); else the value is a literal IPv4/unset.
AUTO_EXT=0
[ "${NEWSERV_EXTERNAL_ADDRESS:-}" = "auto" ] && AUTO_EXT=1

# The intended ExternalAddress to stamp: the public IP in auto mode, else the literal env value.
resolve_ext() {
  if [ "$AUTO_EXT" -eq 1 ]; then
    fetch_public_ip
  else
    printf '%s' "${NEWSERV_EXTERNAL_ADDRESS:-}"
  fi
}

if [ ! -f "$CFG" ]; then
  echo "[entrypoint] $CFG not found -- seeding from $DEFAULT (first boot)."
  mkdir -p "$SYS"
  cp -a "$DEFAULT/." "$SYS/"

  LAN_IP=$(detect_ip)
  EXT_IP="$(resolve_ext || true)"; [ -n "$EXT_IP" ] || EXT_IP="$LAN_IP"
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
  # DDNS/WAN knob: refresh ExternalAddress when opted in (literal IP, or the current public IP if auto).
  if [ -n "${NEWSERV_EXTERNAL_ADDRESS:-}" ]; then
    EXT_IP="$(resolve_ext || true)"
    if [ -n "$EXT_IP" ]; then
      echo "[entrypoint] refreshing ExternalAddress=$EXT_IP"
      set_addr ExternalAddress "$EXT_IP"
    else
      echo "[entrypoint] NEWSERV_EXTERNAL_ADDRESS=auto but couldn't fetch the public IP; leaving ExternalAddress as-is"
    fi
  fi
fi

# WAN self-heal poller: in auto mode, keep ExternalAddress synced to the current public IP without a
# manual step. Runs alongside newserv; on a change it rewrites config.json + `reload config` (live).
if [ "$AUTO_EXT" -eq 1 ]; then
  interval="${NEWSERV_EXTERNAL_ADDRESS_INTERVAL:-300}"
  echo "[entrypoint] ExternalAddress auto-sync enabled (checking every ${interval}s)"
  (
    set +e
    while true; do
      sleep "$interval"
      new_ip="$(fetch_public_ip)" || continue
      cur="$(get_cfg_external)"
      [ -n "$new_ip" ] && [ "$new_ip" != "$cur" ] || continue
      echo "[ext-sync] public IP changed: ExternalAddress $cur -> $new_ip (updating + reload config)"
      set_addr ExternalAddress "$new_ip"
      curl -fsS --max-time 8 -X POST http://127.0.0.1:5000/y/shell-exec \
        -H 'Content-Type: application/json' -d '{"command":"reload config"}' >/dev/null 2>&1 \
        || echo "[ext-sync] reload-config request failed (will retry next cycle)"
    done
  ) &
fi

exec "$@"
