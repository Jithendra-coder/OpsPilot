"""Manage named operator and approver accounts from the host running OpsPilot."""

from __future__ import annotations

import argparse
import getpass

import app
from backend.auth import hash_password, normalize_username


def list_accounts():
    with app.db() as con:
        return con.execute("SELECT username,role,active FROM users ORDER BY username").fetchall()


def add_account(username: str, role: str, password: str) -> str:
    username = normalize_username(username)
    if role not in {"operator", "approver"}:
        raise ValueError("Role must be operator or approver.")
    salt, digest = hash_password(password)
    with app.db() as con:
        if con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ValueError("That username already exists; use set-password to rotate its password.")
        first_user = not con.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        user_id = app.ident("USR")
        stamp = app.now()
        con.execute("INSERT INTO users(id,username,password_hash,password_salt,role,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",
            (user_id, username, digest, salt, role, stamp, stamp))
        if first_user:
            con.execute("DELETE FROM sessions WHERE user_id IS NULL")
        app.audit(con, "Local account administrator", "admin", "team_account.created", user_id, {"username": username, "role": role})
    return user_id


def disable_account(username: str) -> None:
    username = normalize_username(username)
    with app.db() as con:
        user = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            raise ValueError("No such team account.")
        con.execute("UPDATE users SET active=0,updated_at=? WHERE id=?", (app.now(), user["id"]))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        app.audit(con, "Local account administrator", "admin", "team_account.disabled", user["id"], {"username": username})


def set_account_password(username: str, password: str) -> None:
    username = normalize_username(username)
    salt, digest = hash_password(password)
    with app.db() as con:
        user = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            raise ValueError("No such team account.")
        con.execute("UPDATE users SET password_hash=?,password_salt=?,updated_at=? WHERE id=?",
            (digest, salt, app.now(), user["id"]))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        app.audit(con, "Local account administrator", "admin", "team_account.password_changed", user["id"], {"username": username})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="create a named team account")
    add.add_argument("--username", required=True)
    add.add_argument("--role", choices=("operator", "approver"), required=True)
    reset = commands.add_parser("set-password", help="change an account password and revoke its sessions")
    reset.add_argument("--username", required=True)
    disable = commands.add_parser("disable", help="disable an account and revoke its sessions")
    disable.add_argument("--username", required=True)
    commands.add_parser("list", help="list account names and roles")
    args = parser.parse_args(argv)
    app.initialize()

    if args.command == "list":
        for row in list_accounts():
            print(f"{row['username']}\t{row['role']}\t{'active' if row['active'] else 'disabled'}")
        return 0

    try:
        username = normalize_username(args.username)
    except ValueError as error:
        parser.error(str(error))
    if args.command == "disable":
        try:
            disable_account(username)
        except ValueError as error:
            parser.error(str(error))
        print(f"Disabled {username} and revoked its sessions.")
        return 0

    if args.command == "add":
        role = args.role
    else:
        role = None
    password = getpass.getpass("New password (16+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords did not match.")
    try:
        if args.command == "add":
            add_account(username, role, password)
        else:
            set_account_password(username, password)
    except ValueError as error:
        parser.error(str(error))
    print(f"{'Created' if args.command == 'add' else 'Updated'} account {username}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
