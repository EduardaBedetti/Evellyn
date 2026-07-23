from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
AUTO_ALL_SHEETS = "__AUTO_ALL_SHEETS__"


@dataclass(frozen=True)
class SheetSource:
    name: str
    spreadsheet_ref: str
    range_name: str


@dataclass(frozen=True)
class LoadedSheetSource:
    name: str
    spreadsheet_id: str
    range_name: str
    dataframe: pd.DataFrame


def extract_spreadsheet_id(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("Informe a URL ou o ID da planilha do Google Sheets.")

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", text)
    if match:
        return match.group(1)

    if re.fullmatch(r"[a-zA-Z0-9-_]+", text):
        return text

    raise ValueError("Nao foi possivel identificar o spreadsheetId a partir do valor informado.")


def load_credentials(credentials_path: str | Path, token_path: str | Path) -> Credentials:
    credentials_path = Path(credentials_path)
    token_path = Path(token_path)

    if "gcp_service_account" in st.secrets:
        return service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=SCOPES,
        )

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Arquivo de credenciais nao encontrado: {credentials_path}. "
            "Para deploy no Streamlit Cloud, configure uma service account em st.secrets."
        )

    with credentials_path.open("r", encoding="utf-8") as handle:
        info = json.load(handle)

    if info.get("type") == "service_account":
        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=SCOPES,
        )

    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def build_values_dataframe(values: list[list[str]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()

    header = [str(cell).strip() or f"coluna_{index + 1}" for index, cell in enumerate(values[0])]
    width = len(header)
    rows: list[list[str]] = []

    for row in values[1:]:
        safe_row = list(row[:width])
        if len(safe_row) < width:
            safe_row.extend([""] * (width - len(safe_row)))
        rows.append(safe_row)

    if not rows:
        return pd.DataFrame(columns=header)

    return pd.DataFrame(rows, columns=header)


def read_google_sheet(
    source: SheetSource,
    credentials_path: str | Path,
    token_path: str | Path,
) -> LoadedSheetSource:
    spreadsheet_id = extract_spreadsheet_id(source.spreadsheet_ref)
    credentials = load_credentials(credentials_path, token_path)
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=source.range_name)
        .execute()
    )
    values = result.get("values", [])
    dataframe = build_values_dataframe(values)

    return LoadedSheetSource(
        name=source.name,
        spreadsheet_id=spreadsheet_id,
        range_name=source.range_name,
        dataframe=dataframe,
    )


def list_spreadsheet_sheet_titles(
    spreadsheet_ref: str,
    credentials_path: str | Path,
    token_path: str | Path,
) -> tuple[str, list[str]]:
    spreadsheet_id = extract_spreadsheet_id(spreadsheet_ref)
    credentials = load_credentials(credentials_path, token_path)
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    spreadsheet = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title,hidden))")
        .execute()
    )

    sheet_titles: list[str] = []
    for sheet in spreadsheet.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("hidden"):
            continue
        title = str(properties.get("title", "")).strip()
        if title:
            sheet_titles.append(title)

    return spreadsheet_id, sheet_titles


def expand_auto_sources(
    source: SheetSource,
    credentials_path: str | Path,
    token_path: str | Path,
) -> list[SheetSource]:
    if source.range_name != AUTO_ALL_SHEETS:
        return [source]

    _, sheet_titles = list_spreadsheet_sheet_titles(
        source.spreadsheet_ref,
        credentials_path=credentials_path,
        token_path=token_path,
    )

    expanded_sources = [
        SheetSource(
            name=sheet_title,
            spreadsheet_ref=source.spreadsheet_ref,
            range_name=f"'{sheet_title}'!A:ZZ",
        )
        for sheet_title in sheet_titles
    ]

    return expanded_sources or [source]


def read_sources(
    sources: Iterable[SheetSource],
    credentials_path: str | Path,
    token_path: str | Path,
) -> list[LoadedSheetSource]:
    expanded_sources: list[SheetSource] = []
    for source in sources:
        expanded_sources.extend(
            expand_auto_sources(
                source,
                credentials_path=credentials_path,
                token_path=token_path,
            )
        )

    return [read_google_sheet(source, credentials_path, token_path) for source in expanded_sources]
