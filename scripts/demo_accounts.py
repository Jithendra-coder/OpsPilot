"""Create or verify the two named identities used by the isolated Compose demo."""

from __future__ import annotations

import os

import app
from backend.auth import normalize_username
from scripts.accounts import add_account


def ensure_account(username: str, role: str, password: str) -> None:
    username = normalize_username(username)
    with app.db() as con:
        existing = con.execute("SELECT role,active FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        if existing["role"] != role or not existing["active"]:
            raise SystemExit("Configured demo identity exists with a different role or is disabled: " + username)
        return
    add_account(username, role, password)


def main() -> None:
    app.initialize()
    ensure_account(os.environ["OPSPILOT_OPERATOR_USERNAME"], "operator", os.environ["OPSPILOT_OPERATOR_PASSWORD"])
    ensure_account(os.environ["OPSPILOT_APPROVER_USERNAME"], "approver", os.environ["OPSPILOT_APPROVER_PASSWORD"])
    with app.db() as con:
        roles = {row["role"] for row in con.execute("SELECT role FROM users WHERE active=1").fetchall()}
    if not {"operator", "approver"}.issubset(roles):
        raise SystemExit("The demo database must contain an active operator and approver.")


if __name__ == "__main__":
    main()
