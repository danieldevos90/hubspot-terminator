#!/usr/bin/env python3
"""
Manage Resend API keys from the CLI.

Usage examples:
  python3 resend_keys.py --env hubspot/.env.local list
  python3 resend_keys.py --env hubspot/.env.local create --name "Production"
  python3 resend_keys.py --env hubspot/.env.local remove --id <api_key_id>
"""

from __future__ import annotations

import argparse
import os
import sys

from send_missing_deals_emails import load_env  # reuse env loader


def ensure_resend_installed() -> None:
    try:
        import resend  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise SystemExit("Resend SDK not installed. Please pip install resend.") from exc


def cmd_list() -> None:
    import resend

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("Missing RESEND_API_KEY in environment.", file=sys.stderr)
        sys.exit(2)
    resend.api_key = api_key
    result = resend.ApiKeys.list()
    keys = result.get("data") or result
    print("API Keys:")
    for k in keys:
        key_id = k.get("id")
        name = k.get("name")
        created = k.get("created_at") or k.get("createdAt")
        print(f"- {name} | id={key_id} | created={created}")


def cmd_create(name: str) -> None:
    import resend

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("Missing RESEND_API_KEY in environment.", file=sys.stderr)
        sys.exit(2)
    resend.api_key = api_key

    params = {"name": name}
    created = resend.ApiKeys.create(params)
    # Resend typically returns token only once on creation
    token = created.get("token") or created.get("key")
    print("Created API key:")
    print(f"- id={created.get('id')}")
    print(f"- name={created.get('name')}")
    print(f"- created_at={created.get('created_at') or created.get('createdAt')}")
    if token:
        print("- token=", token)
        print("IMPORTANT: Store this token securely; it may not be retrievable again.")


def cmd_remove(key_id: str) -> None:
    import resend

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("Missing RESEND_API_KEY in environment.", file=sys.stderr)
        sys.exit(2)
    resend.api_key = api_key
    resend.ApiKeys.remove(api_key_id=key_id)
    print(f"Removed API key {key_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Resend API keys")
    parser.add_argument("--env", default=None, help="Path to .env file (e.g., hubspot/.env.local)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List API keys")

    p_create = sub.add_parser("create", help="Create a new API key")
    p_create.add_argument("--name", required=True, help="Name for the new API key")

    p_remove = sub.add_parser("remove", help="Remove an API key")
    p_remove.add_argument("--id", required=True, help="API key id to remove")

    args = parser.parse_args()
    load_env(args.env)
    ensure_resend_installed()

    if args.command == "list":
        cmd_list()
    elif args.command == "create":
        cmd_create(args.name)
    elif args.command == "remove":
        cmd_remove(args.id)
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()


