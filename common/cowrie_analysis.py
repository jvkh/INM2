"""Lightweight heuristics for grouping and classifying Cowrie shell commands."""

import re


_COMMAND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("persistence", re.compile(r"(?:\bcrontab\b|/etc/cron|\bsystemctl\s+enable\b|\bservice\s+\S+\s+start\b|/etc/rc\.local|/etc/init\.d|authorized_keys)", re.I)),
    ("credential_access", re.compile(r"(?:/etc/(?:passwd|shadow|gshadow)|\.ssh/|\bssh-keygen\b|\bpasswd\b|\bhistory\b|\b(secret|token|credential)s?\b|\.aws/credentials)", re.I)),
    ("download", re.compile(r"(?:\b(?:wget|curl|tftp|ftp|scp|sftp|nc|netcat)\b|busybox\s+wget)", re.I)),
    ("destructive", re.compile(r"(?:\brm\s+-[^\n]*r[^\n]*f\b|\bmkfs(?:\.|\s)|\bdd\s+if=|\b(?:shutdown|reboot|poweroff)\b)", re.I)),
    ("execution", re.compile(r"(?:\bchmod\b|\bbase64\b.*(?:-d|--decode)|\b(?:python\w*|perl|ruby)\s+-[ce]\b|\b(?:bash|sh)\s+-c\b|/dev/shm/|/tmp/|\bnohup\b)", re.I)),
    ("discovery", re.compile(r"(?:\b(?:whoami|id|uname|hostname|pwd|ls|find|ps|netstat|ifconfig|mount|df|env|printenv)\b|\bip\s+(?:addr|route|link)\b|/etc/os-release|/proc/)", re.I)),
)


def classify_command(command: str) -> str:
    """Return a broad behavioral category; this is a heuristic, not a verdict."""
    value = command.strip()
    for category, pattern in _COMMAND_PATTERNS:
        if pattern.search(value):
            return category
    return "other"

