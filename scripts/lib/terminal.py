"""Terminal output utilities — colors and formatting.

Replaces raw ANSI escape codes (TD-006) with structured helpers.
Uses `rich` when available, falls back to TTY-detected ANSI codes.

Usage:
    from scripts.lib.terminal import green, red, yellow, bold, cyan, header

    print(green("PASS"), "All tests passed")
    print(red("FAIL"), "Something broke")
    print(header("GATE 2: Semantic Compatibility"))
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# TTY detection
# ---------------------------------------------------------------------------

_IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _tty_wrap(text: str, ansi_code: str) -> str:
    if _IS_TTY:
        return f"{ansi_code}{text}\033[0m"
    return text


# ---------------------------------------------------------------------------
# Color helpers — rich-style naming
# ---------------------------------------------------------------------------


def green(text: str) -> str:
    """Return text wrapped in green (TTY only)."""
    return _tty_wrap(text, "\033[92m")


def red(text: str) -> str:
    """Return text wrapped in red (TTY only)."""
    return _tty_wrap(text, "\033[91m")


def yellow(text: str) -> str:
    """Return text wrapped in yellow (TTY only)."""
    return _tty_wrap(text, "\033[93m")


def cyan(text: str) -> str:
    """Return text wrapped in cyan (TTY only)."""
    return _tty_wrap(text, "\033[96m")


def bold(text: str) -> str:
    """Return text wrapped in bold (TTY only)."""
    return _tty_wrap(text, "\033[1m")


def magenta(text: str) -> str:
    """Return text wrapped in magenta (TTY only)."""
    return _tty_wrap(text, "\033[95m")


def header(text: str) -> str:
    """Return a formatted header line."""
    bar = "=" * 60
    return f"\n{bar}\n{text}\n{bar}"


def ok(msg: str) -> str:
    """Format as OK message."""
    return f"{green('PASS')} {msg}"


def fail(msg: str) -> str:
    """Format as FAIL message."""
    return f"{red('FAIL')} {msg}"


def warn(msg: str) -> str:
    """Format as WARN message."""
    return f"{yellow('WARN')} {msg}"


def fix(msg: str) -> str:
    """Format as FIX message."""
    return f"{cyan('FIX')} {msg}"
