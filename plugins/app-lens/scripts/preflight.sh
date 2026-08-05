#!/usr/bin/env bash

set -u

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
check_command aapt 'optional Android package metadata extraction'
check_command aapt2 'optional Android package metadata extraction'
check_command adb 'optional isolated-emulator exploration'
check_command emulator 'optional isolated-emulator exploration'
check_command jadx 'optional restricted reverse-static UI structure analysis'
check_command flutter 'optional generated-prototype verification'

printf '\nNo software was installed and no device was accessed.\n'
