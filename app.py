from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_core import (
    aggregate_count,
    apply_filters,
    build_company_averages,
    build_export_dataframe,
    build_operational_alerts,
    build_operational_window_summary,
    build_status_distribution,
    build_summary_text,
    prepare_dashboard,
    unique_sorted_values,
)
from google_sheets import AUTO_ALL_SHEETS, SheetSource, read_sources

DEFAULT_SOURCES = "https://docs.google.com/spreadsheets/d/1kSGMUmoaERk9GK91te_CPuq5hNb0ZEsRgF1uztRosTI/edit?usp=sharing"


def parse_sources_config(raw_text: str) -> list[SheetSource]:
    sources: list[SheetSource] = []
    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "|" not in line:
            sources.append(
                SheetSource(
                    name=f"Planilha {len(sources) + 1}",
                    spreadsheet_ref=line,
                    range_name=AUTO_ALL_SHEETS,
                )
            )
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            raise ValueError(
                f"Linha {line_number}: use apenas o link/ID da planilha ou o formato nome_da_fonte|url_ou_id_da_planilha|aba!A:Z."
            )

        name, spreadsheet_ref, range_name = parts
        if not name or not spreadsheet_ref or not range_name:
            raise ValueError(
                f"Linha {line_number}: todos os campos precisam estar preenchidos."
            )

        sources.append(
            SheetSource(
                name=name,
                spreadsheet_ref=spreadsheet_ref,
                range_name=range_name,
            )
        )

    if not sources:
        raise ValueError("Informe pelo menos uma fonte do Google Sheets.")

    return sources


def load_dashboard_data(credentials_path: str, token_path: str, sources_text: str):
    sources = parse_sources_config(sources_text)
    loaded_sources = read_sources(sources, credentials_path=credentials_path, token_path=token_path)
    return prepare_dashboard(loaded_sources)


def dataframe_to_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    dataframe.to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue().encode("utf-8-sig")


def main() -> None:
    st.set_page_config(page_title="Dashboard SLA V2", page_icon=":bar_chart:", layout="wide")
    st.title("Dashboard SLA V2")
    st.caption(
        "Versao em Python com pandas + Google Sheets. O fluxo segue o padrao de autenticacao do quickstart oficial "
        "do Google Sheets API e troca os CSVs por ranges lidos direto da planilha."
    )
    using_cloud_secrets = "gcp_service_account" in st.secrets

    with st.sidebar:
        st.header("Conexao Google Sheets")
        if using_cloud_secrets:
            st.success("Service account carregada via st.secrets.")
            credentials_path = "credentials.json"
            token_path = "token.json"
        else:
            credentials_path = st.text_input(
                "Arquivo de credenciais",
                value="credentials.json",
                help="Localmente, use o credentials.json do OAuth desktop ou um service account JSON.",
            )
            token_path = st.text_input(
                "Arquivo de token",
                value="token.json",
                help="No fluxo OAuth local, esse arquivo sera criado na primeira autenticacao.",
            )
        sources_text = st.text_area(
            "Links da planilha",
            value=st.session_state.get("sources_text", DEFAULT_SOURCES),
            height=180,
            help="Cole um link ou ID por linha. Se quiser, o formato nome|planilha|aba!A:Z continua funcionando.",
        )
        st.caption(
            "Fluxo simples: cole o link da planilha e a app tenta ler automaticamente todas as abas visiveis."
        )
        load_button = st.button("Carregar dashboard", type="primary", use_container_width=True)

    if load_button:
        st.session_state["sources_text"] = sources_text
        try:
            dashboard = load_dashboard_data(credentials_path, token_path, sources_text)
            st.session_state["dashboard_data"] = dashboard
            st.session_state["dashboard_error"] = ""
        except Exception as exc:  # noqa: BLE001
            st.session_state["dashboard_error"] = str(exc)
            st.session_state.pop("dashboard_data", None)

    if st.session_state.get("dashboard_error"):
        st.error(st.session_state["dashboard_error"])

    dashboard = st.session_state.get("dashboard_data")
    if not dashboard:
        st.info(
            "Preencha os links do Google Sheets na barra lateral e clique em `Carregar dashboard` para montar a visao."
        )
        st.markdown(
            """
**Formato simples**

`https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0`

**Formato avancado opcional**

`Pluggy|https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0|Tickets!A:Z`
            """
        )
        st.markdown(
            """
**Deploy simples no Streamlit Cloud**

Use `st.secrets` com uma `service_account` e compartilhe a planilha com o e-mail dessa conta.
            """
        )
        return

    records = dashboard.records
    warnings = dashboard.warnings
    info_messages = dashboard.info_messages

    with st.sidebar:
        st.header("Filtros")
        areas = st.multiselect("Area", options=unique_sorted_values(records, "area_display"))
        clients = st.multiselect("Cliente", options=unique_sorted_values(records, "client_display"))
        statuses = st.multiselect("Status", options=unique_sorted_values(records, "status_display"))
        search = st.text_input("Busca", placeholder="ticket, cliente, area, status")
        start_date = st.date_input("Data inicial", value=None, format="DD/MM/YYYY")
        end_date = st.date_input("Data final", value=None, format="DD/MM/YYYY")

    start_value = None if start_date in ("", None) else start_date
    end_value = None if end_date in ("", None) else end_date
    filtered = apply_filters(
        records,
        areas=areas,
        clients=clients,
        statuses=statuses,
        search=search,
        start_date=start_value,
        end_date=end_value,
    )

    for message in info_messages[-6:]:
        st.info(message)
    for message in warnings[-8:]:
        st.warning(message)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    total = int(len(filtered.index))
    resolved = int(filtered["is_resolved"].sum()) if not filtered.empty else 0
    overdue = int(filtered["is_overdue"].sum()) if not filtered.empty else 0
    on_time = (
        int(filtered["sla_category"].isin(["Dentro do prazo", "Resolvido no prazo"]).sum())
        if not filtered.empty
        else 0
    )
    at_risk = int(filtered["is_due_soon"].sum()) if not filtered.empty else 0
    resolved_on_time = (
        int((filtered["sla_category"] == "Resolvido no prazo").sum()) if not filtered.empty else 0
    )
    sla_percent = (resolved_on_time / resolved * 100) if resolved else 0.0

    col1.metric("Total de tickets", total)
    col2.metric("Resolvidos", resolved)
    col3.metric("Atrasados", overdue)
    col4.metric("No prazo", on_time)
    col5.metric("Em risco", at_risk)
    col6.metric("SLA no prazo", f"{sla_percent:.1f}%")

    summary_col, alerts_col = st.columns([1.3, 1])
    with summary_col:
        st.subheader("Resumo do recorte")
        st.write(build_summary_text(filtered, len(records.index)))

        area_breakdown = aggregate_count(filtered, "area_display")
        if not area_breakdown.empty:
            st.dataframe(area_breakdown, use_container_width=True, hide_index=True)

    with alerts_col:
        st.subheader("Alertas operacionais")
        alerts = build_operational_alerts(filtered)
        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("Nenhum alerta operacional no recorte atual.")

        window_summary = build_operational_window_summary(filtered)
        if not window_summary.empty:
            st.dataframe(window_summary, use_container_width=True, hide_index=True)

    st.subheader("Media por empresa")
    st.caption(
        "Indicadores calculados automaticamente por empresa: volume, SLA e tempos medios em dias uteis. "
        "Os valores respeitam os filtros aplicados na barra lateral."
    )
    group_option = st.radio(
        "Agrupar medias por",
        options=["Empresa (area)", "Cliente"],
        horizontal=True,
    )
    group_column = "area_display" if group_option == "Empresa (area)" else "client_display"
    company_averages = build_company_averages(filtered, group_column)

    if company_averages.empty:
        st.info("Sem dados suficientes para calcular as medias por empresa.")
    else:
        st.dataframe(company_averages, use_container_width=True, hide_index=True)
        st.download_button(
            label="Baixar medias por empresa em CSV",
            data=dataframe_to_csv_bytes(company_averages),
            file_name="medias-por-empresa.csv",
            mime="text/csv",
        )

        max_chart_groups = 12
        chart_base = company_averages.head(max_chart_groups)
        if len(company_averages.index) > max_chart_groups:
            st.caption(
                f"Os graficos mostram as {max_chart_groups} empresas com maior volume de tickets. "
                "A tabela e o CSV acima contem todas."
            )

        resolution_data = chart_base.dropna(
            subset=["Tempo medio de resolucao (dias uteis)"]
        )
        avg_res_col, avg_sla_col = st.columns(2)
        with avg_res_col:
            if resolution_data.empty:
                st.info("Nenhuma empresa possui tickets resolvidos com datas validas para calcular o tempo medio.")
            else:
                resolution_figure = px.bar(
                    resolution_data,
                    x="Tempo medio de resolucao (dias uteis)",
                    y="Empresa",
                    orientation="h",
                    color="Empresa",
                    text_auto=".1f",
                    title="Tempo medio de resolucao por empresa",
                )
                resolution_figure.update_layout(
                    showlegend=False,
                    yaxis={"categoryorder": "total ascending"},
                    height=max(340, 40 * len(resolution_data.index) + 140),
                )
                st.plotly_chart(resolution_figure, use_container_width=True)
        with avg_sla_col:
            sla_figure = px.bar(
                chart_base,
                x="SLA no prazo (%)",
                y="Empresa",
                orientation="h",
                color="Empresa",
                text_auto=".1f",
                title="SLA no prazo por empresa (%)",
            )
            sla_figure.update_layout(
                showlegend=False,
                xaxis_range=[0, 100],
                yaxis={"categoryorder": "total ascending"},
                height=max(340, 40 * len(chart_base.index) + 140),
            )
            st.plotly_chart(sla_figure, use_container_width=True)

    chart_col, source_col = st.columns([1.3, 1])
    with chart_col:
        st.subheader("Status dos tickets")
        status_distribution = build_status_distribution(filtered)
        if status_distribution.empty:
            st.info("Sem dados suficientes para o grafico.")
        else:
            figure = px.pie(
                status_distribution,
                names="categoria",
                values="total",
                color="categoria",
                color_discrete_sequence=[
                    "#1d7d4f",
                    "#b23a3a",
                    "#01DDD5",
                    "#b67611",
                    "#d65b5b",
                    "#52676D",
                    "#96A7AC",
                ],
            )
            figure.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(figure, use_container_width=True)

    with source_col:
        st.subheader("Fontes conectadas")
        if dashboard.source_summaries.empty:
            st.info("Nenhuma fonte carregada.")
        else:
            st.dataframe(dashboard.source_summaries, use_container_width=True, hide_index=True)

    st.subheader("Tickets consolidados")
    export_frame = build_export_dataframe(filtered)
    st.download_button(
        label="Baixar recorte em CSV",
        data=dataframe_to_csv_bytes(export_frame),
        file_name="dashboard-sla-v2-filtrado.csv",
        mime="text/csv",
    )
    st.dataframe(export_frame, use_container_width=True, hide_index=True)

    with st.expander("Diagnosticos de mapeamento"):
        if dashboard.diagnostics.empty:
            st.info("Nenhum diagnostico disponivel.")
        else:
            st.dataframe(dashboard.diagnostics, use_container_width=True, hide_index=True)

    with st.expander("Como autenticar no Google Sheets"):
        st.markdown(
            """
1. No deploy, prefira `service_account` via `st.secrets`.
2. Localmente, voce ainda pode usar `credentials.json` no fluxo OAuth.
3. Se usar `service_account`, compartilhe a planilha com o e-mail da conta de servico.
            """
        )


if __name__ == "__main__":
    main()
