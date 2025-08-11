#!/usr/bin/env python3
"""
Generate and send humorous reminder emails for deals with missing values.

Environment:
- .env.local must contain:
  - RESEND_API_KEY: API key for Resend
  - RESEND_FROM: From email address, e.g. notifications@yourdomain.com
  - OPEN_AI_KEY: API key for OpenAI

Usage:
  python3 send_missing_deals_emails.py --input deals_missing.csv --emails emails.json --only "Wesley"

Notes:
- By default filters to a single recipient when --only is provided (case-insensitive match on name)
- Focuses on missing fields for value or company_name, but will include any missing fields present in the CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import List, Dict, Any

from dotenv import load_dotenv


def load_env() -> None:
    # Load variables from .env.local if present
    # Variables already present in the environment are not overwritten
    load_dotenv(".env.local", override=False)


def read_emails(path: str) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    results: List[Dict[str, str]] = []
    for item in data:
        name = (item.get("name") or "").strip()
        email = (item.get("email") or "").strip()
        if name and email:
            results.append({"name": name, "email": email})
    return results


def read_missing_deals(path: str) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def filter_rows_for_owner(rows: List[Dict[str, Any]], owner_name: str) -> List[Dict[str, Any]]:
    target = owner_name.strip().lower()
    target_first = target.split(" ")[0] if target else ""
    results: List[Dict[str, Any]] = []
    for r in rows:
        owner = (r.get("dealowner") or "").strip().lower()
        # Match when the provided name is contained in the full owner string,
        # or when first name matches
        if target and (target in owner or (target_first and owner.startswith(target_first))):
            # Focus on missing fields value/company_name if present in helper column
            missing_fields = (r.get("missing_fields") or "").strip()
            if missing_fields:
                r = dict(r)
                r["missing_fields_list"] = [x.strip() for x in missing_fields.split(",") if x.strip()]
            results.append(r)
    return results


def build_human_summary(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines: List[str] = []
    for r in rows:
        deal = r.get("deal") or r.get("dealname") or "(unnamed deal)"
        company = r.get("company_name") or "(missing company_name)"
        value = r.get("value") or "(missing value)"
        missing = r.get("missing_fields_list") or []
        if not missing and r.get("missing_fields"):
            missing = [x.strip() for x in (r.get("missing_fields") or "").split(",") if x.strip()]
        missing_str = ", ".join(missing) if missing else "value or company_name"
        lines.append(f"- {deal} | company: {company} | value: {value} | missing: {missing_str}")
    return "\n".join(lines)


def generate_email_with_openai(openai_api_key: str, recipient_name: str, deals_summary: str) -> Dict[str, str]:
    """Return dict with subject and html body."""
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover
        raise SystemExit("OpenAI SDK not installed. Please pip install openai.") from exc

    client = OpenAI(api_key=openai_api_key)

    system = (
        "You are a witty but professional assistant. Write concise, light-hearted emails that are helpful, "
        "never snarky, and easy to skim. Keep it under 180 words. Use a friendly tone, a playful metaphor, and a "
        "short actionable list. Close with a supportive one-liner. Return valid HTML with basic tags (<p>, <ul>, <li>, <strong>)."
    )
    user = (
        "Create a funny reminder email asking for missing deal details. Address the recipient by first name. "
        "Explain we’re tidying our HubSpot and need a couple of fields filled in (value/company name). "
        "List the deals below and what’s missing."
        f"\n\nRecipient: {recipient_name}\n\nDeals:\n{deals_summary}"
    )

    # Use small, fast model to keep it simple
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.8,
    )

    content = response.choices[0].message.content or ""
    # Heuristic: split first line as subject if prefixed
    subject = f"{recipient_name}, quick HubSpot tidy-up: a couple of fields missing"
    html = content
    return {"subject": subject, "html": html}


def send_with_resend(resend_api_key: str, from_email: str, to_email: str, subject: str, html: str) -> None:
    try:
        import resend
    except Exception as exc:  # pragma: no cover
        raise SystemExit("Resend SDK not installed. Please pip install resend.") from exc

    resend.api_key = resend_api_key
    params = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    resend.Emails.send(params)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send humorous reminders for missing deal fields")
    parser.add_argument("--input", default="deals_missing.csv", help="Path to missing deals CSV")
    parser.add_argument("--emails", default="emails.json", help="Path to recipients JSON")
    parser.add_argument("--only", default="Wesley", help="Only send to this name (exact match, case-insensitive)")
    parser.add_argument("--dry-run", action="store_true", help="Do not send, just print output")
    args = parser.parse_args()

    load_env()

    resend_api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM") or "onboarding@resend.dev"
    openai_key = os.getenv("OPEN_AI_KEY")

    if not openai_key:
        print("Missing OPEN_AI_KEY in environment (.env.local)", file=sys.stderr)
        sys.exit(2)

    if not args.dry_run and (not resend_api_key):
        print("Missing RESEND_API_KEY in environment (.env.local)", file=sys.stderr)
        sys.exit(2)

    recipients = read_emails(args.emails)
    rows = read_missing_deals(args.input)

    target_name_lower = (args.only or "").strip().lower()
    recipients = [r for r in recipients if r["name"].lower() == target_name_lower]

    if not recipients:
        print(f"No recipient found for --only={args.only}")
        sys.exit(1)

    for r in recipients:
        name = r["name"]
        email = r["email"]
        owner_rows = filter_rows_for_owner(rows, name)
        # Only include rows that actually miss value or company_name
        owner_rows = [x for x in owner_rows if "value" in (x.get("missing_fields") or "") or "company_name" in (x.get("missing_fields") or "")]

        if not owner_rows:
            print(f"No missing rows for {name}. Skipping.")
            continue

        summary = build_human_summary(owner_rows)
        payload = generate_email_with_openai(openai_key, name.split(" ")[0], summary)

        subject = payload["subject"]
        html = payload["html"]

        if args.dry_run:
            print(f"\n=== DRY RUN: Email to {name} <{email}> ===")
            print(f"Subject: {subject}")
            print(html)
        else:
            send_with_resend(resend_api_key, from_email, email, subject, html)
            print(f"Sent email to {name} <{email}>")


if __name__ == "__main__":
    main()


