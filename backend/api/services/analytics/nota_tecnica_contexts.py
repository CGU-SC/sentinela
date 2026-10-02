import os
from datetime import date
from statistics import median
from typing import Any, Optional

import polars as pl

from cache_files import MOVIMENTACAO_MENSAL_GTIN_PARQUET
from data_cache import (
    get_df,
    get_df_perfil_estabelecimento,
    get_df_sentinela_metadados_base,
    get_localidades_df,
    get_medicamentos_df,
    scan_esocial_cnpj_ano,
    scan_esocial_cnpj_trabalhador_ano,
    scan_esocial_cnpj_ultima_movimentacao,
    scan_pagamentos_consolidados_farmacia_popular,
)
from ._cache import _get_cnpj_cache_dir
from .financeiro import get_evolucao_financeira, get_evolucao_mensal_gtin
from .indicator_rules import get_volume_atipico_aumento_minimo
from .nota_tecnica_formatters import (
    _format_date_pt,
    _format_date_month_year_long_pt,
    _format_month_year_long_pt,
    _format_month_year_pt,
    _format_semestre_pt,
    _semester_distance,
    _semester_key_from_date,
    _semester_key_from_label,
)
from .regional import get_metric_percentiles, get_regional_benchmarking


def _resolve_regional_context(cadastro: dict) -> dict[str, Any]:
    """Resolve id_regiao_saude a partir do id_ibge7 cadastral da farmacia."""
    id_ibge7 = cadastro.get("id_ibge7")
    if id_ibge7 in (None, "", "None"):
        raise RuntimeError("id_ibge7 e obrigatorio para resolver a Regiao de Saude da Nota Tecnica.")

    df_loc = get_localidades_df()
    required_cols = {"id_ibge7", "id_regiao_saude", "sg_uf"}
    missing_cols = required_cols - set(df_loc.columns)
    if missing_cols:
        raise RuntimeError(
            f"Cache de localidades sem colunas obrigatorias para Nota Tecnica: {', '.join(sorted(missing_cols))}."
        )

    rows = df_loc.filter(pl.col("id_ibge7").cast(pl.String) == str(id_ibge7))
    if rows.is_empty():
        raise RuntimeError(f"id_ibge7 {id_ibge7} nao encontrado no cache de localidades.")

    row = rows.row(0, named=True)
    id_regiao_saude = row.get("id_regiao_saude")
    uf = row.get("sg_uf")
    if id_regiao_saude in (None, "", "None") or not uf:
        raise RuntimeError(f"Localidade {id_ibge7} sem id_regiao_saude/UF obrigatorios para Nota Tecnica.")

    return {
        "id_regiao_saude": int(id_regiao_saude),
        "uf": str(uf),
        "nome_regiao": f"ID {id_regiao_saude}",
    }


def _build_regional_comparison_context(
    cnpj_data: dict,
    cadastro: dict,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> dict[str, Any]:
    """Calcula comparacao do percentual do CNPJ contra a mediana regional no periodo."""
    regional_context = _resolve_regional_context(cadastro)
    regional = get_regional_benchmarking(
        uf=regional_context["uf"],
        data_inicio=data_inicio,
        data_fim=data_fim,
        regiao_id=regional_context["id_regiao_saude"],
    )

    if not regional.farmacias:
        raise RuntimeError("Benchmarking regional sem farmacias para o periodo da Nota Tecnica.")

    percentual_cnpj = cnpj_data.get("percValSemComp")
    if percentual_cnpj is None:
        raise RuntimeError("percValSemComp e obrigatorio para comparacao regional da Nota Tecnica.")

    percentuais_regionais = [
        f.percValSemComp
        for f in regional.farmacias
        if f.percValSemComp is not None
    ]
    if not percentuais_regionais:
        raise RuntimeError("Percentuais regionais obrigatorios ausentes para comparacao da Nota Tecnica.")

    mediana_regional = median(percentuais_regionais)
    if mediana_regional <= 0:
        raise RuntimeError("Mediana regional deve ser maior que zero para calcular o multiplicador da Nota Tecnica.")

    municipios = [m.municipio for m in regional.municipios if m.municipio]
    if not municipios:
        raise RuntimeError("Municipios regionais obrigatorios ausentes para comparacao da Nota Tecnica.")

    uf_comp = _build_scope_percentual_comparison(cnpj_data, data_inicio, data_fim, uf=regional_context["uf"])
    br_comp = _build_scope_percentual_comparison(cnpj_data, data_inicio, data_fim)

    return {
        **regional_context,
        "multiplicador": float(percentual_cnpj) / mediana_regional,
        "mediana_regional": mediana_regional,
        "qtd_farmacias": len(regional.farmacias),
        "municipios": municipios,
        "multiplicador_uf": uf_comp["multiplicador"],
        "mediana_uf": uf_comp["mediana"],
        "multiplicador_brasil": br_comp["multiplicador"],
        "mediana_brasil": br_comp["mediana"],
    }


def _build_posicionamento_regional_context(
    cnpj: str,
    cadastro: dict,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> dict[str, Any]:
    """Monta o contexto do scatter de posicionamento regional da Nota Tecnica."""
    regional_context = _resolve_regional_context(cadastro)
    regional = get_regional_benchmarking(
        uf=regional_context["uf"],
        data_inicio=data_inicio,
        data_fim=data_fim,
        regiao_id=regional_context["id_regiao_saude"],
    )

    if not regional.farmacias:
        raise RuntimeError("Benchmarking regional sem farmacias para Figura de Posicionamento Regional.")

    cnpj_norm = "".join(ch for ch in (cnpj) if ch.isdigit())
    rows: list[dict[str, Any]] = []
    current_row: dict[str, Any] | None = None
    for farmacia in regional.farmacias:
        farmacia_cnpj = "".join(ch for ch in (farmacia.cnpj or "") if ch.isdigit())
        row = {
            "cnpj": farmacia_cnpj,
            "razao_social": farmacia.razao_social or "",
            "municipio": farmacia.municipio or "",
            "total_mov": (farmacia.totalMov or 0.0),
            "pct_sem_comprovacao": min((farmacia.percValSemComp or 0.0), 100.0),
            "score_risco": (farmacia.score_risco or 0.0),
            "is_current": farmacia_cnpj == cnpj_norm,
        }
        rows.append(row)
        if row["is_current"]:
            current_row = row

    if current_row is None:
        raise RuntimeError("CNPJ analisado nao encontrado no benchmarking regional da Nota Tecnica.")

    return {
        **regional_context,
        "rows": rows,
        "current": current_row,
        "metric_label": "% de dispensações sem comprovação",
    }


def _build_percentil_risco_context(
    cnpj_data: dict,
    cadastro: dict,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> dict[str, Any]:
    """Monta a curva de percentis do percentual de vendas sem comprovacao na regiao."""
    regional_context = _resolve_regional_context(cadastro)
    percentiles = get_metric_percentiles(
        scope="regiao",
        uf=regional_context["uf"],
        regiao_id=str(regional_context["id_regiao_saude"]),
        metric="percentual_sem_comprovacao",
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    if not percentiles:
        raise RuntimeError("Percentis regionais indisponiveis para Figura de Percentil de Risco.")

    valor_cnpj = min(float(cnpj_data.get("percValSemComp") or 0.0), 100.0)
    percentile_rank = 100
    for point in percentiles:
        if float(point.get("score") or 0.0) >= valor_cnpj:
            percentile_rank = int(point.get("percentile") or 100)
            break

    return {
        **regional_context,
        "scope": "regiao",
        "metric": "percentual_sem_comprovacao",
        "metric_label": "% de vendas sem comprovação",
        "current_value": valor_cnpj,
        "percentile_rank": percentile_rank,
        "percentiles": percentiles,
    }


def _build_scope_percentual_comparison(
    cnpj_data: dict,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    *,
    uf: Optional[str] = None,
) -> dict[str, float]:
    """Calcula mediana de percentual sem comprovacao para UF ou Brasil no periodo."""
    percentual_cnpj = cnpj_data.get("percValSemComp")
    if percentual_cnpj is None:
        raise RuntimeError("percValSemComp e obrigatorio para comparacao geografica da Nota Tecnica.")

    df = get_df().join(get_df_perfil_estabelecimento(), on="id_cnpj", how="left")
    min_data = date(2015, 7, 1)
    max_data = date(2024, 12, 31)
    inicio = (data_inicio if data_inicio and data_inicio >= min_data else min_data) if data_inicio else min_data
    fim = data_fim if data_fim else max_data

    mask = pl.col("periodo").is_between(inicio, fim)
    if uf:
        mask = mask & (pl.col("uf") == uf)

    scoped = df.filter(mask)
    if scoped.is_empty():
        label = f"UF {uf}" if uf else "Brasil"
        raise RuntimeError(f"Sem movimentacao para calcular mediana de {label} da Nota Tecnica.")

    cnpj_agg = (
        scoped
        .group_by("id_cnpj")
        .agg([
            pl.sum("total_vendas").alias("totalMov"),
            pl.sum("total_sem_comprovacao").alias("valSemComp"),
        ])
        .with_columns(
            (
                pl.col("valSemComp") /
                pl.when(pl.col("totalMov") > 0)
                .then(pl.col("totalMov"))
                .otherwise(None) * 100
            ).alias("percValSemComp")
        )
        .filter(pl.col("percValSemComp").is_not_null())
    )
    if cnpj_agg.is_empty():
        label = f"UF {uf}" if uf else "Brasil"
        raise RuntimeError(f"Percentuais ausentes para calcular mediana de {label} da Nota Tecnica.")

    mediana_raw = cnpj_agg.get_column("percValSemComp").median()
    mediana = float(mediana_raw if isinstance(mediana_raw, (int, float)) else 0.0)
    if mediana <= 0:
        label = f"UF {uf}" if uf else "Brasil"
        raise RuntimeError(f"Mediana de {label} deve ser maior que zero para calcular o multiplicador da Nota Tecnica.")

    return {
        "mediana": mediana,
        "multiplicador": float(percentual_cnpj) / mediana,
    }


def _normalize_gtin(value: Any) -> str:
    """Normaliza GTIN/codigo de barras preservando zeros quando vier como texto."""
    text = str(value).strip()
    return text.split(".")[0] if "." in text else text


def _build_medicamentos_lookup() -> dict[str, dict[str, str | None]]:
    """Monta lookup GTIN -> descricao e patologia do medicamento."""
    df_med = get_medicamentos_df()
    required_cols = {"codigo_barra", "patologia"}
    missing_cols = required_cols - set(df_med.columns)
    if missing_cols:
        raise RuntimeError(
            f"Cache de medicamentos sem colunas obrigatorias para Nota Tecnica: {', '.join(sorted(missing_cols))}."
        )

    lookup: dict[str, dict[str, str | None]] = {}
    for row in df_med.iter_rows(named=True):
        codigo = row.get("codigo_barra")
        if codigo in (None, "", "None"):
            continue
        descricao = row.get("principio_ativo") or row.get("produto") or row.get("descricao")
        if descricao in (None, "", "None"):
            continue
        gtin = _normalize_gtin(codigo)
        patologia = row.get("patologia")
        lookup[gtin] = {
            "descricao": str(descricao),
            "patologia": (
                str(patologia).strip()
                if patologia not in (None, "", "None")
                else None
            ),
        }

    if not lookup:
        raise RuntimeError("Cache de medicamentos sem descricoes validas para Nota Tecnica.")
    return lookup


def _build_gtin_sem_comprovacao_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    concentration_target: float = 0.80,
) -> dict[str, Any]:
    """Agrega todos os GTINs com valor sem comprovacao no periodo e calcula concentracao."""
    get_evolucao_mensal_gtin(cnpj, data_inicio, data_fim)

    parquet_path = os.path.join(_get_cnpj_cache_dir(cnpj), MOVIMENTACAO_MENSAL_GTIN_PARQUET)
    if not os.path.exists(parquet_path):
        raise RuntimeError(f"Parquet mensal por GTIN obrigatorio nao encontrado para Nota Tecnica: {parquet_path}.")

    df = pl.read_parquet(parquet_path)
    required_cols = {
        "codigo_barra",
        "periodo",
        "qnt_caixas_sem_comprovacao",
        "valor_vendas",
        "valor_sem_comprovacao",
    }
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise RuntimeError(
            f"Parquet mensal por GTIN sem colunas obrigatorias para Nota Tecnica: {', '.join(sorted(missing_cols))}."
        )

    df = df.with_columns([
        pl.col("codigo_barra").cast(pl.String),
        pl.col("periodo").cast(pl.Date),
        pl.col("qnt_caixas_sem_comprovacao").cast(pl.Int64, strict=False).fill_null(0),
        pl.col("valor_vendas").cast(pl.Float64, strict=False).fill_null(0.0),
        pl.col("valor_sem_comprovacao").cast(pl.Float64, strict=False).fill_null(0.0),
    ])
    if data_inicio:
        df = df.filter(pl.col("periodo") >= pl.lit(data_inicio).cast(pl.Date))
    if data_fim:
        df = df.filter(pl.col("periodo") <= pl.lit(data_fim).cast(pl.Date))

    if df.is_empty():
        raise RuntimeError("Movimentacao mensal por GTIN vazia no periodo da Nota Tecnica.")

    agg = (
        df.group_by("codigo_barra")
        .agg([
            pl.sum("qnt_caixas_sem_comprovacao").alias("qtd_sem_comprovacao"),
            pl.sum("valor_vendas").alias("valor_vendas"),
            pl.sum("valor_sem_comprovacao").alias("valor_sem_comprovacao"),
        ])
        .filter(pl.col("valor_sem_comprovacao") > 0)
        .sort("valor_sem_comprovacao", descending=True)
    )
    if agg.is_empty():
        raise RuntimeError("Nenhum GTIN com valor sem comprovacao encontrado no periodo da Nota Tecnica.")

    medicamentos_lookup = _build_medicamentos_lookup()
    rows: list[dict[str, Any]] = []
    missing_descriptions: list[str] = []
    for r in agg.iter_rows(named=True):
        gtin = _normalize_gtin(r["codigo_barra"])
        medicamento = medicamentos_lookup.get(gtin)
        if not medicamento:
            missing_descriptions.append(gtin)
            continue
        patologia = medicamento["patologia"]
        if patologia is None:
            raise RuntimeError(
                f"Patologia obrigatoria ausente para o GTIN {gtin} exibido na Tabela 1 da Nota Tecnica."
            )
        rows.append({
            "gtin": gtin,
            "descricao": medicamento["descricao"],
            "patologia": patologia,
            "qtd_sem_comprovacao": int(r["qtd_sem_comprovacao"] or 0),
            "valor_vendas": round(float(r["valor_vendas"] or 0.0), 2),
            "valor_sem_comprovacao": round(float(r["valor_sem_comprovacao"] or 0.0), 2),
            "pct_sem_comprovacao": round(
                (float(r["valor_sem_comprovacao"] or 0.0) / float(r["valor_vendas"] or 0.0) * 100)
                if float(r["valor_vendas"] or 0.0) > 0
                else 0.0,
                2,
            ),
        })

    if missing_descriptions:
        preview = ", ".join(missing_descriptions[:10])
        raise RuntimeError(f"Descricao obrigatoria ausente para GTIN(s) da Nota Tecnica: {preview}.")

    total_valor = round(sum(r["valor_sem_comprovacao"] for r in rows), 2)
    total_vendas = round(sum(r["valor_vendas"] for r in rows), 2)
    total_pct_sem_comprovacao = (total_valor / total_vendas * 100) if total_vendas > 0 else 0.0
    total_qtd = sum(r["qtd_sem_comprovacao"] for r in rows)
    target_value = total_valor * concentration_target
    acumulado = 0.0
    representativos_count = 0
    for row in rows:
        if acumulado >= target_value and representativos_count > 0:
            break
        acumulado += row["valor_sem_comprovacao"]
        representativos_count += 1

    representativos_valor = round(acumulado, 2)
    representativos_pct = (representativos_valor / total_valor * 100) if total_valor > 0 else 0.0

    return {
        "rows": rows,
        "total_gtins": len(rows),
        "total_qtd": total_qtd,
        "total_valor": total_valor,
        "total_vendas": total_vendas,
        "total_pct_sem_comprovacao": total_pct_sem_comprovacao,
        "representativos_count": representativos_count,
        "representativos_valor": representativos_valor,
        "representativos_pct": representativos_pct,
        "concentration_target_pct": concentration_target * 100,
    }


def _model_to_dict(model: Any) -> dict[str, Any]:
    """Converte modelos Pydantic ou dicts em dicionario simples."""
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    raise TypeError(f"Objeto semestral inesperado para Nota Tecnica: {type(model)!r}.")


def _semestre_fmt_from_key(chave_semestre: int) -> str:
    ano = (chave_semestre) // 100
    semestre = (chave_semestre) % 100
    return _format_semestre_pt(f"{semestre}S/{ano}")


def _build_medicamentos_aumento_atipico_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    semestres_atipicos: list[dict[str, Any]],
    max_por_semestre: Optional[int] = None,
    participacao_minima_pct: float = 0.1,
) -> list[dict[str, Any]]:
    """Lista GTINs que mais contribuiram para os aumentos positivos em semestres atipicos."""
    if not semestres_atipicos:
        return []

    get_evolucao_mensal_gtin(cnpj, data_inicio, data_fim)

    parquet_path = os.path.join(_get_cnpj_cache_dir(cnpj), MOVIMENTACAO_MENSAL_GTIN_PARQUET)
    if not os.path.exists(parquet_path):
        return []

    df = pl.read_parquet(parquet_path)
    required_cols = {
        "codigo_barra",
        "periodo",
        "valor_vendas",
        "valor_sem_comprovacao",
    }
    if required_cols - set(df.columns):
        return []

    df = df.with_columns([
        pl.col("codigo_barra").cast(pl.String),
        pl.col("periodo").cast(pl.Date),
        pl.col("valor_vendas").cast(pl.Float64, strict=False).fill_null(0.0),
        pl.col("valor_sem_comprovacao").cast(pl.Float64, strict=False).fill_null(0.0),
    ])
    if data_inicio:
        df = df.filter(pl.col("periodo") >= pl.lit(data_inicio).cast(pl.Date))
    if data_fim:
        df = df.filter(pl.col("periodo") <= pl.lit(data_fim).cast(pl.Date))
    if df.is_empty():
        return []

    df = df.with_columns([
        (
            pl.col("periodo").dt.year() * 100
            + pl.when(pl.col("periodo").dt.month() <= 6).then(pl.lit(1)).otherwise(pl.lit(2))
        ).alias("chave_semestre")
    ])

    chaves: set[int] = set()
    for semestre in semestres_atipicos:
        chave = semestre.get("chave_semestre")
        chave_anterior = semestre.get("chave_semestre_anterior")
        if chave is not None:
            chaves.add(int(chave))
        if chave_anterior is not None:
            chaves.add(int(chave_anterior))
    if not chaves:
        return []

    agg = (
        df.filter(pl.col("chave_semestre").is_in(sorted(chaves)))
        .group_by(["chave_semestre", "codigo_barra"])
        .agg([
            pl.sum("valor_vendas").alias("valor_vendas"),
            pl.sum("valor_sem_comprovacao").alias("valor_sem_comprovacao"),
        ])
    )
    if agg.is_empty():
        return []

    valores: dict[tuple[int, str], dict[str, float]] = {}
    for row in agg.iter_rows(named=True):
        gtin = _normalize_gtin(row["codigo_barra"])
        valores[(int(row["chave_semestre"]), gtin)] = {
            "valor_vendas": float(row["valor_vendas"] or 0.0),
            "valor_sem_comprovacao": float(row["valor_sem_comprovacao"] or 0.0),
        }

    medicamentos_lookup = _build_medicamentos_lookup()
    resultado: list[dict[str, Any]] = []

    for semestre in semestres_atipicos:
        chave = semestre.get("chave_semestre")
        chave_anterior = semestre.get("chave_semestre_anterior")
        if chave is None or chave_anterior is None:
            continue

        chave = int(chave)
        chave_anterior = int(chave_anterior)
        gtins = {
            gtin
            for key, gtin in valores
            if key in {chave, chave_anterior}
        }

        candidatos: list[dict[str, Any]] = []
        for gtin in gtins:
            atual = valores.get((chave, gtin), {})
            anterior = valores.get((chave_anterior, gtin), {})
            valor_atual = (atual.get("valor_vendas") or 0.0)
            valor_anterior = (anterior.get("valor_vendas") or 0.0)
            aumento = valor_atual - valor_anterior
            if aumento <= 0:
                continue
            medicamento = medicamentos_lookup.get(gtin)
            if medicamento is None:
                raise RuntimeError(
                    f"Descricao obrigatoria ausente para o GTIN {gtin} na tabela de aumento atipico da Nota Tecnica."
                )
            candidatos.append({
                "semestre": semestre.get("semestre"),
                "semestre_fmt": semestre.get("semestre_fmt") or _semestre_fmt_from_key(chave),
                "semestre_anterior_fmt": _semestre_fmt_from_key(chave_anterior),
                "gtin": gtin,
                "descricao": medicamento["descricao"],
                "valor_anterior": round(valor_anterior, 2),
                "valor_atual": round(valor_atual, 2),
                "aumento_valor": round(aumento, 2),
                "aumento_relativo_pct": round(aumento / valor_anterior * 100, 1) if valor_anterior > 1.0 else None,
                "valor_sem_comprovacao": round((atual.get("valor_sem_comprovacao") or 0.0), 2),
            })

        if not candidatos:
            continue

        total_aumentos_positivos = sum(item["aumento_valor"] for item in candidatos)
        candidatos_ordenados = sorted(candidatos, key=lambda row: row["aumento_valor"], reverse=True)
        if max_por_semestre is not None:
            candidatos_ordenados = candidatos_ordenados[:max_por_semestre]

        demais = {
            "qtd_gtins": 0,
            "valor_anterior": 0.0,
            "valor_atual": 0.0,
            "aumento_valor": 0.0,
            "valor_sem_comprovacao": 0.0,
        }

        for item in candidatos_ordenados:
            participacao_aumento_pct = (
                round(item["aumento_valor"] / total_aumentos_positivos * 100, 1)
                if total_aumentos_positivos > 0
                else 0.0
            )
            if participacao_aumento_pct <= participacao_minima_pct:
                demais["qtd_gtins"] += 1
                demais["valor_anterior"] += item["valor_anterior"]
                demais["valor_atual"] += item["valor_atual"]
                demais["aumento_valor"] += item["aumento_valor"]
                demais["valor_sem_comprovacao"] += item["valor_sem_comprovacao"]
                continue
            item["participacao_aumento_pct"] = participacao_aumento_pct
            resultado.append(item)

        if demais["aumento_valor"] > 0:
            gtins_txt = "GTIN" if demais["qtd_gtins"] == 1 else "GTINs"
            resultado.append({
                "semestre": semestre.get("semestre"),
                "semestre_fmt": semestre.get("semestre_fmt") or _semestre_fmt_from_key(chave),
                "semestre_anterior_fmt": _semestre_fmt_from_key(chave_anterior),
                "gtin": f'{(demais["qtd_gtins"])} {gtins_txt}',
                "descricao": "GTINs com participacao individual menor ou igual a 0,1%",
                "valor_anterior": round(demais["valor_anterior"], 2),
                "valor_atual": round(demais["valor_atual"], 2),
                "aumento_valor": round(demais["aumento_valor"], 2),
                "aumento_relativo_pct": (
                    round(demais["aumento_valor"] / demais["valor_anterior"] * 100, 1)
                    if demais["valor_anterior"] > 1.0
                    else None
                ),
                "valor_sem_comprovacao": round(demais["valor_sem_comprovacao"], 2),
                "participacao_aumento_pct": (
                    round(demais["aumento_valor"] / total_aumentos_positivos * 100, 1)
                    if total_aumentos_positivos > 0
                    else 0.0
                ),
                "is_demais": True,
            })

    return resultado


def _format_competencia_esocial(value: Any) -> str:
    if value in (None, "", "None"):
        return "—"
    try:
        competencia = int(value)
    except (TypeError, ValueError):
        return str(value)
    ano = competencia // 100
    mes = competencia % 100
    if ano <= 0 or not 1 <= mes <= 12:
        return str(value)
    return f"{mes:02d}/{ano:04d}"


def _format_cbo_label(cbo: Any, titulo: Any) -> str:
    titulo_txt = str(titulo or "").strip()
    try:
        cbo_int = int(cbo) if cbo is not None else None
    except (TypeError, ValueError):
        cbo_int = None
    if cbo_int is None:
        return "CBO não informado"
    if titulo_txt:
        return f"{titulo_txt} (CBO {cbo_int:06d})"
    return f"CBO {cbo_int:06d} sem título válido"


def _format_date_iso(value: Any) -> str:
    if value in (None, "", "None"):
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_esocial_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> dict[str, Any]:
    """Monta o contexto trabalhista anual do eSocial para a Nota Tecnica."""
    cnpj_norm = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    if len(cnpj_norm) != 14:
        raise RuntimeError("CNPJ invalido para montar contexto eSocial da Nota Tecnica.")

    perfil = get_df_perfil_estabelecimento()
    perfil_required = {"id_cnpj", "cnpj"}
    missing_perfil = perfil_required - set(perfil.columns)
    if missing_perfil:
        raise RuntimeError(
            "Cache de perfil_estabelecimento sem colunas obrigatorias para contexto eSocial: "
            + ", ".join(sorted(missing_perfil))
        )

    perfil_rows = perfil.filter(pl.col("cnpj").cast(pl.String).str.replace_all(r"\D", "") == cnpj_norm)
    if perfil_rows.is_empty():
        raise RuntimeError(f"CNPJ {cnpj_norm} nao encontrado no cache de perfil_estabelecimento para contexto eSocial.")
    id_cnpj = int(perfil_rows.row(0, named=True)["id_cnpj"])

    df_ano = scan_esocial_cnpj_ano().filter(pl.col("id_cnpj") == id_cnpj).collect()
    df_trabalhador = (
        scan_esocial_cnpj_trabalhador_ano()
        .filter(pl.col("id_cnpj") == id_cnpj)
        .collect()
    )
    df_ultima_movimentacao = (
        scan_esocial_cnpj_ultima_movimentacao()
        .filter(pl.col("id_cnpj") == id_cnpj)
        .collect()
    )
    df_metadados = get_df_sentinela_metadados_base()
    ano_required = {
        "id_cnpj",
        "ano_base",
        "competencia_base",
        "qtd_trabalhadores",
        "qtd_farmaceuticos",
        "qtd_registros_vinculo_ano",
        "qtd_trabalhadores_vinculo_ano",
        "qtd_farmaceuticos_vinculo_ano",
        "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano",
        "has_cbo_sem_titulo",
        "is_um_trabalhador",
        "is_um_trabalhador_sem_farmaceutico",
        "is_um_trabalhador_cbo_sem_titulo",
        "cbo_unico_trabalhador",
        "titulo_cbo_unico_trabalhador",
        "dt_carga_fonte",
    }
    trabalhador_required = {
        "id_cnpj",
        "ano_base",
        "cpf_trabalhador",
        "cbo",
        "titulo_cbo",
        "dt_admissao",
        "dt_rescisao",
        "is_cbo_sem_titulo",
    }
    metadados_required = {
        "nome_base",
        "nome_artefato",
        "dt_referencia_max",
    }
    ultima_movimentacao_required = {
        "id_cnpj",
        "ano_ultima_movimentacao",
        "ano_esocial_referencia_ultima_movimentacao",
        "is_sem_esocial_no_ano_ultima_movimentacao",
        "ultimo_periodo_movimentacao",
        "dt_referencia_ultima_movimentacao",
        "valor_pfpb_ultimo_mes",
        "qtd_autorizacoes_ultimo_mes",
        "qtd_trabalhadores_ativos_ultima_movimentacao",
        "qtd_farmaceuticos_ativos_ultima_movimentacao",
        "dt_ultima_rescisao_antes_ultima_movimentacao",
        "dt_ultimo_trabalhador_ativo",
        "ultimo_mes_trabalhador_ativo",
        "dt_inicio_periodo_sem_funcionario",
        "qtd_dias_sem_funcionario_ate_ultima_movimentacao",
        "valor_pfpb_periodo_sem_funcionario",
        "qtd_autorizacoes_periodo_sem_funcionario",
        "has_movimentacao_sem_funcionario_ativo",
    }
    missing_ano = ano_required - set(df_ano.columns)
    missing_trabalhador = trabalhador_required - set(df_trabalhador.columns)
    missing_metadados = metadados_required - set(df_metadados.columns)
    missing_ultima_movimentacao = ultima_movimentacao_required - set(df_ultima_movimentacao.columns)
    if missing_ano:
        raise RuntimeError("Cache eSocial CNPJ/ano sem colunas obrigatorias: " + ", ".join(sorted(missing_ano)))
    if missing_trabalhador:
        raise RuntimeError("Cache eSocial trabalhador/ano sem colunas obrigatorias: " + ", ".join(sorted(missing_trabalhador)))
    if missing_metadados:
        raise RuntimeError("Cache de metadados das bases sem colunas obrigatorias: " + ", ".join(sorted(missing_metadados)))
    if missing_ultima_movimentacao:
        raise RuntimeError(
            "Cache eSocial ultima movimentacao sem colunas obrigatorias: "
            + ", ".join(sorted(missing_ultima_movimentacao))
        )

    metadados_esocial = df_metadados.filter(
        (pl.col("nome_base") == "esocial")
        & (pl.col("nome_artefato") == "esocial_cnpj_ano")
    )
    if metadados_esocial.is_empty():
        raise RuntimeError("Cache de metadados sem registro para esocial_cnpj_ano.")
    dt_carga_base = metadados_esocial.select(pl.col("dt_referencia_max").max()).item()
    if dt_carga_base is None:
        raise RuntimeError("Metadado esocial_cnpj_ano sem dt_referencia_max.")
    dt_carga_base_txt = _format_date_month_year_long_pt(dt_carga_base)

    anos = df_ano
    trabalhadores = df_trabalhador
    ultima_movimentacao = df_ultima_movimentacao

    if data_inicio or data_fim:
        ano_inicio = data_inicio.year if data_inicio else int(anos.select(pl.col("ano_base").min()).item() or 0)
        ano_fim = data_fim.year if data_fim else int(anos.select(pl.col("ano_base").max()).item() or 9999)
        anos = anos.filter(pl.col("ano_base").is_between(ano_inicio, ano_fim))
        trabalhadores = trabalhadores.filter(pl.col("ano_base").is_between(ano_inicio, ano_fim))
        ultima_movimentacao = ultima_movimentacao.filter(
            pl.col("ano_ultima_movimentacao").is_between(ano_inicio, ano_fim)
        )

    if anos.is_empty():
        return {
            "id_cnpj": id_cnpj,
            "has_data": False,
            "rows": [],
            "periodo_anos_txt": "",
            "dt_carga_fonte": dt_carga_base,
            "dt_carga_fonte_txt": dt_carga_base_txt,
            "anos_sem_farmaceutico": [],
            "anos_um_trabalhador": [],
            "trabalhador_detalhe_rows": [],
            "trabalhador_detalhe_total_cpfs": 0,
            "trabalhador_detalhe_modo": "sem_dados",
            "movimentacao_sem_funcionario_alerta": None,
        }

    trabalhador_rows_by_year: dict[int, list[dict[str, Any]]] = {}
    for row in trabalhadores.sort(["ano_base", "cpf_trabalhador"]).to_dicts():
        trabalhador_rows_by_year.setdefault(int(row["ano_base"]), []).append(row)

    rows: list[dict[str, Any]] = []
    for row in anos.sort("ano_base").to_dicts():
        ano_base = int(row["ano_base"])
        qtd_trabalhadores = int(row.get("qtd_trabalhadores") or 0)
        qtd_farmaceuticos = int(row.get("qtd_farmaceuticos") or 0)
        qtd_registros_vinculo_ano = int(row.get("qtd_registros_vinculo_ano") or 0)
        qtd_trabalhadores_vinculo_ano = int(row.get("qtd_trabalhadores_vinculo_ano") or 0)
        qtd_farmaceuticos_vinculo_ano = int(row.get("qtd_farmaceuticos_vinculo_ano") or 0)
        qtd_trabalhadores_cbo_sem_titulo_vinculo_ano = int(
            row.get("qtd_trabalhadores_cbo_sem_titulo_vinculo_ano") or 0
        )
        trabalhador_unico = None
        if bool(row.get("is_um_trabalhador")):
            candidatos = trabalhador_rows_by_year.get(ano_base) or []
            trabalhador_unico = candidatos[0] if candidatos else None
        cbo_unico = (
            _format_cbo_label(trabalhador_unico.get("cbo"), trabalhador_unico.get("titulo_cbo"))
            if trabalhador_unico
            else (
                _format_cbo_label(row.get("cbo_unico_trabalhador"), row.get("titulo_cbo_unico_trabalhador"))
                if row.get("is_um_trabalhador")
                else "Não se aplica"
            )
        )
        dt_admissao = trabalhador_unico.get("dt_admissao") if trabalhador_unico else None
        rows.append({
            "ano_base": ano_base,
            "competencia_base": row.get("competencia_base"),
            "competencia_txt": _format_competencia_esocial(row.get("competencia_base")),
            "qtd_trabalhadores": qtd_trabalhadores,
            "qtd_farmaceuticos": qtd_farmaceuticos,
            "qtd_trabalhadores_ativos_competencia": qtd_trabalhadores,
            "qtd_farmaceuticos_ativos_competencia": qtd_farmaceuticos,
            "qtd_registros_vinculo_ano": qtd_registros_vinculo_ano,
            "qtd_trabalhadores_vinculo_ano": qtd_trabalhadores_vinculo_ano,
            "qtd_farmaceuticos_vinculo_ano": qtd_farmaceuticos_vinculo_ano,
            "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano": qtd_trabalhadores_cbo_sem_titulo_vinculo_ano,
            "has_cbo_sem_titulo": bool(row.get("has_cbo_sem_titulo")),
            "is_um_trabalhador": bool(row.get("is_um_trabalhador")),
            "is_um_trabalhador_sem_farmaceutico": bool(row.get("is_um_trabalhador_sem_farmaceutico")),
            "is_um_trabalhador_cbo_sem_titulo": bool(row.get("is_um_trabalhador_cbo_sem_titulo")),
            "cbo_unico_trabalhador": row.get("cbo_unico_trabalhador"),
            "titulo_cbo_unico_trabalhador": row.get("titulo_cbo_unico_trabalhador"),
            "trabalhador_unico_cbo_txt": cbo_unico,
            "trabalhador_unico_dt_admissao": dt_admissao,
            "trabalhador_unico_dt_admissao_txt": _format_date_month_year_long_pt(dt_admissao) if dt_admissao else "—",
            "dt_carga_fonte": row.get("dt_carga_fonte"),
        })

    anos_lista = [row["ano_base"] for row in rows]
    anos_sem_farmaceutico = [
        row for row in rows
        if row["qtd_trabalhadores_vinculo_ano"] > 0 and row["qtd_farmaceuticos_vinculo_ano"] == 0
    ]
    anos_um_trabalhador = [row for row in rows if row["is_um_trabalhador"]]
    anos_criticos = [
        row["ano_base"] for row in rows
        if row["qtd_trabalhadores_vinculo_ano"] > 0
        and (
            row["qtd_farmaceuticos_vinculo_ano"] == 0
            or row["qtd_farmaceuticos_ativos_competencia"] == 0
            or row["has_cbo_sem_titulo"]
            or row["qtd_trabalhadores_cbo_sem_titulo_vinculo_ano"] > 0
            or row["is_um_trabalhador_sem_farmaceutico"]
            or row["is_um_trabalhador_cbo_sem_titulo"]
        )
    ]
    total_cpfs_periodo = int(trabalhadores.select(pl.col("cpf_trabalhador").n_unique()).item() or 0)
    if total_cpfs_periodo <= 15:
        trabalhadores_detalhe = trabalhadores
        detalhe_modo = "lista_completa"
    elif anos_criticos:
        trabalhadores_detalhe = trabalhadores.filter(pl.col("ano_base").is_in(anos_criticos))
        detalhe_modo = "anos_criticos"
    else:
        trabalhadores_detalhe = trabalhadores.head(0)
        detalhe_modo = "omitido"

    trabalhador_detalhe_rows = []
    for row in trabalhadores_detalhe.sort(["ano_base", "cpf_trabalhador", "cbo"]).to_dicts():
        trabalhador_detalhe_rows.append({
            "ano_base": int(row.get("ano_base") or 0),
            "cpf_trabalhador": str(row.get("cpf_trabalhador") or ""),
            "cbo": int(row["cbo"]) if row.get("cbo") is not None else None,
            "titulo_cbo": str(row.get("titulo_cbo") or "").strip() or "—",
            "dt_admissao_txt": _format_date_pt(row.get("dt_admissao")),
            "dt_rescisao_txt": _format_date_pt(row.get("dt_rescisao")),
        })

    movimentacao_sem_funcionario_alerta = None
    movimentacao_alerta = ultima_movimentacao.filter(pl.col("has_movimentacao_sem_funcionario_ativo") == True)
    if not movimentacao_alerta.is_empty():
        alert_row = (
            movimentacao_alerta
            .sort("ultimo_periodo_movimentacao", descending=True)
            .row(0, named=True)
        )
        campos_alerta_obrigatorios = {
            "ultimo_periodo_movimentacao",
            "dt_referencia_ultima_movimentacao",
            "valor_pfpb_ultimo_mes",
            "qtd_autorizacoes_ultimo_mes",
            "qtd_trabalhadores_ativos_ultima_movimentacao",
            "qtd_farmaceuticos_ativos_ultima_movimentacao",
            "ultimo_mes_trabalhador_ativo",
            "dt_inicio_periodo_sem_funcionario",
            "qtd_dias_sem_funcionario_ate_ultima_movimentacao",
            "valor_pfpb_periodo_sem_funcionario",
            "qtd_autorizacoes_periodo_sem_funcionario",
        }
        missing_alerta = [
            campo for campo in campos_alerta_obrigatorios
            if alert_row.get(campo) is None
        ]
        if missing_alerta:
            raise RuntimeError(
                "Alerta de movimentacao sem funcionario ativo sem campos obrigatorios: "
                + ", ".join(sorted(missing_alerta))
            )
        ultimo_periodo = alert_row["ultimo_periodo_movimentacao"]
        movimentacao_sem_funcionario_alerta = {
            "ano_ultima_movimentacao": int(alert_row.get("ano_ultima_movimentacao") or 0),
            "ano_esocial_referencia_ultima_movimentacao": int(
                alert_row.get("ano_esocial_referencia_ultima_movimentacao") or 0
            ),
            "is_sem_esocial_no_ano_ultima_movimentacao": bool(
                alert_row.get("is_sem_esocial_no_ano_ultima_movimentacao")
            ),
            "ultimo_periodo_movimentacao": ultimo_periodo,
            "ultimo_periodo_movimentacao_txt": (
                _format_date_month_year_long_pt(ultimo_periodo)
                if hasattr(ultimo_periodo, "year")
                else str(ultimo_periodo)
            ),
            "dt_referencia_ultima_movimentacao": alert_row.get("dt_referencia_ultima_movimentacao"),
            "dt_referencia_ultima_movimentacao_txt": _format_date_iso(
                alert_row.get("dt_referencia_ultima_movimentacao")
            ),
            "valor_pfpb_ultimo_mes": float(alert_row.get("valor_pfpb_ultimo_mes") or 0.0),
            "qtd_autorizacoes_ultimo_mes": int(alert_row.get("qtd_autorizacoes_ultimo_mes") or 0),
            "qtd_trabalhadores_ativos_ultima_movimentacao": int(
                alert_row.get("qtd_trabalhadores_ativos_ultima_movimentacao") or 0
            ),
            "qtd_farmaceuticos_ativos_ultima_movimentacao": int(
                alert_row.get("qtd_farmaceuticos_ativos_ultima_movimentacao") or 0
            ),
            "dt_ultima_rescisao_antes_ultima_movimentacao": alert_row.get(
                "dt_ultima_rescisao_antes_ultima_movimentacao"
            ),
            "dt_ultima_rescisao_antes_ultima_movimentacao_txt": _format_date_iso(
                alert_row.get("dt_ultima_rescisao_antes_ultima_movimentacao")
            ),
            "dt_ultimo_trabalhador_ativo": alert_row.get("dt_ultimo_trabalhador_ativo"),
            "dt_ultimo_trabalhador_ativo_txt": _format_date_iso(
                alert_row.get("dt_ultimo_trabalhador_ativo")
            ),
            "ultimo_mes_trabalhador_ativo": alert_row.get("ultimo_mes_trabalhador_ativo"),
            "ultimo_mes_trabalhador_ativo_txt": (
                _format_date_month_year_long_pt(alert_row.get("ultimo_mes_trabalhador_ativo"))  # type: ignore
                if isinstance(alert_row.get("ultimo_mes_trabalhador_ativo"), date)
                else str(alert_row.get("ultimo_mes_trabalhador_ativo") or "")
            ),
            "dt_inicio_periodo_sem_funcionario": alert_row.get("dt_inicio_periodo_sem_funcionario"),
            "dt_inicio_periodo_sem_funcionario_txt": _format_date_iso(
                alert_row.get("dt_inicio_periodo_sem_funcionario")
            ),
            "qtd_dias_sem_funcionario_ate_ultima_movimentacao": int(
                alert_row.get("qtd_dias_sem_funcionario_ate_ultima_movimentacao") or 0
            ),
            "valor_pfpb_periodo_sem_funcionario": float(
                alert_row.get("valor_pfpb_periodo_sem_funcionario") or 0.0
            ),
            "qtd_autorizacoes_periodo_sem_funcionario": int(
                alert_row.get("qtd_autorizacoes_periodo_sem_funcionario") or 0
            ),
        }

    return {
        "id_cnpj": id_cnpj,
        "has_data": True,
        "rows": rows,
        "periodo_anos_txt": (
            str(anos_lista[0]) if len(anos_lista) == 1 else f"{anos_lista[0]} a {anos_lista[-1]}"
        ),
        "dt_carga_fonte": dt_carga_base,
        "dt_carga_fonte_txt": dt_carga_base_txt,
        "anos_sem_farmaceutico": anos_sem_farmaceutico,
        "anos_um_trabalhador": anos_um_trabalhador,
        "trabalhador_detalhe_rows": trabalhador_detalhe_rows,
        "trabalhador_detalhe_total_cpfs": total_cpfs_periodo,
        "trabalhador_detalhe_modo": detalhe_modo,
        "movimentacao_sem_funcionario_alerta": movimentacao_sem_funcionario_alerta,
    }


def _build_ultimo_mes_sav_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> dict[str, Any]:
    """Identifica o ultimo mes com vendas no SAV dentro do periodo analisado."""
    evolucao = get_evolucao_financeira(cnpj, data_inicio, data_fim)
    semestres_raw = getattr(evolucao, "semestres", None)
    if semestres_raw is None:
        raise RuntimeError("Resposta de evolucao financeira sem campo semestres para Nota Tecnica.")

    meses: list[dict[str, Any]] = []
    for sem in semestres_raw:
        sem_item = _model_to_dict(sem)
        for mes in sem_item.get("meses") or []:
            mes_item = _model_to_dict(mes)
            if mes_item.get("mes"):
                meses.append(mes_item)

    if not meses:
        raise RuntimeError("Evolucao financeira mensal obrigatoria vazia para Nota Tecnica.")

    ultimo_mes = max(meses, key=lambda item: str(item.get("mes") or ""))
    total = float(ultimo_mes.get("total") or 0.0)
    return {
        "mes": str(ultimo_mes["mes"]),
        "mes_formatado": _format_month_year_pt(str(ultimo_mes["mes"])),
        "total": round(total, 2),
    }


def _build_evolucao_financeira_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    growth_threshold_pct: float = 50.0,
) -> dict[str, Any]:
    """Monta a evolucao financeira semestral e identifica saltos relevantes."""
    evolucao = get_evolucao_financeira(cnpj, data_inicio, data_fim)
    semestres_raw = getattr(evolucao, "semestres", None)
    if semestres_raw is None:
        raise RuntimeError("Resposta de evolucao financeira sem campo semestres para Nota Tecnica.")
    if not semestres_raw:
        raise RuntimeError("Evolucao financeira obrigatoria vazia para Nota Tecnica.")

    rows: list[dict[str, Any]] = []
    for sem in semestres_raw:
        item = _model_to_dict(sem)
        for col in ("semestre", "total", "regular", "irregular", "pct_irregular"):
            if col not in item:
                raise RuntimeError(f"Evolucao financeira sem coluna obrigatoria para Nota Tecnica: {col}.")
        total = float(item["total"] or 0.0)
        irregular = float(item["irregular"] or 0.0)
        regular = float(item["regular"] or 0.0)
        pct_irregular = float(item["pct_irregular"] or 0.0)
        semestre = str(item["semestre"])
        taxa_crescimento_raw = item.get("taxa_crescimento_pct")
        aumento_valor_raw = item.get("aumento_valor_semestre")
        limite_volume_atipico_raw = item.get("limite_volume_atipico_pct")
        chave_semestre = item.get("chave_semestre") or _semester_key_from_label(semestre)
        rows.append({
            "semestre": semestre,
            "semestre_fmt": _format_semestre_pt(semestre),
            "chave_semestre": int(chave_semestre) if chave_semestre is not None else None,
            "mes_inicio": item.get("mes_inicio"),
            "mes_fim": item.get("mes_fim"),
            "total": round(total, 2),
            "regular": round(regular, 2),
            "irregular": round(irregular, 2),
            "pct_irregular": round(pct_irregular, 2),
            "volume_atipico": bool(item.get("volume_atipico")),
            "taxa_crescimento_pct": round(float(taxa_crescimento_raw), 2) if taxa_crescimento_raw is not None else None,
            "aumento_valor_semestre": round(float(aumento_valor_raw), 2) if aumento_valor_raw is not None else None,
            "chave_semestre_anterior": item.get("chave_semestre_anterior"),
            "limite_volume_atipico_pct": float(limite_volume_atipico_raw) if limite_volume_atipico_raw is not None else None,
        })

    if not rows:
        raise RuntimeError("Evolucao financeira sem linhas validas para Nota Tecnica.")

    total_geral = round(sum(row["total"] for row in rows), 2)
    irregular_geral = round(sum(row["irregular"] for row in rows), 2)
    regular_geral = round(sum(row["regular"] for row in rows), 2)
    pct_irregular_geral = (irregular_geral / total_geral * 100) if total_geral > 0 else 0.0

    semestres_atipicos = [row for row in rows if row["volume_atipico"]]
    medicamentos_aumento_atipico = _build_medicamentos_aumento_atipico_context(
        cnpj,
        data_inicio,
        data_fim,
        semestres_atipicos,
    )
    limites_volume_atipico = [
        row["limite_volume_atipico_pct"]
        for row in rows
        if row["limite_volume_atipico_pct"] is not None
    ]
    limite_volume_atipico = limites_volume_atipico[0] if limites_volume_atipico else growth_threshold_pct
    limite_aumento_volume_atipico = get_volume_atipico_aumento_minimo()

    semestres_irregulares = [
        row for row in rows
        if row["irregular"] >= limite_aumento_volume_atipico
    ]
    top_irregulares = sorted(semestres_irregulares, key=lambda row: row["irregular"], reverse=True)
    primeiro_mes = rows[0].get("mes_inicio")
    ultimo_mes = rows[-1].get("mes_fim")
    periodo_meses = (
        f'{_format_month_year_long_pt(primeiro_mes)} a {_format_month_year_long_pt(ultimo_mes)}'
        if primeiro_mes and ultimo_mes
        else (
            rows[0]["semestre_fmt"] if rows[0]["semestre"] == rows[-1]["semestre"]
            else f'{rows[0]["semestre_fmt"]} a {rows[-1]["semestre_fmt"]}'
        )
    )

    return {
        "rows": rows,
        "total": total_geral,
        "regular": regular_geral,
        "irregular": irregular_geral,
        "pct_irregular": pct_irregular_geral,
        "primeiro_semestre": rows[0]["semestre"],
        "ultimo_semestre": rows[-1]["semestre"],
        "primeiro_semestre_fmt": rows[0]["semestre_fmt"],
        "ultimo_semestre_fmt": rows[-1]["semestre_fmt"],
        "periodo_semestres": (
            rows[0]["semestre_fmt"] if rows[0]["semestre"] == rows[-1]["semestre"]
            else f'{rows[0]["semestre_fmt"]} a {rows[-1]["semestre_fmt"]}'
        ),
        "periodo_meses": periodo_meses,
        "growth_threshold_pct": limite_volume_atipico,
        "crescimento_relevante": semestres_atipicos,
        "semestres_atipicos": semestres_atipicos,
        "top_irregulares": top_irregulares,
        "medicamentos_aumento_atipico": medicamentos_aumento_atipico,
    }


def _build_socios_volume_atipico_context(
    socios_ativos: list[Any],
    evolucao_comp: dict[str, Any],
    max_semestres_apos_entrada: int = 2,
) -> list[dict[str, Any]]:
    """Identifica aumentos atipicos proximos ao ingresso de socios ativos."""
    semestres_atipicos = evolucao_comp.get("semestres_atipicos") or []
    matches: list[dict[str, Any]] = []

    for socio in socios_ativos:
        entrada = getattr(socio, "data_entrada_sociedade", None)
        if not entrada:
            continue

        entrada_key = _semester_key_from_date(entrada)
        nome = getattr(socio, "nome_socio", None) or "socio nao identificado"

        for semestre in semestres_atipicos:
            semestre_key = semestre.get("chave_semestre") or _semester_key_from_label(semestre.get("semestre"))
            if semestre_key is None:
                continue

            distancia = _semester_distance(entrada_key, int(semestre_key))
            if 0 <= distancia <= max_semestres_apos_entrada:
                matches.append({
                    "nome_socio": nome,
                    "entrada": entrada,
                    "entrada_txt": _format_date_month_year_long_pt(entrada),
                    "semestre_fmt": semestre.get("semestre_fmt") or _format_semestre_pt(semestre.get("semestre")),
                    "taxa_crescimento_pct": semestre.get("taxa_crescimento_pct"),
                    "distancia_semestres": distancia,
                })

    return sorted(matches, key=lambda item: (item["entrada"], item["distancia_semestres"], item["nome_socio"]))


def _build_repasses_anuais_context(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
) -> dict[str, Any]:
    """
    Agrega ordens bancárias do SIAFI por ano para o CNPJ informado.

    Retorna:
        rows: lista de {ano, valor} ordenada por ano
        total: soma geral de valor_pago
        periodo_fmt: string "Ano1 a AnoN" para uso no título da tabela
        sem_repasses: True quando a consulta é válida, mas não há registros no período
    """
    perfil = get_df_perfil_estabelecimento().filter(pl.col("cnpj") == cnpj).select("id_cnpj")
    if perfil.is_empty():
        raise RuntimeError(f"CNPJ {cnpj} não encontrado no perfil para contexto de repasses anuais.")

    id_cnpj = int(perfil.item(0, 0))

    query = (
        scan_pagamentos_consolidados_farmacia_popular()
        .filter(pl.col("id_cnpj") == id_cnpj)
        .with_columns(
            pl.col("data_pagamento").str.to_date("%Y-%m-%d", strict=True).alias("dt_pagamento"),
        )
    )
    if data_inicio:
        query = query.filter(pl.col("dt_pagamento") >= pl.lit(data_inicio).cast(pl.Date))
    if data_fim:
        query = query.filter(pl.col("dt_pagamento") <= pl.lit(data_fim).cast(pl.Date))

    df = (
        query
        .with_columns(pl.col("dt_pagamento").dt.year().alias("ano"))
        .group_by("ano")
        .agg(pl.col("valor_pago").sum().alias("valor"))
        .sort("ano")
        .collect()
    )

    if df.is_empty():
        periodo_inicio = data_inicio.year if data_inicio else None
        periodo_fim = data_fim.year if data_fim else None
        if periodo_inicio and periodo_fim:
            periodo_fmt = str(periodo_inicio) if periodo_inicio == periodo_fim else f"{periodo_inicio} a {periodo_fim}"
        elif periodo_inicio:
            periodo_fmt = f"a partir de {periodo_inicio}"
        elif periodo_fim:
            periodo_fmt = f"até {periodo_fim}"
        else:
            periodo_fmt = "período analisado"
        return {
            "rows": [],
            "total": 0.0,
            "periodo_fmt": periodo_fmt,
            "sem_repasses": True,
        }

    rows = [{"ano": int(r["ano"]), "valor": round(float(r["valor"]), 2)} for r in df.to_dicts()]

    # Preenche anos do período de análise sem recebimentos com R$ 0,00
    if data_inicio and data_fim:
        anos_existentes = {r["ano"] for r in rows}
        for ano in range(data_inicio.year, data_fim.year + 1):
            if ano not in anos_existentes:
                rows.append({"ano": ano, "valor": 0.0})
        rows = sorted(rows, key=lambda r: r["ano"])

    total = round(sum(r["valor"] for r in rows), 2)
    anos = [r["ano"] for r in rows]
    periodo_fmt = str(anos[0]) if len(anos) == 1 else f"{anos[0]} a {anos[-1]}"

    return {
        "rows": rows,
        "total": total,
        "periodo_fmt": periodo_fmt,
        "sem_repasses": False,
    }
