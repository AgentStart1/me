#!/usr/bin/env bash
set -euo pipefail

LOCK_PATH="/data/local/tmp/android-device-test.lock.d"
PROJECT_DIR=""
TEST_NAME=""
MAX_TIMEOUT_SECONDS="1800"
WAIT_TIMEOUT_SECONDS="1800"
POLL_SECONDS="5"
TOKEN_FILE=""
SERIAL=""
COMMAND=()

METADATA_PYTHON=

resolve_metadata_python() {
  local candidate
  local -a candidates=(python3 python)
  [ -z "${ANDROID_DEVICE_LOCK_PYTHON:-}" ] || candidates=("$ANDROID_DEVICE_LOCK_PYTHON")
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info.major >= 3 else 1)' >/dev/null 2>&1; then
      METADATA_PYTHON="$candidate"; return 0
    fi
  done
  echo 'Error: Device lock metadata requires Python 3; set ANDROID_DEVICE_LOCK_PYTHON.' >&2
  return 1
}

usage() {
  cat <<'USAGE'
Usage:
  adb-device-lock.sh acquire [options]
  adb-device-lock.sh release [options]
  adb-device-lock.sh renew [options]
  adb-device-lock.sh run [options] -- command [args...]

Options:
  --serial SERIAL                  adb device serial; optional when only one device is connected
  --lock-path PATH                 device-side lock directory (default: /data/local/tmp/android-device-test.lock.d)
  --project-dir DIR                project directory recorded in lock metadata
  --test-name NAME                 test name recorded in lock metadata
  --max-timeout-seconds SECONDS    lease duration before a lock is stale (default: 1800)
  --wait-timeout-seconds SECONDS   max time to wait for another lock (default: 1800)
  --poll-seconds SECONDS           polling interval while waiting (default: 5)
  --token-file FILE                local file used to store/read the owner token
USAGE
}

adb_cmd() {
  if [[ -n "$SERIAL" ]]; then
    MSYS_NO_PATHCONV=1 adb -s "$SERIAL" "$@"
  else
    MSYS_NO_PATHCONV=1 adb "$@"
  fi
}

shell_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

push_metadata() {
  local source="$1"
  if command -v cygpath >/dev/null 2>&1; then
    source="$(cygpath -w "$source")"
  fi
  adb_cmd push "$source" "$(lock_json_path).tmp" >/dev/null || return 1
  adb_cmd shell "mv $(shell_quote "$(lock_json_path).tmp") $(shell_quote "$(lock_json_path)")" >/dev/null
}

remote_exists() {
  adb_cmd shell "[ -e $(shell_quote "$1") ]" >/dev/null 2>&1
}

remote_read() {
  adb_cmd shell "cat $(shell_quote "$1") 2>/dev/null" 2>/dev/null || true
}

remote_rm_lock() {
  adb_cmd shell "rm -rf $(shell_quote "$LOCK_PATH")" >/dev/null
}

lock_json_path() {
  printf "%s/lock.json" "$LOCK_PATH"
}

now_epoch() {
  date +%s
}

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

make_token() {
  printf "%s:%s:%s:%s" "$(hostname 2>/dev/null || printf unknown-host)" "$$" "$(now_epoch)" "$RANDOM"
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

metadata_field() {
  PYTHONIOENCODING=utf-8 "$METADATA_PYTHON" "$SCRIPT_DIR/lock-metadata.py" "$1" "$2"
}

extract_json_number() { metadata_field number "$1"; }
extract_json_string() { metadata_field string "$1"; }

write_metadata() {
  local token="$1"
  local requested_at="$2"
  local acquired_at="$3"
  local expires_at="$4"
  local tmp_file
  tmp_file="$(mktemp)"
  if ! PYTHONIOENCODING=utf-8 "$METADATA_PYTHON" "$SCRIPT_DIR/lock-metadata.py" render \
      "$PROJECT_DIR" "$TEST_NAME" "$requested_at" "$acquired_at" \
      "$MAX_TIMEOUT_SECONDS" "$expires_at" "$(hostname 2>/dev/null || printf unknown-host)" \
      "$$" "$SERIAL" "$LOCK_PATH" "$token" >"$tmp_file"; then
    rm -f "$tmp_file"; return 1
  fi
  if ! push_metadata "$tmp_file"; then rm -f "$tmp_file"; return 1; fi
  rm -f "$tmp_file"
}

print_existing_lock() {
  local metadata
  metadata="$(remote_read "$(lock_json_path)")"
  if [[ -n "$metadata" ]]; then
    printf '%s' "$metadata" | metadata_field summary '' >&2 ||
      echo 'Existing lease metadata is unreadable; ownership remains unknown.' >&2
  else
    printf "No readable lease metadata at %s; inspect lease and mutation guard state.\n" "$LOCK_PATH" >&2
  fi
}

try_acquire_once() {
  adb_cmd shell "mkdir $(shell_quote "$LOCK_PATH")" >/dev/null 2>&1
}

# Every participant must use this guard protocol: mkdir alone cannot protect
# expiry check/remove/reacquire or token-checked release/renew.
with_device_guard() {
  local callback="$1"; shift
  (
    local guard="${LOCK_PATH}.guard"
    adb_cmd shell "mkdir $(shell_quote "$guard")" >/dev/null 2>&1 || return 1
    cleanup_guard() {
      local status=$?
      trap - EXIT INT TERM
      adb_cmd shell "rmdir $(shell_quote "$guard")" >/dev/null || status=2
      exit "$status"
    }
    trap cleanup_guard EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    "$callback" "$@"
  )
}

acquire_guarded() {
  local token="$1" requested_at="$2"
  if ! try_acquire_once; then
    local metadata expires_at now
    metadata="$(remote_read "$(lock_json_path)")"
    expires_at="$(printf '%s' "$metadata" | extract_json_number expires_at_epoch || true)"
    now="$(now_epoch)"
    [[ -n "$expires_at" && "$expires_at" -le "$now" ]] || return 1
    remote_rm_lock || return 2
    try_acquire_once || return 2
  fi
  local acquired_at expires_at
  acquired_at="$(now_utc)"
  expires_at=$(( $(now_epoch) + MAX_TIMEOUT_SECONDS ))
  if ! write_metadata "$token" "$requested_at" "$acquired_at" "$expires_at" ||
      ! printf '%s\n' "$token" > "$TOKEN_FILE"; then
    remote_rm_lock || true
    return 2
  fi
  printf 'Acquired Android device lock at %s\n' "$LOCK_PATH" >&2
}

acquire_lock() {
  adb_cmd get-state >/dev/null

  local requested_at token deadline
  requested_at="$(now_utc)"
  token="$(make_token)"
  deadline=$(( $(now_epoch) + WAIT_TIMEOUT_SECONDS ))

  while true; do
    local status=0 now
    with_device_guard acquire_guarded "$token" "$requested_at" || status=$?
    [ "$status" -ne 0 ] || return 0
    [ "$status" -eq 1 ] || return "$status"
    now="$(now_epoch)"

    if [[ "$now" -ge "$deadline" ]]; then
      printf "Timed out waiting for Android device lock at %s\n" "$LOCK_PATH" >&2
      print_existing_lock
      return 1
    fi

    printf "Waiting for Android device lock at %s\n" "$LOCK_PATH" >&2
    sleep "$POLL_SECONDS"
  done
}

release_lock() {
  adb_cmd get-state >/dev/null || return 1

  if ! remote_exists "$LOCK_PATH"; then
    printf "No Android device lock exists at %s\n" "$LOCK_PATH" >&2
    return 0
  fi

  local expected_token metadata actual_token
  if [[ -n "$TOKEN_FILE" && -f "$TOKEN_FILE" ]]; then
    expected_token="$(tr -d '\r\n' <"$TOKEN_FILE")"
  else
    printf "release requires --token-file containing the owner token\n" >&2
    return 2
  fi

  metadata="$(remote_read "$(lock_json_path)")"
  actual_token="$(printf "%s" "$metadata" | extract_json_string owner_token || true)"
  if [[ -z "$actual_token" || "$actual_token" != "$expected_token" ]]; then
    printf "Refusing to release Android device lock: owner token does not match\n" >&2
    return 1
  fi

  if ! remote_rm_lock; then
    printf "Failed to delete Android device lock; owner token retained for recovery.\n" >&2
    return 1
  fi
  rm -f "$TOKEN_FILE" || return 1
  printf "Released Android device lock at %s\n" "$LOCK_PATH" >&2
}

finish_run() {
  local status="$1"
  trap - EXIT INT TERM
  if ! with_device_guard release_lock; then
    echo 'Release failed or mutation guard busy; owner token retained for recovery.' >&2
    [ "$status" -ne 0 ] || status=1
  fi
  exit "$status"
}

renew_lock() {
  adb_cmd get-state >/dev/null

  if ! remote_exists "$LOCK_PATH"; then
    printf "No Android device lock exists at %s\n" "$LOCK_PATH" >&2
    return 1
  fi

  local expected_token metadata actual_token
  if [[ -n "$TOKEN_FILE" && -f "$TOKEN_FILE" ]]; then
    expected_token="$(tr -d '\r\n' <"$TOKEN_FILE")"
  else
    printf "renew requires --token-file containing the owner token\n" >&2
    return 2
  fi

  metadata="$(remote_read "$(lock_json_path)")"
  actual_token="$(printf "%s" "$metadata" | extract_json_string owner_token || true)"
  if [[ -z "$actual_token" || "$actual_token" != "$expected_token" ]]; then
    printf "Refusing to renew Android device lock: owner token does not match\n" >&2
    return 1
  fi

  local new_expires_at tmp_file
  new_expires_at=$(( $(now_epoch) + MAX_TIMEOUT_SECONDS ))
  tmp_file="$(mktemp)"
  if ! printf '%s' "$metadata" | PYTHONIOENCODING=utf-8 "$METADATA_PYTHON" \
      "$SCRIPT_DIR/lock-metadata.py" renew "$MAX_TIMEOUT_SECONDS" "$new_expires_at" \
      "$SERIAL" "$LOCK_PATH" >"$tmp_file"; then
    rm -f "$tmp_file"; return 1
  fi
  if ! push_metadata "$tmp_file"; then rm -f "$tmp_file"; return 1; fi
  rm -f "$tmp_file"
  printf "Renewed Android device lock at %s, expires at epoch %d\n" "$LOCK_PATH" "$new_expires_at" >&2
}

parse_args() {
  if [[ $# -lt 1 ]]; then
    usage >&2
    exit 2
  fi

  if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    usage
    exit 0
  fi

  local mode="$1"
  shift

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --serial)
        SERIAL="$2"; shift 2 ;;
      --lock-path)
        LOCK_PATH="$2"; shift 2 ;;
      --project-dir)
        PROJECT_DIR="$2"; shift 2 ;;
      --test-name)
        TEST_NAME="$2"; shift 2 ;;
      --max-timeout-seconds)
        MAX_TIMEOUT_SECONDS="$2"; shift 2 ;;
      --wait-timeout-seconds)
        WAIT_TIMEOUT_SECONDS="$2"; shift 2 ;;
      --poll-seconds)
        POLL_SECONDS="$2"; shift 2 ;;
      --token-file)
        TOKEN_FILE="$2"; shift 2 ;;
      --help|-h)
        usage; exit 0 ;;
      --)
        shift
        COMMAND=("$@")
        break ;;
      *)
        printf "Unknown argument: %s\n" "$1" >&2
        usage >&2
        exit 2 ;;
    esac
  done

  if [[ -z "$PROJECT_DIR" ]]; then
    PROJECT_DIR="$(pwd)"
  fi
  if [[ ! "$LOCK_PATH" =~ ^/data/local/tmp/[^/]+(/[^/]+)*$ || "$LOCK_PATH" == *'/../'* || "$LOCK_PATH" == *'/./'* || "$LOCK_PATH" == */.. || "$LOCK_PATH" == */. ]]; then
    echo 'Error: lock path must name a directory below /data/local/tmp without parent traversal.' >&2
    exit 2
  fi
  for value in "$MAX_TIMEOUT_SECONDS" "$POLL_SECONDS"; do
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo 'Error: lease duration and poll interval must be positive integers.' >&2; exit 2; }
  done
  [[ "$WAIT_TIMEOUT_SECONDS" =~ ^(0|[1-9][0-9]*)$ ]] || { echo 'Error: wait timeout must be a nonnegative integer.' >&2; exit 2; }
  if [[ -z "$TEST_NAME" ]]; then
    TEST_NAME="android-device-test"
  fi
  if [[ -z "$TOKEN_FILE" ]]; then
    TOKEN_FILE="$(mktemp)"
  fi

  resolve_metadata_python || return 1

  case "$mode" in
    acquire)
      acquire_lock ;;
    release)
      with_device_guard release_lock || { echo 'Release failed or mutation guard busy; inspect ownership before retrying.' >&2; return 1; } ;;
    renew)
      with_device_guard renew_lock || { echo 'Renew failed or mutation guard busy; stop device work if the lease cannot be renewed.' >&2; return 1; } ;;
    run)
      if [[ ${#COMMAND[@]} -eq 0 ]]; then
        printf "run requires a command after --\n" >&2
        exit 2
      fi
      acquire_lock
      trap 'finish_run "$?"' EXIT
      trap 'finish_run 130' INT
      trap 'finish_run 143' TERM
      "${COMMAND[@]}" ;;
    *)
      printf "Unknown command: %s\n" "$mode" >&2
      usage >&2
      exit 2 ;;
  esac
}

parse_args "$@"
