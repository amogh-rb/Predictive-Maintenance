#!/usr/bin/env bash
# Generates a dev-only CA plus a Mosquitto server cert for mTLS.
# Per-vehicle client certs are issued later by the simulator's cert-issuing
# script (session 2), keyed by VIN, using this same CA.
#
# Output goes to infra/certs/ca/ and infra/certs/issued/, both gitignored.
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CA_DIR="$CERT_DIR/ca"
ISSUED_DIR="$CERT_DIR/issued"
DAYS=825

mkdir -p "$CA_DIR" "$ISSUED_DIR"

if [ -f "$CA_DIR/ca.key" ]; then
  echo "Dev CA already exists at $CA_DIR/ca.key, skipping CA generation."
else
  echo "Generating dev CA..."
  openssl genrsa -out "$CA_DIR/ca.key" 4096
  openssl req -x509 -new -nodes -key "$CA_DIR/ca.key" -sha256 -days "$DAYS" \
    -subj "/O=FleetPulse Dev/CN=FleetPulse Dev CA" \
    -out "$CA_DIR/ca.crt"
fi

echo "Generating Mosquitto server cert..."
openssl genrsa -out "$ISSUED_DIR/server.key" 2048
openssl req -new -key "$ISSUED_DIR/server.key" \
  -subj "/O=FleetPulse Dev/CN=mosquitto" \
  -out "$ISSUED_DIR/server.csr"
openssl x509 -req -in "$ISSUED_DIR/server.csr" \
  -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" -CAcreateserial \
  -days "$DAYS" -sha256 \
  -out "$ISSUED_DIR/server.crt"

cp "$CA_DIR/ca.crt" "$ISSUED_DIR/ca.crt"
rm -f "$ISSUED_DIR/server.csr"

echo "Done. CA at $CA_DIR, server cert at $ISSUED_DIR."
echo "Client (per-VIN) certs are issued in session 2 by the simulator's cert script, signed by this CA."
