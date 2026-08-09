# AGENTS.md - CoC Bot Developer Guide

## Project Overview

This is a Python CLI bot that automates attacks in Clash of Clans using ADB and image recognition (OpenCV, EasyOCR).

## Build / Lint / Test Commands

### Install Dependencies
```bash
uv sync
```

### Running the Bot
```bash
python main.py                    # Run with default device
python main.py --device <ID>      # Run with specific ADB device
python main.py --webhook <URL>    # Override Discord webhook
```

### Linting & Formatting
```bash
# Format code (Black)
black .

# Run linter (Ruff)
ruff check .

# Type checking (MyPy)
mypy .
```

### Single Test Commands
There are currently **no tests** in this project. If tests are added, run them with:
```bash
pytest                           # Run all tests
pytest path/to/test_file.py     # Run specific test file
pytest -k test_name             # Run tests matching pattern
```

---

## Code Style Guidelines

### General Conventions
- **Language**: Python 3.10+
- **Line length**: 88 characters (Black default)
- **Indentation**: 4 spaces
- **Encoding**: UTF-8

### Naming Conventions
- **Classes**: `PascalCase` (e.g., `CoCBot`, `DeviceController`)
- **Functions/variables**: `snake_case` (e.g., `take_screenshot`, `device_id`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `SCREENSHOT_NAME`)
- **Private methods**: prefix with `_` (e.g., `_run_flow`)

### Type Hints
- **Always use type hints** for function parameters and return types
- Use built-in types (`int`, `str`, `list`, `dict`) or `typing` module
- Example:
```python
def detect_button(self, button_folder: str, threshold: float = 0.8) -> tuple[int, int] | None:
```

### Import Organization
Sort imports with Ruff or manually maintain this order (separate with blank lines):
1. Standard library (`time`, `os`, `subprocess`)
2. Third-party packages (`cv2`, `easyocr`, `numpy`)
3. Local imports (`config`, `utils.device`)

### Error Handling
- Use specific exception types when possible
- Log errors with descriptive messages
- Continue execution gracefully for recoverable errors
- Example:
```python
try:
    subprocess.run(cmd, check=True, stdout=f)
except subprocess.CalledProcessError as e:
    print(f"Failed to take screenshot: {e}")
```

### Code Documentation
- Use docstrings for public classes and functions
- Keep docstrings concise; describe what the function does, not how
- Example:
```python
def take_screenshot(self, local_path: str = config.SCREENSHOT_NAME) -> None:
    """Captures a screenshot from the device."""
```

### File Structure
- Main entry point: `main.py`
- Core logic: `bot.py`
- Configuration: `config.py`
- Utilities: `utils/` directory

### Configuration
- All configurable values go in `config.py`
- Use descriptive constant names
- Group related settings with comments

### Logging
- Use `print()` for runtime output (CLI app)
- Use f-strings for formatting
- Include context in error messages

### Best Practices
- Avoid magic numbers; use named constants
- Use `pathlib` for file paths when possible
- Validate inputs in public methods
- Keep functions small and focused (single responsibility)
- Use `enumerate()` instead of manual counters when looping with index

---

## Common Tasks

### Adding a New Feature
1. Add configuration in `config.py` if needed
2. Implement logic in `bot.py` or create new module in `utils/`
3. Add to `FLOW_CONFIG` if it's a toggleable task
4. Run linters: `ruff check . && black . && mypy .`

### Debugging
- Screenshots are saved to `screen.png` during execution
- Logs are written to `bot_session_log.txt`
- Enable verbose mode in `DeviceController` for detection debug output

### Adding UI Templates
Place PNG templates in `templates/<category>/<name>/` directory for template matching.

### Match Tool (`match_tool/`)
- Frontend: `match_tool/templates/index.html`; server: `match_tool/app.py` (Flask, run with `python match_tool/app.py <port>`).
- Do NOT use the Playwright browser tools to test this project. The user tests the UI themselves. Verify with server-side checks only (e.g. start the server and `curl` the endpoints), and never run destructive API calls (like `POST /api/clear_crops`) against real data.
