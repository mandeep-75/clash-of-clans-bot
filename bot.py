import random
import time

import config
from utils.text_detect_resource import get_resource_values


class CoCBot:
    def __init__(self, device_controller, webhook_url=None):
        self.device = device_controller
        self.webhook_url = webhook_url

        self.loop_count = 0
        self.start_time = time.time()
        self.stop_flag = False

        self.session_gold = 0
        self.session_elixir = 0
        self.session_dark = 0
        self.last_resources = None
        self.deployed_heroes = {}

        self.flow = config.FLOW_CONFIG

    def stop(self):
        """Signal the bot to stop after current loop."""
        self.stop_flag = True

    def run(self):
        """Main Bot Loop"""
        self._print_flow()
        self.stop_flag = False

        with open(config.LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n\n===== NEW BOT SESSION STARTED =====\n")
            f.write(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        while not self.stop_flag:
            try:
                self.loop_count += 1
                print(f"\n{'='*20} LOOP {self.loop_count} {'='*20}")
                self._run_flow()
                self._log_summary()
            except Exception as e:
                print(f"Error in loop: {e}")
                time.sleep(5)

        print("\n Bot stopped gracefully.")

    def _print_flow(self):
        """Print the flow of tasks at startup."""
        print("\n" + "=" * 50)
        print("BOT FLOW CONFIGURATION")
        print("=" * 50)
        for task, enabled in self.flow.items():
            status = "[ON]" if enabled else "[OFF]"
            print(f"  {status} {task}")
        print("=" * 50 + "\n")

    def _run_flow(self):
        """Run each enabled task in order."""
        if self.flow.get("collect_gold"):
            self._collect_resource("gold_collect", "Gold")
        if self.flow.get("collect_elixir"):
            self._collect_resource("elixir_collect", "Elixir")
        if self.flow.get("collect_dark_elixir"):
            self._collect_resource("dark_elixir_collect", "Dark Elixir")

        if not self.flow.get("find_match"):
            return

        if not self._navigate_to_attack():
            return

        if self.flow.get("search_for_base"):
            if not self._search_and_select_base():
                return

        self._zoom_on_battle_start()

        if self.flow.get("deploy_troops"):
            self._deploy_troops()
        if self.flow.get("deploy_heroes"):
            self._deploy_heroes()
        if self.flow.get("deploy_spells"):
            self._deploy_spells()
        if self.flow.get("trigger_abilities"):
            self._trigger_abilities()

        if self.flow.get("return_home"):
            self._return_home()

    def _collect_resource(self, folder: str, name: str):
        """Collect a single resource type."""
        print(f"Collecting {name}...")
        self.device.take_screenshot()
        self.device.detect_and_tap(f"templates/{folder}")

    def _navigate_to_attack(self) -> bool:
        """Navigate to attack screen and click Find Match."""
        print("Navigating to attack...")

        if not self._wait_for_button("templates/attack_button", timeout=30):
            print("Timeout waiting for Attack button")
            return False

        time.sleep(1)

        if not self._wait_for_button("templates/find_match_button", timeout=30):
            print("Timeout waiting for Find Match button")
            return False

        time.sleep(2)
        self.device.take_screenshot()

        if self.device.detect_and_tap("templates/attack"):
            time.sleep(2)

        return True

    def _wait_for_button(self, folder: str, timeout: int = 30) -> bool:
        """Wait for a button to appear."""
        start = time.time()
        while time.time() - start < timeout:
            self.device.take_screenshot()
            if self.device.detect_and_tap(folder):
                return True
            self.device.detect_and_tap("templates/okay_button")
            time.sleep(2)
        return False

    def _search_and_select_base(self) -> bool:
        """Search for base meeting resource requirements."""
        print("Searching for base...")
        search_start = time.time()
        attempt = 1

        while not self.stop_flag:
            if time.time() - search_start > config.BASE_SEARCH_TIMEOUT:
                print("Timeout searching for base")
                return False

            resources = get_resource_values(config.SCREENSHOT_NAME)
            if resources is None:
                print(f"Base {attempt}: (failed to read resources)")
                time.sleep(random.uniform(4.5, 5))
                self.device.take_screenshot()
                attempt += 1
                continue

            gold = resources.get("gold", 0)
            elixir = resources.get("elixir", 0)
            dark = resources.get("dark_elixir", 0)

            if self.last_resources == resources or (
                gold == 0 and elixir == 0 and dark == 0
            ):
                print(f"Base {attempt}: (skipping invalid read)")
            else:
                print(f"Base {attempt}: Gold={gold:,} Elixir={elixir:,} Dark={dark:,}")

            self.last_resources = resources.copy()

            if (
                gold >= config.GOLD_THRESHOLD or elixir >= config.ELIXIR_THRESHOLD
            ) and dark >= config.DARK_ELIXIR_THRESHOLD:
                print("Target found!")
                self.session_gold += gold
                self.session_elixir += elixir
                self.session_dark += dark

                with open(config.LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(
                        f"Attack {self.loop_count}: Gold={gold:,}, Elixir={elixir:,}, Dark={dark:,}\n"
                    )

                return True

            print("Skipping...")
            if self.device.detect_and_tap("templates/next_button"):
                search_start = time.time()

            time.sleep(random.uniform(4.5, 5))
            self.device.take_screenshot()
            attempt += 1

        return False  # Stopped

    def _zoom_on_battle_start(self):
        """Pinch-zoom the battlefield before deploying (if enabled)."""
        direction = config.BATTLE_ZOOM
        if not direction:
            return

        print(f"Pinch zooming {direction} on battle start...")
        try:
            self.device.pinch_zoom(
                direction=direction,
                start_dist=config.ZOOM_START_DIST,
                end_dist=config.ZOOM_END_DIST,
                steps=config.ZOOM_STEPS,
            )
        except (RuntimeError, OSError) as e:
            print(f"Pinch zoom failed: {e}")
        time.sleep(1.5)

    def _deploy_troops(self):
        """Deploy troops to battlefield with per-troop counts."""
        deployment_plan = {k: v for k, v in config.SELECTED_TROOPS.items() if v > 0}

        # Check if any troops have count > 0
        if not deployment_plan:
            print("No troops to deploy!")
            return

        locs = config.TROOP_LOCATIONS[:]
        random_offset = config.RANDOM_OFFSET

        if not locs:
            print("No troop locations defined!")
            return

        random.shuffle(locs)
        loc_index = 0

        # Deploy each troop type with its count
        for troop_folder, count in deployment_plan.items():
            if count <= 0:
                continue

            # Select this troop type in the UI
            if self.device.detect_and_tap(f"templates/troops/{troop_folder}"):
                print(f"Deploying {troop_folder} ({count})...")
                time.sleep(0.3)  # Wait for troop selection UI

                # Deploy 'count' troops at locations
                for i in range(count):
                    tgt = locs[loc_index % len(locs)]
                    self.device.tap(tgt[0], tgt[1], random_offset)
                    time.sleep(random.uniform(0.1, 0.2))
                    loc_index += 1

                time.sleep(0.3)  # Brief pause between troop types
            else:
                print(f"Troop button not found: {troop_folder}")

        time.sleep(random.uniform(4, 5))

    def _deploy_heroes(self):
        """Deploy heroes to battlefield."""
        print("Deploying heroes...")
        self.deployed_heroes = {}

        selected_heroes = [k for k, v in config.SELECTED_HEROES.items() if v > 0]

        if not selected_heroes:
            print("No heroes selected!")
            return

        hero_locs = config.HERO_LOCATIONS[:]
        random_offset = config.RANDOM_OFFSET_HEROES

        if not hero_locs:
            print("No hero locations defined!")
            return

        random.shuffle(hero_locs)
        loc_index = 0

        for hero_folder in selected_heroes:
            count = config.SELECTED_HEROES[hero_folder]
            if count <= 0:
                continue

            if self.device.detect_and_tap(f"templates/hero/{hero_folder}"):
                print(f"Deploying {hero_folder}...")
                for i in range(count):
                    loc = hero_locs[loc_index % len(hero_locs)]
                    self.device.tap(loc[0], loc[1], random_offset)
                    coords = self.device.detect_button(
                        f"templates/hero/{hero_folder}", threshold=0.8
                    )
                    if coords:
                        self.deployed_heroes[hero_folder] = coords
                    time.sleep(random.uniform(0.5, 1.0))
                    loc_index += 1
            else:
                print(f"Hero button not found: {hero_folder}")

    def _deploy_spells(self):
        """Deploy spells to battlefield."""
        selected_spells = [k for k, v in config.SELECTED_SPELLS.items() if v > 0]

        if not selected_spells:
            print("No spells selected!")
            return

        spell_locs = config.SPELL_LOCATIONS
        random_offset = config.RANDOM_OFFSET_SPELLS

        if not spell_locs:
            print("No spell locations defined!")
            return

        print("Deploying spells...")

        for spell_folder in selected_spells:
            count = config.SELECTED_SPELLS[spell_folder]
            if count <= 0:
                continue

            if self.device.detect_and_tap(f"templates/spells/{spell_folder}"):
                print(f"Deploying {spell_folder}...")
                for i in range(count):
                    loc = spell_locs[i % len(spell_locs)]
                    self.device.tap(loc[0], loc[1], random_offset)
                    time.sleep(0.3)
            else:
                print(f"Spell button not found: {spell_folder}")

    def _trigger_abilities(self):
        """Trigger hero abilities."""
        self._trigger_hero_ability("grand_warden")

    def _trigger_hero_ability(self, hero_name_partial: str):
        """Trigger a specific hero ability."""
        for name, coords in self.deployed_heroes.items():
            if hero_name_partial in name.lower():
                print(f"Activating {name} ability!")
                self.device.tap(coords[0], coords[1], config.RANDOM_OFFSET_HEROES)
                break

    def _return_home(self):
        """Return home after battle."""
        print("Returning home...")
        wait_start = time.time()
        timeout = config.RETURN_HOME_TIMEOUT

        while time.time() - wait_start < timeout:
            if self.stop_flag:
                return
            self.device.take_screenshot()

            if self.device.detect_and_tap("templates/return_home"):
                time.sleep(3)
                self.device.detect_and_tap("templates/okay_button")
                return

            time.sleep(3)

        print("Force ending battle...")
        self.device.take_screenshot()
        self.device.detect_and_tap("templates/end_battle")
        self.device.detect_and_tap("templates/surrender_button")
        time.sleep(1)
        self.device.take_screenshot()
        self.device.detect_and_tap("templates/return_home")

    def _log_summary(self):
        """Log session summary every 5 loops."""
        if self.loop_count % 5 != 0:
            return

        elapsed_min = (time.time() - self.start_time) / 60
        avg_gold = self.session_gold / self.loop_count
        avg_elixir = self.session_elixir / self.loop_count
        avg_dark = self.session_dark / self.loop_count

        summary = (
            f"\n===== SESSION SUMMARY =====\n"
            f"Attacks: {self.loop_count}\n"
            f"Avg Gold: {avg_gold:,.0f}\n"
            f"Avg Elixir: {avg_elixir:,.0f}\n"
            f"Avg Dark: {avg_dark:,.0f}\n"
            f"Runtime: {elapsed_min:.1f} min\n"
            f"===========================\n"
        )
        print(summary)
        with open(config.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(summary)
