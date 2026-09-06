#!/usr/bin/env python3
# DigiForge — Developed by Mikal

import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path

RPC_USER = "digiforge"
PASSWORD_FILE = Path(
    os.environ.get(
        "DIGIBYTE_RPC_PASSWORD_FILE",
        "/secrets/digibyte-rpc-password",
    )
)

try:
    password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
except OSError as exc:
    raise SystemExit(f"DigiForge: cannot read RPC password file: {exc}")

if not password:
    raise SystemExit("DigiForge: RPC password file is empty")

args = sys.argv[1:] or ["/usr/bin/digibyted", "-daemon=0"]

if any(arg.startswith("-rpcpassword=") for arg in args):
    raise SystemExit(
        "DigiForge: refusing to start with plaintext -rpcpassword argument"
    )

salt = secrets.token_hex(16)
digest = hmac.new(
    salt.encode("utf-8"),
    password.encode("utf-8"),
    hashlib.sha256,
).hexdigest()

rpcauth = f"{RPC_USER}:{salt}${digest}"

os.execvp(args[0], [*args, f"-rpcauth={rpcauth}"])
