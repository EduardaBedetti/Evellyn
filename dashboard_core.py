from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from google_sheets import LoadedSheetSource

FIELD_DETECTION: dict[str, dict[str, Any]] = {
    "ticket": {
        "exact": ["ticket", "chamado", "ticket id", "issue key", "issuekey", "id", "protocolo", "numero ticket"],
        "partial": ["ticket", "chamado", "issue key", "issue", "protocolo"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "status", "situacao", "sla", "prazo", "data", "date", "abertura", "limite", "venc", "resolu", "resolved", "produto", "squad", "sistema", "frente", "equipe", "area"],
        "sample_type": "ticket",
    },
    "link_ticket": {
        "exact": ["ticket url", "url", "link", "issue url", "jira url"],
        "partial": ["url", "link", "jira"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "status", "sla", "prazo", "data", "date", "area"],
        "sample_type": "url",
    },
    "cliente": {
        "exact": ["cliente", "client", "customer", "nome cliente", "empresa", "empresa cliente", "conta", "account", "organization", "organizacao", "nome da empresa", "cliente final"],
        "partial": ["cliente", "client", "customer", "empresa cliente", "empresa", "conta", "account", "organization", "organizacao", "cliente final"],
        "forbidden": ["data", "date", "abertura", "limite", "due", "venc", "resolu", "resolved", "status", "situacao", "sla", "prazo", "area", "produto", "squad", "tipo", "sistema", "frente", "equipe", "url", "link", "ticket", "chamado", "issue", "key", "id", "responsavel", "owner", "assignee", "solicitante", "reporter", "autor", "analista", "atendente"],
        "sample_type": "client",
    },
    "area": {
        "exact": ["area", "produto", "squad", "tipo", "sistema", "frente", "equipe", "team", "grupo", "fila"],
        "partial": ["area", "produto", "squad", "tipo", "sistema", "frente", "equipe", "team", "grupo", "fila"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "data", "date", "abertura", "limite", "due", "venc", "resolu", "resolved", "status", "situacao", "sla", "prazo", "url", "link", "ticket", "chamado", "issue", "key", "id"],
        "sample_type": "area",
    },
    "status": {
        "exact": ["status", "situacao", "state"],
        "partial": ["status", "situacao", "state"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "data", "date", "abertura", "limite", "due", "venc", "resolu", "resolved", "sla", "prazo", "url", "link", "ticket", "chamado", "issue", "key", "id", "area", "produto", "squad", "tipo", "sistema", "frente", "equipe"],
        "sample_type": "status",
    },
    "data_abertura": {
        "exact": ["data abertura", "data de abertura", "abertura", "created", "created at", "open date", "criado", "criado em"],
        "partial": ["data abertura", "data de abertura", "abertura", "created", "open date", "criado"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "status", "sla", "prazo", "limite", "due", "venc", "resolu", "resolved", "url", "link", "ticket", "chamado", "issue", "key", "id", "area", "produto", "squad", "tipo", "sistema", "frente", "equipe"],
        "sample_type": "date",
    },
    "data_limite": {
        "exact": ["data limite", "due date", "duedate", "prazo", "prazo final", "data vencimento", "data de vencimento", "deadline"],
        "partial": ["data limite", "due date", "duedate", "prazo", "venc", "deadline", "limite"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "status", "resolu", "resolved", "abertura", "created", "open", "url", "link", "ticket", "chamado", "issue", "key", "id", "area", "produto", "squad", "tipo", "sistema", "frente", "equipe"],
        "sample_type": "date",
    },
    "data_resolucao": {
        "exact": ["data resolucao", "resolved", "resolved at", "resolution date", "data fechamento", "closed at", "resolvido em"],
        "partial": ["resolu", "resolved", "resolution", "fech", "closed"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "status", "sla", "prazo", "abertura", "created", "open", "limite", "due", "venc", "url", "link", "ticket", "chamado", "issue", "key", "id", "area", "produto", "squad", "tipo", "sistema", "frente", "equipe"],
        "sample_type": "date",
    },
    "sla": {
        "exact": ["sla", "prazo em dias", "dias sla", "tempo sla"],
        "partial": ["sla", "prazo"],
        "forbidden": ["cliente", "client", "customer", "empresa", "conta", "account", "status", "situacao", "abertura", "created", "open", "url", "link", "ticket", "chamado", "issue", "key", "id", "area", "produto", "squad", "sistema", "frente", "equipe"],
        "sample_type": "sla",
    },
}

OPERATIONAL_WINDOWS = [
    {"keys": ["pluggy"], "label": "Pluggy", "threshold": 10},
    {"keys": ["s1nc", "sync"], "label": "S1NC", "threshold": 4},
    {"keys": ["winner", "w1nner"], "label": "Winner", "threshold": 1},
]


@dataclass(frozen=True)
class PreparedDashboard:
    records: pd.DataFrame
    warnings: list[str]
    info_messages: list[str]
    source_summaries: pd.DataFrame
    diagnostics: pd.DataFrame


def safe_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def safe_display(value: Any, fallback: str) -> str:
    text = safe_string(value)
    return text or fallback


def normalize_comparable(value: Any) -> str:
    text = safe_string(value)
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return normalized.lower()


def normalize_key(value: Any) -> str:
    text = normalize_comparable(value)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(value: Any) -> str:
    text = safe_string(value)
    if re.match(r"^https?://", text, flags=re.IGNORECASE):
        return text
    return ""


def sanitize_area_value(value: Any) -> str:
    text = safe_string(value)
    if not text:
        return ""
    text = re.sub(r"\.[^.]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def derive_area_from_source_name(source_name: str) -> str:
    if not safe_string(source_name):
        return ""
    if " - " in source_name:
        return sanitize_area_value(source_name.split(" - ")[-1])
    return sanitize_area_value(source_name)


def extract_ticket_id_from_link(url: str) -> str:
    if not url:
        return ""
    jira_key_match = re.search(r"([A-Z][A-Z0-9]+-\d+)", url)
    if jira_key_match:
        return jira_key_match.group(1)
    parts = [part for part in url.split("/") if part]
    return parts[-1] if parts else ""


def parse_date_value(value: Any) -> pd.Timestamp | pd.NaT:
    text = safe_string(value)
    if not text:
        return pd.NaT
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(parsed).normalize()


def is_likely_date_value(value: Any) -> bool:
    return not pd.isna(parse_date_value(value))


def is_likely_url_value(value: Any) -> bool:
    return bool(normalize_url(value))


def is_likely_numeric_value(value: Any) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:[.,]\d+)?", safe_string(value)))


def analyze_column_values(dataframe: pd.DataFrame, column_name: str) -> dict[str, float]:
    values = [safe_string(value) for value in dataframe[column_name].tolist()]
    values = [value for value in values if value][:25]
    if not values:
        return {"count": 0, "date_ratio": 0, "url_ratio": 0, "numeric_ratio": 0}

    date_count = sum(is_likely_date_value(value) for value in values)
    url_count = sum(is_likely_url_value(value) for value in values)
    numeric_count = sum(is_likely_numeric_value(value) for value in values)
    count = len(values)

    return {
        "count": count,
        "date_ratio": date_count / count,
        "url_ratio": url_count / count,
        "numeric_ratio": numeric_count / count,
    }


def column_passes_sample_type(sample: dict[str, float], sample_type: str) -> bool:
    if not sample["count"]:
        return True
    if sample_type == "date":
        return sample["date_ratio"] >= 0.5
    if sample_type == "url":
        return sample["url_ratio"] >= 0.5
    if sample_type in {"client", "area", "status", "ticket"}:
        return sample["date_ratio"] < 0.25 and sample["url_ratio"] < 0.2
    if sample_type == "sla":
        return sample["url_ratio"] < 0.15 and sample["date_ratio"] < 0.6
    return True


def get_sample_score(sample: dict[str, float], sample_type: str) -> int:
    if not sample["count"]:
        return 0
    if sample_type == "date":
        return round(sample["date_ratio"] * 100)
    if sample_type == "url":
        return round(sample["url_ratio"] * 100)
    if sample_type in {"client", "area", "status", "ticket"}:
        return round((1 - sample["date_ratio"] - sample["url_ratio"]) * 50)
    if sample_type == "sla":
        return round((sample["numeric_ratio"] + (1 - sample["url_ratio"])) * 20)
    return 0


def get_header_match_score(header: str, rules: dict[str, Any]) -> int:
    exact_match = next((alias for alias in rules.get("exact", []) if header == normalize_key(alias)), None)
    if exact_match:
        return 400 + len(normalize_key(exact_match))

    partial_match = next((alias for alias in rules.get("partial", []) if normalize_key(alias) in header), None)
    if partial_match:
        return 200 + len(normalize_key(partial_match))

    return 0


def contains_forbidden_term(header: str, forbidden_terms: list[str]) -> bool:
    return any(normalize_key(term) in header for term in forbidden_terms)


def find_column_by_rules(
    headers: list[str],
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
    used_indexes: set[int],
) -> int | None:
    normalized_headers = [normalize_key(header) for header in headers]
    candidates: list[tuple[int, int]] = []

    for index, header in enumerate(normalized_headers):
        if index in used_indexes:
            continue

        match_score = get_header_match_score(header, rules)
        if match_score <= 0:
            continue
        if contains_forbidden_term(header, rules.get("forbidden", [])):
            continue

        sample = analyze_column_values(dataframe, headers[index])
        if not column_passes_sample_type(sample, rules.get("sample_type", "")):
            continue

        candidates.append((index, match_score + get_sample_score(sample, rules.get("sample_type", ""))))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[1], item[0]))
    return candidates[0][0]


def map_headers(dataframe: pd.DataFrame) -> dict[str, int | None]:
    headers = [safe_string(column) for column in dataframe.columns.tolist()]
    used_indexes: set[int] = set()
    mapping: dict[str, int | None] = {}

    for field in ["ticket", "link_ticket", "cliente", "area", "status", "data_abertura", "data_limite", "data_resolucao"]:
        rules = FIELD_DETECTION[field]
        index = find_column_by_rules(headers, dataframe, rules, used_indexes)
        mapping[field] = index
        if index is not None:
            used_indexes.add(index)

    mapping["sla"] = find_column_by_rules(headers, dataframe, FIELD_DETECTION["sla"], used_indexes)
    return mapping


def build_field_diagnostic(source_name: str, label: str, headers: list[str], index: int | None) -> str:
    if index is not None:
        return f"Fonte {source_name}: {label} <- coluna '{safe_display(headers[index], 'Sem nome')}'."
    return f"Fonte {source_name}: {label} <- nao identificada."


def detect_source_area(source_name: str, headers: list[str], header_map: dict[str, int | None]) -> dict[str, Any]:
    area_index = header_map.get("area")
    if area_index is not None:
        return {
            "detected_area": "Definida por linha",
            "final_area": "Definida por linha",
            "source": "column",
            "requires_manual": False,
        }

    source_area = derive_area_from_source_name(source_name)
    if source_area:
        return {
            "detected_area": source_area,
            "final_area": source_area,
            "source": "source",
            "requires_manual": False,
        }

    return {
        "detected_area": "",
        "final_area": "",
        "source": "manual",
        "requires_manual": True,
    }


def get_field_value(row: pd.Series, headers: list[str], index: int | None) -> str:
    if index is None:
        return ""
    return safe_string(row[headers[index]])


def resolve_ticket_value(row: pd.Series, headers: list[str], header_map: dict[str, int | None], link_ticket: str) -> str:
    mapped_ticket = get_field_value(row, headers, header_map.get("ticket"))
    if mapped_ticket:
        normalized_url = normalize_url(mapped_ticket)
        if normalized_url:
            return extract_ticket_id_from_link(normalized_url) or normalized_url
        return mapped_ticket
    if link_ticket:
        return extract_ticket_id_from_link(link_ticket) or link_ticket
    return "Sem identificador"


def normalize_source_dataframe(source: LoadedSheetSource) -> tuple[pd.DataFrame, list[str], list[str], dict[str, Any]]:
    dataframe = source.dataframe.copy()
    dataframe.columns = [safe_string(column) for column in dataframe.columns.tolist()]
    headers = dataframe.columns.tolist()
    header_map = map_headers(dataframe)
    file_area = detect_source_area(source.name, headers, header_map)

    diagnostics = [
        build_field_diagnostic(source.name, "Ticket", headers, header_map.get("ticket")),
        build_field_diagnostic(source.name, "Link do ticket", headers, header_map.get("link_ticket")),
        build_field_diagnostic(source.name, "Cliente", headers, header_map.get("cliente")),
        build_field_diagnostic(source.name, "Area", headers, header_map.get("area")),
        build_field_diagnostic(source.name, "Data de abertura", headers, header_map.get("data_abertura")),
        build_field_diagnostic(source.name, "Data limite", headers, header_map.get("data_limite")),
        build_field_diagnostic(source.name, "SLA", headers, header_map.get("sla")),
        build_field_diagnostic(source.name, "Status", headers, header_map.get("status")),
        build_field_diagnostic(source.name, "Data de resolucao", headers, header_map.get("data_resolucao")),
    ]

    warnings: list[str] = []
    if header_map.get("ticket") is None and header_map.get("cliente") is None and header_map.get("data_abertura") is None:
        warnings.append(
            f"Fonte {source.name}: cabecalhos pouco reconheciveis. O sistema tentou inferir as colunas automaticamente."
        )

    if file_area["source"] == "source":
        warnings.append(
            f"Fonte {source.name}: nao possui coluna Area/equivalente; a area foi preenchida com o nome da fonte."
        )

    if file_area["requires_manual"]:
        warnings.append(
            f"Fonte {source.name}: defina um nome de fonte com a area desejada (ex.: Pluggy) ou adicione uma coluna Area."
        )

    normalized_rows: list[dict[str, Any]] = []
    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=2):
        link_ticket = normalize_url(get_field_value(row, headers, header_map.get("link_ticket")))
        ticket = resolve_ticket_value(row, headers, header_map, link_ticket)
        record = {
            "source_name": source.name,
            "spreadsheet_id": source.spreadsheet_id,
            "range_name": source.range_name,
            "source_row": row_number,
            "ticket": ticket,
            "cliente": get_field_value(row, headers, header_map.get("cliente")) or "Nao informado",
            "area": sanitize_area_value(get_field_value(row, headers, header_map.get("area")))
            or sanitize_area_value(file_area["final_area"])
            or "Nao informada",
            "data_abertura": get_field_value(row, headers, header_map.get("data_abertura")),
            "data_limite": get_field_value(row, headers, header_map.get("data_limite")),
            "sla": get_field_value(row, headers, header_map.get("sla")),
            "status": get_field_value(row, headers, header_map.get("status")) or "Nao informado",
            "data_resolucao": get_field_value(row, headers, header_map.get("data_resolucao")),
            "link_ticket": link_ticket,
        }
        if any(safe_string(value) for value in record.values()):
            normalized_rows.append(record)

    normalized_df = pd.DataFrame(normalized_rows)
    info_summary = {
        "fonte": source.name,
        "spreadsheet_id": source.spreadsheet_id,
        "range": source.range_name,
        "linhas": int(len(normalized_df.index)),
        "area_detectada": file_area["detected_area"] or "Ajuste manual necessario",
        "area_final": file_area["final_area"] or "Pendente",
        "origem_area": file_area["source"],
    }

    return normalized_df, warnings, diagnostics, info_summary


def business_days_between(start: pd.Timestamp | pd.NaT, end: pd.Timestamp | pd.NaT) -> int | None:
    if pd.isna(start) or pd.isna(end):
        return None

    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if start_ts == end_ts:
        return 0

    signal = 1
    from_ts = start_ts
    to_ts = end_ts
    if from_ts > to_ts:
        signal = -1
        from_ts, to_ts = to_ts, from_ts

    from_day = np.datetime64((from_ts + pd.Timedelta(days=1)).date())
    to_day = np.datetime64((to_ts + pd.Timedelta(days=1)).date())
    count = int(np.busday_count(from_day, to_day))
    return count * signal


def format_date(value: pd.Timestamp | pd.NaT) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%d/%m/%Y")


def get_operational_window_config(area_display: str) -> dict[str, Any] | None:
    normalized_area = normalize_comparable(area_display)
    return next((config for config in OPERATIONAL_WINDOWS if normalized_area in config["keys"]), None)


def build_sla_state(
    today: pd.Timestamp,
    due_date: pd.Timestamp | pd.NaT,
    resolved_date: pd.Timestamp | pd.NaT,
    business_days_to_resolution: int | None,
) -> dict[str, Any]:
    if pd.isna(due_date):
        return {
            "sla_category": "Resolvido sem data limite" if not pd.isna(resolved_date) else "Sem data limite",
            "sla_badge_class": "info",
            "is_overdue": False,
            "is_due_soon": False,
            "is_within_sla": False,
            "business_days_delta": None,
            "days_indicator_value": math.inf,
            "days_indicator_display": "Sem data limite",
            "business_days_to_resolution": business_days_to_resolution,
        }

    if not pd.isna(resolved_date):
        difference = business_days_between(due_date, resolved_date)
        resolved_within_sla = difference is not None and difference <= 0
        if resolved_within_sla:
            return {
                "sla_category": "Resolvido no prazo",
                "sla_badge_class": "success",
                "is_overdue": False,
                "is_due_soon": False,
                "is_within_sla": True,
                "business_days_delta": abs(difference or 0),
                "days_indicator_value": abs(difference or 0),
                "days_indicator_display": "Resolvido no prazo"
                if difference == 0
                else f"{abs(difference)} dia(s) uteis antes/no prazo",
                "business_days_to_resolution": business_days_to_resolution,
            }
        difference = difference or 0
        return {
            "sla_category": "Resolvido atrasado",
            "sla_badge_class": "danger",
            "is_overdue": True,
            "is_due_soon": False,
            "is_within_sla": False,
            "business_days_delta": difference,
            "days_indicator_value": difference,
            "days_indicator_display": f"{difference} dia(s) uteis de atraso",
            "business_days_to_resolution": business_days_to_resolution,
        }

    days_until_due = business_days_between(today, due_date)
    if days_until_due is None:
        days_until_due = math.inf

    if days_until_due < 0:
        return {
            "sla_category": "Atrasado",
            "sla_badge_class": "danger",
            "is_overdue": True,
            "is_due_soon": False,
            "is_within_sla": False,
            "business_days_delta": abs(days_until_due),
            "days_indicator_value": abs(days_until_due),
            "days_indicator_display": f"{abs(days_until_due)} dia(s) uteis de atraso",
            "business_days_to_resolution": None,
        }

    if days_until_due <= 2:
        return {
            "sla_category": "Proximo do vencimento",
            "sla_badge_class": "warning",
            "is_overdue": False,
            "is_due_soon": True,
            "is_within_sla": False,
            "business_days_delta": days_until_due,
            "days_indicator_value": days_until_due,
            "days_indicator_display": f"{days_until_due} dia(s) uteis restantes",
            "business_days_to_resolution": None,
        }

    return {
        "sla_category": "Dentro do prazo",
        "sla_badge_class": "success",
        "is_overdue": False,
        "is_due_soon": False,
        "is_within_sla": True,
        "business_days_delta": days_until_due,
        "days_indicator_value": days_until_due,
        "days_indicator_display": f"{days_until_due} dia(s) uteis restantes",
        "business_days_to_resolution": None,
    }


def build_operational_state(
    area_display: str,
    is_resolved: bool,
    due_date: pd.Timestamp | pd.NaT,
    business_days_until_due: int | None,
) -> dict[str, Any]:
    config = get_operational_window_config(area_display)
    if config is None or is_resolved or pd.isna(due_date) or business_days_until_due is None:
        return {
            "operational_area_label": config["label"] if config else "",
            "operational_window_threshold": config["threshold"] if config else None,
            "operational_classification": "Fora da janela",
            "operational_badge_class": "info",
            "operational_priority": 4,
            "within_operational_window": False,
        }

    if business_days_until_due <= 0:
        return {
            "operational_area_label": config["label"],
            "operational_window_threshold": config["threshold"],
            "operational_classification": "Critico hoje",
            "operational_badge_class": "danger",
            "operational_priority": 0,
            "within_operational_window": True,
        }

    if business_days_until_due <= config["threshold"]:
        attention_threshold = max(1, math.ceil(config["threshold"] / 2))
        if business_days_until_due <= attention_threshold:
            classification = "Em atencao"
            badge_class = "warning"
            priority = 1
        else:
            classification = "Dentro da janela"
            badge_class = "success"
            priority = 2
        return {
            "operational_area_label": config["label"],
            "operational_window_threshold": config["threshold"],
            "operational_classification": classification,
            "operational_badge_class": badge_class,
            "operational_priority": priority,
            "within_operational_window": True,
        }

    return {
        "operational_area_label": config["label"],
        "operational_window_threshold": config["threshold"],
        "operational_classification": "Fora da janela",
        "operational_badge_class": "info",
        "operational_priority": 3,
        "within_operational_window": False,
    }


def process_records(records: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if records.empty:
        return pd.DataFrame(), []

    today = pd.Timestamp.now().normalize()
    warnings: list[str] = []
    processed_rows: list[dict[str, Any]] = []

    for index, record in records.iterrows():
        opened_date = parse_date_value(record.get("data_abertura"))
        due_date = parse_date_value(record.get("data_limite"))
        resolved_date = parse_date_value(record.get("data_resolucao"))

        business_days_to_resolution = (
            business_days_between(opened_date, resolved_date)
            if not pd.isna(opened_date) and not pd.isna(resolved_date)
            else None
        )
        business_days_until_due = (
            business_days_between(today, due_date)
            if pd.isna(resolved_date) and not pd.isna(due_date)
            else None
        )

        if safe_string(record.get("data_abertura")) and pd.isna(opened_date):
            warnings.append(
                f"Linha {record['source_row']} da fonte {record['source_name']}: data de abertura invalida ({record.get('data_abertura')})."
            )
        if safe_string(record.get("data_limite")) and pd.isna(due_date):
            warnings.append(
                f"Linha {record['source_row']} da fonte {record['source_name']}: data limite invalida ({record.get('data_limite')})."
            )
        if safe_string(record.get("data_resolucao")) and pd.isna(resolved_date):
            warnings.append(
                f"Linha {record['source_row']} da fonte {record['source_name']}: data de resolucao invalida ({record.get('data_resolucao')})."
            )

        status_display = safe_display(record.get("status"), "Nao informado")
        client_display = safe_display(record.get("cliente"), "Nao informado")
        area_display = safe_display(record.get("area"), "Nao informada")
        ticket = safe_display(record.get("ticket"), "Sem identificador")
        ticket_url = normalize_url(record.get("link_ticket"))

        sla_state = build_sla_state(today, due_date, resolved_date, business_days_to_resolution)
        operational_state = build_operational_state(
            area_display=area_display,
            is_resolved=not pd.isna(resolved_date),
            due_date=due_date,
            business_days_until_due=business_days_until_due,
        )

        processed_rows.append(
            {
                "id": f"{record['source_name']}::{record['source_row']}::{index}",
                "source_name": record["source_name"],
                "spreadsheet_id": record["spreadsheet_id"],
                "range_name": record["range_name"],
                "source_row": record["source_row"],
                "ticket": ticket,
                "ticket_url": ticket_url,
                "cliente": client_display,
                "client_display": client_display,
                "client_key": normalize_comparable(client_display),
                "area": area_display,
                "area_display": area_display,
                "area_key": normalize_comparable(area_display),
                "status": status_display,
                "status_display": status_display,
                "status_key": normalize_comparable(status_display),
                "data_abertura": safe_display(record.get("data_abertura"), ""),
                "data_limite": safe_display(record.get("data_limite"), ""),
                "data_resolucao": safe_display(record.get("data_resolucao"), ""),
                "sla_original_display": safe_display(record.get("sla"), "Nao informado"),
                "opened_date": opened_date,
                "opened_date_display": format_date(opened_date) or safe_display(record.get("data_abertura"), "Nao informada"),
                "due_date": due_date,
                "due_date_display": format_date(due_date) or safe_display(record.get("data_limite"), "Nao informada"),
                "resolved_date": resolved_date,
                "resolved_date_display": format_date(resolved_date) or safe_display(record.get("data_resolucao"), "Em aberto"),
                "is_resolved": not pd.isna(resolved_date),
                "search_blob": normalize_comparable(" ".join([ticket, client_display, area_display, status_display, safe_display(record.get("sla"), "")])),
                **sla_state,
                **operational_state,
            }
        )

    return pd.DataFrame(processed_rows), sorted(set(warnings))


def prepare_dashboard(loaded_sources: list[LoadedSheetSource]) -> PreparedDashboard:
    normalized_frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    info_messages: list[str] = []
    source_summaries: list[dict[str, Any]] = []
    diagnostics_rows: list[dict[str, str]] = []

    for source in loaded_sources:
        normalized_df, source_warnings, diagnostics, summary = normalize_source_dataframe(source)
        normalized_frames.append(normalized_df)
        warnings.extend(source_warnings)
        source_summaries.append(summary)
        info_messages.append(
            f"Fonte {source.name}: {len(normalized_df.index)} ticket(s) lido(s) em {source.range_name}."
        )
        for message in diagnostics:
            diagnostics_rows.append({"fonte": source.name, "mensagem": message})

    raw_records = (
        pd.concat([frame for frame in normalized_frames if not frame.empty], ignore_index=True)
        if any(not frame.empty for frame in normalized_frames)
        else pd.DataFrame()
    )
    processed_records, processing_warnings = process_records(raw_records)
    warnings.extend(processing_warnings)

    source_summary_df = pd.DataFrame(source_summaries)
    diagnostics_df = pd.DataFrame(diagnostics_rows)

    return PreparedDashboard(
        records=processed_records,
        warnings=sorted(set(warnings)),
        info_messages=info_messages,
        source_summaries=source_summary_df,
        diagnostics=diagnostics_df,
    )


def apply_filters(
    records: pd.DataFrame,
    areas: list[str] | None = None,
    clients: list[str] | None = None,
    statuses: list[str] | None = None,
    search: str = "",
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    if records.empty:
        return records.copy()

    filtered = records.copy()
    if areas:
        filtered = filtered[filtered["area_display"].isin(areas)]
    if clients:
        filtered = filtered[filtered["client_display"].isin(clients)]
    if statuses:
        filtered = filtered[filtered["status_display"].isin(statuses)]
    if search:
        normalized_search = normalize_comparable(search)
        filtered = filtered[filtered["search_blob"].str.contains(normalized_search, regex=False)]

    if start_date:
        filtered = filtered[filtered["opened_date"].notna() & (filtered["opened_date"] >= pd.Timestamp(start_date))]
    if end_date:
        filtered = filtered[filtered["opened_date"].notna() & (filtered["opened_date"] <= pd.Timestamp(end_date))]

    return filtered


def unique_sorted_values(records: pd.DataFrame, column_name: str) -> list[str]:
    if records.empty or column_name not in records.columns:
        return []
    values = [safe_string(value) for value in records[column_name].dropna().tolist()]
    values = sorted({value for value in values if value}, key=lambda item: normalize_comparable(item))
    return values


def aggregate_count(records: pd.DataFrame, column_name: str) -> pd.DataFrame:
    if records.empty or column_name not in records.columns:
        return pd.DataFrame(columns=["label", "value"])
    grouped = (
        records.groupby(column_name, dropna=False)
        .size()
        .reset_index(name="value")
        .rename(columns={column_name: "label"})
        .sort_values(["value", "label"], ascending=[False, True])
    )
    grouped["label"] = grouped["label"].map(lambda item: safe_display(item, "Nao informado"))
    return grouped


def average_business_days(records: pd.DataFrame) -> float | None:
    if records.empty or "business_days_to_resolution" not in records.columns:
        return None
    series = pd.to_numeric(records["business_days_to_resolution"], errors="coerce").dropna()
    # Datas digitadas erradas geram tempos negativos ou de centenas de anos;
    # fora do intervalo plausivel, o ticket fica fora da media.
    series = series[(series >= 0) & (series <= 1300)]
    if series.empty:
        return None
    return round(float(series.mean()), 1)


COMPANY_AVERAGE_COLUMNS = [
    "Empresa",
    "Total de tickets",
    "Resolvidos",
    "Em aberto",
    "Atrasados",
    "SLA no prazo (%)",
    "Tempo medio de resolucao (dias uteis)",
    "Atraso medio (dias uteis)",
]


def build_company_averages(records: pd.DataFrame, group_column: str = "area_display") -> pd.DataFrame:
    if records.empty or group_column not in records.columns:
        return pd.DataFrame(columns=COMPANY_AVERAGE_COLUMNS)

    rows: list[dict[str, Any]] = []
    for group_value, group in records.groupby(group_column, dropna=False):
        label = safe_display(group_value, "Nao informado")
        total = int(len(group.index))
        resolved = int(group["is_resolved"].sum())
        overdue = int(group["is_overdue"].sum())
        resolved_on_time = int((group["sla_category"] == "Resolvido no prazo").sum())
        sla_percent = round(resolved_on_time / resolved * 100, 1) if resolved else 0.0

        average_resolution = average_business_days(group)

        overdue_deltas = pd.to_numeric(
            group.loc[group["is_overdue"], "business_days_delta"], errors="coerce"
        ).dropna()
        average_delay = round(float(overdue_deltas.mean()), 1) if not overdue_deltas.empty else 0.0

        rows.append(
            {
                "Empresa": label,
                "Total de tickets": total,
                "Resolvidos": resolved,
                "Em aberto": total - resolved,
                "Atrasados": overdue,
                "SLA no prazo (%)": sla_percent,
                "Tempo medio de resolucao (dias uteis)": average_resolution,
                "Atraso medio (dias uteis)": average_delay,
            }
        )

    result = pd.DataFrame(rows, columns=COMPANY_AVERAGE_COLUMNS)
    return result.sort_values(
        ["Total de tickets", "Empresa"], ascending=[False, True]
    ).reset_index(drop=True)


def build_summary_text(records: pd.DataFrame, total_records: int) -> str:
    if records.empty:
        if total_records:
            return "Nenhum ticket atende aos filtros atuais. Ajuste o recorte para visualizar resultados."
        return "Conecte uma ou mais fontes do Google Sheets para gerar o resumo automatico."

    overdue = int(records["is_overdue"].sum())
    due_soon = int(records["is_due_soon"].sum())
    resolved = int(records["is_resolved"].sum())
    areas = aggregate_count(records, "area_display")
    clients = aggregate_count(records, "client_display")
    average_resolution = average_business_days(records)

    parts = [
        f"{overdue} ticket(s) atrasado(s)",
        f"{due_soon} proximo(s) do vencimento",
        f"{resolved} resolvido(s)",
    ]
    if not areas.empty:
        parts.append(f"maior concentracao na area {areas.iloc[0]['label']}")
    if not clients.empty:
        parts.append(f"cliente com maior volume: {clients.iloc[0]['label']}")
    if average_resolution is not None:
        parts.append(f"tempo medio ate resolucao: {average_resolution} dia(s) uteis")

    text = ", ".join(parts) + "."
    return text[:1].upper() + text[1:]


def build_operational_window_summary(records: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for config in OPERATIONAL_WINDOWS:
        group_records = records[records["operational_area_label"] == config["label"]]
        within_window = group_records[group_records["within_operational_window"]]
        critical_today = int((within_window["operational_classification"] == "Critico hoje").sum())
        in_attention = int((within_window["operational_classification"] == "Em atencao").sum())
        if len(within_window.index) > 0 or len(group_records.index) > 0:
            rows.append(
                {
                    "label": config["label"],
                    "count": int(len(within_window.index)),
                    "description": f"{len(within_window.index)} ticket(s) com vencimento em ate {config['threshold']} dia(s) uteis",
                    "meta": f"{critical_today} critico(s) hoje/atrasado(s), {in_attention} em atencao",
                }
            )
    return pd.DataFrame(rows)


def build_operational_alerts(records: pd.DataFrame) -> list[str]:
    summary = build_operational_window_summary(records)
    alerts: list[str] = []
    for _, entry in summary.iterrows():
        count = int(entry["count"])
        if count <= 0:
            continue
        if entry["label"] == "Winner":
            text = f"{count} ticket(s) da Winner estao a ate 1 dia util do vencimento."
        elif entry["label"] == "S1NC":
            text = f"{count} ticket(s) da S1NC estao proximos do vencimento."
        else:
            text = f"{count} ticket(s) da Pluggy estao dentro da janela critica."
        alerts.append(f"{entry['label']}: {text}")
    return alerts


def build_status_distribution(records: pd.DataFrame) -> pd.DataFrame:
    order = [
        "Resolvido no prazo",
        "Resolvido atrasado",
        "Dentro do prazo",
        "Proximo do vencimento",
        "Atrasado",
        "Sem data limite",
        "Resolvido sem data limite",
    ]
    if records.empty:
        return pd.DataFrame(columns=["categoria", "total"])

    grouped = (
        records.groupby("sla_category")
        .size()
        .reset_index(name="total")
        .rename(columns={"sla_category": "categoria"})
    )
    grouped["ordem"] = grouped["categoria"].map(lambda item: order.index(item) if item in order else len(order))
    grouped = grouped.sort_values(["ordem", "categoria"]).drop(columns=["ordem"])
    return grouped


def build_export_dataframe(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame(
            columns=[
                "Ticket",
                "Cliente",
                "Area",
                "Data abertura",
                "Data limite",
                "SLA",
                "Status",
                "Classificacao operacional",
                "Data resolucao",
                "Dias restantes/atraso",
                "Fonte",
                "Range",
            ]
        )

    return records[
        [
            "ticket",
            "client_display",
            "area_display",
            "opened_date_display",
            "due_date_display",
            "sla_category",
            "status_display",
            "operational_classification",
            "resolved_date_display",
            "days_indicator_display",
            "source_name",
            "range_name",
        ]
    ].rename(
        columns={
            "ticket": "Ticket",
            "client_display": "Cliente",
            "area_display": "Area",
            "opened_date_display": "Data abertura",
            "due_date_display": "Data limite",
            "sla_category": "SLA",
            "status_display": "Status",
            "operational_classification": "Classificacao operacional",
            "resolved_date_display": "Data resolucao",
            "days_indicator_display": "Dias restantes/atraso",
            "source_name": "Fonte",
            "range_name": "Range",
        }
    )
