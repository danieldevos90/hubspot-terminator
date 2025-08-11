#!/usr/bin/env python3
"""
Send humorous reminder emails via Outlook (Microsoft Graph) for deals with missing values.

Environment (put in .env.local or pass via --env hubspot/.env.local):
- OPEN_AI_KEY: OpenAI API key
- AZURE_TENANT_ID: Azure AD tenant ID (GUID)
- AZURE_CLIENT_ID: App registration (client) ID
- AZURE_CLIENT_SECRET: Client secret for the app registration (or use certificate instead)
- OUTLOOK_SENDER: User principal name (email) to send as, e.g. daniel.devos@vasco-consult.com

This uses Microsoft Graph sendMail endpoint with application permissions:
POST https://graph.microsoft.com/v1.0/users/{OUTLOOK_SENDER}/sendMail

Your Azure app must have "Mail.Send" application permission with admin consent.

References:
- Microsoft Graph Mail API overview: https://learn.microsoft.com/en-us/outlook/rest/get-started
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict

import requests
import msal

from send_missing_deals_emails import (
    load_env,
    read_emails,
    read_missing_deals,
    filter_rows_for_owner,
    build_human_summary,
    generate_email_with_openai,
)


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def acquire_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )
    # Application permission: use .default to use app's granted permissions (Mail.Send)
    result: Dict = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise SystemExit(f"Failed to acquire token: {json.dumps(result, indent=2)}")
    return str(result["access_token"])


def send_with_outlook_graph(
    access_token: str,
    sender_upn: str,
    to_email: str,
    subject: str,
    html: str,
) -> None:
    url = f"{GRAPH_BASE}/users/{sender_upn}/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": True,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code not in (202, 200):
        raise SystemExit(
            f"Graph sendMail failed {resp.status_code}: {resp.text}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send reminders via Outlook (Microsoft Graph)")
    parser.add_argument("--env", default=None, help="Path to .env file (e.g., hubspot/.env.local)")
    parser.add_argument("--input", default="deals_missing.csv", help="Path to missing deals CSV")
    parser.add_argument("--emails", default="emails.json", help="Path to recipients JSON")
    parser.add_argument("--only", default="Wesley", help="Only send to this name (exact match, case-insensitive)")
    parser.add_argument("--all", action="store_true", help="Send to all recipients in emails.json")
    parser.add_argument("--dry-run", action="store_true", help="Do not send, just print output")
    args = parser.parse_args()

    load_env(args.env)

    openai_key = os.getenv("OPEN_AI_KEY")
    if not openai_key:
        print("Missing OPEN_AI_KEY in environment", file=sys.stderr)
        sys.exit(2)

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    sender_upn = os.getenv("OUTLOOK_SENDER")

    if not args.dry_run and (not tenant_id or not client_id or not client_secret or not sender_upn):
        print("Missing one of AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, OUTLOOK_SENDER", file=sys.stderr)
        sys.exit(2)

    recipients = read_emails(args.emails)
    rows = read_missing_deals(args.input)

    if not args.all:
        target_name_lower = (args.only or "").strip().lower()
        recipients = [r for r in recipients if r["name"].lower() == target_name_lower]

    if not recipients:
        print(f"No recipient found for --only={args.only}")
        sys.exit(1)

    # Acquire token only once
    access_token = None
    if not args.dry_run:
        access_token = acquire_graph_token(tenant_id, client_id, client_secret)

    for r in recipients:
        name = r["name"]
        email = r["email"]
        owner_rows = filter_rows_for_owner(rows, name)
        owner_rows = [x for x in owner_rows if "value" in (x.get("missing_fields") or "") or "company_name" in (x.get("missing_fields") or "")]

        if not owner_rows:
            print(f"No missing rows for {name}. Skipping.")
            continue

        summary = build_human_summary(owner_rows)
        payload = generate_email_with_openai(openai_key, name.split(" ")[0], summary)

        subject = payload["subject"]
        html = payload["html"]

        if args.dry_run:
            print(f"\n=== DRY RUN (Outlook): Email to {name} <{email}> ===")
            print(f"Subject: {subject}")
            print(html)
        else:
            send_with_outlook_graph(access_token, sender_upn, email, subject, html)
            print(f"Sent email to {name} <{email}> via Outlook")


if __name__ == "__main__":
    main()


