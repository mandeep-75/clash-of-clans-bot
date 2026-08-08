#!/usr/bin/env python3
"""Clash of Clans Bot - Main Entry Point."""

import argparse

import config
from bot import CoCBot
from utils.device import DeviceController


def main(args):
    """Run the bot."""
    print("Initializing Device Controller...")
    device = DeviceController(device_id=args.device)

    print("Starting CoC Bot...")
    coc_bot = CoCBot(device_controller=device, webhook_url=args.webhook)

    try:
        coc_bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")


def main_entry() -> None:
    """CLI entry point for the `coc-bot` script."""
    parser = argparse.ArgumentParser(description="Clash of Clans Bot")
    parser.add_argument("--device", type=str, help="ADB Device ID")
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
