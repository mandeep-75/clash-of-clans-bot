"""Clash of Clans Bot - core flow and CLI entry point."""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message=".*pin_memory.*")

import argparse
import os
import random
import subprocess
import threading
import time

import cv2
import easyocr
import numpy as np

import config
from utils.click_controller import ClickController
from utils.device import list_devices
from utils.logger import log, rlog
from utils.scrcpy_controller import ScrcpyController

HERO_TAP_DELAY = (0.3, 0.5)


def select_devices() -> list[str] | None:
    """Prompts the user to pick which connected devices to run."""
    devices = list_devices()

    if not devices:
        print("No devices connected.")
        return None
    if len(devices) == 1:
        print(f"One device detected: {devices[0]} (auto-selected)")
        return devices

    print("Multiple devices detected. Select which to run:")
    for i, d in enumerate(devices, 1):
        print(f"  [{i}] {d}")
    print("  [a] all")

    choice = input("Enter numbers separated by commas (e.g. 1,2), or 'a': ").strip()
    if choice.lower() == "a":
        return devices

    chosen: list[str] = []
    for part in choice.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        idx = int(part) - 1
        if 0 <= idx < len(devices):
            chosen.append(devices[idx])

    if not chosen:
        print("No valid devices selected.")
        return None
    return chosen


def main() -> None:
    """CLI entry point: parse args and run the bot."""
    parser = argparse.ArgumentParser(description="Clash of Clans Bot")
    parser.add_argument("--device", type=str, help="ADB Device ID")
    args = parser.parse_args()

    if args.device:
        device_ids = [args.device]
    else:
        device_ids = select_devices()  # type: ignore[assignment]
    if not device_ids:
        return

    log.info(f"Initializing {len(device_ids)} device(s)...")
    bots: list[Bot] = []
    threads: list[threading.Thread] = []

    try:
        for i, device_id in enumerate(device_ids):
            try:
                device = ScrcpyController(
                    device_id=device_id,
                    port=config.SCRCPY_PORT + i,
                    scid=config.SCRCPY_SCID + i,
                )
            except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
                log.error(f"Failed to init device {device_id}: {e}")
                continue

            device.screenshot_name = f"screen_{device_id}.png"
            bot = Bot(device, device.screenshot_name)
            bots.append(bot)
            threads.append(
                threading.Thread(target=bot.run, name=f"bot-{device_id}", daemon=True)
            )

        if not threads:
            log.error("No devices initialized; exiting.")
            return

        for t in threads:
            t.start()

        log.info(f"Running {len(threads)} bot(s). Ctrl+C to stop.")

        try:
            while any(t.is_alive() for t in threads):
                time.sleep(0.5)
        except KeyboardInterrupt:
            log.info("Shutting down...")
            for bot in bots:
                bot.stop_flag = True
            for t in threads:
                t.join(timeout=10)
    finally:
        for bot in bots:
            bot.device.close()


class Bot:
    def __init__(
        self, device: ScrcpyController, screenshot_name: str = config.SCREENSHOT_NAME
    ):
        self.device = device
        self.screenshot_name = screenshot_name
        self.click = ClickController(device)
        self.ocr_reader = easyocr.Reader(config.OCR_LANGUAGES, gpu=False)

        self.loop_count = 0
        self.start_time = time.time()
        self.stop_flag = False
        self.failures = 0
        self.deployed_heroes: dict[str, tuple[int, int]] = {}
        self.total_gold = 0
        self.total_elixir = 0
        self.total_dark_elixir = 0
        self.attacks = 0
        self.total_attack_time = 0.0
        self.batch_start_time = time.time()
        self.batch_gold = 0
        self.batch_elixir = 0
        self.batch_dark_elixir = 0
        self.batch_attacks = 0

    def run(self):
        """Main bot loop."""
        self.stop_flag = False
        self.failures = 0

        log.info("===== SESSION START =====")

        while not self.stop_flag:
            try:
                self.loop_count += 1
                loop_start = time.time()
                log.info(f"--- LOOP {self.loop_count} ---")

                if not self.device.check_connection():
                    log.warning("Device disconnected")
                    self.stop_flag = True
                    break

                # --- Collect resources ---
                for folder, name in (
                    ("gold_collect", "Gold"),
                    ("elixir_collect", "Elixir"),
                    ("dark_elixir_collect", "Dark Elixir"),
                ):
                    self.device.take_screenshot(self.screenshot_name)
                    if self.click.detect_and_tap(f"templates/{folder}"):
                        log.info(f"Collected {name}")
                    else:
                        log.info(f"{name} not on screen")

                # --- Navigate to attack ---
                if not self.wait_for_button("templates/attack_button", timeout=30):
                    log.warning("No Attack button")
                    continue

                time.sleep(config.POST_ATTACK_SLEEP)

                if not self.wait_for_button("templates/find_match_button", timeout=30):
                    log.warning("No Find Match button")
                    continue

                if not self.wait_for_button("templates/attack"):
                    log.warning("No Start Battle button")
                    continue

                time.sleep(config.POST_ATTACK_SLEEP)
                self.device.take_screenshot(self.screenshot_name)

                # --- Search for a base ---
                log.info("Searching for suitable base...")

                base_found = False
                attempt = 0
                while not base_found and not self.stop_flag:
                    attempt += 1
                    log.info(f"Evaluating base {attempt}")
                    self.device.take_screenshot(self.screenshot_name)

                    if self.evaluate_base():
                        base_found = True
                        break

                    log.info(f"Skipping base {attempt}, searching next...")
                    if not self.wait_for_button("templates/next_button", timeout=10):
                        log.warning("No Next button")
                        break
                    time.sleep(random.uniform(*config.SEARCH_NEXT_SLEEP_RANGE))

                if not base_found:
                    log.warning("No suitable base found, returning home")
                    self._return_home()
                    continue

                log.info("Found suitable base, attacking")
                time.sleep(config.POST_ATTACK_SLEEP)

                # --- Adjust battle view ---
                if config.BATTLE_ZOOM:
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
                        log.warning(f"View adjust failed: {e}")
                    time.sleep(config.POST_ZOOM_SLEEP)

                # --- Deploy units ---
                self.deployed_heroes = {}
                self.deploy(config.SELECTED_TROOPS, "troops", config.TROOP_LOCATIONS)
                self.deploy(config.SELECTED_SPELLS, "spells", config.SPELL_LOCATIONS)
                self.deploy_heroes(config.HERO_LOCATIONS)
                self.activate_heroes()

                # --- Return home ---
                self._return_home()

                # --- Attack timing ---
                attack_duration = time.time() - loop_start
                self.total_attack_time += attack_duration

                # --- Batch report (every 5 attacks) ---
                if self.batch_attacks >= 5:
                    batch_time = time.time() - self.batch_start_time
                    avg_time = self.total_attack_time / self.attacks
                    loot_per_min = (
                        self.total_gold / (self.total_attack_time / 60)
                        if self.total_attack_time
                        else 0
                    )
                    b_mins, b_secs = divmod(int(batch_time), 60)
                    a_mins, a_secs = divmod(int(avg_time), 60)
                    lpm_k = int(loot_per_min / 1000)

                    report = (
                        f"===== 5 ATTACKS =====\n"
                        f"Batch time: {b_mins}m {b_secs}s\n"
                        f"Loot: {self.batch_gold:,}G {self.batch_elixir:,}E {self.batch_dark_elixir:,}DE\n"
                        f"Avg time/attack: {a_mins}m {a_secs}s\n"
                        f"Gold/min: {lpm_k}k\n"
                        f"Total: {self.attacks} attacks | {self.total_gold:,}G {self.total_elixir:,}E\n"
                        f"======================"
                    )
                    log.info(report)
                    rlog.info(report)

                    self.batch_gold = 0
                    self.batch_elixir = 0
                    self.batch_dark_elixir = 0
                    self.batch_attacks = 0
                    self.batch_start_time = time.time()

                # --- Session summary (every 5 loops) ---
                if self.loop_count % 5 == 0:
                    elapsed = int(time.time() - self.start_time)
                    mins, secs = divmod(elapsed, 60)
                    log.info(
                        f"===== SUMMARY =====\n"
                        f"Attacks: {self.attacks}/{self.loop_count} bases\n"
                        f"Gold: {self.total_gold:,} | Elixir: {self.total_elixir:,} | DE: {self.total_dark_elixir:,}\n"
                        f"Runtime: {mins}:{secs:02d}\n"
                        f"===================="
                    )

            except Exception as e:  # noqa: BLE001
                self.failures += 1
                if self.failures >= config.MAX_CONSECUTIVE_FAILURES:
                    log.warning(f"Aborting: {config.MAX_CONSECUTIVE_FAILURES} failures")
                    self.stop_flag = True
                log.error(f"Loop error: {e}")
                if self.stop_flag:
                    break
                time.sleep(5)

        elapsed = int(time.time() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        avg_time = self.total_attack_time / self.attacks if self.attacks else 0
        avg_mins, avg_secs = divmod(int(avg_time), 60)
        loot_per_min = (
            self.total_gold / (self.total_attack_time / 60)
            if self.total_attack_time
            else 0
        )
        lpm_k = int(loot_per_min / 1000)
        skip_rate = (
            ((self.loop_count - self.attacks) / self.loop_count * 100)
            if self.loop_count
            else 0
        )
        log.info(
            f"===== FINAL SUMMARY =====\n"
            f"Bases scanned: {self.loop_count} | Attacked: {self.attacks} | Skip rate: {skip_rate:.0f}%\n"
            f"Gold: {self.total_gold:,} | Elixir: {self.total_elixir:,} | DE: {self.total_dark_elixir:,}\n"
            f"Avg time/attack: {avg_mins}m {avg_secs}s | Gold/min: {lpm_k}k\n"
            f"Runtime: {mins}:{secs:02d}\n"
            f"=========================="
        )
        rlog.info(
            f"SESSION END | "
            f"Scanned: {self.loop_count} | Attacked: {self.attacks} | Skip: {skip_rate:.0f}% | "
            f"Gold: {self.total_gold:,} | Elixir: {self.total_elixir:,} | DE: {self.total_dark_elixir:,} | "
            f"Avg: {avg_mins}m {avg_secs}s | Gold/min: {lpm_k}k"
        )
        log.info("Bot stopped.")

    def _return_home(self) -> None:
        """Wait for the return-home button after battle."""
        wait_start = time.time()
        event_taps = 0

        while time.time() - wait_start < config.RETURN_HOME_TIMEOUT:
            if self.stop_flag:
                return
            if not self.device.take_screenshot(self.screenshot_name):
                time.sleep(config.RETURN_HOME_TAP_SLEEP)
                continue

            if self.click.detect_and_tap("templates/return_home"):
                log.info("Battle ended, returning home")
                time.sleep(config.RETURN_HOME_TAP_SLEEP)
                self.click.detect_and_tap("templates/okay_button")
                self.click.detect_and_tap("templates/okay_button")
                self.click.detect_and_tap("templates/continue")
                self.click.detect_and_tap("templates/continue")
                self.click.detect_and_tap("templates/okay_button")
                return

            if event_taps < config.MAX_EVENT_TAPS and self.click.detect_and_tap(
                "templates/event_tap"
            ):
                event_taps += 1
                log.info(f"Event tap dismissed ({event_taps}/{config.MAX_EVENT_TAPS})")

            time.sleep(config.RETURN_HOME_TAP_SLEEP)

        # Fallback: force end the battle
        log.warning("Timed out, force ending")
        self.device.take_screenshot(self.screenshot_name)
        self.click.detect_and_tap("templates/end_battle")
        self.click.detect_and_tap("templates/surrender_button")
        time.sleep(config.POST_ATTACK_SLEEP)
        self.device.take_screenshot(self.screenshot_name)
        self.click.detect_and_tap("templates/return_home")

    def deploy(
        self,
        units: dict[str, int],
        category: str,
        locations: list[tuple[int, int]],
    ) -> None:
        """Deploy troops or spells to the battlefield."""
        plan = {k: v for k, v in units.items() if v > 0}
        if not plan:
            log.info(f"No {category} to deploy")
            return

        log.info(f"Deploy {sum(plan.values())} {category}")

        locs = locations[:]
        random.shuffle(locs)
        loc_index = 0

        for folder, count in plan.items():
            if category == "troops":
                time.sleep(1)

            if not self.device.take_screenshot(self.screenshot_name):
                log.warning(f"Screenshot failed before {folder}")
                continue

            coords = self.device.detect_button(f"templates/{category}/{folder}")
            if not coords:
                log.warning(f"{folder} button not found")
                continue

            log.info(f"Deploying {folder} x{count}")
            self.click.tap(coords[0], coords[1])
            time.sleep(config.SELECTION_UI_DELAY)

            for i in range(count):
                loc = locs[loc_index % len(locs)]
                drop_x = loc[0] - 20 if category == "spells" else loc[0]
                drop_y = loc[1] - 20 if category == "spells" else loc[1]
                self.click.tap(drop_x, drop_y)
                time.sleep(0.15)
                loc_index += 1

        time.sleep(random.uniform(2, 3))

    def deploy_heroes(
        self,
        locations: list[tuple[int, int]],
    ) -> None:
        """Scan templates/hero/, detect all available heroes, deploy found ones."""
        hero_dir = "templates/hero"
        hero_folders = [
            d for d in os.listdir(hero_dir) if os.path.isdir(os.path.join(hero_dir, d))
        ]
        if not hero_folders:
            log.info("No hero templates found")
            return

        if not self.device.take_screenshot(self.screenshot_name):
            log.warning("Screenshot failed before hero deploy")
            return

        locs = locations[:]
        random.shuffle(locs)
        loc_index = 0

        for folder in hero_folders:
            coords = self.device.detect_button(f"{hero_dir}/{folder}")
            if not coords:
                log.info(f"{folder} not available")
                continue

            log.info(f"Deploying {folder}")
            self.click.tap(coords[0], coords[1])
            self.deployed_heroes[folder] = coords
            time.sleep(config.SELECTION_UI_DELAY)

            loc = locs[loc_index % len(locs)]
            self.click.tap(loc[0], loc[1])
            time.sleep(random.uniform(*HERO_TAP_DELAY))
            loc_index += 1

    def activate_heroes(self) -> None:
        """Trigger abilities for deployed heroes in random order with random delays."""
        if not self.deployed_heroes:
            return
        heroes = list(self.deployed_heroes.items())
        random.shuffle(heroes)
        for name, coords in heroes:
            time.sleep(random.uniform(*config.ABILITY_DELAY_RANGE))
            log.info(f"Ability: {name}")
            self.click.tap(coords[0], coords[1])

    def evaluate_base(self) -> bool:
        """Evaluate base resources using OCR. Returns True if loot meets thresholds."""
        img = cv2.imread(self.screenshot_name)
        if img is None:
            log.warning("Failed to load screenshot for evaluation")
            return True

        gold = self._read_resource(img, config.GOLD_CROP_REGION)
        elixir = self._read_resource(img, config.ELIXIR_CROP_REGION)
        dark_elixir = self._read_resource(img, config.DARK_ELIXIR_CROP_REGION)

        self._save_resource_bboxes(img, gold, elixir, dark_elixir)

        log.info(f"Loot: {gold} gold, {elixir} elixir, {dark_elixir} dark elixir")

        if gold < config.MIN_GOLD:
            log.info(f"Skipping: gold {gold} < {config.MIN_GOLD}")
            return False
        if elixir < config.MIN_ELIXIR:
            log.info(f"Skipping: elixir {elixir} < {config.MIN_ELIXIR}")
            return False
        if config.MIN_DARK_ELIXIR > 0 and dark_elixir < config.MIN_DARK_ELIXIR:
            log.info(f"Skipping: dark elixir {dark_elixir} < {config.MIN_DARK_ELIXIR}")
            return False

        self.total_gold += gold
        self.total_elixir += elixir
        self.total_dark_elixir += dark_elixir
        self.batch_gold += gold
        self.batch_elixir += elixir
        self.batch_dark_elixir += dark_elixir
        self.attacks += 1
        self.batch_attacks += 1
        log.info(f"Base meets resource thresholds (attack #{self.attacks})")
        return True

    def _read_resource(self, img: np.ndarray, region: tuple[int, int, int, int]) -> int:
        """Read a single resource value from its bounding box with preprocessing."""
        x, y, w, h = region
        crop = img[y : y + h, x : x + w]
        processed = self._preprocess_resource(crop)

        raw_results = self.ocr_reader.readtext(crop)
        raw_value = self._extract_number(raw_results)

        filtered_results = self.ocr_reader.readtext(processed)
        filtered_value = self._extract_number(filtered_results)

        if raw_value and filtered_value:
            if raw_value != filtered_value:
                log.warning(
                    f"OCR mismatch: raw={raw_value} filtered={filtered_value}, using filtered"
                )
            return filtered_value
        return raw_value or filtered_value or 0

    def _preprocess_resource(self, crop: np.ndarray) -> np.ndarray:
        """Apply filters to improve OCR accuracy on resource text."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        upscaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        denoised = cv2.fastNlMeansDenoising(upscaled, h=10)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        bgr = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)
        return bgr

    def _extract_number(self, results: list) -> int | None:
        """Extract the first number from OCR results."""
        for _, text, _ in results:
            nums = [c for c in text if c.isdigit()]
            if nums:
                return int("".join(nums))
        return None

    def _save_resource_bboxes(
        self,
        img: np.ndarray,
        gold: int,
        elixir: int,
        dark_elixir: int,
    ) -> None:
        """Draw and save bounding boxes + preprocessed crops for comparison."""
        vis = img.copy()
        regions = [
            (config.GOLD_CROP_REGION, f"Gold: {gold}", (0, 215, 255)),
            (config.ELIXIR_CROP_REGION, f"Elixir: {elixir}", (255, 0, 255)),
            (config.DARK_ELIXIR_CROP_REGION, f"DE: {dark_elixir}", (0, 0, 255)),
        ]

        raw_crops = []
        filtered_crops = []
        for (x, y, w, h), label, color in regions:
            cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
            cv2.putText(vis, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            crop = img[y : y + h, x : x + w]
            processed = self._preprocess_resource(crop)
            raw_crops.append(crop)
            filtered_crops.append(processed)

        cv2.imwrite("resource_bboxes.png", vis)

        raw_row = np.hstack([cv2.resize(c, None, fx=2, fy=2) for c in raw_crops])
        filtered_row = np.hstack(
            [cv2.resize(c, None, fx=2, fy=2) for c in filtered_crops]
        )
        comparison = np.vstack([raw_row, filtered_row])
        cv2.imwrite("resource_comparison.png", comparison)

    def wait_for_button(
        self,
        folder: str,
        timeout: int = 180,
        dismiss_okay: bool = True,
    ) -> bool:
        """Poll screenshots until the button appears or timeout."""
        button_name = folder.rstrip("/").split("/")[-1]
        log.info(f"Searching for {button_name}...")
        start = time.time()

        while time.time() - start < timeout:
            if not self.device.take_screenshot(self.screenshot_name):
                time.sleep(config.BUTTON_POLL_INTERVAL)
                continue
            if self.click.detect_and_tap(folder):
                return True
            if dismiss_okay:
                self.click.detect_and_tap("templates/okay_button")
            time.sleep(config.BUTTON_POLL_INTERVAL)

        log.warning(f"Timeout: {button_name} not found")
        return False


if __name__ == "__main__":
    main()
