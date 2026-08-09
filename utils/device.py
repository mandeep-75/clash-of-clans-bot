"""ADB-based device controller (fallback control mode)."""

import os
import random
import re
import subprocess

import config
from utils.template_detector import TemplateDetector


def select_device() -> str | None:
    """Auto-selects a device or asks the user."""
    adb_command = ["adb", "devices"]
    try:
        result = subprocess.run(adb_command, capture_output=True, text=True, check=True)
        devices = [
            line.split("\t")[0]
            for line in result.stdout.strip().split("\n")[1:]
            if line.strip() and "\tdevice" in line
        ]
        if not devices:
            print("❌ No devices connected.")
            return None
        if len(devices) == 1:
            print(f"✅ One device detected: {devices[0]} (auto-selected)")
            return devices[0]

        print("📱 Connected devices:")
        for i, d in enumerate(devices):
            print(f"{i + 1}: {d}")
        # For automation safety, just pick the first one if multiple are present
        # and no input mechanism. For now, default to first.
        print(f"✅ Auto-selecting first device: {devices[0]}")
        return devices[0]
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Failed to execute ADB command: {e}")
        return None


class DeviceController(TemplateDetector):
    """Controls an Android device through ADB `input` commands."""

    def __init__(self, device_id=None, verbose=False):
        super().__init__()
        self.device_id = device_id
        self.verbose = verbose
        if not self.device_id:
            self.device_id = select_device()

    def close(self) -> None:
        """No-op for interface parity with the scrcpy controller."""

    def tap(self, x: int, y: int, offset: int = 0) -> None:
        """Performs a human-like tap with random offset."""
        if not self.device_id:
            print("⚠️ No device connected.")
            return

        tx = x + random.randint(-offset, offset)
        ty = y + random.randint(-offset, offset)
        cmd = ["adb", "-s", self.device_id, "shell", "input", "tap", str(tx), str(ty)]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to tap: {e}")

    def take_screenshot(self, local_path=config.SCREENSHOT_NAME) -> None:
        """Captures a screenshot from the device."""
        if not self.device_id:
            return
        try:
            cmd = ["adb", "-s", self.device_id, "exec-out", "screencap", "-p"]
            with open(local_path, "wb") as f:
                subprocess.run(cmd, check=True, stdout=f)
        except subprocess.CalledProcessError as e:
            print(f"Failed to take screenshot: {e}")

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
            )
            m = re.search(r"(\d+)\s*x\s*(\d+)", out.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
        except (subprocess.CalledProcessError, OSError):
            pass
        return 0, 0

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

        jar_local = os.path.join("utils", "pinch_src", "pinch.jar")
        jar_device = "/data/local/tmp/pinch.jar"
        subprocess.run(
            ["adb", "-s", self.device_id, "push", jar_local, jar_device],
            capture_output=True,
            check=False,
        )

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
        shell_cmd = f"CLASSPATH={jar_device} app_process / Pinch " + " ".join(args)
        subprocess.run(
            ["adb", "-s", self.device_id, "shell", shell_cmd],
            capture_output=True,
            check=False,
        )
