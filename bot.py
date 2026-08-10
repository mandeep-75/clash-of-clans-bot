"""Clash of Clans Bot - core flow and CLI entry point."""

import argparse
import random
import subprocess
import time

import config
from utils.click_controller import ClickController
from utils.device import DeviceController
from utils.logger import log
from utils.scrcpy_controller import ScrcpyController

HERO_TAP_DELAY_RANGE = (0.5, 1.0)


def main() -> None:
    """CLI entry point: parse args and run the bot."""
    parser = argparse.ArgumentParser(description="Clash of Clans Bot")
    parser.add_argument("--device", type=str, help="ADB Device ID")
    parser.add_argument(
        "--control",
        type=str,
        choices=["scrcpy", "adb"],
        default=config.CONTROL_MODE,
        help="Input/screenshot backend (default: scrcpy)",
    )

    args = parser.parse_args()

    log.info("Initializing Device Controller...")
    try:
        device: DeviceController | ScrcpyController
        if args.control == "scrcpy":
            device = ScrcpyController(device_id=args.device)
        else:
            device = DeviceController(device_id=args.device)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
        log.error(f"Failed to initialize {args.control} controller: {e}")
        return

    log.info("Starting CoC Bot...")
    coc_bot = CoCBot(device_controller=device)

    try:
        coc_bot.run()
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
    finally:
        device.close()


class CoCBot:
    def __init__(self, device_controller):
        self.device = device_controller

        self.loop_count = 0
        self.start_time = time.time()
        self.stop_flag = False
        self.consecutive_failures = 0

        self.deployed_heroes = {}

        self.click = ClickController(self.device)

    def stop(self):
        """Signal the bot to stop after current loop."""
        self.stop_flag = True

    def run(self):
        """Main bot loop: the whole flow, read top to bottom."""
        self.stop_flag = False
        self.consecutive_failures = 0

        log.info("===== NEW BOT SESSION STARTED =====")

        while not self.stop_flag:
            try:
                self.loop_count += 1
                log.info("=" * 20 + f" LOOP {self.loop_count} " + "=" * 20)

                if not self.device.check_connection():
                    self._abort("Device connection lost")
                    break

                # ---------------- Collect resources ----------------
                for folder, name in (
                    ("gold_collect", "Gold"),
                    ("elixir_collect", "Elixir"),
                    ("dark_elixir_collect", "Dark Elixir"),
                ):
                    log.info(f"Collecting {name}...")
                    self._screenshot()
                    self.click.detect_and_tap(f"templates/{folder}")

                # ---------------- Navigate to attack ----------------
                log.info("Navigating to attack...")

                if not self._wait_for_button("templates/attack_button", timeout=30):
                    log.warning("Timeout waiting for Attack button")
                    continue

                time.sleep(config.POST_ATTACK_SLEEP)

                if not self._wait_for_button("templates/find_match_button", timeout=30):
                    log.warning("Timeout waiting for Find Match button")
                    continue

                if not self._wait_for_button("templates/attack"):
                    log.warning("Could not find Attack button")
                    continue

                time.sleep(config.POST_ATTACK_SLEEP)
                self._screenshot()

                # ---------------- Search and select a base ----------------
                log.info("Searching for base...")

                searches = random.randint(1, config.MAX_BASE_SEARCHES)
                search_ok = True
                for attempt in range(1, searches):
                    log.info(f"Search {attempt + 1}/{searches}: skipping to next base")
                    if not self._wait_for_button("templates/next_button", timeout=10):
                        log.warning("Could not find Next button")
                        search_ok = False
                        break
                    time.sleep(random.uniform(*config.SEARCH_NEXT_SLEEP_RANGE))
                    self._screenshot()

                if not search_ok:
                    continue

                log.info(f"Attacking base (search {searches})")
                time.sleep(config.POST_ATTACK_SLEEP)

                # ---------------- Adjust the battle view ----------------
                if config.BATTLE_ZOOM:
                    log.info("Adjusting battle view...")
                    try:
                        self.device.pinch_zoom(
                            direction=config.BATTLE_ZOOM,
                            start_dist=config.ZOOM_START_DIST,
                            end_dist=config.ZOOM_END_DIST,
                            steps=config.ZOOM_STEPS,
                        )
                        self.device.swipe(*config.BATTLE_PAN_SWIPE_1)
                        self.device.swipe(*config.BATTLE_PAN_SWIPE_2)
                        self.device.swipe(*config.BATTLE_PAN_SWIPE_3)
                    except (RuntimeError, OSError) as e:
                        log.warning(f"Adjusting battle view failed: {e}")
                    time.sleep(config.POST_ZOOM_SLEEP)

                # ---------------- Deploy troops / heroes / spells ----------------
                self.deployed_heroes = {}
                self._deploy_units(
                    "troops",
                    config.SELECTED_TROOPS,
                    config.TROOP_LOCATIONS,
                    final_delay=random.uniform(4, 5),
                )
                self._deploy_heroes()
                self._deploy_units(
                    "spells",
                    config.SELECTED_SPELLS,
                    config.SPELL_LOCATIONS,
                    between_taps=0.3,
                    shuffle=False,
                )

                # ---------------- Trigger hero abilities ----------------
                self._activate_hero_abilities(config.HERO_ABILITIES)

                # ---------------- Return home ----------------
                log.info("Returning home...")
                wait_start = time.time()
                returned = False
                while time.time() - wait_start < config.RETURN_HOME_TIMEOUT:
                    if self.stop_flag:
                        break
                    if not self._screenshot():
                        time.sleep(config.RETURN_HOME_TAP_SLEEP)
                        continue

                    if self.click.detect_and_tap("templates/return_home"):
                        time.sleep(config.RETURN_HOME_TAP_SLEEP)
                        self.click.detect_and_tap("templates/okay_button")
                        returned = True
                        break

                    time.sleep(config.RETURN_HOME_TAP_SLEEP)

                if not returned:
                    log.warning("Force ending battle...")
                    self._screenshot()
                    self.click.detect_and_tap("templates/end_battle")
                    self.click.detect_and_tap("templates/surrender_button")
                    time.sleep(config.POST_ATTACK_SLEEP)
                    self._screenshot()
                    self.click.detect_and_tap("templates/return_home")

                # ---------------- Session summary (every 5 loops) ----------------
                if self.loop_count % 5 == 0:
                    elapsed_min = (time.time() - self.start_time) / 60
                    log.info(
                        f"===== SESSION SUMMARY =====\n"
                        f"Attacks: {self.loop_count}\n"
                        f"Runtime: {elapsed_min:.1f} min\n"
                        f"==========================="
                    )

            except Exception as e:  # noqa: BLE001
                # Keep the loop alive; failures are counted and abort when too many.
                self._record_failure()
                log.error(f"Error in loop: {e}")
                if self.stop_flag:
                    break
                time.sleep(5)

        log.info("Bot stopped gracefully.")

    # ------------------------------------------------------------- deploy units

    def _deploy_heroes(self) -> None:
        """Deploy every selected hero, remembering their button positions."""
        self.deployed_heroes = {}
        self._deploy_units(
            "hero",
            config.SELECTED_HEROES,
            config.HERO_LOCATIONS,
            track_buttons=True,
        )

    def _activate_hero_abilities(self, name_partials: list[str] | None = None) -> None:
        """Trigger abilities for deployed heroes.

        `name_partials` are case-insensitive substrings matched against the
        template folder names; every matching hero gets its ability tapped.
        Defaults to activating every deployed hero when no names are given.
        """
        partials = name_partials or list(self.deployed_heroes)
        for name, coords in self.deployed_heroes.items():
            if any(partial.lower() in name.lower() for partial in partials):
                log.info(f"Activating {name} ability!")
                self.click.tap(coords[0], coords[1])

    def _deploy_units(
        self,
        kind: str,
        units: dict[str, int],
        locations: list[tuple[int, int]],
        between_taps: tuple[float, float] | float = (0.1, 0.2),
        shuffle: bool = True,
        track_buttons: bool = False,
        final_delay: float | None = None,
    ) -> None:
        """Deploy units from a template folder to the battlefield.

        `kind` selects the template subfolder (troops/hero/spells) and
        `units` maps each template folder name to how many to deploy.
        When `track_buttons` is set, each deployed unit's button position is
        remembered in ``self.deployed_heroes`` for ability triggering.
        """
        plan = {k: v for k, v in units.items() if v > 0}
        if not plan:
            log.info("No units to deploy!")
            return

        locs = locations[:]
        if shuffle:
            random.shuffle(locs)

        loc_index = 0
        for folder, count in plan.items():
            coords = self.device.detect_button(f"templates/{kind}/{folder}")
            if not coords:
                log.warning(f"{folder} button not found")
                continue

            self.click.tap(coords[0], coords[1])
            if track_buttons:
                self.deployed_heroes[folder] = coords

            log.info(f"Deploying {folder} ({count})...")
            time.sleep(config.SELECTION_UI_DELAY)  # Wait for selection UI

            for _ in range(count):
                loc = locs[loc_index % len(locs)]
                self.click.tap(loc[0], loc[1])
                if track_buttons:
                    time.sleep(random.uniform(*HERO_TAP_DELAY_RANGE))
                elif isinstance(between_taps, tuple):
                    time.sleep(random.uniform(*between_taps))
                else:
                    time.sleep(between_taps)
                loc_index += 1

        if final_delay:
            time.sleep(final_delay)

    # ------------------------------------------------------------- device helpers

    def _screenshot(self) -> bool:
        """Takes a screenshot, tracking device failures on the way."""
        ok = self.device.take_screenshot()
        if ok:
            self.consecutive_failures = 0
        else:
            self._record_failure()
        return ok

    def _record_failure(self) -> None:
        """Counts a device failure and aborts after too many in a row."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= config.MAX_CONSECUTIVE_FAILURES:
            self._abort(f"{config.MAX_CONSECUTIVE_FAILURES} consecutive failures")

    def _abort(self, reason: str) -> None:
        """Stops the bot and reports why."""
        log.warning(f"Stopping bot: {reason}")
        self.stop_flag = True

    def _wait_for_button(
        self,
        folder: str,
        timeout: int = 30,
        dismiss_okay: bool = True,
    ) -> bool:
        """Wait for a button to appear.

        Polls until the button is found or `timeout` seconds elapse. When
        `dismiss_okay` is set, taps the okay button on every miss so stray
        dialogs don't block the flow.
        """
        start = time.time()
        while time.time() - start < timeout:
            if not self._screenshot():
                time.sleep(config.BUTTON_POLL_INTERVAL)
                continue
            if self.click.detect_and_tap(folder):
                return True
            if dismiss_okay:
                self.click.detect_and_tap("templates/okay_button")
            time.sleep(config.BUTTON_POLL_INTERVAL)
        return False


if __name__ == "__main__":
    main()
