#!/usr/bin/env bash
# Demo helper: run the app as a self-contained Wi-Fi access point so a room
# full of people can reach it without depending on the venue network.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/venv/bin/python3"          # venv shebangs are broken, call python directly
CON="mns-demo"
IFACE="wlp0s20f3"
SSID="MNS-DEMO"
PSK="demo12345"
PORT=8000

qr() { "$PY" -c "
import sys, qrcode
q = qrcode.QRCode(border=1)
q.add_data(sys.argv[1]); q.make()
q.print_ascii(invert=True)" "$1"; }

ip_of() { ip -4 -br addr show "$IFACE" | awk '{print $3}' | cut -d/ -f1; }

case "${1:-}" in
  on)
    echo "Starting access point '$SSID'..."
    echo "NOTE: this disconnects $IFACE from your router. Internet will drop."
    nmcli connection up "$CON"
    for _ in $(seq 20); do [ -n "$(ip_of)" ] && break; sleep 0.5; done
    "$0" qr
    ;;
  off)
    nmcli connection down "$CON" 2>/dev/null || true
    echo "Access point stopped. Reconnecting to your normal Wi-Fi..."
    sleep 2
    nmcli -g NAME,DEVICE connection show --active | grep "$IFACE" || \
      echo "Not auto-reconnected. Run: nmcli device wifi connect <YOUR_SSID>"
    ;;
  qr)
    addr="$(ip_of)"
    [ -z "$addr" ] && { echo "No IP on $IFACE - is the hotspot running?"; exit 1; }
    echo
    echo "=== 1. JOIN THE WI-FI (scan, or connect manually) ==="
    echo "    SSID: $SSID    password: $PSK"
    qr "WIFI:T:WPA;S:${SSID};P:${PSK};;"
    echo "=== 2. THEN OPEN THE APP ==="
    echo "    http://${addr}:${PORT}"
    qr "http://${addr}:${PORT}"
    ;;
  serve)
    cd "$ROOT/app"                    # main:app resolves relative to app/
    exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
    ;;
  *)
    echo "usage: $0 {on|off|qr|serve}"
    echo "  on     start the Wi-Fi access point (drops your internet)"
    echo "  off    stop it and return to normal Wi-Fi"
    echo "  qr     reprint the join + app QR codes"
    echo "  serve  run uvicorn for the demo (no --reload)"
    exit 1
    ;;
esac
