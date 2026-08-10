"""ADB-based device controller (fallback control mode)."""

import os
import random
import re
import subprocess

import config
from utils.template_detector import TemplateDetector


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


class DeviceController(TemplateDetector):
    """Controls an Android device through ADB `input` commands."""

    def __init__(self, device_id=None, verbose=False):
        super().__init__()
        self.device_id = device_id
        self.verbose = verbose
        if not self.device_id:
            self.device_id = select_device()
        if not self.device_id:
            raise RuntimeError("No ADB device available (use --device if multiple)")
        self._push_pinch_jar()

    def close(self) -> None:
        """No-op for interface parity with the scrcpy controller."""

    def check_connection(self) -> bool:
        """Returns True if the device is still reachable over adb."""
        if not self.device_id:
            return False
        try:
            subprocess.run(
                ["adb", "-s", self.device_id, "get-state"],
                capture_output=True,
                check=False,
                timeout=config.ADB_TIMEOUT,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return False

    def tap(self, x: int, y: int, offset: int = 0, hold: float = 0.1) -> bool:
        """Performs a human-like tap with random offset.

        A positive `hold` keeps the finger down for that many seconds via
        `input swipe` (parity with the scrcpy controller).

        Returns True if the tap command was sent successfully.
        """
        if not self.device_id:
            print("No device connected.")
            return False

        tx = x + random.randint(-offset, offset)
        ty = y + random.randint(-offset, offset)
        if hold > 0:
            cmd = [
                "adb",
                "-s",
                self.device_id,
                "shell",
                "input",
                "swipe",
                str(tx),
                str(ty),
                str(tx),
                str(ty),
                str(int(hold * 1000)),
            ]
        else:
            cmd = [
                "adb",
                "-s",
                self.device_id,
                "shell",
                "input",
                "tap",
                str(tx),
                str(ty),
            ]
        try:
            subprocess.run(cmd, check=True, timeout=config.ADB_TIMEOUT)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Failed to tap: {e}")
            return False

    def take_screenshot(self, local_path=config.SCREENSHOT_NAME) -> bool:
        """Captures a screenshot from the device.

        Writes atomically and removes the old screenshot on failure so
        detection can never act on a stale frame. Returns success.
        """
        if not self.device_id:
            return False
        tmp_path = local_path + ".tmp"
        try:
            cmd = ["adb", "-s", self.device_id, "exec-out", "screencap", "-p"]
            with open(tmp_path, "wb") as f:
                subprocess.run(cmd, check=True, stdout=f, timeout=config.ADB_TIMEOUT)
            os.replace(tmp_path, local_path)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Failed to take screenshot: {e}")
            for p in (tmp_path, local_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            return False

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        steps: int = 20,
        dt: float = 0.01,
    ) -> bool:
        """Performs a swipe from (x1, y1) to (x2, y2) via `adb input swipe`.

        Signature matches the scrcpy controller's swipe. Returns True if the
        swipe command was sent successfully.
        """
        if not self.device_id:
            print("No device connected.")
            return False

        duration_ms = int(steps * dt * 1000)
        try:
            subprocess.run(
                [
                    "adb",
                    "-s",
                    self.device_id,
                    "shell",
                    "input",
                    "swipe",
                    str(x1),
                    str(y1),
                    str(x2),
                    str(y2),
                    str(duration_ms),
                ],
                check=True,
                timeout=config.ADB_TIMEOUT,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Failed to swipe: {e}")
            return False

    def _screen_size(self) -> tuple[int, int]:
        """Returns (width, height) of the device display via `wm size`."""
        if not self.device_id:
            return 0, 0
        try:
            out = subprocess.run(
                ["adb", "-s", self.device_id, "shell", "wm", "size"],
                capture_output=True,
                text=True,
                check=True,
                timeout=config.ADB_TIMEOUT,
            )
            m = re.search(r"(\d+)\s*x\s*(\d+)", out.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            pass
        return 0, 0

    def _push_pinch_jar(self) -> None:
        """Pushes the Pinch helper to the device once at startup."""
        jar_local = os.path.join("utils", "pinch_src", "pinch.jar")
        jar_device = "/data/local/tmp/pinch.jar"
        try:
            subprocess.run(
                ["adb", "-s", self.device_id, "push", jar_local, jar_device],
                capture_output=True,
                check=True,
                timeout=config.ADB_TIMEOUT,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Failed to push pinch.jar: {e}")

    def pinch_zoom(
        self,
        direction: str = "in",
        center: tuple[int, int] | None = None,
        start_dist: int | None = None,
        end_dist: int | None = None,
        steps: int = 25,
        dt: float = 0.01,
    ) -> None:
        """Pinch-zoom using the on-device Pinch helper (multi-touch)."""
        if not self.device_id:
            return

        w, h = self._screen_size()
        cx, cy = center or (w // 2, h // 2)
        if direction == "in":
            start, end = start_dist or 60, end_dist or 320
        else:
            start, end = start_dist or 320, end_dist or 60

        duration_ms = int(steps * dt * 1000)
        args = [
            str(a)
            for a in (
                int(cx - start),
                cy,
                int(cx + start),
                cy,
                int(cx - end),
                cy,
                int(cx + end),
                cy,
                steps,
                duration_ms,
            )
        ]
        shell_cmd = (
            "CLASSPATH=/data/local/tmp/pinch.jar app_process / Pinch " + " ".join(args)
        )
        try:
            subprocess.run(
                ["adb", "-s", self.device_id, "shell", shell_cmd],
                capture_output=True,
                check=False,
                timeout=config.ADB_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"Pinch zoom failed: {e}")
