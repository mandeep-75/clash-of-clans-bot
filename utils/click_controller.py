"""Top-level click control: every tap the bot makes funnels through here.

All clicks go through ``ClickController.detect_and_tap`` (and ``tap`` for raw
coordinates), giving one place to globally enable/disable clicks, pace them
with a human-like delay and log every tap. Detection itself is delegated to
the device's own ``TemplateDetector`` methods.
"""

import random
import time

import config


class ClickController:
    """Central control point for every tap made by the bot.

    Wrap a device controller with this and route all taps through it:
        click = ClickController(device)
        click.tap(x, y)
        click.detect_and_tap("templates/attack_button")
    """

    def __init__(
        self,
        device,
        enabled: bool | None = None,
        log_path: str | None = None,
    ):
        self.device = device
        self.enabled = config.CLICK_ENABLED if enabled is None else enabled
        self.log_path = log_path if log_path is not None else config.CLICK_LOG
        self.total_taps = 0

    def tap(
        self,
        x: int,
        y: int,
        offset: int | None = None,
        hold: float | None = None,
    ) -> bool:
        """Central tap control. Every click passes through here.

        `offset` is the max pixel jitter (default config.TAP_OFFSET_MAX);
        `hold` is the finger-down time in seconds and defaults to a small
        random value (config.TAP_HOLD_MIN..TAP_HOLD_MAX) for a human feel.

        Returns True if the tap was sent, False if clicks are disabled.
        """
        self.total_taps += 1
        if not self.enabled:
            print(f"[click] disabled - dropped tap ({x}, {y})")
            return False
        jx = x + random.randint(
            -(offset or config.TAP_OFFSET_MAX), offset or config.TAP_OFFSET_MAX
        )
        jy = y + random.randint(
            -(offset or config.TAP_OFFSET_MAX), offset or config.TAP_OFFSET_MAX
        )
        if hold is None:
            hold = random.uniform(config.TAP_HOLD_MIN, config.TAP_HOLD_MAX)
        ok = self.device.tap(jx, jy, offset=0, hold=hold)
        self._log(
            f"tap ({jx}, {jy}) offset={offset or config.TAP_OFFSET_MAX} hold={hold:.3f}"
        )
        time.sleep(config.CLICK_DELAY)
        return ok

    def detect_and_tap(
        self,
        button_folder: str,
        threshold: float = config.MATCH_THRESHOLD,
        offset: int | None = config.TAP_OFFSET_MAX,
    ) -> bool:
        """Detect a button via the device's own detector and tap it.

        Returns True when the button was found and tapped.
        """
        coords = self.device.detect_button(button_folder, threshold=threshold)
        if coords:
            return self.tap(coords[0], coords[1], offset=offset)
        return False

    def _log(self, message: str) -> None:
        if not self.log_path:
            return
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")
