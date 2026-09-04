"""OpenCV template matching shared by the device controllers."""

import glob
import os

import cv2
import numpy as np

import config


class TemplateDetector:
    """Detects UI templates (buttons) on a screenshot.

    Subclasses provide `tap(x, y, offset)` and may set `verbose`.

    Templates are cached in memory per folder (invalidated when any file in
    the folder changes) and the decoded screenshot is cached per file mtime,
    so repeated detection calls within one poll cycle avoid re-reading the
    same bytes from disk.
    """

    verbose: bool = False

    def __init__(self):
        self._template_cache: dict[str, tuple[dict[str, float], list[np.ndarray]]] = {}
        self._screen_cache: tuple[tuple[str, int, int], np.ndarray | None] | None = None
        # Per-instance screenshot file; lets several devices run at once
        # without clobbering each other's frame. Override per device.
        self.screenshot_name: str = config.SCREENSHOT_NAME

    def tap(self, x: int, y: int, offset: int = 0, hold: float = 0.0) -> bool:
        """Taps at (x, y); overridden by subclasses."""
        raise NotImplementedError

    def detect_button(
        self,
        button_folder: str,
        screenshot_path: str | None = None,
        threshold: float = config.MATCH_THRESHOLD,
    ) -> tuple[int, int] | None:
        """Detects a button/template on the screen.

        Returns (x, y) tuple if found, else None.
        """
        screen = self._load_screen(screenshot_path or self.screenshot_name)
        if screen is None:
            return None

        templates = self._load_templates(button_folder)
        if not templates:
            return None

        best_val = -1.0
        best_loc = None
        best_w, best_h = 0, 0

        for template in templates:
            if (
                screen.shape[0] < template.shape[0]
                or screen.shape[1] < template.shape[1]
            ):
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

    # ------------------------------------------------------------------ caching

    def _load_screen(self, screenshot_path: str) -> np.ndarray | None:
        """Decodes the screenshot, cached by (path, mtime_ns, size)."""
        try:
            stat = os.stat(screenshot_path)
        except OSError:
            return None
        key = (screenshot_path, stat.st_mtime_ns, stat.st_size)
        if self._screen_cache is not None and self._screen_cache[0] == key:
            return self._screen_cache[1]
        screen = cv2.imread(screenshot_path)
        self._screen_cache = (key, screen)
        return screen

    def _load_templates(self, button_folder: str) -> list[np.ndarray]:
        """Decodes all templates in a folder, cached by folder file mtimes."""
        template_paths = [
            p for p in glob.glob(os.path.join(button_folder, "*")) if os.path.isfile(p)
        ]
        if not template_paths:
            return []
        try:
            files: dict[str, float] = {p: os.path.getmtime(p) for p in template_paths}
        except OSError:
            return []

        cached = self._template_cache.get(button_folder)
        if cached is not None and cached[0] == files:
            return cached[1]

        templates = [tpl for p in template_paths if (tpl := cv2.imread(p)) is not None]
        self._template_cache[button_folder] = (files, templates)
        return templates
