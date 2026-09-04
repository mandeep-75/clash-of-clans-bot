"""Screenshot tap recorder for an ADB device.

Shows the device screen in a window; click on it to record that position.
Every click is printed to the terminal (device-pixel coordinates) and appended
to the output file, ready to paste into config.py (e.g. TROOP_LOCATIONS).

    python record_taps.py                    # auto-select device
    python record_taps.py --device <ID>      # pick a specific device
    python record_taps.py --output taps.txt  # save to a different file
    python record_taps.py --max-taps 28      # quit after 28 recorded taps
    python record_taps.py --width 960        # window width (auto-scaled)
    python record_taps.py --image live.png   # record against a saved image

Keys:
    r / Space   refresh the screenshot from the device
    u           undo the last recorded tap
    q / Esc     quit and print the full recorded list
"""

import argparse
import os
import sys

import cv2

import config
from utils.scrcpy_controller import ScrcpyController

WINDOW_NAME = "Tap Recorder - click to record"


class TapRecorder:
    """Displays a device screenshot and records clicks as coordinates."""

    def __init__(
        self,
        device: ScrcpyController,
        output: str,
        max_taps: int,
        window_width: int,
        image_path: str | None = None,
    ):
        self.device = device
        self.output = output
        self.max_taps = max_taps
        self.window_width = window_width
        self.image_path = image_path

        self.screen: cv2.typing.MatLike | None = None
        self.scale = 1.0
        self.taps: list[tuple[int, int]] = []

    def refresh(self) -> bool:
        """Loads the source image (device screenshot or --image) and redraws."""
        if self.image_path:
            screen = cv2.imread(self.image_path)
        else:
            if not self.device.take_screenshot():
                print("Failed to take screenshot; press 'r' to retry.")
                return False
            screen = cv2.imread(config.SCREENSHOT_NAME)
        if screen is None:
            print("Could not read image; press 'r' to retry.")
            return False

        self.screen = screen
        _, w = screen.shape[:2]
        self.scale = self.window_width / w if self.window_width else 1.0
        self._draw()
        return True

    def _draw(self) -> None:
        """Draws the screenshot (scaled) with recorded taps overlaid."""
        assert self.screen is not None
        display = self.screen
        if self.scale != 1.0:
            display = cv2.resize(
                self.screen,
                None,
                fx=self.scale,
                fy=self.scale,
                interpolation=cv2.INTER_NEAREST,
            )
        for i, (x, y) in enumerate(self.taps, 1):
            cx, cy = int(x * self.scale), int(y * self.scale)
            cv2.circle(display, (cx, cy), 8, (0, 0, 255), 2)
            cv2.putText(
                display,
                str(i),
                (cx + 12, cy - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )
        cv2.imshow(WINDOW_NAME, display)

    def record(self, x: int, y: int) -> None:
        """Records a click (window pixels -> device pixels) and logs it."""
        dx = int(x / self.scale)
        dy = int(y / self.scale)
        self.taps.append((dx, dy))
        idx = len(self.taps)
        print(f"  #{idx:<3} tap at ({dx}, {dy})")
        with open(self.output, "a", encoding="utf-8") as f:
            f.write(f"({dx}, {dy})\n")

    def undo(self) -> None:
        """Removes the last recorded tap."""
        if self.taps:
            dropped = self.taps.pop()
            print(f"  removed last tap {dropped}")

    def summary(self) -> None:
        """Prints the recorded list ready for pasting into config.py."""
        print("\n=== RECORDED TAPS ===")
        print("TROOP_LOCATIONS = [")
        for x, y in self.taps:
            print(f"    ({x}, {y}),")
        print("]")

    def run(self) -> None:
        """Main loop: refresh screenshot and handle clicks/keys."""
        if not self.refresh():
            return

        def on_click(event, x, y, _flags, _param) -> None:  # type: ignore[no-untyped-def]
            if event == cv2.EVENT_LBUTTONDOWN:
                self.record(x, y)
                self._draw()
                if self.max_taps and len(self.taps) >= self.max_taps:
                    cv2.destroyWindow(WINDOW_NAME)

        cv2.setMouseCallback(WINDOW_NAME, on_click)

        while True:
            key = cv2.waitKey(0) & 0xFF
            if key in (ord("q"), 27):  # q or Esc
                break
            if key in (ord("r"), ord(" ")):  # r or Space
                self.refresh()
            elif key == ord("u"):
                self.undo()
                self._draw()

        cv2.destroyAllWindows()
        self.summary()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record tap coordinates by clicking a screenshot"
    )
    parser.add_argument("--device", type=str, help="ADB Device ID")
    parser.add_argument(
        "--output",
        type=str,
        default="recorded_taps.txt",
        help="File to append each recorded tap (default: recorded_taps.txt)",
    )
    parser.add_argument(
        "--max-taps",
        type=int,
        default=0,
        help="Auto-quit after this many taps (default: quit with q/Esc)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=960,
        help="Window width in pixels; screenshot is scaled to fit",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Use this image instead of pulling from the device (e.g. live.png)",
    )
    args = parser.parse_args()

    if args.image:
        device = ScrcpyController.__new__(ScrcpyController)  # no device needed
    else:
        try:
            device = ScrcpyController(device_id=args.device)
        except RuntimeError as e:
            sys.exit(f"Failed to init device: {e}")

    if os.path.exists(args.output):
        os.remove(args.output)

    recorder = TapRecorder(
        device, args.output, args.max_taps, args.width, image_path=args.image
    )
    try:
        recorder.run()
    finally:
        device.close()


if __name__ == "__main__":
    main()
