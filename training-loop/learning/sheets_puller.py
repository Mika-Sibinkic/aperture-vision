"""Pull the Google Sheet of donations into in-memory records for the
learning cycle.

Reads from the "Donations" tab. Uses a service account JSON for auth so
there's no OAuth popup on the Dell G7.

Setup (one-time):
  1. In Google Cloud Console, create a service account for Aperture
  2. Download the JSON key, save as /etc/aperture-sheets-sa.json
  3. Share the Donations sheet with the service account email
     (ends with iam.gserviceaccount.com) as Editor

The puller yields dicts matching the Sheet columns + a synthesized
donation_id (sheet row id is sufficient when no UUID was captured).
"""
from __future__ import annotations

import logging
import os
import pathlib
from typing import Iterator

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
except ImportError:
    Credentials = None  # allows running learners in isolation without google deps

log = logging.getLogger(__name__)

SHEET_SCOPE = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def pull_rows(
    sheet_id: str,
    tab_name: str = "Donations",
    sa_json_path: pathlib.Path = pathlib.Path("/etc/aperture-sheets-sa.json"),
) -> Iterator[dict]:
    if Credentials is None:
        raise RuntimeError("google-api-python-client not installed — pip install google-api-python-client google-auth")
    if not sa_json_path.exists():
        raise FileNotFoundError(f"service account JSON missing at {sa_json_path}")

    creds = Credentials.from_service_account_file(str(sa_json_path), scopes=SHEET_SCOPE)
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{tab_name}!A:Z",
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return
    headers = rows[0]
    for i, row in enumerate(rows[1:], start=2):  # row 2+ in Sheets terms
        padded = row + [""] * (len(headers) - len(row))
        rec = dict(zip(headers, padded))
        rec["__sheet_row"] = i
        rec.setdefault("donation_id", f"sheetrow-{i}")
        yield rec
