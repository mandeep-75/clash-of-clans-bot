"""OpenCV template matching shared by the device controllers."""

import glob
import os

import cv2

import config


class TemplateDetector:
    """Detects UI templates (buttons) on a screenshot.

    Subclasses provide `tap(x, y, offset)` and may set `verbose`.
    """

    verbose: bool = False

    def tap(self, x: int, y: int, offset: int = 0) -> None:
        """Taps at (x, y); overridden by subclasses."""
        raise NotImplementedError

    def detect_button(
        self,
        button_folder: str,
        screenshot_path: str = config.SCREENSHOT_NAME,
        threshold: float = 0.8,
    ) -> tuple[int, int] | None:
        """Detects a button/template on the screen.

        Returns (x, y) tuple if found, else None.
        """
        if not os.path.exists(screenshot_path):
            return None

        screen = cv2.imread(screenshot_path)
        if screen is None:
            return None

        template_paths = glob.glob(os.path.join(button_folder, "*"))
        if not template_paths:
            return None

        best_val = -1.0
        best_loc = None
        best_w, best_h = 0, 0

        for template_path in template_paths:
            template = cv2.imread(template_path)
            if template is None:
                continue

            try:
                res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            except cv2.error:
                continue

            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val and max_val >= threshold:
                best_val = max_val
                best_loc = max_loc
                best_w, best_h = template.shape[1], template.shape[0]

        if best_loc:
            x = best_loc[0] + best_w // 2
            y = best_loc[1] + best_h // 2
            if self.verbose:
                print(
                    f"Found {os.path.basename(button_folder)} at ({x},{y}) "
                    f"conf={best_val * 100:.1f}%"
                )
            return x, y
        return None

    def detect_and_tap(
        self,
        button_folder: str,
        screenshot_path: str = config.SCREENSHOT_NAME,
        threshold: float = 0.8,
        offset: int = config.RANDOM_OFFSET,
    ) -> bool:
        """Detects a button and taps it immediately."""
        coords = self.detect_button(button_folder, screenshot_path, threshold)
        if coords:
            self.tap(coords[0], coords[1], offset)
            return True
        return False
