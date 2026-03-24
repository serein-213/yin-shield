#!/usr/bin/env bash
set -euo pipefail

PACKAGE_SPEC="${YINSHIELD_PACKAGE_SPEC:-yinshield}"
PLUGIN_PACKAGE="${YINSHIELD_OPENCLAW_PLUGIN_PACKAGE:-@serein-213/openclaw-yinshield}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found." >&2
  exit 1
fi

if ! command -v openclaw >/dev/null 2>&1; then
  echo "openclaw is required but was not found." >&2
  exit 1
fi

echo "Installing or upgrading ${PACKAGE_SPEC}..."
python3 -m pip install --upgrade "${PACKAGE_SPEC}"

echo "Scaffolding YinShield config for OpenClaw..."
python3 -m yinshield.install_openclaw "$@"

echo "Installing OpenClaw plugin ${PLUGIN_PACKAGE}..."
openclaw plugins install "${PLUGIN_PACKAGE}"

echo "Enabling OpenClaw plugin openclaw-yinshield..."
openclaw plugins enable openclaw-yinshield

echo
echo "Bootstrap complete."
echo "Start the local bridge with the auth token printed above:"
echo "  yinshield serve"
