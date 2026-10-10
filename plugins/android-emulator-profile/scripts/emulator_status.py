"""Read-only AVD inventory, emulator boot state, and on-demand screen capture."""
import base64
import os
from pathlib import Path
import re

from android_probe import ProbeError, adb, collect_devices, devices, native_path, observed_at, validate_serial

ROOT = Path(__file__).resolve().parents[1]
PROPERTIES = "getprop sys.boot_completed; getprop ro.boot.qemu.avd_name; getprop ro.build.version.release; getprop ro.build.version.sdk; getprop ro.kernel.qemu"


def read_ini(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith(("#", ";")):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def configured_avds():
    android_user = Path(native_path(os.environ.get("ANDROID_USER_HOME") or Path.home() / ".android"))
    avd_home = Path(native_path(os.environ.get("ANDROID_AVD_HOME") or android_user / "avd"))
    items, warnings = [], []
    try:
        paths = sorted(avd_home.glob("*.ini"))
        if avd_home.exists() and not avd_home.is_dir():
            raise OSError("Not a directory")
    except OSError:
        return [], ["AVD inventory could not be read"]
    for path in paths:
        try:
            descriptor = read_ini(path)
            directory = Path(native_path(descriptor["path"])) if descriptor.get("path") else avd_home / f"{path.stem}.avd"
            config = read_ini(directory / "config.ini")
            items.append({"name": path.stem, "api": descriptor.get("target", "").removeprefix("android-"),
                          "abi": config.get("abi.type", ""), "memory": config.get("hw.ramSize", ""),
                          "resolution": " × ".join(filter(None, [config.get("hw.lcd.width"), config.get("hw.lcd.height")])),
                          "configured": True})
        except (OSError, ValueError):
            items.append({"name": path.stem, "configured": True, "detail": "AVD configuration is unreadable"})
    return items, warnings


def inspect_device(device):
    emulator_serial = bool(re.fullmatch(r"emulator-[0-9]+", device["serial"]))
    if device["connection"] != "device":
        return {**device, "name": device["model"] or device["serial"], "state": device["connection"], "detail": "Boot state cannot be read"} if emulator_serial else None
    try:
        values = adb(["shell", PROPERTIES], device["serial"]).splitlines()
        if len(values) < 5:
            raise ProbeError("Emulator properties are incomplete")
        boot, name, version, api, qemu = values[:5]
        if not emulator_serial and qemu.strip() != "1":
            return None
        if not name.strip() and emulator_serial:
            try:
                name = next((line.strip() for line in adb(["emu", "avd", "name"], device["serial"]).splitlines() if line.strip() and line.strip() != "OK"), "")
            except ProbeError:
                pass
        return {**device, "name": name.strip() or "Unidentified emulator", "avdName": name.strip(),
                "state": "online" if boot.strip() == "1" else "booting", "androidVersion": version.strip(),
                "api": api.strip(), "bootCompleted": boot.strip() == "1"}
    except ProbeError as error:
        return {**device, "name": device["model"] or device["serial"], "state": "unknown", "detail": str(error)} if emulator_serial else None


def collect_status():
    inventory, inventory_warnings = configured_avds()
    adb_status, running, warnings = collect_devices(inspect_device)
    matched = set()
    result = []
    unresolved = bool(warnings) or any(not item.get("avdName") for item in running)
    for config in inventory:
        matches = [item for item in running if item.get("avdName") == config["name"]]
        if matches:
            for item in matches:
                matched.add(item["serial"])
                result.append({**config, **item})
        else:
            result.append({**config, "serial": None, "state": "disconnected" if adb_status["state"] == "available" and not unresolved else "unknown"})
    result.extend({"configured": False, **item} for item in running if item["serial"] not in matched)
    return {"observedAt": observed_at(), "adb": adb_status, "emulators": result,
            "warnings": inventory_warnings + warnings}


def screenshot(serial):
    validate_serial(serial)
    device = next((item for item in devices() if item["serial"] == serial), None)
    if device is None or device["connection"] != "device":
        raise ProbeError("The selected emulator is not connected")
    emulator = inspect_device(device)
    if emulator is None or emulator["state"] != "online":
        raise ProbeError("Screen capture requires a booted Android emulator")
    data = adb(["exec-out", "screencap", "-p"], serial, binary=True)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ProbeError("The emulator did not return a PNG screenshot")
    return base64.b64encode(data).decode("ascii")


if __name__ == "__main__":
    import json
    print(json.dumps(collect_status(), indent=2))
