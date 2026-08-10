# coc Bot (Terminal-Based)

This is a **personal-use coc bot** built to automate attacks in **Main Village**.  
It is designed to run fully from the **terminal (no GUI)** using **ADB + image recognition**.  
Optimized for farming and hands-free gameplay.


# IN ACTION VIDEO

https://github.com/user-attachments/assets/b609796c-f414-47ae-aeb2-35f4bfbc7c7b


---


## 🧪 Setup (uv)

The project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies and create the lockfile
uv sync

# Run the bot
uv run coc-bot
uv run coc-bot --device <DEVICE_ID>

# Run the OpenCV match tool (live crop detection web app)
uv run match-tool                # serves on http://127.0.0.1:8080
uv run match-tool 9090           # custom port

# Lint / format / type-check
uv run ruff check .
uv run black .
uv run mypy .
```


---

## 🔧 Features

- 🏰 **Base Searching**

  - Searches for enemy bases using loot.
  - Set minimum loot threshold (Gold, Elixir, Dark Elixir).

- ⚔️ **Troop Deployment**

  - Smart deployment logic for farming or trophy pushing.
  - Works best with optimized army compositions.
  - Avoids poor bases, improving chances of consistent wins.


- 🎯 **Custom Threshold Settings**

  - Set loot threshold
  - Lower thresholds = more frequent matches and faster farming.

- 🖥️ **Terminal-Based Only**
  - Simple, fast, and lightweight.
  - No GUI, no mouse simulation — just clean CLI execution.

---

## 🚀 Improvements & New Features

### 1. Configuration File (`config.py`)
All settings (loot thresholds, deployment coordinates, file paths) are now in `config.py`.  
Edit this file to change your bot's behavior without touching the code.

### 2. Command Line Arguments
Run the bot with specific options:
```bash
# Run with a specific device ID
python bot.py --device <DEVICE_ID>

# Install / run as a console script instead
uv run coc-bot
```


---
*Auto-sync: 2026-07-26 11:03*
