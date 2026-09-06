#!/usr/bin/env python3
# DigiForge — Developed by Mikal

import os
import secrets
from pathlib import Path

SECRETS_DIR = Path("/secrets")


def ensure_secret(name):
    path = SECRETS_DIR / name

    if path.exists():
        os.chmod(path, 0o600)
        print(f"{name}: existing")
        return

    value = secrets.token_urlsafe(32) + "\n"

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    try:
        os.write(fd, value.encode())
        os.fsync(fd)
    finally:
        os.close(fd)

    print(f"{name}: created")


SECRETS_DIR.mkdir(parents=True, exist_ok=True)
os.chmod(SECRETS_DIR, 0o700)

ensure_secret("digibyte-rpc-password")
ensure_secret("postgres-password")
