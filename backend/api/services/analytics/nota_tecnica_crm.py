import os
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import polars as pl
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from cache_files import CRM_RAIOX_TX_PARQUET
from ._cache import _get_cnpj_cache_dir
from .crm import (
    _build_alertas_crm_multiplos_por_medico,
    _build_crm_unico_alertas_por_medico,
    _filter_competencia,
    _filter_crm_date_range,
    get_crm_data,
)
from .matriz_risco_dinamica import build_dynamic_matriz_risco as _build_dynamic_matriz_risco
from cache_producers.crm import (
    load_or_sync_crm_multi_alertas,
    load_or_sync_crm_timeline_hora,
    load_or_sync_crm_unico_alertas,
    sync_crm_raiox_tx,
)
from .nota_tecnica_docx_utils import (
    _add_bookmark,
    _cell_bg,
    _footnote_ref,
    _format_block_footnote,
    _format_block_title,
    _run,
    _set_table_fixed_widths,
    _set_table_open_borders,
    _write_cell,
)
from .nota_tecnica_formatters import _format_decimal_pt, _title_case_pt


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
        return None if result != result else result
    except (TypeError, ValueError):
        return None


def _required_positive_float(value: Any, field_name: str, context: str) -> float:
    number = _as_optional_float(value)
    if number is None or number <= 0:
        raise ValueError(f"Campo obrigatorio {field_name} ausente ou invalido em {context}.")
    return number


def _required_nonnegative_float(value: Any, field_name: str, context: str) -> float:
    number = _as_optional_float(value)
    if number is None or number < 0:
        raise ValueError(f"Campo obrigatorio {field_name} ausente ou invalido em {context}.")
    return number


def _required_nonnegative_int(value: Any, field_name: str, context: str) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        raise ValueError(f"Campo obrigatorio {field_name} ausente ou invalido em {context}.")
    if number < 0:
        raise ValueError(f"Campo obrigatorio {field_name} ausente ou invalido em {context}.")
    return number


def _format_optional_decimal_pt(value: Any, decimals: int = 1, empty: str = "n.c.") -> str:
    number = _as_optional_float(value)
    if number is None:
        return empty
    return _format_decimal_pt(number, decimals)


def _volume_horario_multiplicador_value(row: dict[str, Any]) -> float:
    mediana = _required_nonnegative_float(row.get("mediana_hora"), "mediana_hora", "alerta de volume horario CRM")
    nu_prescricoes = _required_nonnegative_int(row.get("nu_prescricoes"), "nu_prescricoes", "alerta de volume horario CRM")
    return nu_prescricoes / max(mediana, 1.0)


def _format_volume_horario_multiplicador(row: dict[str, Any]) -> str:
    multiplicador = _volume_horario_multiplicador_value(row)
    return f"{_format_decimal_pt(multiplicador, 1)}x"


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _date_to_competencia(value: Optional[date]) -> int | None:
    return value.year * 100 + value.month if value else None


def _select_crm_concentracao_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _as_float(row.get("taxa_hora")) > 30]


def _select_crm_unico_concentracao_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if _required_positive_float(row.get("taxa_hora"), "taxa_hora", "alerta de CRM unico") > 30
    ]


def _crm_event_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("dt") or "")[:10], _as_int(row.get("hr")))


def _format_date_br(value: Any) -> str:
    if value is None:
        return "Não localizada"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    if not text:
        return "Não localizada"
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return text


def _as_date_for_weekend_marker(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _write_date_cell_with_weekend_marker(cell, value: Any, formatter: Callable[[Any], str] = _format_date_br):
    p = cell.paragraphs[0]
    p.text = ""
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, formatter(value), color="0F172A", size=9)

    parsed_date = _as_date_for_weekend_marker(value)
    if parsed_date is None or parsed_date.weekday() < 5:
        return

    p.add_run().add_break()
    _run(p, "(fim de semana)", color="64748B", size=9)


def _vez_ou_vezes(value: float) -> str:
    return "vez" if abs(value) <= 1 else "vezes"


def _crm_num_uf(id_medico: Any) -> tuple[str, str]:
    text = str(id_medico or "").strip()
    if "/" not in text:
        return text or "Não informado", ""
    numero, uf = text.split("/", 1)
    return numero.strip() or "Não informado", uf.strip()


def _format_competencia_crm(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 6 and text.isdigit():
        return f"{text[4:6]}/{text[:4]}"
    return text or "—"


def _required_competencia_crm(value: Any, context: str) -> str:
    text = str(value or "").strip()
    if len(text) != 6 or not text.isdigit():
        raise ValueError(
            f"Campo obrigatorio competencia_nu_estabelecimentos ausente ou invalido em {context}."
        )
    return _format_competencia_crm(text)


def _format_time_hour(value: Any) -> str:
    try:
        return f"{int(float(value or 0)):02d}:00"
    except (TypeError, ValueError):
        return "—"


def _format_hour_range(value: Any) -> str:
    try:
        hora = int(float(value or 0))
    except (TypeError, ValueError):
        return "—"
    return f"{hora % 24:02d}:00 até {(hora + 1) % 24:02d}:00"


def _format_datetime_br_minute(value: Any) -> str:
    dt = _parse_datetime_crm(value)
    if dt is None:
        return "N/d"
    return dt.strftime("%d/%m/%y %H:%M")


def _format_janela_minutos(value: Any) -> str:
    minutos = _as_int(value)
    if minutos <= 0:
        return "Mesmo instante"
    if minutos < 60:
        return f"{minutos} min"
    horas = minutos // 60
    resto = minutos % 60
    return f"{horas}h {resto}min" if resto else f"{horas}h"


def _format_crm_table_title(paragraph):
    _format_block_title(paragraph, space_before=16, space_after=8, alignment=WD_ALIGN_PARAGRAPH.CENTER)


def _format_crm_table_footnote(paragraph):
    _format_block_footnote(paragraph, space_before=5, space_after=18, alignment=WD_ALIGN_PARAGRAPH.CENTER)


def _add_crm_alert_legend(doc, rows: list[dict[str, Any]]):
    alertas_presentes = {
        str(alerta)
        for row in rows
        for alerta in (row.get("alertas_contexto") or [])
    }
    definitions = [
        (
            "Concentração em único CRM",
            "Muitas autorizações em sequência pelo mesmo CRM",
            "Este alerta é gerado quando o mesmo CRM registra várias autorizações de venda em uma janela de tempo muito curta. A análise considera a quantidade de autorizações, a duração do intervalo e a taxa de autorizações por hora. Quanto maior a quantidade registrada em menor tempo, mais atípico é o padrão observado.",
        ),
        (
            "Concentração em múltiplos CRMs",
            "Muitas autorizações em sequência por alguns CRMs",
            "Este alerta é gerado quando, em uma mesma janela de tempo muito curta, a farmácia registra várias autorizações de venda distribuídas entre diferentes CRMs. A análise considera o volume total de autorizações, a quantidade de CRMs envolvidos, a duração do intervalo e a taxa de autorizações por hora.",
        ),
        (
            "CRM não localizado",
            "CRM não localizado",
            "O número informado não foi localizado na base oficial consultada do Conselho Federal de Medicina. O resultado deve ser confrontado com outras fontes oficiais, como o RMS, quando aplicável.",
        ),
        (
            "CRM irregular",
            "CRM irregular",
            "A data da autorização de venda é anterior à primeira inscrição do médico na UF do CRM, indicando uma incompatibilidade temporal que deve ser verificada na documentação correspondente.",
        ),
    ]
    items = [item for item in definitions if item[0] in alertas_presentes]
    items.extend(
        [
            (
                "Nº Estab.",
                "Nº Estab.",
                "Número de estabelecimentos distintos em que o CRM registrou autorizações. O valor corresponde ao maior número mensal observado no período, cuja competência aparece logo abaixo.",
            ),
            (
                "Nº Aut.",
                "Nº Aut.",
                "Quantidade de autorizações de venda vinculadas ao CRM na farmácia analisada durante o período selecionado.",
            ),
            (
                "Part.",
                "Part.",
                "Participação percentual do valor autorizado associado ao CRM em relação ao valor total autorizado pela farmácia.",
            ),
            (
                "Presc./dia",
                "Presc./dia",
                "Média diária de prescrições associadas ao CRM. Local corresponde à farmácia analisada; Brasil corresponde ao conjunto de estabelecimentos associados ao CRM na base consultada.",
            ),
        ]
    )
    if not items:
        return

    title = doc.add_paragraph()
    title.paragraph_format.space_before = Pt(8)
    title.paragraph_format.space_after = Pt(4)
    title.paragraph_format.keep_with_next = True
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(title, "Quadro 1 – Definição dos alertas e status de auditoria dos CRMs", color="334155", size=10, bold=True)

    headers = ["Alerta/status", "Definição e interpretação"]
    table = doc.add_table(rows=1, cols=len(headers))
    _crm_table_header(table, headers, [Inches(2.35), Inches(4.95)], size=9.0)

    for index, (_, label, description) in enumerate(items):
        cells = table.add_row().cells
        if index % 2 == 0:
            for cell in cells:
                _cell_bg(cell, "F8FAFC")
        _write_cell(cells[0], label, size=9.0, bold=True, color="334155", align=WD_ALIGN_PARAGRAPH.LEFT)
        _write_cell(cells[1], description, size=9.0, color="0F172A", align=WD_ALIGN_PARAGRAPH.LEFT)


def _format_crm_subheading(paragraph):
    paragraph.paragraph_format.space_before = Pt(14)
    paragraph.paragraph_format.space_after = Pt(10)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.keep_together = True
    return paragraph


def _add_crm_subheading(doc, text: str):
    return _format_crm_subheading(doc.add_heading(text, level=3))


def _parse_datetime_crm(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ").replace("Z", "")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def _datetime_in_alert_window(tx_dt: datetime, dt_ini: datetime, dt_fim: datetime) -> bool:
    if dt_ini <= tx_dt <= dt_fim:
        return True

    if tx_dt.second != 0 or tx_dt.microsecond != 0:
        return False

    def _floor_minute(value: datetime) -> datetime:
        return value.replace(second=0, microsecond=0)

    def _round_minute(value: datetime) -> datetime:
        floored = _floor_minute(value)
        return floored + timedelta(minutes=1) if value.second >= 30 or value.microsecond else floored

    # Algumas bases publicadas do Raio-X preservam apenas o minuto. Historicamente
    # isso apareceu tanto como truncamento quanto como arredondamento para o minuto
    # mais proximo, enquanto os alertas preservam segundos.
    tx_min = _floor_minute(tx_dt)
    ini_min = min(_floor_minute(dt_ini), _round_minute(dt_ini))
    fim_min = max(_floor_minute(dt_fim), _round_minute(dt_fim))
    return ini_min <= tx_min <= fim_min


def _datetime_windows_overlap(
    a_ini_raw: Any,
    a_fim_raw: Any,
    b_ini_raw: Any,
    b_fim_raw: Any,
) -> bool:
    a_ini = _parse_datetime_crm(a_ini_raw)
    a_fim = _parse_datetime_crm(a_fim_raw)
    b_ini = _parse_datetime_crm(b_ini_raw)
    b_fim = _parse_datetime_crm(b_fim_raw)
    if a_ini is None or a_fim is None or b_ini is None or b_fim is None:
        return False
    if a_fim < a_ini:
        a_ini, a_fim = a_fim, a_ini
    if b_fim < b_ini:
        b_ini, b_fim = b_fim, b_ini
    return a_ini <= b_fim and b_ini <= a_fim


def _enrich_crm_unico_valores(cnpj: str, rows: list[dict[str, Any]]) -> None:
    targets: list[tuple[dict[str, Any], str, str, datetime, datetime]] = []
    for row in rows:
        row["valor_alerta"] = 0.0
        row["valor_alerta_disponivel"] = False

        id_medico = str(row.get("id_medico") or "").strip()
        dt_ini = _parse_datetime_crm(row.get("dt_ini_hora"))
        dt_fim = _parse_datetime_crm(row.get("dt_fim_hora"))
        if not id_medico or dt_ini is None or dt_fim is None:
            continue
        if dt_fim < dt_ini:
            dt_ini, dt_fim = dt_fim, dt_ini
        targets.append((row, id_medico, dt_ini.date().isoformat(), dt_ini, dt_fim))

    if not targets:
        return

    parquet_path = os.path.join(_get_cnpj_cache_dir(cnpj), CRM_RAIOX_TX_PARQUET)
    if not os.path.exists(parquet_path):
        return

    id_medicos = sorted({target[1] for target in targets})
    datas = sorted({target[2] for target in targets})
    try:
        df_tx = (
            pl.scan_parquet(parquet_path)
            .select(["dt_janela", "data_hora", "id_medico", "valor_pago"])
            .with_columns([
                pl.col("dt_janela").cast(pl.Utf8).str.slice(0, 10).alias("_dt_janela"),
                pl.col("data_hora").cast(pl.Utf8),
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("valor_pago").cast(pl.Float64),
            ])
            .filter(pl.col("id_medico").is_in(id_medicos) & pl.col("_dt_janela").is_in(datas))
            .collect()
        )
    except Exception as exc:
        print(f"[NOTA_TECNICA] Valores do Raio-X CRM indisponiveis para {cnpj}: {exc}")
        return

    tx_por_medico_data: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for tx in df_tx.iter_rows(named=True):
        tx_dt = _parse_datetime_crm(tx.get("data_hora"))
        if tx_dt is None:
            continue
        key = (str(tx.get("id_medico") or ""), str(tx.get("_dt_janela") or ""))
        tx_por_medico_data.setdefault(key, []).append((tx_dt, _as_float(tx.get("valor_pago"))))

    for row, id_medico, data_key, dt_ini, dt_fim in targets:
        valores = [
            valor
            for tx_dt, valor in tx_por_medico_data.get((id_medico, data_key), [])
            if _datetime_in_alert_window(tx_dt, dt_ini, dt_fim)
        ]
        valor = sum(valores)
        row["valor_alerta"] = valor
        row["valor_alerta_disponivel"] = bool(valores)


def _enrich_crm_multiplo_valores(cnpj: str, rows: list[dict[str, Any]]) -> None:
    targets: list[tuple[dict[str, Any], str, datetime, datetime]] = []
    for row in rows:
        row["valor_alerta"] = 0.0
        row["valor_alerta_disponivel"] = False

        dt_ini = _parse_datetime_crm(row.get("dt_ini_hora"))
        dt_fim = _parse_datetime_crm(row.get("dt_fim_hora"))
        if dt_ini is None or dt_fim is None:
            continue
        if dt_fim < dt_ini:
            dt_ini, dt_fim = dt_fim, dt_ini
        targets.append((row, dt_ini.date().isoformat(), dt_ini, dt_fim))

    if not targets:
        return

    parquet_path = os.path.join(_get_cnpj_cache_dir(cnpj), CRM_RAIOX_TX_PARQUET)
    if not os.path.exists(parquet_path):
        return

    datas = sorted({target[1] for target in targets})
    try:
        df_tx = (
            pl.scan_parquet(parquet_path)
            .select(["dt_janela", "data_hora", "valor_pago"])
            .with_columns([
                pl.col("dt_janela").cast(pl.Utf8).str.slice(0, 10).alias("_dt_janela"),
                pl.col("data_hora").cast(pl.Utf8),
                pl.col("valor_pago").cast(pl.Float64),
            ])
            .filter(pl.col("_dt_janela").is_in(datas))
            .collect()
        )
    except Exception as exc:
        print(f"[NOTA_TECNICA] Valores do Raio-X CRM multiplo indisponiveis para {cnpj}: {exc}")
        return

    tx_por_data: dict[str, list[tuple[datetime, float]]] = {}
    for tx in df_tx.iter_rows(named=True):
        tx_dt = _parse_datetime_crm(tx.get("data_hora"))
        if tx_dt is None:
            continue
        tx_por_data.setdefault(str(tx.get("_dt_janela") or ""), []).append((tx_dt, _as_float(tx.get("valor_pago"))))

    for row, data_key, dt_ini, dt_fim in targets:
        valores = [
            valor
            for tx_dt, valor in tx_por_data.get(data_key, [])
            if _datetime_in_alert_window(tx_dt, dt_ini, dt_fim)
        ]
        valor = sum(valores)
        row["valor_alerta"] = valor
        row["valor_alerta_disponivel"] = bool(valores)


def _plural(value: int, singular: str, plural: str) -> str:
    return singular if value == 1 else plural


def _crm_table_header(table, headers: list[str], widths: list[Any], *, size: float = 7.0):
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_fixed_widths(table, widths)
    _set_table_open_borders(table)
    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        _cell_bg(cell, "E2E8F0")
        _write_cell(cell, header, size=size, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)


def _crm_alertas_contexto_labels(row: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if _as_int(row.get("flag_crm_invalido")) > 0:
        labels.append("CRM não localizado")
    if _as_int(row.get("flag_prescricao_antes_registro")) > 0:
        labels.append("CRM irregular")
    if _as_int(row.get("flag_crm_exclusivo")) > 0:
        labels.append("CRM exclusivo")
    if row.get("alertas_crm_unico") or _as_int(row.get("qtd_alertas_crm_unico")) > 0:
        labels.append("Concentração em único CRM")
    if row.get("alertas_crm_multiplos") or _as_int(row.get("qtd_alertas_crm_multiplos")) > 0:
        labels.append("Concentração em múltiplos CRMs")
    if row.get("alerta5_geografico") or row.get("alertas_geograficos") or _as_int(row.get("qtd_alertas_geograficos")) > 0:
        labels.append("Registro geográfico")

    prescricoes_dia_local = _as_float(row.get("nu_prescricoes_dia"))
    prescricoes_dia_brasil = _as_float(row.get("prescricoes_dia_total_brasil"))
    alerta_30_local = _as_int(row.get("flag_robo")) > 0 or prescricoes_dia_local > 30
    alerta_30_brasil = _as_int(row.get("flag_robo_oculto")) > 0 or prescricoes_dia_brasil > 30
    if alerta_30_local and alerta_30_brasil:
        labels.append("Volume diário atípico local/Brasil")
    elif alerta_30_local:
        labels.append("Volume diário atípico local")
    elif alerta_30_brasil:
        labels.append("Volume diário atípico Brasil")

    return labels


_CRM_ALERTAS_TABELA_LABELS = {
    "Concentração em único CRM": "Muitas autorizações em sequência pelo mesmo CRM",
    "Concentração em múltiplos CRMs": "Muitas autorizações em sequência por alguns CRMs",
}

def _write_crm_alertas_cell(cell, alertas: list[str], *, size: float = 9.0):
    paragraph = cell.paragraphs[0]
    paragraph.text = ""
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

    if not alertas:
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        _run(paragraph, "Sem alerta", color="64748B", size=size)
        return

    for index, alerta in enumerate(alertas):
        current = paragraph if index == 0 else cell.add_paragraph()
        current.alignment = WD_ALIGN_PARAGRAPH.LEFT
        current.paragraph_format.space_before = Pt(0)
        current.paragraph_format.space_after = Pt(2 if index < len(alertas) - 1 else 0)
        current.paragraph_format.line_spacing = 1.0
        label = _CRM_ALERTAS_TABELA_LABELS.get(alerta, alerta)
        _run(current, f"• {label}", color="0F172A", size=size)


def _build_principais_crms_contexto_rows(crms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    crms_ordenados = sorted(
        crms,
        key=lambda row: (
            _as_float(row.get("vl_total_prescricoes")),
            _as_int(row.get("nu_prescricoes")),
        ),
        reverse=True,
    )
    top10_ids = {str(row.get("id_medico") or "") for row in crms_ordenados[:10]}
    crms_selecionados = list(crms_ordenados[:10])
    crms_selecionados.extend(
        row
        for row in crms_ordenados[10:]
        if str(row.get("id_medico") or "") not in top10_ids
        and _crm_alertas_contexto_labels(row)
    )

    rows: list[dict[str, Any]] = []
    for row in crms_selecionados:
        contexto_row = {
            "id_medico": row.get("id_medico"),
            "no_medico": row.get("no_medico") or "Não localizado",
            "nu_prescricoes": _as_int(row.get("nu_prescricoes")),
            "vl_total_prescricoes": _as_float(row.get("vl_total_prescricoes")),
            "pct_participacao": _as_float(row.get("pct_participacao")),
            "nu_prescricoes_dia": _as_float(row.get("nu_prescricoes_dia")),
            "prescricoes_dia_total_brasil": _as_float(row.get("prescricoes_dia_total_brasil")),
            "nu_estabelecimentos": _required_nonnegative_int(
                row.get("nu_estabelecimentos"),
                "nu_estabelecimentos",
                "Tabela de principais CRMs",
            ),
            "competencia_nu_estabelecimentos": _required_competencia_crm(
                row.get("competencia_nu_estabelecimentos"),
                "Tabela de principais CRMs",
            ),
        }
        contexto_row["alertas_contexto"] = _crm_alertas_contexto_labels(row)
        rows.append(contexto_row)
    return rows


def _load_crm_evidencias_detalhadas(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    comp_ini = _date_to_competencia(data_inicio)
    comp_fim = _date_to_competencia(data_fim)
    data_inicio_txt = data_inicio.isoformat() if data_inicio else None
    data_fim_txt = data_fim.isoformat() if data_fim else None

    hourly_result = load_or_sync_crm_timeline_hora(cnpj)
    if hourly_result.error:
        raise RuntimeError(f"Alertas de volume horario CRM indisponiveis para a Nota Tecnica: {hourly_result.error}")
    df_hourly = hourly_result.df if hourly_result.df is not None else pl.DataFrame()
    cnpj_alerts: list[dict[str, Any]] = []
    if not df_hourly.is_empty():
        required = {
            "dt_janela",
            "hr_janela",
            "nu_prescricoes",
            "nu_crms_diferentes",
            "mediana_hora",
            "is_volume_horario_anomalo",
        }
        missing = sorted(required - set(df_hourly.columns))
        if missing:
            raise RuntimeError(
                "Cache horario CRM sem colunas obrigatorias para o anexo de evidencias CRM da Nota Tecnica: "
                + ", ".join(missing)
            )
        df_volume = _filter_crm_date_range(df_hourly, "dt_janela", data_inicio_txt, data_fim_txt)
        df_volume = df_volume.filter(pl.col("is_volume_horario_anomalo").cast(pl.Int8) == 1)
        for row in df_volume.iter_rows(named=True):
            cnpj_alerts.append({
                "tipo": "VOLUME",
                "dt": str(row.get("dt_janela") or "")[:10],
                "hr": _as_int(row.get("hr_janela")),
                "nu_prescricoes": _as_int(row.get("nu_prescricoes")),
                "nu_crms": _as_int(row.get("nu_crms_diferentes")),
                "mediana_hora": _as_optional_float(row.get("mediana_hora")),
            })

    unico_result = load_or_sync_crm_unico_alertas(cnpj)
    if unico_result.error:
        raise RuntimeError(f"Alertas de CRM unico indisponiveis para a Nota Tecnica: {unico_result.error}")
    df_unico = unico_result.df if unico_result.df is not None else pl.DataFrame()
    df_unico = _filter_competencia(df_unico, comp_ini, comp_fim)
    alertas_unico_por_medico = _build_crm_unico_alertas_por_medico(df_unico)

    multi_result = load_or_sync_crm_multi_alertas(cnpj)
    if multi_result.error:
        raise RuntimeError(f"Alertas de multiplos CRMs indisponiveis para a Nota Tecnica: {multi_result.error}")
    df_multi = multi_result.df if multi_result.df is not None else pl.DataFrame()
    raio_x_result = sync_crm_raiox_tx(cnpj)
    if raio_x_result.error:
        raise RuntimeError(f"Raio-X CRM indisponivel para cruzamento do anexo de evidencias CRM da Nota Tecnica: {raio_x_result.error}")
    alertas_multiplos_por_medico = _build_alertas_crm_multiplos_por_medico(
        _get_cnpj_cache_dir(cnpj),
        df_multi,
        comp_ini,
        comp_fim,
    )

    return cnpj_alerts, alertas_unico_por_medico, alertas_multiplos_por_medico


def _build_hhi_crm_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    total_mov_quadro_02: float | None,
    crm_data: Any = None,
) -> dict[str, Any] | None:
    """Monta o contexto do subitem de concentração atípica de CRM."""
    if crm_data is None:
        try:
            crm_data = get_crm_data(
                cnpj,
                data_inicio.isoformat() if data_inicio else None,
                data_fim.isoformat() if data_fim else None,
            )
        except Exception as exc:
            print(f"[NOTA_TECNICA] CRM indisponivel para {cnpj}: {exc}")
            return None

    crms = list(getattr(crm_data, "crms_interesse", None) or [])
    if not crms:
        return None

    cnpj_norm = "".join(ch for ch in str(cnpj) if ch.isdigit()).zfill(14)
    df_matriz = _build_dynamic_matriz_risco(data_inicio=data_inicio, data_fim=data_fim)
    required_matriz_cols = [
        "cnpj",
        "val_hhi_crm",
        "risco_crm_reg",
        "risco_crm_uf",
        "risco_crm_br",
    ]
    missing_cols = [col for col in required_matriz_cols if col not in df_matriz.columns]
    if missing_cols:
        raise RuntimeError(
            "Matriz de risco sem colunas obrigatorias para comparativo HHI/CRM: "
            + ", ".join(missing_cols)
        )

    matriz_rows = df_matriz.with_columns(
        pl.col("cnpj").cast(pl.Utf8).str.replace_all(r"\D", "").str.zfill(14).alias("_cnpj_norm")
    ).filter(pl.col("_cnpj_norm") == cnpj_norm)
    if matriz_rows.is_empty():
        raise RuntimeError(f"Matriz de risco sem registro obrigatorio para HHI/CRM do CNPJ {cnpj_norm}.")
    matriz_row = matriz_rows.row(0, named=True)
    indice_hhi = _required_positive_float(matriz_row.get("val_hhi_crm"), "val_hhi_crm", "comparativo HHI/CRM")
    multiplicador_regiao = _required_positive_float(
        matriz_row.get("risco_crm_reg"),
        "risco_crm_reg",
        "comparativo HHI/CRM",
    )
    multiplicador_uf = _required_positive_float(
        matriz_row.get("risco_crm_uf"),
        "risco_crm_uf",
        "comparativo HHI/CRM",
    )
    multiplicador_brasil = _required_positive_float(
        matriz_row.get("risco_crm_br"),
        "risco_crm_br",
        "comparativo HHI/CRM",
    )

    total_medicos = len(crms)
    total_autorizacoes = sum(_as_int(row.get("nu_prescricoes")) for row in crms)
    valor_total_crm = sum(_as_float(row.get("vl_total_prescricoes")) for row in crms)
    valor_total_farmacia = _as_float(total_mov_quadro_02)
    if total_medicos <= 0 or total_autorizacoes <= 0:
        return None
    if valor_total_farmacia <= 0:
        raise RuntimeError("Total financeiro da farmacia obrigatorio para o indicador HHI/CRM da Nota Tecnica.")

    crms_ordenados = sorted(
        crms,
        key=lambda row: (
            _as_float(row.get("vl_total_prescricoes")),
            _as_int(row.get("nu_prescricoes")),
        ),
        reverse=True,
    )
    top_crms: list[dict[str, Any]] = []
    autorizacoes_acumuladas = 0
    for row in crms_ordenados:
        if len(top_crms) >= 10:
            break
        top_crms.append(row)
        autorizacoes_acumuladas += _as_int(row.get("nu_prescricoes"))
        if len(top_crms) >= 5 and (autorizacoes_acumuladas / total_autorizacoes * 100) >= 80:
            break
    principal = top_crms[0]
    principal_autorizacoes = _as_int(principal.get("nu_prescricoes"))
    principal_valor = _as_float(principal.get("vl_total_prescricoes"))

    media_autorizacoes = total_autorizacoes / total_medicos
    media_valor = valor_total_farmacia / total_medicos

    if data_inicio is not None and data_fim is not None:
        periodo_intervalo = f'de {data_inicio.strftime("%d.%m.%Y")} a {data_fim.strftime("%d.%m.%Y")}'
    elif data_inicio is not None:
        periodo_intervalo = f'a partir de {data_inicio.strftime("%d.%m.%Y")}'
    elif data_fim is not None:
        periodo_intervalo = f'até {data_fim.strftime("%d.%m.%Y")}'
    else:
        periodo_intervalo = "no período analisado"

    return {
        "periodo_intervalo": periodo_intervalo,
        "total_medicos": total_medicos,
        "total_autorizacoes": total_autorizacoes,
        "valor_total": valor_total_farmacia,
        "valor_total_crm": valor_total_crm,
        "media_autorizacoes": media_autorizacoes,
        "media_valor": media_valor,
        "top_crms": top_crms,
        "principal": principal,
        "principal_autorizacoes": principal_autorizacoes,
        "principal_valor": principal_valor,
        "pct_autorizacoes": principal_autorizacoes / total_autorizacoes * 100,
        "pct_valor": principal_valor / valor_total_farmacia * 100,
        "mult_autorizacoes": principal_autorizacoes / media_autorizacoes,
        "mult_valor": principal_valor / media_valor,
        "indice_hhi": indice_hhi,
        "multiplicador_regiao": multiplicador_regiao,
        "multiplicador_uf": multiplicador_uf,
        "multiplicador_brasil": multiplicador_brasil,
    }


def _build_crms_irregulares_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    crm_data: Any = None,
) -> dict[str, Any]:
    """Monta o contexto do subitem de CRMs irregulares ou invalidos."""
    cnpj_norm = "".join(ch for ch in str(cnpj) if ch.isdigit()).zfill(14)
    df_matriz = _build_dynamic_matriz_risco(data_inicio=data_inicio, data_fim=data_fim)
    required_matriz_cols = [
        "cnpj",
        "pct_crms_irregulares",
        "crms_irregulares_valor_total",
        "crms_irregulares_valor",
        "risco_crms_irregulares_reg",
        "risco_crms_irregulares_uf",
        "risco_crms_irregulares_br",
    ]
    missing_cols = [col for col in required_matriz_cols if col not in df_matriz.columns]
    if missing_cols:
        raise RuntimeError(
            "Matriz de risco sem colunas obrigatorias para CRMs irregulares: "
            + ", ".join(missing_cols)
        )
    rows = df_matriz.with_columns(
        pl.col("cnpj").cast(pl.Utf8).str.replace_all(r"\D", "").str.zfill(14).alias("_cnpj_norm")
    ).filter(pl.col("_cnpj_norm") == cnpj_norm)
    if rows.is_empty():
        raise RuntimeError(f"Matriz de risco sem registro obrigatorio para CRMs irregulares do CNPJ {cnpj_norm}.")
    matriz_row = rows.row(0, named=True)
    total_financeiro_base = _required_positive_float(
        matriz_row.get("crms_irregulares_valor_total"),
        "crms_irregulares_valor_total",
        "indicador de CRMs irregulares",
    )
    valor_irregular = _required_nonnegative_float(
        matriz_row.get("crms_irregulares_valor"),
        "crms_irregulares_valor",
        "indicador de CRMs irregulares",
    )
    pct_irregular = _required_nonnegative_float(
        matriz_row.get("pct_crms_irregulares"),
        "pct_crms_irregulares",
        "indicador de CRMs irregulares",
    )

    def matriz_float(key: str) -> float:
        try:
            return float(matriz_row.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    if crm_data is None:
        try:
            crm_data = get_crm_data(
                cnpj,
                data_inicio.isoformat() if data_inicio else None,
                data_fim.isoformat() if data_fim else None,
            )
        except Exception as exc:
            print(f"[NOTA_TECNICA] CRM indisponivel para {cnpj}: {exc}")
            crm_data = None

    crms = list(getattr(crm_data, "crms_interesse", None) or [])
    total_autorizacoes = sum(_as_int(row.get("nu_prescricoes")) for row in crms)

    crms_irregulares = [
        row
        for row in crms
        if _as_int(row.get("flag_crm_invalido")) > 0
        or _as_int(row.get("flag_prescricao_antes_registro")) > 0
    ]
    irregulares_ordenados = sorted(
        crms_irregulares,
        key=lambda row: (
            _as_float(row.get("vl_total_prescricoes")),
            _as_int(row.get("nu_prescricoes")),
        ),
        reverse=True,
    )
    top_irregulares = irregulares_ordenados[:10]

    qtd_invalidos = sum(1 for row in crms if _as_int(row.get("flag_crm_invalido")) > 0)
    qtd_antes_registro = sum(1 for row in crms if _as_int(row.get("flag_prescricao_antes_registro")) > 0)

    if data_inicio is not None and data_fim is not None:
        periodo_intervalo = f'de {data_inicio.strftime("%d.%m.%Y")} a {data_fim.strftime("%d.%m.%Y")}'
    elif data_inicio is not None:
        periodo_intervalo = f'a partir de {data_inicio.strftime("%d.%m.%Y")}'
    elif data_fim is not None:
        periodo_intervalo = f'até {data_fim.strftime("%d.%m.%Y")}'
    else:
        periodo_intervalo = "no período analisado"

    return {
        "periodo_intervalo": periodo_intervalo,
        "total_autorizacoes": total_autorizacoes,
        "total_financeiro_base": total_financeiro_base,
        "top_irregulares": top_irregulares,
        "qtd_invalidos": qtd_invalidos,
        "qtd_antes_registro": qtd_antes_registro,
        "valor_irregular": valor_irregular,
        "pct_irregular": pct_irregular,
        "multiplicador_regiao": matriz_float("risco_crms_irregulares_reg"),
        "multiplicador_uf": matriz_float("risco_crms_irregulares_uf"),
        "multiplicador_brasil": matriz_float("risco_crms_irregulares_br"),
    }


def _build_crm_evidencias_complementares_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    crm_data: Any = None,
) -> dict[str, Any] | None:
    """Detecta evidencias operacionais de CRM independentes da matriz de risco."""
    if crm_data is None:
        try:
            crm_data = get_crm_data(
                cnpj,
                data_inicio.isoformat() if data_inicio else None,
                data_fim.isoformat() if data_fim else None,
            )
        except Exception as exc:
            print(f"[NOTA_TECNICA] Evidencias complementares CRM indisponiveis para {cnpj}: {exc}")
            return None

    crms = list(getattr(crm_data, "crms_interesse", None) or [])
    cnpj_alerts = list(getattr(crm_data, "cnpj_alerts", None) or [])
    cnpj_alerts_detalhados, alertas_unico_por_medico, alertas_multiplos_por_medico = _load_crm_evidencias_detalhadas(
        cnpj,
        data_inicio,
        data_fim,
    )
    if cnpj_alerts_detalhados:
        cnpj_alerts = cnpj_alerts_detalhados
    if not crms and not cnpj_alerts:
        return None

    intensiva_rows: list[dict[str, Any]] = []
    intensiva_medicos: set[str] = set()
    crm_unico_rows: list[dict[str, Any]] = []
    crm_unico_medicos: set[str] = set()
    crms_multiplos_rows: list[dict[str, Any]] = []
    crms_multiplos_medicos: set[str] = set()

    for row in crms:
        id_medico = str(row.get("id_medico") or "")
        if id_medico:
            if not row.get("alertas_crm_unico"):
                row["alertas_crm_unico"] = alertas_unico_por_medico.get(id_medico, [])
            if not row.get("alertas_crm_multiplos"):
                row["alertas_crm_multiplos"] = alertas_multiplos_por_medico.get(id_medico, [])

        prescricoes_dia_local = _as_float(row.get("nu_prescricoes_dia"))
        prescricoes_dia_brasil = _as_float(row.get("prescricoes_dia_total_brasil"))
        flag_intensiva_local = _as_int(row.get("flag_robo")) > 0 or prescricoes_dia_local > 30
        flag_intensiva_brasil = _as_int(row.get("flag_robo_oculto")) > 0 or prescricoes_dia_brasil > 30
        if flag_intensiva_local or flag_intensiva_brasil:
            if id_medico:
                intensiva_medicos.add(id_medico)
            if flag_intensiva_local and flag_intensiva_brasil:
                tipo_intensiva = "Local e Brasil"
            elif flag_intensiva_local:
                tipo_intensiva = "Local"
            else:
                tipo_intensiva = "Brasil"
            intensiva_rows.append({
                "id_medico": id_medico or "Não informado",
                "no_medico": row.get("no_medico") or "Não localizado",
                "tipo": tipo_intensiva,
                "nu_prescricoes": _as_int(row.get("nu_prescricoes")),
                "nu_prescricoes_total_brasil": _as_int(row.get("nu_prescricoes_total_brasil")),
                "nu_prescricoes_dia": prescricoes_dia_local,
                "prescricoes_dia_total_brasil": prescricoes_dia_brasil,
                "vl_total_prescricoes": _as_float(row.get("vl_total_prescricoes")),
            })

        for alerta in list(row.get("alertas_crm_unico") or []):
            nu_prescricoes = _as_int(alerta.get("nu_prescricoes"))
            if nu_prescricoes <= 0:
                continue
            nu_minutos_intervalo_raw = alerta.get("nu_minutos_intervalo")
            taxa_hora = _required_positive_float(alerta.get("taxa_hora"), "taxa_hora", "alerta de CRM unico")
            if id_medico:
                crm_unico_medicos.add(id_medico)
            crm_unico_rows.append({
                "id_medico": id_medico or "Não informado",
                "no_medico": row.get("no_medico") or "Não localizado",
                "dt": alerta.get("dt"),
                "nu_prescricoes": nu_prescricoes,
                "nu_minutos": _as_int(alerta.get("nu_minutos")),
                "nu_minutos_intervalo": (
                    _as_int(nu_minutos_intervalo_raw)
                    if nu_minutos_intervalo_raw is not None
                    else None
                ),
                "taxa_hora": taxa_hora,
                "id_severidade": _as_int(alerta.get("id_severidade")),
                "dt_ini_hora": alerta.get("dt_ini_hora"),
                "dt_fim_hora": alerta.get("dt_fim_hora"),
            })

        for alerta in list(row.get("alertas_crm_multiplos") or []):
            nu_presc_total = _as_int(alerta.get("nu_presc_total"))
            if nu_presc_total <= 0:
                continue
            if id_medico:
                crms_multiplos_medicos.add(id_medico)
            crms_multiplos_rows.append({
                "id_medico": id_medico or "Não informado",
                "no_medico": row.get("no_medico") or "Não localizado",
                "dt": alerta.get("dt"),
                "hr": alerta.get("hr"),
                "nu_presc_crm": _as_int(alerta.get("nu_presc_crm")),
                "nu_presc_total": nu_presc_total,
                "nu_crms_total": _as_int(alerta.get("nu_crms_total")),
                "nu_minutos": _as_int(alerta.get("nu_minutos")),
                "taxa_hora": _as_float(alerta.get("taxa_hora")),
                "dt_ini_hora": alerta.get("dt_ini_hora"),
                "dt_fim_hora": alerta.get("dt_fim_hora"),
                "id_severidade": _as_int(alerta.get("id_severidade")),
                "severidade": alerta.get("severidade") or "ALERTA",
                "descricao": alerta.get("descricao"),
            })

    intensiva_rows.sort(
        key=lambda item: (
            max(item["nu_prescricoes_dia"], item["prescricoes_dia_total_brasil"]),
            item["vl_total_prescricoes"],
        ),
        reverse=True,
    )
    crm_unico_rows.sort(
        key=lambda item: (_as_float(item.get("taxa_hora")), item["nu_prescricoes"], item["id_severidade"]),
        reverse=True,
    )
    crms_multiplos_rows.sort(
        key=lambda item: (item["nu_presc_total"], item["nu_crms_total"]),
        reverse=True,
    )
    principais_crms_contexto = _build_principais_crms_contexto_rows(crms)
    qtd_principais_contexto_alertas = sum(
        1 for row in principais_crms_contexto if row.get("alertas_contexto")
    )
    qtd_intensiva_local = sum(1 for row in intensiva_rows if row["nu_prescricoes_dia"] > 30)
    qtd_intensiva_brasil = sum(1 for row in intensiva_rows if row["prescricoes_dia_total_brasil"] > 30)
    qtd_crm_unico = len(crm_unico_medicos)
    qtd_crms_multiplos = len(crms_multiplos_medicos)
    intensiva_local_rows = [row for row in intensiva_rows if row["nu_prescricoes_dia"] > 30]
    volume_horario_rows = [
        {
            "dt": alerta.get("dt"),
            "hr": alerta.get("hr"),
            "nu_prescricoes": _as_int(alerta.get("nu_prescricoes")),
            "nu_crms": _as_int(alerta.get("nu_crms")),
            "mediana_hora": _as_optional_float(alerta.get("mediana_hora")),
        }
        for alerta in cnpj_alerts
        if alerta.get("tipo") == "VOLUME"
        and _as_int(alerta.get("nu_prescricoes")) > 0
    ]
    volume_horario_rows.sort(
        key=lambda item: (
            _volume_horario_multiplicador_value(item),
            item["nu_prescricoes"],
        ),
        reverse=True,
    )
    volume_horario_top_rows = volume_horario_rows[:30]
    surtos_multiplos = [
        alerta
        for alerta in cnpj_alerts
        if alerta.get("tipo") == "MULTIPLO" and _as_int(alerta.get("nu_prescricoes")) > 0
    ]
    principal_crm_por_evento: dict[tuple[str, int], dict[str, Any]] = {}
    for row in crms_multiplos_rows:
        key = (str(row.get("dt") or ""), _as_int(row.get("hr")))
        atual = principal_crm_por_evento.get(key)
        if atual is None or (
            _as_int(row.get("nu_presc_crm")),
            str(row.get("id_medico") or ""),
        ) > (
            _as_int(atual.get("nu_presc_crm")),
            str(atual.get("id_medico") or ""),
        ):
            principal_crm_por_evento[key] = {
                "id_medico": row.get("id_medico"),
                "nu_presc_crm": _as_int(row.get("nu_presc_crm")),
            }
    for alerta in surtos_multiplos:
        key = (str(alerta.get("dt") or "")[:10], _as_int(alerta.get("hr")))
        principal_crm = principal_crm_por_evento.get(key)
        if principal_crm:
            alerta["crm_principal"] = principal_crm.get("id_medico")
            alerta["crm_principal_autorizacoes"] = _as_int(principal_crm.get("nu_presc_crm"))
    if not surtos_multiplos and crms_multiplos_rows:
        eventos_derivados: dict[tuple[str, int], dict[str, Any]] = {}
        for row in crms_multiplos_rows:
            key = (str(row.get("dt") or ""), _as_int(row.get("hr")))
            atual = eventos_derivados.get(key)
            candidato = {
                "tipo": "MULTIPLO",
                "dt": row.get("dt"),
                "hr": row.get("hr"),
                "nu_prescricoes": _as_int(row.get("nu_presc_total")),
                "nu_crms": _as_int(row.get("nu_crms_total")),
                "nu_minutos": _as_int(row.get("nu_minutos")),
                "taxa_hora": _as_float(row.get("taxa_hora")),
                "dt_ini_hora": row.get("dt_ini_hora"),
                "dt_fim_hora": row.get("dt_fim_hora"),
                "crm_principal": row.get("id_medico"),
                "crm_principal_autorizacoes": _as_int(row.get("nu_presc_crm")),
                "id_severidade": _as_int(row.get("id_severidade")),
            }
            if atual is None or (
                _as_float(candidato.get("taxa_hora")),
                _as_int(candidato.get("nu_prescricoes")),
                _as_int(candidato.get("nu_crms")),
            ) > (
                _as_float(atual.get("taxa_hora")),
                _as_int(atual.get("nu_prescricoes")),
                _as_int(atual.get("nu_crms")),
            ):
                eventos_derivados[key] = candidato
        surtos_multiplos = list(eventos_derivados.values())
    surtos_multiplos.sort(
        key=lambda item: (
            _as_float(item.get("taxa_hora")),
            _as_int(item.get("nu_prescricoes")),
            _as_int(item.get("nu_crms")),
        ),
        reverse=True,
    )
    qtd_surtos_multiplos = len(surtos_multiplos)
    crm_unico_por_medico: dict[str, list[dict[str, Any]]] = {}
    for row in crm_unico_rows:
        crm_unico_por_medico.setdefault(str(row.get("id_medico") or ""), []).append(row)
    surtos_multiplos = [
        alerta
        for alerta in surtos_multiplos
        if not any(
            _datetime_windows_overlap(
                alerta.get("dt_ini_hora"),
                alerta.get("dt_fim_hora"),
                unico.get("dt_ini_hora"),
                unico.get("dt_fim_hora"),
            )
            for unico in crm_unico_por_medico.get(str(alerta.get("crm_principal") or ""), [])
        )
    ]
    qtd_surtos_multiplos = len(surtos_multiplos)
    surtos_multiplos_top = _select_crm_concentracao_table_rows(surtos_multiplos)
    if surtos_multiplos_top:
        _enrich_crm_multiplo_valores(cnpj, surtos_multiplos_top)
    crm_unico_top_rows = _select_crm_unico_concentracao_table_rows(crm_unico_rows)
    if crm_unico_top_rows:
        _enrich_crm_unico_valores(cnpj, crm_unico_top_rows)
    crm_unico_top_medicos = {
        str(row.get("id_medico") or "")
        for row in crm_unico_top_rows
        if str(row.get("id_medico") or "")
    }
    surtos_multiplos_top_keys = {_crm_event_key(row) for row in surtos_multiplos_top}
    crms_multiplos_top_rows = [
        row for row in crms_multiplos_rows if _crm_event_key(row) in surtos_multiplos_top_keys
    ]
    crms_multiplos_top_medicos = {
        str(row.get("id_medico") or "")
        for row in crms_multiplos_top_rows
        if str(row.get("id_medico") or "")
    }
    if not crms_multiplos_top_medicos and surtos_multiplos_top:
        qtd_crms_multiplos_top = max((_as_int(row.get("nu_crms")) for row in surtos_multiplos_top), default=0)
    else:
        qtd_crms_multiplos_top = len(crms_multiplos_top_medicos)
    total_evidencias = (
        qtd_intensiva_local
        + len(volume_horario_top_rows)
        + len(crm_unico_top_medicos)
        + qtd_crms_multiplos_top
        + len(surtos_multiplos_top)
    )
    if total_evidencias <= 0:
        return None

    return {
        "principais_crms_contexto": {
            "rows": principais_crms_contexto,
            "qtd_com_alerta": qtd_principais_contexto_alertas,
        } if principais_crms_contexto else None,
        "qtd_intensiva_local": qtd_intensiva_local,
        "qtd_intensiva_brasil": qtd_intensiva_brasil,
        "qtd_crm_unico": qtd_crm_unico,
        "qtd_crms_multiplos": qtd_crms_multiplos,
        "qtd_surtos_multiplos": qtd_surtos_multiplos,
        "volume_horario": {
            "qtd_alertas": len(volume_horario_rows),
            "maior_multiplicador": next(
                (
                    _volume_horario_multiplicador_value(row)
                    for row in volume_horario_top_rows
                ),
                None,
            ),
            "maior_qtd": max((row["nu_prescricoes"] for row in volume_horario_top_rows), default=0),
            "rows": volume_horario_top_rows,
        } if volume_horario_top_rows else None,
        "intensiva": {
            "qtd_medicos": len({row["id_medico"] for row in intensiva_local_rows}),
            "qtd_local": qtd_intensiva_local,
            "qtd_brasil": qtd_intensiva_brasil,
            "maior_media_local": max((row["nu_prescricoes_dia"] for row in intensiva_local_rows), default=0.0),
            "maior_media_brasil": max((row["prescricoes_dia_total_brasil"] for row in intensiva_local_rows), default=0.0),
            "rows": intensiva_local_rows[:10],
        } if qtd_intensiva_local > 0 else None,
        "crm_unico": {
            "qtd_medicos": len(crm_unico_top_medicos),
            "qtd_alertas": len(crm_unico_top_rows),
            "maior_qtd": max((row["nu_prescricoes"] for row in crm_unico_top_rows), default=0),
            "rows": crm_unico_top_rows,
        } if crm_unico_top_rows else None,
        "crms_multiplos": {
            "qtd_medicos": qtd_crms_multiplos_top,
            "qtd_surtos": len(surtos_multiplos_top),
            "qtd_participacoes": len(crms_multiplos_top_rows),
            "maior_qtd": max((_as_int(row.get("nu_prescricoes")) for row in surtos_multiplos_top), default=0),
            "eventos": surtos_multiplos_top,
        } if surtos_multiplos_top else None,
    }


def _add_crm_intensiva_complementar_text(
    doc,
    letra: str,
    razao_social: str,
    intensiva_comp: dict[str, Any],
    tabela_num: int,
):
    """Adiciona o bloco de prescritores com mais de 30 prescricoes por dia."""
    qtd_medicos = _as_int(intensiva_comp.get("qtd_medicos"))
    qtd_local = _as_int(intensiva_comp.get("qtd_local"))
    qtd_brasil = _as_int(intensiva_comp.get("qtd_brasil"))
    maior_media_local = _as_float(intensiva_comp.get("maior_media_local"))
    maior_media_brasil = _as_float(intensiva_comp.get("maior_media_brasil"))
    rows = list(intensiva_comp.get("rows") or [])

    _add_crm_subheading(doc, f"{letra}) Médicos com mais de 30 prescrições por dia")

    p = doc.add_paragraph()
    _run(
        p,
        f"Na Farmácia {razao_social}, {_plural(qtd_medicos, 'foi identificado', 'foram identificados')} ",
        color="0F172A",
        size=12,
    )
    _run(p, f"{qtd_medicos}", color="334155", size=12, bold=True)
    _run(p, f" {_plural(qtd_medicos, 'CRM com média', 'CRMs com média')} superior a ", color="0F172A", size=12)
    _run(p, "30 prescrições por dia", color="334155", size=12, bold=True)
    _run(
        p,
        " no próprio estabelecimento, indicando uso intensivo do mesmo registro médico nas autorizações do SAV. ",
        color="0F172A",
        size=12,
    )
    if maior_media_local > 0:
        _run(p, "A maior média local observada foi de ", color="0F172A", size=12)
        _run(p, f"{_format_decimal_pt(maior_media_local, 2)} prescrições/dia", color="334155", size=12, bold=True)
        if qtd_brasil > 0 and maior_media_brasil > 0:
            _run(
                p,
                f"; considerando todas as autorizações associadas {_plural(qtd_medicos, 'a esse CRM', 'a esses CRMs')} no Brasil, a maior média chegou a ",
                color="0F172A",
                size=12,
            )
            _run(p, f"{_format_decimal_pt(maior_media_brasil, 2)} prescrições/dia", color="334155", size=12, bold=True)
        _run(p, ".", color="0F172A", size=12)

    if not rows:
        return

    title = doc.add_paragraph()
    _format_crm_table_title(title)
    _run(title, f"Tabela {tabela_num} - Principais médicos com volume médio diário superior a 30 prescrições.", color="334155", size=10, bold=True)

    headers = ["CRM/UF", "Nome", "Tipo", "Presc./dia local", "Presc./dia Brasil", "Autorizações", "Valor"]
    table = doc.add_table(rows=1, cols=len(headers))
    widths = [Inches(0.78), Inches(1.82), Inches(0.78), Inches(0.88), Inches(0.88), Inches(0.93), Inches(1.23)]
    _crm_table_header(table, headers, widths, size=9.0)

    for row in rows:
        cells = table.add_row().cells
        crm_row, uf_row = _crm_num_uf(row.get("id_medico"))
        crm_uf = f"{crm_row}/{uf_row}" if uf_row else crm_row
        values = [
            crm_uf,
            _title_case_pt(row.get("no_medico") or "Não localizado"),
            str(row.get("tipo") or "—"),
            _format_decimal_pt(_as_float(row.get("nu_prescricoes_dia")), 2),
            _format_decimal_pt(_as_float(row.get("prescricoes_dia_total_brasil")), 2),
            str(_as_int(row.get("nu_prescricoes"))),
            f'R$ {_format_decimal_pt(_as_float(row.get("vl_total_prescricoes")), 2)}',
        ]
        for idx, value in enumerate(values):
            align = WD_ALIGN_PARAGRAPH.RIGHT if idx in (3, 4, 5, 6) else WD_ALIGN_PARAGRAPH.CENTER if idx in (0, 2) else None
            _write_cell(cells[idx], value, size=9.0, align=align)

    fonte = doc.add_paragraph()
    _format_crm_table_footnote(fonte)
    _run(
        fonte,
        "Fonte: Bases de Dados do CFM e Sistema Autorizador de Vendas (SAV).",
        color="0F172A",
        size=10,
        italic=True,
    )


def _add_crm_unico_complementar_text(
    doc,
    letra: str,
    razao_social: str,
    crm_unico_comp: dict[str, Any],
    tabela_num: int,
):
    """Adiciona o bloco de concentracao temporal em um unico CRM."""
    qtd_medicos = _as_int(crm_unico_comp.get("qtd_medicos"))
    qtd_alertas = _as_int(crm_unico_comp.get("qtd_alertas"))
    maior_qtd = _as_int(crm_unico_comp.get("maior_qtd"))
    rows = list(crm_unico_comp.get("rows") or [])
    principal = rows[0] if rows else {}
    principal_intervalo = None
    if principal:
        principal_intervalo = principal.get("nu_minutos_intervalo")
        if principal_intervalo is None:
            principal_intervalo = principal.get("nu_minutos")

    _add_crm_subheading(doc, f"{letra}) Muitas autorizações em sequência pelo mesmo CRM")

    p = doc.add_paragraph()
    _run(p, f"{_plural(qtd_alertas, 'Foi identificado', 'Foram identificados')} ", color="0F172A", size=12)
    _run(p, f"{qtd_alertas}", color="334155", size=12, underline=True)
    _run(
        p,
        f" {_plural(qtd_alertas, 'episódio', 'episódios')} em que autorizações vinculadas a um mesmo CRM foram registradas em curto intervalo de tempo, envolvendo ",
        color="0F172A",
        size=12,
    )
    _run(p, f"{qtd_medicos}", color="334155", size=12, underline=True)
    _run(
        p,
        f" {_plural(qtd_medicos, 'médico', 'médicos')}. Esse padrão indica concentração incomum de lançamentos no SAV e pode sugerir uso sequencial {_plural(qtd_medicos, 'desse registro profissional', 'desses registros profissionais')} em operações de balcão. ",
        color="0F172A",
        size=12,
    )
    _run(p, "O episódio de maior ritmo observado concentrou ", color="0F172A", size=12)
    _run(p, f"{_as_int(principal.get('nu_prescricoes')) or maior_qtd}", color="334155", size=12, underline=True)
    ritmo_principal = (
        _required_positive_float(principal.get("taxa_hora"), "taxa_hora", "principal alerta de CRM unico")
        if principal
        else 0.0
    )
    _run(
        p,
        (
            f" autorizações em {_format_janela_minutos(principal_intervalo) if principal_intervalo is not None else 'intervalo reduzido'}, "
            f"o que corresponde a um ritmo de {_format_decimal_pt(ritmo_principal, 1)} autorizações por hora."
        ),
        color="0F172A",
        size=12,
    )

    if not rows:
        return

    title = doc.add_paragraph()
    _format_crm_table_title(title)
    _run(title, f"Tabela {tabela_num} - Muitas autorizações em sequência pelo mesmo CRM — principais episódios.", color="334155", size=10, bold=True)

    headers = ["Início", "Fim", "Médico/CRM", "Autorizações", "Intervalo", "Taxa/hora", "Valor"]
    table = doc.add_table(rows=1, cols=len(headers))
    widths = [Inches(1.05), Inches(1.05), Inches(2.62), Inches(0.48), Inches(0.55), Inches(0.68), Inches(0.87)]
    _crm_table_header(table, headers, widths, size=9.0)

    for row in rows:
        cells = table.add_row().cells
        crm_row, uf_row = _crm_num_uf(row.get("id_medico"))
        crm_uf = f"{crm_row}/{uf_row}" if uf_row else crm_row
        intervalo = row.get("nu_minutos_intervalo")
        taxa_hora = _required_positive_float(row.get("taxa_hora"), "taxa_hora", "alerta de CRM unico")
        dt_inicio = row.get("dt_ini_hora") or row.get("dt")
        dt_fim = row.get("dt_fim_hora") or row.get("dt")
        _write_date_cell_with_weekend_marker(cells[0], dt_inicio, _format_datetime_br_minute)
        _write_date_cell_with_weekend_marker(cells[1], dt_fim, _format_datetime_br_minute)
        values = [
            str(_as_int(row.get("nu_prescricoes"))),
            _format_janela_minutos(intervalo if intervalo is not None else row.get("nu_minutos")),
            f'{_format_decimal_pt(taxa_hora, 1)}/h',
            f'R$ {_format_decimal_pt(_as_float(row.get("valor_alerta")), 2)}'
            if row.get("valor_alerta_disponivel")
            else "N/d",
        ]
        p_medico = cells[2].paragraphs[0]
        p_medico.text = ""
        p_medico.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_medico.paragraph_format.space_before = Pt(0)
        p_medico.paragraph_format.space_after = Pt(0)
        _run(p_medico, _title_case_pt(row.get("no_medico") or "Não localizado"), color="0F172A", size=9)
        _run(p_medico, f"\nCRM {crm_uf}", color="64748B", size=9)

        for col_idx, value in enumerate(values, start=3):
            align = WD_ALIGN_PARAGRAPH.RIGHT if col_idx in (3, 5, 6) else WD_ALIGN_PARAGRAPH.CENTER
            _write_cell(cells[col_idx], value, size=9.0, align=align)

    fonte = doc.add_paragraph()
    _format_crm_table_footnote(fonte)
    _run(
        fonte,
        "Fonte: Bases de Dados do CFM e Sistema Autorizador de Vendas (SAV).",
        color="0F172A",
        size=10,
        italic=True,
    )


def _add_crms_multiplos_complementar_text(
    doc,
    letra: str,
    razao_social: str,
    crms_multiplos_comp: dict[str, Any],
    tabela_num: int,
):
    """Adiciona o bloco de concentracao temporal envolvendo multiplos CRMs."""
    qtd_medicos = _as_int(crms_multiplos_comp.get("qtd_medicos"))
    qtd_surtos = _as_int(crms_multiplos_comp.get("qtd_surtos"))
    maior_qtd = _as_int(crms_multiplos_comp.get("maior_qtd"))
    eventos = list(crms_multiplos_comp.get("eventos") or [])
    principal = eventos[0] if eventos else {}

    _add_crm_subheading(doc, f"{letra}) Muitas autorizações em sequência por alguns CRMs")

    p = doc.add_paragraph()
    _run(
        p,
        f"No nível do estabelecimento, {_plural(qtd_surtos, 'foi identificado', 'foram identificados')} ",
        color="0F172A",
        size=12,
    )
    _run(p, f"{qtd_surtos}", color="334155", size=12, underline=True)
    _run(
        p,
        f" {_plural(qtd_surtos, 'episódio', 'episódios')} em que autorizações associadas a diferentes CRMs foram registradas em curto intervalo, com participação de ",
        color="0F172A",
        size=12,
    )
    _run(p, f"{qtd_medicos}", color="334155", size=12, underline=True)
    _run(
        p,
        f" {_plural(qtd_medicos, 'médico', 'médicos')} entre os principais prescritores analisados. Esse comportamento sugere concentração operacional de lançamentos e pode indicar processamento sequencial de autorizações com alternância de registros profissionais. ",
        color="0F172A",
        size=12,
    )
    if maior_qtd > 0:
        _run(p, "O principal episódio reuniu ", color="0F172A", size=12)
        _run(p, f"{_as_int(principal.get('nu_prescricoes')) or maior_qtd}", color="334155", size=12, underline=True)
        _run(p, " autorizações", color="0F172A", size=12)
        if principal:
            _run(p, ", envolvendo ", color="0F172A", size=12)
            _run(p, f"{_as_int(principal.get('nu_crms'))}", color="334155", size=12, underline=True)
            _run(
                p,
                f" CRMs distintos em {_format_janela_minutos(principal.get('nu_minutos'))}.",
                color="0F172A",
                size=12,
            )
        else:
            _run(p, ".", color="0F172A", size=12)

    if eventos:
        title = doc.add_paragraph()
        _format_crm_table_title(title)
        _run(title, f"Tabela {tabela_num} - Muitas autorizações em sequência por alguns CRMs — principais episódios.", color="334155", size=10, bold=True)

        headers = ["Início", "Fim", "CRMs", "Autorizações", "Intervalo", "Taxa/hora", "Valor"]
        table = doc.add_table(rows=1, cols=len(headers))
        widths = [Inches(1.18), Inches(1.18), Inches(0.60), Inches(1.05), Inches(0.80), Inches(1.05), Inches(1.44)]
        _crm_table_header(table, headers, widths, size=9.0)
        for evento in eventos:
            cells = table.add_row().cells
            dt_inicio = evento.get("dt_ini_hora") or evento.get("dt")
            dt_fim = evento.get("dt_fim_hora") or evento.get("dt")
            _write_date_cell_with_weekend_marker(cells[0], dt_inicio, _format_datetime_br_minute)
            _write_date_cell_with_weekend_marker(cells[1], dt_fim, _format_datetime_br_minute)
            values = [
                str(_as_int(evento.get("nu_crms"))),
                str(_as_int(evento.get("nu_prescricoes"))),
                _format_janela_minutos(evento.get("nu_minutos")),
                f'{_format_decimal_pt(_as_float(evento.get("taxa_hora")), 1)}/h',
                f'R$ {_format_decimal_pt(_as_float(evento.get("valor_alerta")), 2)}'
                if evento.get("valor_alerta_disponivel")
                else "N/d",
            ]
            for col_idx, value in enumerate(values, start=2):
                align = WD_ALIGN_PARAGRAPH.RIGHT if col_idx in (3, 5, 6) else WD_ALIGN_PARAGRAPH.CENTER
                _write_cell(cells[col_idx], value, size=9.0, align=align)

        fonte = doc.add_paragraph()
        _format_crm_table_footnote(fonte)
        _run(
            fonte,
            "Fonte: Bases de Dados do CFM e Sistema Autorizador de Vendas (SAV).",
            color="0F172A",
            size=10,
            italic=True,
        )


def _add_crm_volume_horario_complementar_text(
    doc,
    letra: str,
    razao_social: str,
    volume_comp: dict[str, Any],
    tabela_num: int,
):
    """Adiciona o bloco de volume horario anomalo de autorizacoes."""
    qtd_alertas = _as_int(volume_comp.get("qtd_alertas"))
    rows = list(volume_comp.get("rows") or [])
    principal = rows[0] if rows else {}

    _add_crm_subheading(doc, f"{letra}) Volume de autorizações em horário anômalo")

    p = doc.add_paragraph()
    _run(
        p,
        f"Na Farmácia {razao_social}, {_plural(qtd_alertas, 'foi identificado', 'foram identificados')} ",
        color="0F172A",
        size=12,
    )
    _run(p, f"{qtd_alertas}", color="334155", size=12, underline=True)
    _run(
        p,
        f" {_plural(qtd_alertas, 'horário', 'horários')} com volume de autorizações acima do padrão histórico do próprio estabelecimento para a mesma faixa horária. A tabela exibe ",
        color="0F172A",
        size=12,
    )
    qtd_exibida = len(rows)
    _run(
        p,
        f"{qtd_exibida} {_plural(qtd_exibida, 'principal horário', 'principais horários')}",
        color="334155",
        size=12,
        underline=True,
    )
    _run(
        p,
        ", ordenados pelo multiplicador em relação à mediana histórica da respectiva faixa horária. ",
        color="0F172A",
        size=12,
    )
    if principal:
        _run(p, "O principal horário concentrou ", color="0F172A", size=12)
        _run(p, f"{_as_int(principal.get('nu_prescricoes'))}", color="334155", size=12, underline=True)
        _run(
            p,
            f" autorizações em {_format_date_br(principal.get('dt'))}, às {_format_time_hour(principal.get('hr'))}",
            color="0F172A",
            size=12,
        )
        mediana_principal = _as_optional_float(principal.get("mediana_hora"))
        multiplicador_principal = _volume_horario_multiplicador_value(principal)
        if mediana_principal == 0:
            _run(
                p,
                ". Como a mediana histórica desse horário é de ",
                color="0F172A",
                size=12,
            )
            _run(p, "0,0 autorização", color="334155", size=12, underline=True)
            _run(
                p,
                ", o multiplicador exibido na tabela foi calculado com denominador mínimo de 1 autorização, resultando em volume ",
                color="0F172A",
                size=12,
            )
            _run(p, f"{_format_decimal_pt(multiplicador_principal, 1)} vezes", color="334155", size=12, bold=True)
            _run(p, " superior à mediana histórica para o horário.", color="0F172A", size=12)
        else:
            _run(p, ", volume ", color="0F172A", size=12)
            _run(p, f"{_format_decimal_pt(multiplicador_principal, 1)} vezes", color="334155", size=12, bold=True)
            _run(p, " a mediana histórica de ", color="0F172A", size=12)
            _run(
                p,
                f"{_format_optional_decimal_pt(mediana_principal, 1)} {_plural(int(round(mediana_principal or 0.0)), 'autorização', 'autorizações')}",
                color="334155",
                size=12,
                underline=True,
            )
            _run(p, " para esse horário.", color="0F172A", size=12)

    if not rows:
        return

    title = doc.add_paragraph()
    _format_crm_table_title(title)
    _run(title, f"Tabela {tabela_num} - Principais horários com volume anômalo de autorizações.", color="334155", size=10, bold=True)

    headers = ["Data", "Hora", "Autorizações", "CRMs", "Mediana", "Multiplicador"]
    table = doc.add_table(rows=1, cols=len(headers))
    widths = [Inches(1.03), Inches(0.78), Inches(1.30), Inches(0.78), Inches(1.38), Inches(2.03)]
    _crm_table_header(table, headers, widths, size=9.0)

    for row in rows:
        cells = table.add_row().cells
        _write_date_cell_with_weekend_marker(cells[0], row.get("dt"))
        values = [
            _format_hour_range(row.get("hr")),
            str(_as_int(row.get("nu_prescricoes"))),
            str(_as_int(row.get("nu_crms"))),
            _format_optional_decimal_pt(row.get("mediana_hora"), 1),
            _format_volume_horario_multiplicador(row),
        ]
        for idx, value in enumerate(values, start=1):
            align = WD_ALIGN_PARAGRAPH.RIGHT if idx in (2, 3, 4, 5) else WD_ALIGN_PARAGRAPH.CENTER
            _write_cell(cells[idx], value, size=9.0, align=align)

    fonte = doc.add_paragraph()
    _format_crm_table_footnote(fonte)
    _run(
        fonte,
        "Fonte: Bases de Dados do CFM e Sistema Autorizador de Vendas (SAV).",
        color="0F172A",
        size=10,
        italic=True,
    )


def _add_principais_crms_contexto_text(
    doc,
    razao_social: str,
    principais_comp: dict[str, Any],
    tabela_num: int,
):
    """Adiciona a tabela contextual dos principais CRMs por valor autorizado."""
    rows = list(principais_comp.get("rows") or [])
    if not rows:
        return

    qtd_com_alerta = _as_int(principais_comp.get("qtd_com_alerta"))

    p = doc.add_paragraph()
    _run(
        p,
        f"Para contextualizar os achados, a tabela a seguir apresenta os 10 principais CRMs utilizados pela Farmácia {razao_social}, ordenados pelo valor autorizado no SAV.",
        color="0F172A",
        size=12,
    )
    if qtd_com_alerta > 0:
        _run(
            p,
            " CRMs fora do top 10 também são exibidos quando possuem alertas ou anomalias relevantes para a análise; nesses casos, as linhas aparecem destacadas.",
            color="0F172A",
            size=12,
        )

    title = doc.add_paragraph()
    _format_crm_table_title(title)
    _run(title, f"Tabela {tabela_num} - Principais CRMs do estabelecimento por valor autorizado.", color="334155", size=10, bold=True)

    headers = [
        "Médico/CRM",
        "Alertas",
        "Nº Aut.",
        "Nº Estab.",
        "Valor autorizado",
        "Part.",
        "Presc./dia",
    ]
    table = doc.add_table(rows=1, cols=len(headers))
    widths = [
        Inches(1.50),
        Inches(1.65),
        Inches(0.65),
        Inches(0.83),
        Inches(1.05),
        Inches(0.62),
        Inches(1.00),
    ]
    _crm_table_header(table, headers, widths, size=9.0)

    for row in rows:
        cells = table.add_row().cells
        alertas = list(row.get("alertas_contexto") or [])
        if alertas:
            for cell in cells:
                _cell_bg(cell, "FFF7ED")

        crm_row, uf_row = _crm_num_uf(row.get("id_medico"))
        crm_uf = f"{crm_row}/{uf_row}" if uf_row else crm_row
        presc_dia = (
            f'{_format_decimal_pt(_as_float(row.get("nu_prescricoes_dia")), 2)} Local\n'
            f'{_format_decimal_pt(_as_float(row.get("prescricoes_dia_total_brasil")), 2)} Brasil'
        )
        estabelecimentos = (
            f'{row["nu_estabelecimentos"]}\n'
            f'{row["competencia_nu_estabelecimentos"]}'
        )
        values = [
            str(_as_int(row.get("nu_prescricoes"))),
            estabelecimentos,
            f'R$ {_format_decimal_pt(_as_float(row.get("vl_total_prescricoes")), 2)}',
            f'{_format_decimal_pt(_as_float(row.get("pct_participacao")), 2)}%',
            presc_dia,
        ]
        p_medico = cells[0].paragraphs[0]
        p_medico.text = ""
        p_medico.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_medico.paragraph_format.space_before = Pt(0)
        p_medico.paragraph_format.space_after = Pt(0)
        _run(p_medico, _title_case_pt(row.get("no_medico") or "Não localizado"), color="0F172A", size=8.5)
        _run(p_medico, f"\nCRM {crm_uf}", color="64748B", size=8.5)

        for col_idx, value in enumerate(values, start=2):
            align = (
                WD_ALIGN_PARAGRAPH.RIGHT
                if col_idx in (2, 4)
                else WD_ALIGN_PARAGRAPH.CENTER
                if col_idx in (3, 5, 6)
                else WD_ALIGN_PARAGRAPH.RIGHT
                if col_idx == 7
                else None
            )
            _write_cell(cells[col_idx], value, size=8.5, align=align)

        _write_crm_alertas_cell(cells[1], alertas, size=8.5)

    fonte = doc.add_paragraph()
    _format_crm_table_footnote(fonte)
    _run(
        fonte,
        "Fonte: Bases de Dados do CFM e Sistema Autorizador de Vendas (SAV).",
        color="0F172A",
        size=10,
        italic=True,
    )
    _add_crm_alert_legend(doc, rows)


def _add_crm_evidencias_complementares_body(
    doc,
    razao_social: str,
    evidencias_comp: dict[str, Any],
    tabela_num: int,
):
    p_intro = doc.add_paragraph()
    _run(
        p_intro,
        "Além dos indicadores críticos apresentados nos subitens anteriores, foram identificadas evidências operacionais complementares relacionadas ao uso de CRMs no SAV. Tais evidências não correspondem, isoladamente, a indicadores da matriz de risco, mas ajudam a contextualizar a dinâmica dos lançamentos realizados pelo estabelecimento.",
        color="0F172A",
        size=12,
    )

    principais_crms_comp = evidencias_comp.get("principais_crms_contexto")
    if principais_crms_comp:
        tabela_num += 1
        _add_principais_crms_contexto_text(doc, razao_social, principais_crms_comp, tabela_num)

    letras = iter("abcdefghijklmnopqrstuvwxyz")

    volume_horario_comp = evidencias_comp.get("volume_horario")
    if volume_horario_comp:
        tabela_num += 1
        _add_crm_volume_horario_complementar_text(doc, next(letras), razao_social, volume_horario_comp, tabela_num)
    intensiva_comp = evidencias_comp.get("intensiva")
    if intensiva_comp:
        tabela_num += 1
        _add_crm_intensiva_complementar_text(doc, next(letras), razao_social, intensiva_comp, tabela_num)
    crm_unico_comp = evidencias_comp.get("crm_unico")
    if crm_unico_comp:
        tabela_num += 1
        _add_crm_unico_complementar_text(doc, next(letras), razao_social, crm_unico_comp, tabela_num)
    crms_multiplos_comp = evidencias_comp.get("crms_multiplos")
    if crms_multiplos_comp:
        tabela_num += 1
        _add_crms_multiplos_complementar_text(doc, next(letras), razao_social, crms_multiplos_comp, tabela_num)

    return tabela_num


def _add_hhi_crm_text(
    doc,
    num: str,
    razao_social: str,
    cnpj_fmt: str,
    hhi_crm_comp: dict[str, Any],
    tabela_num: int,
    regional_table_renderer: Callable[[], None],
    bookmark_name: str | None = None,
):
    """Adiciona o subitem de concentração atípica de registros do mesmo CRM."""
    periodo_intervalo = hhi_crm_comp["periodo_intervalo"]
    total_medicos = hhi_crm_comp["total_medicos"]
    total_autorizacoes = hhi_crm_comp["total_autorizacoes"]
    valor_total = hhi_crm_comp["valor_total"]
    media_autorizacoes = hhi_crm_comp["media_autorizacoes"]
    media_valor = hhi_crm_comp["media_valor"]
    principal = hhi_crm_comp["principal"]
    principal_autorizacoes = hhi_crm_comp["principal_autorizacoes"]
    principal_valor = hhi_crm_comp["principal_valor"]
    crm_num, crm_uf = _crm_num_uf(principal.get("id_medico"))
    crm_ident = f"{crm_num}/{crm_uf}" if crm_uf else crm_num
    nome_medico = str(principal.get("no_medico") or "Não localizado")

    heading = doc.add_heading(
        f"{num} Concentração atípica de registros do mesmo médico (CRM) no Sistema Autorizador de Vendas do PFPB",
        level=2,
    )
    if bookmark_name:
        _add_bookmark(heading, bookmark_name)

    p1 = doc.add_paragraph()
    _run(
        p1,
        "Este indicador mede o grau de concentração das autorizações registradas no SAV em um conjunto restrito de médicos, identificados pelos respectivos CRMs. A métrica utilizada para essa análise é o Índice Herfindahl-Hirschman (HHI), que aumenta quando as autorizações se concentram em poucos prescritores e é menor quando os registros estão distribuídos de forma mais homogênea entre diversos médicos. Em um padrão ordinário, espera-se maior dispersão dos prescritores, pois os beneficiários tendem a apresentar receitas emitidas por diferentes profissionais, unidades de saúde e momentos de atendimento. Quando parcela relevante das dispensações da farmácia se concentra em poucos CRMs, em patamar superior ao observado para o conjunto de estabelecimentos comparáveis, o achado sugere dependência atípica da farmácia em relação a um grupo limitado de prescritores ou uso recorrente de determinadas identificações médicas nos registros de autorização.",
        color="0F172A",
        size=12,
    )

    p_comparativo = doc.add_paragraph()
    _run(p_comparativo, f"Em relação à Farmácia {razao_social}, verificou-se o índice HHI de ", color="0F172A", size=12)
    _run(p_comparativo, _format_decimal_pt(hhi_crm_comp["indice_hhi"], 2), color="334155", size=12, underline=True)
    _run(p_comparativo, ", correspondente a ", color="0F172A", size=12)
    _run(
        p_comparativo,
        f'{_format_decimal_pt(hhi_crm_comp["multiplicador_regiao"], 2)} vezes',
        color="334155",
        size=12,
        underline=True,
    )
    _run(p_comparativo, " a mediana do índice HHI das farmácias de sua região. Ampliando-se o comparativo geográfico, o índice equivale a ", color="0F172A", size=12)
    _run(
        p_comparativo,
        f'{_format_decimal_pt(hhi_crm_comp["multiplicador_uf"], 2)} vezes',
        color="334155",
        size=12,
        underline=True,
    )
    _run(p_comparativo, " a mediana das farmácias de seu Estado e a ", color="0F172A", size=12)
    _run(
        p_comparativo,
        f'{_format_decimal_pt(hhi_crm_comp["multiplicador_brasil"], 2)} vezes',
        color="334155",
        size=12,
        underline=True,
    )
    _run(p_comparativo, " a mediana das farmácias de todo o Brasil.", color="0F172A", size=12)

    regional_table_renderer()

    p2 = doc.add_paragraph()
    _run(p2, f"No período {periodo_intervalo}, foram identificados ", color="0F172A", size=12)
    _run(p2, f"{total_medicos}", color="334155", size=12, underline=True)
    _run(
        p2,
        f" médicos lançados pela Farmácia {razao_social} como responsáveis pelas receitas prescritas de medicamentos supostamente retirados no estabelecimento. A tabela a seguir apresenta os principais CRMs por valor pago, com indicação da participação individual de cada um na produção total da farmácia, observado o mínimo de 5 e o máximo de 10 médicos:",
        color="0F172A",
        size=12,
    )

    title = doc.add_paragraph()
    _format_crm_table_title(title)
    _run(
        title,
        f"Tabela {tabela_num} - Médicos/CRMs com maiores valores pagos pelo PFPB em vendas lançadas pela Farmácia {razao_social} (CNPJ {cnpj_fmt}) no Sistema Autorizador de Vendas, no período {periodo_intervalo}.",
        color="334155",
        size=10,
        bold=True,
    )

    headers = [
        "CRM/UF",
        "Nome",
        "Data da primeira inscrição na UF",
        "Número de autorizações vinculadas ao CRM",
        "% sobre a produção total da farmácia",
        "Valor total pago pelo PFPB tendo como base o CRM",
    ]
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_open_borders(table)
    widths = [Inches(0.90), Inches(2.05), Inches(0.85), Inches(1.05), Inches(1.00), Inches(1.45)]
    _set_table_fixed_widths(table, widths)

    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        _cell_bg(cell, "E2E8F0")
        _write_cell(cell, header, size=9.0, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)

    for row in hhi_crm_comp["top_crms"]:
        cells = table.add_row().cells
        crm_row, uf_row = _crm_num_uf(row.get("id_medico"))
        row_autorizacoes = _as_int(row.get("nu_prescricoes"))
        row_valor = _as_float(row.get("vl_total_prescricoes"))
        pct_producao_total = (row_valor / valor_total * 100) if valor_total else 0.0
        crm_uf = f"{crm_row}/{uf_row}" if uf_row else crm_row
        values = [
            crm_uf,
            _title_case_pt(row.get("no_medico") or "Não localizado"),
            _format_date_br(row.get("dt_inscricao_crm")),
            str(row_autorizacoes),
            f'{_format_decimal_pt(pct_producao_total, 2)}%',
            f'R$ {_format_decimal_pt(row_valor, 2)}',
        ]
        for idx, value in enumerate(values):
            align = WD_ALIGN_PARAGRAPH.RIGHT if idx in (3, 4, 5) else WD_ALIGN_PARAGRAPH.CENTER if idx in (0, 2) else None
            _write_cell(cells[idx], value, size=9.0, align=align)

    fonte = doc.add_paragraph()
    _format_crm_table_footnote(fonte)
    _run(
        fonte,
        "Fonte: Consulta ao CFM (https://portal.cfm.org.br/busca-medicos) e Sistema Autorizador de Vendas (SAV).",
        color="475569",
        size=10,
        italic=True,
    )

    p3 = doc.add_paragraph()
    _run(p3, f"Conforme a Tabela {tabela_num}, observa-se concentração relevante das dispensações no médico ", color="0F172A", size=12)
    _run(p3, nome_medico, color="334155", size=12, underline=True)
    _run(p3, ", CRM ", color="0F172A", size=12)
    _run(p3, crm_ident, color="334155", size=12, underline=True)
    _run(p3, f". Embora tenham sido identificados {total_medicos} médicos no período analisado, esse CRM concentrou ", color="0F172A", size=12)
    _run(p3, f"{principal_autorizacoes}", color="334155", size=12, underline=True)
    _run(p3, f" das {total_autorizacoes} autorizações verificadas, volume ", color="0F172A", size=12)
    mult_autorizacoes = _as_float(hhi_crm_comp["mult_autorizacoes"])
    mult_autorizacoes_fmt = _format_decimal_pt(mult_autorizacoes, 2)
    _run(
        p3,
        f'{mult_autorizacoes_fmt} {_vez_ou_vezes(mult_autorizacoes)} superior',
        color="334155",
        size=12,
        underline=True,
    )
    _run(
        p3,
        f" à média de {_format_decimal_pt(media_autorizacoes, 2)} autorizações por CRM.",
        color="0F172A",
        size=12,
    )

    p4 = doc.add_paragraph()
    _run(p4, "Sob o aspecto financeiro, as vendas associadas ao referido CRM somaram ", color="0F172A", size=12)
    _run(p4, f"R$ {_format_decimal_pt(principal_valor, 2)}", color="334155", size=12, underline=True)
    _run(p4, ", correspondendo a ", color="0F172A", size=12)
    _run(p4, f'{_format_decimal_pt(hhi_crm_comp["pct_valor"], 2)}%', color="334155", size=12, underline=True)
    _run(
        p4,
        f" dos R$ {_format_decimal_pt(valor_total, 2)} pagos pelo PFPB à farmácia no período e superando em ",
        color="0F172A",
        size=12,
    )
    _run(p4, f'{_format_decimal_pt(hhi_crm_comp["mult_valor"], 2)} vezes', color="334155", size=12, underline=True)
    _run(p4, f" a média de R$ {_format_decimal_pt(media_valor, 2)} por CRM. A presença simultânea de concentração em autorizações e em valores reforça o caráter atípico do padrão observado.", color="0F172A", size=12)

def _add_crms_irregulares_text(
    doc,
    num: str,
    razao_social: str,
    cnpj_fmt: str,
    irregulares_comp: dict[str, Any],
    tabela_num: int,
    bookmark_name: str | None = None,
):
    """Adiciona o subitem de vendas vinculadas a CRMs irregulares."""
    periodo_intervalo = irregulares_comp["periodo_intervalo"]
    total_autorizacoes = irregulares_comp["total_autorizacoes"]
    total_financeiro_base = irregulares_comp["total_financeiro_base"]
    qtd_invalidos = irregulares_comp["qtd_invalidos"]
    qtd_antes_registro = irregulares_comp["qtd_antes_registro"]
    valor_irregular = irregulares_comp["valor_irregular"]
    pct_irregular = irregulares_comp["pct_irregular"]
    has_detalhe_irregulares = bool(irregulares_comp["top_irregulares"])
    multiplicador_reg_fmt = _format_decimal_pt(irregulares_comp["multiplicador_regiao"], 2)
    multiplicador_uf_fmt = _format_decimal_pt(irregulares_comp["multiplicador_uf"], 2)
    multiplicador_br_fmt = _format_decimal_pt(irregulares_comp["multiplicador_brasil"], 2)
    multiplicador_reg_unidade = _vez_ou_vezes(_as_float(irregulares_comp["multiplicador_regiao"]))
    multiplicador_uf_unidade = _vez_ou_vezes(_as_float(irregulares_comp["multiplicador_uf"]))
    multiplicador_br_unidade = _vez_ou_vezes(_as_float(irregulares_comp["multiplicador_brasil"]))

    heading = doc.add_heading(f"{num} Registros de vendas de medicamentos prescritos por médicos com irregularidade em seus CRMs", level=2)
    if bookmark_name:
        _add_bookmark(heading, bookmark_name)

    p1 = doc.add_paragraph()
    _run(
        p1,
        "No âmbito do PFPB, as dispensações devem estar respaldadas por prescrições emitidas por médicos com registro ativo e regular no Conselho Regional de Medicina (CRM) ou, no caso de participantes do Programa Mais Médicos",
        color="0F172A",
        size=12,
    )
    _footnote_ref(
        doc,
        p1,
        17,
        "O Ministério da Saúde disponibiliza a relação de médicos ativos no Painel Mais Médicos - APS do Ministério da Saúde: https://www.gov.br/saude/pt-br/composicao/sgtes/mais-medicos/painel-aps.",
    )
    _run(
        p1,
        ", no Registro do Ministério da Saúde (RMS). Para este indicador, foram consideradas duas situações de irregularidade: registros de CRM ou RMS não localizados e prescrições com data anterior à primeira inscrição do médico na UF de seu registro. A ocorrência de qualquer dessas situações aponta para possível processamento de dispensações com prescrição médica incompatível com os requisitos legais do Programa.",
        color="0F172A",
        size=12,
    )

    p_auditoria = doc.add_paragraph()
    _run(
        p_auditoria,
        "ATENÇÃO: ",
        color="DC2626",
        size=12,
        bold=True,
        italic=True,
    )
    _run(
        p_auditoria,
        "Para registro médico apontado como “não localizado”, sugere-se consulta ao site do Programa Mais Médicos, informado na nota de rodapé, para tentar localizar o seu número (que consta no Programa Farmácia Popular). Em caso de sucesso, pedimos que se traga a identificação do nome do médico para a NT, tanto para as tabelas do corpo da constatação quanto para as tabelas do ANEXO I.",
        color="DC2626",
        size=12,
        italic=True,
    )

    p2 = doc.add_paragraph()
    _run(p2, f"Em relação à Farmácia {razao_social}, verificou-se que as vendas de medicamentos monitoradas por este indicador no período {periodo_intervalo} totalizaram ", color="0F172A", size=12)
    _run(p2, f"R$ {_format_decimal_pt(total_financeiro_base, 2)}", color="334155", size=12, bold=True)
    _run(p2, ". Desse valor, ", color="0F172A", size=12)
    _run(p2, f"{_format_decimal_pt(pct_irregular, 2)}%", color="334155", size=12, bold=True)
    _run(p2, " (", color="0F172A", size=12)
    _run(p2, f"R$ {_format_decimal_pt(valor_irregular, 2)}", color="334155", size=12, bold=True)
    _run(p2, ") corresponderam a vendas com receitas prescritas por médicos com CRMs irregulares ou inválidos. Tal percentual corresponde a ", color="0F172A", size=12)
    _run(p2, f"{multiplicador_reg_fmt} {multiplicador_reg_unidade}", color="334155", size=12, bold=True)
    _run(p2, " o percentual mediano de vendas com essa mesma criticidade entre as farmácias de sua região. Ampliando-se o comparativo geográfico, o percentual equivale a ", color="0F172A", size=12)
    _run(p2, f"{multiplicador_uf_fmt} {multiplicador_uf_unidade}", color="334155", size=12, bold=True)
    _run(p2, " o percentual mediano das farmácias de seu Estado e a ", color="0F172A", size=12)
    _run(p2, f"{multiplicador_br_fmt} {multiplicador_br_unidade}", color="334155", size=12, bold=True)
    _run(p2, " o das farmácias de todo o Brasil.", color="0F172A", size=12)

    if has_detalhe_irregulares:
        p_detalhe = doc.add_paragraph()
        _run(p_detalhe, "No detalhamento operacional dos prescritores, foram identificados ", color="0F172A", size=12)
        _run(p_detalhe, f"{qtd_invalidos}", color="334155", size=12, bold=True)
        _run(p_detalhe, " CRMs não localizados e ", color="0F172A", size=12)
        _run(p_detalhe, f"{qtd_antes_registro}", color="334155", size=12, bold=True)
        _run(p_detalhe, " com prescrição anterior à primeira inscrição na UF. A relação abaixo apresenta os principais registros desse detalhamento.", color="0F172A", size=12)
    else:
        return

    title = doc.add_paragraph()
    _format_crm_table_title(title)
    _run(
        title,
        f"Tabela {tabela_num} - Principais médicos com CRM irregular ou inválido no detalhamento operacional das vendas lançadas pela Farmácia {razao_social} (CNPJ {cnpj_fmt}) no Sistema Autorizador de Vendas, no período {periodo_intervalo}.",
        color="334155",
        size=8,
        bold=True,
    )

    headers = [
        "CRM/UF",
        "Nome",
        "Data da primeira inscrição na UF",
        "Irregularidade identificada",
        "Número de autorizações vinculadas ao CRM",
        "% das autorizações no detalhamento",
        "Valor total pago pelo PFPB tendo como base o CRM",
    ]
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_open_borders(table)
    widths = [Inches(0.76), Inches(1.78), Inches(0.76), Inches(1.10), Inches(0.92), Inches(0.82), Inches(1.16)]
    _set_table_fixed_widths(table, widths)

    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        _cell_bg(cell, "E2E8F0")
        _write_cell(cell, header, size=7.0, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)

    for row in irregulares_comp["top_irregulares"]:
        cells = table.add_row().cells
        crm_row, uf_row = _crm_num_uf(row.get("id_medico"))
        crm_uf = f"{crm_row}/{uf_row}" if uf_row else crm_row
        row_autorizacoes = _as_int(row.get("nu_prescricoes"))
        row_valor = _as_float(row.get("vl_total_prescricoes"))
        pct_producao_total = (row_autorizacoes / total_autorizacoes * 100) if total_autorizacoes else 0.0
        motivos = []
        if _as_int(row.get("flag_crm_invalido")) > 0:
            motivos.append("CRM não localizado")
        if _as_int(row.get("flag_prescricao_antes_registro")) > 0:
            motivos.append("Prescrição antes da primeira inscrição na UF")
        values = [
            crm_uf,
            _title_case_pt(row.get("no_medico") or "Não localizado"),
            _format_date_br(row.get("dt_inscricao_crm")),
            "; ".join(motivos) or "Irregularidade CRM",
            str(row_autorizacoes),
            f"{_format_decimal_pt(pct_producao_total, 2)}%",
            f"R$ {_format_decimal_pt(row_valor, 2)}",
        ]
        for idx, value in enumerate(values):
            align = WD_ALIGN_PARAGRAPH.RIGHT if idx in (4, 5, 6) else WD_ALIGN_PARAGRAPH.CENTER if idx in (0, 2, 3) else None
            _write_cell(cells[idx], value, size=7.0, align=align)

    fonte = doc.add_paragraph()
    _format_crm_table_footnote(fonte)
    _run(
        fonte,
        "Fonte: Consulta ao CFM (https://portal.cfm.org.br/busca-medicos) e Sistema Autorizador de Vendas (SAV).",
        color="475569",
        size=10,
        italic=True,
    )
