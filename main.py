#!/usr/bin/env python3
"""Clash of Clans Bot - Main Entry Point."""

import argparse
import subprocess

import config
from bot import CoCBot
from utils.device import DeviceController
from utils.scrcpy_controller import ScrcpyController


def main(args):
    """Run the bot."""
    print("Initializing Device Controller...")
    try:
        if args.control == "scrcpy":
            device = ScrcpyController(device_id=args.device)
        else:
            device = DeviceController(device_id=args.device)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
        print(f"Failed to initialize {args.control} controller: {e}")
        return

    print("Starting CoC Bot...")
    coc_bot = CoCBot(device_controller=device, webhook_url=args.webhook)

    try:
        coc_bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    finally:
        device.close()


def main_entry() -> None:
    """CLI entry point for the `coc-bot` script."""
    parser = argparse.ArgumentParser(description="Clash of Clans Bot")
    parser.add_argument("--device", type=str, help="ADB Device ID")
    parser.add_argument(
        "--control",
        type=str,
        choices=["scrcpy", "adb"],
        default=config.CONTROL_MODE,
        help="Input/screenshot backend (default: scrcpy)",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        help="Discord Webhook URL",
        default=config.DISCORD_WEBHOOK_URL,
    )

    args = parser.parse_args()
    main(args)


if __name__ == "__main__":
    main_entry()
