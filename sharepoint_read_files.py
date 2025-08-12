#!/usr/bin/env python3
"""
List or download files from SharePoint using Microsoft Graph (application permissions).

Environment (put in .env.local or pass via --env hubspot/.env.local):
- AZURE_TENANT_ID: Azure AD tenant ID (GUID)
- AZURE_CLIENT_ID: App registration (client) ID
- AZURE_CLIENT_SECRET: Client secret for the app registration

Permissions required for the Azure app:
- For reading files: Files.Read.All OR Sites.Read.All (Application) with admin consent

Examples:
  # List root of the default "Documents" library on a site
  python3 sharepoint_read_files.py --env .env.local \
    --site-host contoso.sharepoint.com --site-path /sites/Sales --list /

  # List a folder
  python3 sharepoint_read_files.py --env .env.local \
    --site-host contoso.sharepoint.com --site-path /sites/Sales \
    --list /Shared Reports/2025

  # Download a single file
  python3 sharepoint_read_files.py --env .env.local \
    --site-host contoso.sharepoint.com --site-path /sites/Sales \
    --download /Shared Reports/2025/summary.xlsx --out ./summary.xlsx

  # Download a whole folder recursively into ./downloads
  python3 sharepoint_read_files.py --env .env.local \
    --site-host contoso.sharepoint.com --site-path /sites/Sales \
    --download-folder /Shared Reports/2025 --out-dir ./downloads
"""

from __future__ import annotations

import argparse
import os
import sys
import json
from typing import Dict, List, Optional

import requests
import msal

try:
    # Reuse env loader behavior used by other scripts in this repo
    from send_missing_deals_emails import load_env as load_env_vars
except Exception:
    def load_env_vars(env_path: str | None = None) -> None:  # type: ignore
        try:
            from dotenv import load_dotenv  # type: ignore
        except Exception:  # pragma: no cover
            return
        if env_path:
            load_dotenv(env_path, override=False)
        load_dotenv(".env.local", override=False)


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def acquire_graph_app_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )
    result: Dict = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise SystemExit(f"Failed to acquire token: {json.dumps(result, indent=2)}")
    return str(result["access_token"])


def graph_get(access_token: str, url: str, params: Optional[dict] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        message = f"Graph error {resp.status_code} for GET {url}: {resp.text}"
        raise SystemExit(message) from exc
    return resp.json()


def graph_download(access_token: str, url: str, dest_path: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        try:
            r.raise_for_status()
        except requests.HTTPError as exc:
            message = f"Graph download error {r.status_code} for GET {url}: {r.text}"
            raise SystemExit(message) from exc
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def resolve_site_id(access_token: str, site_host: Optional[str], site_path: Optional[str], site_id: Optional[str]) -> str:
    if site_id:
        return site_id
    if not site_host or not site_path:
        raise SystemExit("Provide either --site-id or both --site-host and --site-path")
    # GET /sites/{host}:/sites/{path}
    url = f"{GRAPH_BASE}/sites/{site_host}:/sites/{site_path}"
    data = graph_get(access_token, url)
    site_id_value = data.get("id")
    if not site_id_value:
        raise SystemExit("Unable to resolve site id from host/path.")
    return str(site_id_value)


def list_site_drives(access_token: str, site_id: str) -> List[dict]:
    url = f"{GRAPH_BASE}/sites/{site_id}/drives"
    data = graph_get(access_token, url)
    return data.get("value", [])


def resolve_drive_id(access_token: str, site_id: str, drive_name: Optional[str]) -> str:
    drives = list_site_drives(access_token, site_id)
    if not drives:
        raise SystemExit("No document libraries found on the site.")
    if drive_name:
        for d in drives:
            if str(d.get("name")).strip().lower() == drive_name.strip().lower():
                return str(d.get("id"))
        raise SystemExit(f"Drive named '{drive_name}' not found. Available: {[d.get('name') for d in drives]}")
    # Default to the standard Documents library if present, else the first one
    for d in drives:
        if str(d.get("name")).strip().lower() in ("documents", "shared documents"):
            return str(d.get("id"))
    return str(drives[0].get("id"))


def get_item_by_path(access_token: str, drive_id: str, path_in_drive: str) -> dict:
    normalized = path_in_drive.strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    # /drives/{drive-id}/root:/path/to/item
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{normalized}"
    return graph_get(access_token, url)


def list_children(access_token: str, drive_id: str, folder_path: str) -> List[dict]:
    normalized = folder_path.strip()
    if normalized in ("", "/"):
        url = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
        data = graph_get(access_token, url)
        return data.get("value", [])
    item = get_item_by_path(access_token, drive_id, normalized)
    item_id = item.get("id")
    if not item_id:
        return []
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children"
    data = graph_get(access_token, url)
    return data.get("value", [])


def download_file(access_token: str, drive_id: str, file_path: str, dest_path: str) -> None:
    normalized = file_path.strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    # Direct content URL
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{normalized}:/content"
    graph_download(access_token, url, dest_path)


def download_folder_recursive(access_token: str, drive_id: str, folder_path: str, dest_dir: str) -> None:
    items = list_children(access_token, drive_id, folder_path)
    for it in items:
        name = it.get("name") or ""
        is_folder = it.get("folder") is not None
        # Build child path within the drive
        child_path = folder_path.rstrip("/") + "/" + name if folder_path not in ("", "/") else name
        if is_folder:
            download_folder_recursive(access_token, drive_id, child_path, os.path.join(dest_dir, name))
        else:
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, name)
            download_file(access_token, drive_id, child_path, dest_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read files from SharePoint via Microsoft Graph")
    parser.add_argument("--env", default=None, help="Path to .env file (e.g., hubspot/.env.local)")
    parser.add_argument("--site-id", dest="site_id", default=None, help="SharePoint site ID (if known)")
    parser.add_argument("--site-host", dest="site_host", default=None, help="SharePoint hostname, e.g. contoso.sharepoint.com")
    parser.add_argument("--site-path", dest="site_path", default=None, help="Site path, e.g. /sites/Sales")
    parser.add_argument("--drive", dest="drive_name", default=None, help="Document library name (default: Documents)")

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", dest="list_path", default=None, help="List items at this folder path (use '/' for root)")
    action.add_argument("--download", dest="download_file_path", default=None, help="Download a single file at this path")
    action.add_argument("--download-folder", dest="download_folder_path", default=None, help="Download a whole folder recursively")

    parser.add_argument("--out", dest="out_path", default=None, help="Destination filepath when using --download")
    parser.add_argument("--out-dir", dest="out_dir", default="downloads", help="Destination directory when downloading a folder (default: downloads)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_env_vars(args.env)

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    if not tenant_id or not client_id or not client_secret:
        print("Missing one of AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET", file=sys.stderr)
        sys.exit(2)

    access_token = acquire_graph_app_token(tenant_id, client_id, client_secret)

    site_id = resolve_site_id(access_token, args.site_host, args.site_path, args.site_id)
    drive_id = resolve_drive_id(access_token, site_id, args.drive_name)

    if args.list_path is not None:
        path = args.list_path or "/"
        items = list_children(access_token, drive_id, path)
        if not items:
            print("(no items)")
            return
        for it in items:
            name = it.get("name")
            size = it.get("size")
            is_folder = it.get("folder") is not None
            marker = "[DIR]" if is_folder else "     "
            print(f"{marker} {name} | size={size}")
        return

    if args.download_file_path is not None:
        if not args.out_path:
            print("--out is required when using --download", file=sys.stderr)
            sys.exit(2)
        download_file(access_token, drive_id, args.download_file_path, args.out_path)
        print(f"Downloaded {args.download_file_path} -> {args.out_path}")
        return

    if args.download_folder_path is not None:
        out_dir = args.out_dir or "downloads"
        download_folder_recursive(access_token, drive_id, args.download_folder_path, out_dir)
        print(f"Downloaded folder {args.download_folder_path} -> {out_dir}")
        return


if __name__ == "__main__":
    main()


