#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

check_command() {
  local command_name="$1"
  local purpose="$2"

  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'available  %-12s %s\n' "$command_name" "$purpose"
  else
    printf 'missing    %-12s %s\n' "$command_name" "$purpose"
  fi
}

printf 'AppLens preflight\n'
check_command python3 'required for included inventory scripts'
check_command aapt 'required Android package metadata extraction'
check_command aapt2 'acceptable aapt replacement when aapt is unavailable'
check_command adb 'optional isolated-emulator exploration'
check_command emulator 'optional isolated-emulator exploration'
check_command jadx 'required restricted reverse-static UI structure analysis'
check_command flutter 'optional generated-prototype verification'

printf '\n'
if python3 "$SCRIPT_DIR/require_analysis_tools.py"; then
  printf 'No software was installed and no device was accessed.\n'
else
  printf 'No software was installed. AppLens will not generate a reduced-evidence analysis.\n' >&2
  exit 2
fi
