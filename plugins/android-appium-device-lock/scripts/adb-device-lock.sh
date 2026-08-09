#!/usr/bin/env bash
set -euo pipefail

LOCK_PATH="/data/local/tmp/appium-device-test.lock.d"
PROJECT_DIR=""
TEST_NAME=""
MAX_TIMEOUT_SECONDS="1800"
WAIT_TIMEOUT_SECONDS="1800"
POLL_SECONDS="5"
TOKEN_FILE=""
SERIAL=""
COMMAND=()

usage() {
  cat <<'USAGE'
Usage:
  adb-device-lock.sh acquire [options]
  adb-device-lock.sh release [options]
  adb-device-lock.sh renew [options]
  adb-device-lock.sh run [options] -- command [args...]

Options:
  --serial SERIAL                  adb device serial; optional when only one device is connected
  --lock-path PATH                 device-side lock directory (default: /data/local/tmp/appium-device-test.lock.d)
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
    adb -s "$SERIAL" "$@"
  else
    adb "$@"
  fi
}

shell_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

json_escape() {
  printf "%s" "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
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

extract_json_number() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p" | head -n 1
}

extract_json_string() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" | head -n 1
}

write_metadata() {
  local token="$1"
  local requested_at="$2"
  local acquired_at="$3"
  local expires_at="$4"
  local tmp_file
  tmp_file="$(mktemp)"
  cat >"$tmp_file" <<JSON
{
  "project_dir": "$(json_escape "$PROJECT_DIR")",
  "test_name": "$(json_escape "$TEST_NAME")",
  "requested_at_utc": "$requested_at",
  "acquired_at_utc": "$acquired_at",
  "max_timeout_seconds": $MAX_TIMEOUT_SECONDS,
  "expires_at_epoch": $expires_at,
  "host": "$(json_escape "$(hostname 2>/dev/null || printf unknown-host)")",
  "pid": $$,
  "adb_serial": "$(json_escape "$SERIAL")",
  "lock_path": "$(json_escape "$LOCK_PATH")",
  "owner_token": "$(json_escape "$token")"
}
JSON
  adb_cmd push "$tmp_file" "$(lock_json_path)" >/dev/null
  rm -f "$tmp_file"
}

print_existing_lock() {
  local metadata
  metadata="$(remote_read "$(lock_json_path)")"
  if [[ -n "$metadata" ]]; then
    printf "%s\n" "$metadata" >&2
  else
    printf "Lock exists at %s, but no readable lock.json was found.\n" "$LOCK_PATH" >&2
  fi
}

try_acquire_once() {
  adb_cmd shell "mkdir $(shell_quote "$LOCK_PATH")" >/dev/null 2>&1
}

acquire_lock() {
  adb_cmd get-state >/dev/null

  local requested_at token deadline
  requested_at="$(now_utc)"
  token="$(make_token)"
  deadline=$(( $(now_epoch) + WAIT_TIMEOUT_SECONDS ))

  while true; do
    if try_acquire_once; then
      local acquired_at expires_at
      acquired_at="$(now_utc)"
      expires_at=$(( $(now_epoch) + MAX_TIMEOUT_SECONDS ))
      write_metadata "$token" "$requested_at" "$acquired_at" "$expires_at"
      if [[ -n "$TOKEN_FILE" ]]; then
        printf "%s\n" "$token" >"$TOKEN_FILE"
      fi
      printf "Acquired Android device lock at %s\n" "$LOCK_PATH" >&2
      return 0
    fi

    local metadata expires_at now
    metadata="$(remote_read "$(lock_json_path)")"
    expires_at="$(printf "%s" "$metadata" | extract_json_number expires_at_epoch || true)"
    now="$(now_epoch)"
    if [[ -n "$expires_at" && "$expires_at" -le "$now" ]]; then
      printf "Removing expired Android device lock at %s\n" "$LOCK_PATH" >&2
      remote_rm_lock
      continue
    fi

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
  adb_cmd get-state >/dev/null

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

  remote_rm_lock
  rm -f "$TOKEN_FILE"
  printf "Released Android device lock at %s\n" "$LOCK_PATH" >&2
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
  cat >"$tmp_file" <<JSON
{
  "project_dir": "$(json_escape "$(printf "%s" "$metadata" | extract_json_string project_dir)")",
  "test_name": "$(json_escape "$(printf "%s" "$metadata" | extract_json_string test_name)")",
  "requested_at_utc": "$(printf "%s" "$metadata" | extract_json_string requested_at_utc)",
  "acquired_at_utc": "$(printf "%s" "$metadata" | extract_json_string acquired_at_utc)",
  "max_timeout_seconds": $MAX_TIMEOUT_SECONDS,
  "expires_at_epoch": $new_expires_at,
  "host": "$(json_escape "$(printf "%s" "$metadata" | extract_json_string host)")",
  "pid": $(printf "%s" "$metadata" | extract_json_number pid || echo 0),
  "adb_serial": "$(json_escape "$SERIAL")",
  "lock_path": "$(json_escape "$LOCK_PATH")",
  "owner_token": "$(json_escape "$actual_token")"
}
JSON
  adb_cmd push "$tmp_file" "$(lock_json_path)" >/dev/null
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
  if [[ -z "$TEST_NAME" ]]; then
    TEST_NAME="android-appium-test"
  fi
  if [[ -z "$TOKEN_FILE" ]]; then
    TOKEN_FILE="$(mktemp)"
  fi

  case "$mode" in
    acquire)
      acquire_lock ;;
    release)
      release_lock ;;
    renew)
      renew_lock ;;
    run)
      if [[ ${#COMMAND[@]} -eq 0 ]]; then
        printf "run requires a command after --\n" >&2
        exit 2
      fi
      acquire_lock
      trap 'status=$?; release_lock || true; exit "$status"' EXIT
      trap 'status=$?; trap - EXIT INT TERM; release_lock || true; exit "$status"' INT TERM
      "${COMMAND[@]}" ;;
    *)
      printf "Unknown command: %s\n" "$mode" >&2
      usage >&2
      exit 2 ;;
  esac
}

parse_args "$@"
