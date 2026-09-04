"""ADB device discovery helpers (used by the scrcpy controller)."""

import subprocess

import config


def list_devices() -> list[str]:
    """Returns the IDs of every connected ADB device."""
    adb_command = ["adb", "devices"]
    try:
        result = subprocess.run(
            adb_command,
            capture_output=True,
            text=True,
            check=True,
            timeout=config.ADB_TIMEOUT,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        print(f"Failed to list ADB devices: {e}")
        return []

    return [
        line.split("\t")[0]
        for line in result.stdout.strip().split("\n")[1:]
        if line.strip() and "\tdevice" in line
    ]


def select_device() -> str | None:
    """Selects a connected device, or returns None if none/multiple.

    When multiple devices are connected the bot refuses to pick for you:
    attacking with the wrong account wastes real resources. Pass `--device`.
    """
    adb_command = ["adb", "devices"]
    try:
        result = subprocess.run(
            adb_command,
            capture_output=True,
            text=True,
            check=True,
            timeout=config.ADB_TIMEOUT,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        print(f"Failed to list ADB devices: {e}")
        return None

    devices = [
        line.split("\t")[0]
        for line in result.stdout.strip().split("\n")[1:]
        if line.strip() and "\tdevice" in line
    ]
    if not devices:
        print("No devices connected.")
        return None
    if len(devices) == 1:
        print(f"One device detected: {devices[0]} (auto-selected)")
        return devices[0]

    print("Multiple devices detected; specify one with --device:")
    for d in devices:
        print(f"  {d}")
    return None
