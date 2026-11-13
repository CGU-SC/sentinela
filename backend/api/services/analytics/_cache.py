from typing import List, Optional
from datetime import date
import calendar
import polars as pl
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import os
import zlib
import json
import copy
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from cache_files import (
    DADOS_PAR_PARQUET,
    FARMACIAS_PARQUET,
    FARMACIAS_CNAES_SECUNDARIOS_PARQUET,
    TEIA_GRAFO_NIVEL2_EDGES_PARQUET,
    TEIA_GRAFO_NIVEL2_NODES_PARQUET,
    TEIA_GRAFO_NIVEL3_EDGES_PARQUET,
    TEIA_GRAFO_NIVEL3_NODES_PARQUET,
    TEIA_GRAFO_NIVEL4_EDGES_PARQUET,
    TEIA_GRAFO_NIVEL4_NODES_PARQUET,
)
from data_cache import (
    get_df, get_rede_df, get_localidades_df,
    get_df_bench_crm_regiao, get_df_bench_crm_br, get_df_dados_farmacia,
    get_df_dados_farmacia_cnaes_secundarios,
    get_df_dados_socios, scan_teia_fonte_nivel2, scan_teia_fonte_nivel3,
    scan_teia_fonte_nivel4, get_df_dados_par, get_cache_dir
)

from ...schemas.analytics import (
    AnalyticsKPISchema,
    ResultadoSentinelaUFSchema,
    AnalyticsResponse,
    ResultadoSentinelaMunicipioSchema,
    ResultadoSentinelaCnpjSchema,
    RedeEstabelecimentoSchema,
    FatorRiscoResponseSchema,
    FatorRiscoBucketSchema,
    EvolucaoSemestreSchema,
    EvolucaoFinanceiraResponse,
    IndicadorDataSchema,
    IndicadoresResponse,
    FalecidoTransactionSchema,
    FalecidosRankingSchema,
    FalecidosSummarySchema,
    FalecidosResponse,
    TimelineEventSchema,
    MultiCnpjTimelineResponse,
    RegionalMunicipioSchema,
    RegionalFarmaciaSchema,
    RegionalResponse,
    RegionalAnimationQuarterSchema,
    RegionalAnimationResponse,
    PrescritoresResponse,
    DadosFarmaciaSchema,
    MovimentacaoRowSchema,
    MovimentacaoSummarySchema,
    MovimentacaoResponse,
    IndicadorKpiSummarySchema,
    IndicadorCnpjRowSchema,
    IndicadorMunicipioRowSchema,
    IndicadorAnaliseResponse,
    MesMensalGtinItem,
    EvolucaoMensalGtinResponse,
    GtinDetalhamentoMensalResponse,
    GtinDetalhamentoMensalSummary,
    GtinDetalhamentoMensalItem,
)

COMPANY_CLASSIFICATION_VERSION = 2
PHARMACY_CNAES = {"4771701", "4771702"}
PHARMACY_NAME_TERMS = ("farmacia", "drogaria")
CNAES_SECUNDARIOS_DTYPE = pl.List(
    pl.Struct({"id_cnae": pl.Int32, "descricao": pl.Utf8})
)


def _normalize_company_text(value) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _normalize_cnae(value) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _is_truthy_flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "sim", "yes"}
    return bool(value)


def _is_pharmacy_by_activity_or_name(row: dict) -> bool:
    if _normalize_cnae(row.get("id_cnae_principal")) in PHARMACY_CNAES:
        return True

    searchable_name = " ".join(
        [
            _normalize_company_text(row.get("razao_social")),
            _normalize_company_text(row.get("nome_fantasia")),
        ]
    )
    return any(term in searchable_name for term in PHARMACY_NAME_TERMS)


def _classify_company_node(row: dict) -> str:
    if _is_truthy_flag(row.get("is_farmacia_fp")):
        return "PJ_FARMACIA_POPULAR"
    if _is_pharmacy_by_activity_or_name(row):
        return "PJ_OUTRAS_FARMACIAS"
    return "PJ_DEMAIS_EMPRESAS"

_known_cnpj_dirs: set[str] = set()

def _get_cnpj_cache_dir(cnpj: str) -> str:
    """Retorna modules/cnpjs/{cnpj}/, criada e conferida contra a versao da base.

    Delega a ``cnpj_cache_versao.get_cnpj_cache_dir``, que invalida os modulos
    do CNPJ gerados com outra versao dos caches globais.
    """
    import cnpj_cache_versao

    cnpj_dir = cnpj_cache_versao.get_cnpj_cache_dir(cnpj)
    _known_cnpj_dirs.add(cnpj_dir)
    return cnpj_dir

def sync_network(cnpj: str) -> None:
    """Sincroniza o cache Parquet da Teia Societária para um CNPJ usando fontes Parquet.

    Fontes:
      - dados_farmacia (parquet): para o nó raiz (PJ_ALVO)
      - dados_socios (parquet): para o Nível 1 (Sócios da farmácia)
      - teia_fonte_nivel2 (parquet): para o Nível 2 (Outras empresas dos sócios)
      - teia_fonte_nivel3 (parquet): para o Nível 3 (Sócios das outras empresas - expansão)
      - teia_fonte_nivel4 (parquet): para o Nível 4 (Empresas dos sócios de N3)
    """
    import time
    cnpj_dir = _get_cnpj_cache_dir(cnpj)
    N2_NODES_PATH  = os.path.join(cnpj_dir, TEIA_GRAFO_NIVEL2_NODES_PARQUET)
    N2_EDGES_PATH  = os.path.join(cnpj_dir, TEIA_GRAFO_NIVEL2_EDGES_PARQUET)
    N3_NODES_PATH  = os.path.join(cnpj_dir, TEIA_GRAFO_NIVEL3_NODES_PARQUET)
    N3_EDGES_PATH  = os.path.join(cnpj_dir, TEIA_GRAFO_NIVEL3_EDGES_PARQUET)
    N4_NODES_PATH  = os.path.join(cnpj_dir, TEIA_GRAFO_NIVEL4_NODES_PARQUET)
    N4_EDGES_PATH  = os.path.join(cnpj_dir, TEIA_GRAFO_NIVEL4_EDGES_PARQUET)

    # Cache hit: se os arquivos existem e são válidos, assume sucesso
    if all(os.path.exists(p) for p in [N2_NODES_PATH, N2_EDGES_PATH, N3_NODES_PATH, N3_EDGES_PATH, N4_NODES_PATH, N4_EDGES_PATH]):
        try:
            def has_required_columns(path: str, columns: set[str]) -> bool:
                return columns.issubset(set(pl.scan_parquet(path).limit(0).collect().columns))

            n2_n4_node_columns = {
                "id", "label", "type", "network_level", "razao_social", "nome_socio",
                "nome_fantasia", "classification_version", "is_falecido", "is_cadunico",
                "is_esocial", "is_seguro_defeso", "is_cnae_farmacia_ausente", "id_cnae_principal",
                "cnae_principal", "cnaes_secundarios", "is_par", "qtd_processos_par",
                "par_situacoes", "par_primeira_instauracao", "par_ultima_instauracao",
                "par_ultima_conclusao"
            }
            par_node_columns = {"is_par", "qtd_processos_par", "par_situacoes", "par_primeira_instauracao", "par_ultima_instauracao", "par_ultima_conclusao"}
            edge_columns = {"id", "source", "target", "type", "network_level", "is_ativo", "data_entrada_sociedade", "data_exclusao_sociedade"}
            if not has_required_columns(N2_NODES_PATH, n2_n4_node_columns):
                raise ValueError("N2 nodes cache com schema antigo")
            if not has_required_columns(N3_NODES_PATH, {"id", "label", "type", "network_level", "nome_socio", "is_falecido", "is_cadunico", "is_esocial", "is_seguro_defeso", "is_cnae_farmacia_ausente", *par_node_columns}):
                raise ValueError("N3 nodes cache com schema antigo")
            if not has_required_columns(N4_NODES_PATH, n2_n4_node_columns):
                raise ValueError("N4 nodes cache com schema antigo")
            if not has_required_columns(N2_EDGES_PATH, edge_columns):
                raise ValueError("N2 edges cache com schema antigo")
            if not has_required_columns(N3_EDGES_PATH, edge_columns):
                raise ValueError("N3 edges cache com schema antigo")
            if not has_required_columns(N4_EDGES_PATH, edge_columns):
                raise ValueError("N4 edges cache com schema antigo")

            graph_mtime = min(
                os.path.getmtime(path)
                for path in [N2_NODES_PATH, N3_NODES_PATH, N4_NODES_PATH]
            )

            FARMACIAS_PATH = os.path.join(get_cache_dir(), FARMACIAS_PARQUET)
            if not os.path.exists(FARMACIAS_PATH):
                raise FileNotFoundError(
                    f"Cache obrigatorio de farmacias nao encontrado: {FARMACIAS_PATH}"
                )
            if os.path.getmtime(FARMACIAS_PATH) > graph_mtime:
                raise ValueError("teia anterior ao cache de farmacias")

            CNAES_SECUNDARIOS_PATH = os.path.join(
                get_cache_dir(),
                FARMACIAS_CNAES_SECUNDARIOS_PARQUET,
            )
            if not os.path.exists(CNAES_SECUNDARIOS_PATH):
                raise FileNotFoundError(
                    "Cache obrigatorio de CNAEs secundarios nao encontrado: "
                    f"{CNAES_SECUNDARIOS_PATH}"
                )
            if os.path.getmtime(CNAES_SECUNDARIOS_PATH) > graph_mtime:
                raise ValueError("teia anterior ao cache de CNAEs secundarios")

            DADOS_PAR_PATH = os.path.join(get_cache_dir(), DADOS_PAR_PARQUET)
            if os.path.exists(DADOS_PAR_PATH):
                par_mtime = os.path.getmtime(DADOS_PAR_PATH)
                if par_mtime > graph_mtime:
                    raise ValueError("teia anterior ao cache PAR")

            return
        except Exception:
            pass

    try:
        print(f"[SYNC] Gerando Teia Societaria (Parquet Source) para {cnpj}...")
        t0 = time.perf_counter()

        nodes: dict[str, dict] = {}
        edges: list[dict]      = []
        df_exp_filtered        = pl.DataFrame() # Inicializa vazio

        def has_value(value) -> bool:
            return value is not None and str(value).strip() not in {"", "00000000000"}


        def add_representative_link(row: dict, node_dict: dict, edge_list: list[dict], active: bool = True, network_level: str = "n1") -> None:
            represented_id = row["cpf_cnpj_socio"]
            representative_id = row["cpf_representante"]
            if not has_value(represented_id) or not has_value(representative_id):
                return
            if represented_id == representative_id:
                return

            representative_name = row["nome_representante"] or representative_id
            if representative_id not in nodes and representative_id not in node_dict:
                node_dict[representative_id] = {
                    "id": representative_id,
                    "label": representative_name,
                    "type": "PF",
                    "network_level": network_level,
                    "nome_socio": representative_name,
                    "nome_fantasia": None,
                    "id_cnae_principal": None,
                    "cnae_principal": None,
                    "cnaes_secundarios": [],
                    "municipio": None,
                    "uf": None,
                    "situacao_rf": None,
                    "is_falecido": False,
                    "is_cadunico": False,
                    "is_esocial": False,
                    "is_seguro_defeso": False,
                    "is_cnae_farmacia_ausente": False,
                    **get_par_fields(representative_id),
                }

            edge_list.append({
                "id": f"{representative_id}->{represented_id}:representante",
                "source": representative_id,
                "target": represented_id,
                "label": "representante",
                "type": "representante",
                "network_level": network_level,
                "is_ativo": active,
                "data_entrada_sociedade": row.get("data_entrada_sociedade"),
                "data_exclusao_sociedade": row.get("data_exclusao_sociedade"),
            })

        # ── 1. Nó raiz: dados do CNPJ alvo ──────────────────────────────────
        df_farm = get_df_dados_farmacia()
        raiz = df_farm.filter(pl.col("cnpj") == cnpj).to_dicts()
        cnae_info_by_cnpj = {
            str(row["cnpj"]): row
            for row in df_farm.select([
                "id_cnpj",
                "cnpj",
                "id_cnae_principal",
                "cnae_principal",
                "is_cnae_farmacia_ausente",
            ]).to_dicts()
        }
        cnaes_secundarios_by_id_cnpj: dict[int, list[dict]] = {}
        for row in get_df_dados_farmacia_cnaes_secundarios().iter_rows(named=True):
            cnaes_secundarios_by_id_cnpj.setdefault(int(row["id_cnpj"]), []).append({
                "id_cnae": row["id_cnae"],
                "descricao": row["descricao"],
            })

        def get_cnaes_secundarios(cnpj_value) -> list[dict]:
            farmacia_info = cnae_info_by_cnpj.get(str(cnpj_value))
            if farmacia_info is None:
                return []
            return cnaes_secundarios_by_id_cnpj.get(
                int(farmacia_info["id_cnpj"]),
                [],
            )

        df_par = get_df_dados_par()
        par_info_by_cnpj = {
            str(row["cnpj"]): row
            for row in df_par.iter_rows(named=True)
        } if not df_par.is_empty() else {}

        def get_par_fields(cnpj_value) -> dict:
            row = par_info_by_cnpj.get(str(cnpj_value))
            if not row:
                return {
                    "is_par": False,
                    "qtd_processos_par": 0,
                    "par_situacoes": None,
                    "par_primeira_instauracao": None,
                    "par_ultima_instauracao": None,
                    "par_ultima_conclusao": None,
                }
            return {
                "is_par": bool(row.get("is_par")),
                "qtd_processos_par": int(row.get("qtd_processos_par") or 0),
                "par_situacoes": row.get("par_situacoes"),
                "par_primeira_instauracao": row.get("par_primeira_instauracao"),
                "par_ultima_instauracao": row.get("par_ultima_instauracao"),
                "par_ultima_conclusao": row.get("par_ultima_conclusao"),
            }
        
        if raiz:
            r = raiz[0]
            nodes[cnpj] = {
                "id": cnpj,
                "label": r.get("nome_fantasia") or r.get("razao_social") or f"CNPJ {cnpj}",
                "type": "PJ_ALVO",
                "network_level": "root",
                "razao_social": r.get("razao_social"),
                "nome_fantasia": r.get("nome_fantasia"),
                "nome_socio": None,
                "id_cnae_principal": r.get("id_cnae_principal"),
                "cnae_principal": r.get("cnae_principal"),
                "cnaes_secundarios": get_cnaes_secundarios(cnpj),
                "municipio": r.get("municipio"),
                "uf": r.get("uf"),
                "situacao_rf": r.get("situacao_rf"),
                "classification_version": COMPANY_CLASSIFICATION_VERSION,
                "is_falecido": False,
                "is_cadunico": False,
                "is_esocial": False,
                "is_seguro_defeso": False,
                "is_cnae_farmacia_ausente": bool(r["is_cnae_farmacia_ausente"]),
                **get_par_fields(cnpj),
            }
        else:
            nodes[cnpj] = {
                "id": cnpj, "label": f"CNPJ {cnpj}", "type": "PJ_ALVO", "network_level": "root",
                "razao_social": None, "nome_fantasia": None, "nome_socio": None,
                "id_cnae_principal": None, "cnae_principal": None,
                "cnaes_secundarios": [], "municipio": None, "uf": None,
                "situacao_rf": None, "classification_version": COMPANY_CLASSIFICATION_VERSION,
                "is_falecido": False, "is_cadunico": False, "is_esocial": False,
                "is_seguro_defeso": False, "is_cnae_farmacia_ausente": False,
                **get_par_fields(cnpj),
            }

        # ── 2. Nível 1: Sócios do CNPJ alvo ─────────────────────────────────
        df_soc = get_df_dados_socios()
        socios_alvo = df_soc.filter(pl.col("cnpj") == cnpj).to_dicts()

        cpfs_socios = []
        for s in socios_alvo:
            id_socio = s["cpf_cnpj_socio"]
            cpfs_socios.append(id_socio)
            
            if id_socio not in nodes:
                nodes[id_socio] = {
                    "id": id_socio,
                    "label": s["nome_socio"],
                    "type": s["indicador_socio"] or "PF",
                    "network_level": "n1",
                    "nome_socio": s["nome_socio"],
                    "id_cnae_principal": None,
                    "cnae_principal": None,
                    "cnaes_secundarios": [],
                    "municipio": s.get("municipio"),
                    "uf": s.get("uf"),
                    "situacao_rf": None,
                    "is_falecido": bool(s.get("is_falecido", 0)),
                    "is_cadunico": bool(s["is_cadunico"]),
                    "is_esocial": bool(s["is_esocial"]),
                    "is_seguro_defeso": bool(s["is_seguro_defeso"]),
                    "is_cnae_farmacia_ausente": False,
                    **get_par_fields(id_socio),
                }

            edges.append({
                "id": f"{id_socio}->{cnpj}",
                "source": id_socio,
                "target": cnpj,
                "label": f"{float(s['percentual_qualificacao'] or 0):.1f}%",
                "type": "socio",
                "network_level": "n1",
                "is_ativo": s.get("data_exclusao_sociedade") is None,
                "data_entrada_sociedade": s.get("data_entrada_sociedade"),
                "data_exclusao_sociedade": s.get("data_exclusao_sociedade"),
            })
            add_representative_link(
                s,
                nodes,
                edges,
                active=s.get("data_exclusao_sociedade") is None,
                network_level="n1"
            )

        cnpjs_externos = []
        if cpfs_socios:
            df_ext_filtered = (
                scan_teia_fonte_nivel2()
                .filter(pl.col("cpf_cnpj_socio").is_in(cpfs_socios))
                .collect()
            )
            participacoes = df_ext_filtered.to_dicts()
            print(f"   -> Nivel 2: Encontradas {len(participacoes)} participacoes para {len(cpfs_socios)} socios.")

            for p in participacoes:
                cnpj_ext = p["cnpj_empresa"]
                id_socio = p["cpf_cnpj_socio"]
                cnpjs_externos.append(cnpj_ext) # Sempre adiciona para disparar N3/N4

                if cnpj_ext not in nodes:
                    tipo = _classify_company_node(p)
                    cnae_info = cnae_info_by_cnpj.get(str(cnpj_ext), {})

                    nodes[cnpj_ext] = {
                        "id": cnpj_ext,
                        "label": p.get("nome_fantasia") or p["razao_social"] or cnpj_ext,
                        "type": tipo,
                        "network_level": "n2",
                        "razao_social": p["razao_social"],
                        "nome_fantasia": p.get("nome_fantasia"),
                        "nome_socio": None,
                        "id_cnae_principal": p.get("id_cnae_principal"),
                        "cnae_principal": cnae_info.get("cnae_principal"),
                        "cnaes_secundarios": get_cnaes_secundarios(cnpj_ext),
                        "municipio": p["municipio"],
                        "uf": p["uf"],
                        "situacao_rf": p["situacao_rf"],
                        "classification_version": COMPANY_CLASSIFICATION_VERSION,
                        "is_falecido": False,
                        "is_cadunico": False,
                        "is_esocial": False,
                        "is_seguro_defeso": False,
                        "is_cnae_farmacia_ausente": bool(cnae_info.get("is_cnae_farmacia_ausente", False)),
                        **get_par_fields(cnpj_ext),
                    }

                edges.append({
                    "id": f"{id_socio}->{cnpj_ext}",
                    "source": id_socio,
                    "target": cnpj_ext,
                    "label": "sócio",
                    "type": "socio",
                    "network_level": "n2",
                    "is_ativo": p.get("data_exclusao_sociedade") is None,
                    "data_entrada_sociedade": p.get("data_entrada_sociedade"),
                    "data_exclusao_sociedade": p.get("data_exclusao_sociedade"),
                })
                add_representative_link(
                    p,
                    nodes,
                    edges,
                    active=p.get("data_exclusao_sociedade") is None,
                    network_level="n2"
                )

        # ── 4. Nível 3: Expansão (Sócios das empresas irmãs) ─────────────────
        # Estes dados ficam em arquivos separados para carregamento on-demand no frontend
        exp_nodes_dict: dict[str, dict] = {}
        exp_edges: list[dict] = []
        df_exp_filtered = pl.DataFrame()
        
        if cnpjs_externos:
            # Filtra sócios de todas as empresas irmãs mapeadas
            cnpjs_externos_unicos = list(set(cnpjs_externos))
            df_exp_filtered = (
                scan_teia_fonte_nivel3()
                .filter(pl.col("cnpj_empresa").is_in(cnpjs_externos_unicos))
                .collect()
            )
            print(f"   -> Nivel 3: Encontrados {df_exp_filtered.height} vinculos de socios para {len(cnpjs_externos_unicos)} empresas N2.")
            
            for row in df_exp_filtered.iter_rows(named=True):
                id_socio = row["cpf_cnpj_socio"]
                cnpj_pai = row["cnpj_empresa"]
                
                # Se o sócio já existe na teia principal (Nível 1), não precisamos duplicar o nó
                if id_socio not in nodes and id_socio not in exp_nodes_dict:
                    exp_nodes_dict[id_socio] = {
                        "id": id_socio,
                        "label": row["nome_socio"],
                        "type": row["indicador_socio"] or "PF",
                        "network_level": "n3",
                        "nome_socio": row["nome_socio"],
                        "nome_fantasia": None,
                        "id_cnae_principal": None,
                        "cnae_principal": None,
                        "cnaes_secundarios": [],
                        "municipio": row.get("municipio"),
                        "uf": row.get("uf"),
                        "situacao_rf": None,
                        "is_falecido": bool(row.get("is_falecido", 0)),
                        "is_cadunico": bool(row["is_cadunico"]),
                        "is_esocial": bool(row["is_esocial"]),
                        "is_seguro_defeso": bool(row["is_seguro_defeso"]),
                        "is_cnae_farmacia_ausente": False,
                        **get_par_fields(id_socio),
                    }
                
                edge_id = f"{id_socio}->{cnpj_pai}"
                
                # Deduplicação: se o mesmo sócio aparecer com dois cargos, mantemos apenas o primeiro (evita duplicar linhas no grafo)
                if not any(e["id"] == edge_id for e in exp_edges):
                    exp_edges.append({
                        "id": edge_id,
                        "source": id_socio,
                        "target": cnpj_pai,
                        "label": "sócio",
                        "type": "socio",
                        "network_level": "n3",
                        "is_ativo": row.get("data_exclusao_sociedade") is None,
                        "data_entrada_sociedade": row.get("data_entrada_sociedade"),
                        "data_exclusao_sociedade": row.get("data_exclusao_sociedade"),
                    })
                add_representative_link(
                    row,
                    exp_nodes_dict,
                    exp_edges,
                    active=row.get("data_exclusao_sociedade") is None,
                    network_level="n3"
                )

        # ── Salva Parquets Principais ────────────────────────────────────────
        def project_rows(rows: list[dict], columns: list[str]) -> list[dict]:
            return [{column: row.get(column) for column in columns} for row in rows]

        n2_node_columns = [
            "id", "label", "type", "network_level", "razao_social", "nome_socio", "nome_fantasia",
            "id_cnae_principal", "cnae_principal", "cnaes_secundarios",
            "municipio", "uf", "situacao_rf", "classification_version",
            "is_falecido", "is_cadunico", "is_esocial", "is_seguro_defeso",
            "is_cnae_farmacia_ausente",
            "is_par", "qtd_processos_par", "par_situacoes", "par_primeira_instauracao",
            "par_ultima_instauracao", "par_ultima_conclusao"
        ]
        n2_node_schema = {
            "id": pl.Utf8, "label": pl.Utf8, "type": pl.Utf8, "network_level": pl.Utf8,
            "razao_social": pl.Utf8, "nome_socio": pl.Utf8, "nome_fantasia": pl.Utf8,
            "id_cnae_principal": pl.Int32, "cnae_principal": pl.Utf8,
            "cnaes_secundarios": CNAES_SECUNDARIOS_DTYPE,
            "municipio": pl.Utf8, "uf": pl.Utf8, "situacao_rf": pl.Utf8,
            "classification_version": pl.Int16, "is_falecido": pl.Boolean, "is_cadunico": pl.Boolean,
            "is_esocial": pl.Boolean,
            "is_seguro_defeso": pl.Boolean,
            "is_cnae_farmacia_ausente": pl.Boolean,
            "is_par": pl.Boolean, "qtd_processos_par": pl.Int32, "par_situacoes": pl.Utf8,
            "par_primeira_instauracao": pl.Date, "par_ultima_instauracao": pl.Date,
            "par_ultima_conclusao": pl.Date,
        }

        pl.DataFrame(project_rows(list(nodes.values()), n2_node_columns), schema=n2_node_schema).write_parquet(N2_NODES_PATH, compression="zstd")
        edge_schema = {
            "id": pl.Utf8,
            "source": pl.Utf8,
            "target": pl.Utf8,
            "label": pl.Utf8,
            "type": pl.Utf8,
            "network_level": pl.Utf8,
            "is_ativo": pl.Boolean,
            "data_entrada_sociedade": pl.Date,
            "data_exclusao_sociedade": pl.Date,
        }

        pl.DataFrame(edges if edges else [], schema=edge_schema).unique(subset=["id"], keep="first").write_parquet(N2_EDGES_PATH, compression="zstd")

        # ── Salva Parquets de Expansão (On-Demand) ──────────────────────────
        n3_node_columns = [
            "id", "label", "type", "network_level", "nome_socio", "municipio", "uf",
            "is_falecido", "is_cadunico", "is_esocial", "is_seguro_defeso",
            "is_cnae_farmacia_ausente",
            "is_par", "qtd_processos_par", "par_situacoes", "par_primeira_instauracao",
            "par_ultima_instauracao", "par_ultima_conclusao"
        ]
        pl.DataFrame(project_rows(list(exp_nodes_dict.values()), n3_node_columns) if exp_nodes_dict else [], schema={
            "id": pl.Utf8, "label": pl.Utf8, "type": pl.Utf8, "network_level": pl.Utf8, "nome_socio": pl.Utf8,
            "municipio": pl.Utf8, "uf": pl.Utf8, "is_falecido": pl.Boolean, "is_cadunico": pl.Boolean,
            "is_esocial": pl.Boolean,
            "is_seguro_defeso": pl.Boolean,
            "is_cnae_farmacia_ausente": pl.Boolean,
            "is_par": pl.Boolean, "qtd_processos_par": pl.Int32, "par_situacoes": pl.Utf8,
            "par_primeira_instauracao": pl.Date, "par_ultima_instauracao": pl.Date,
            "par_ultima_conclusao": pl.Date,
        }).unique(subset=["id"], keep="first").write_parquet(N3_NODES_PATH, compression="zstd")
        
        pl.DataFrame(exp_edges if exp_edges else [], schema=edge_schema).unique(subset=["id"], keep="first").write_parquet(N3_EDGES_PATH, compression="zstd")

        # ── 5. Nível 4: Expansão (Outras empresas dos sócios de N3) ─────────
        n4_nodes_dict: dict[str, dict] = {}
        n4_edges: list[dict] = []
        
        # CPFs que disparam o Nível 4 (todos os sócios de empresas irmãs)
        cpfs_n3_trigger = []
        if not df_exp_filtered.is_empty() and cnpjs_externos:
            cpfs_n3_trigger = df_exp_filtered.select("cpf_cnpj_socio").unique().to_series().to_list()
        
        print(f"   -> Nivel 4: Disparando busca para {len(cpfs_n3_trigger)} CPFs do Nivel 3...")
        if cpfs_n3_trigger:
            df_n4_filtered = (
                scan_teia_fonte_nivel4()
                .filter(pl.col("cpf_cnpj_socio").is_in(cpfs_n3_trigger))
                .collect()
            )
            print(f"   -> Nivel 4: Encontradas {df_n4_filtered.height} empresas de expansao.")
            
            for row in df_n4_filtered.iter_rows(named=True):
                cnpj_ext = row["cnpj_empresa"]
                id_socio = row["cpf_cnpj_socio"]
                
                # Se a empresa já existe na teia (N2 ou Alvo), não duplicamos
                if cnpj_ext not in nodes and cnpj_ext not in n4_nodes_dict:
                    tipo = _classify_company_node(row)
                    cnae_info = cnae_info_by_cnpj.get(str(cnpj_ext), {})
                        
                    n4_nodes_dict[cnpj_ext] = {
                        "id": cnpj_ext,
                        "label": row.get("nome_fantasia") or row["razao_social"] or cnpj_ext,
                        "type": tipo,
                        "network_level": "n4",
                        "razao_social": row["razao_social"],
                        "nome_fantasia": row.get("nome_fantasia"),
                        "nome_socio": None,
                        "id_cnae_principal": row.get("id_cnae_principal"),
                        "cnae_principal": cnae_info.get("cnae_principal"),
                        "cnaes_secundarios": get_cnaes_secundarios(cnpj_ext),
                        "municipio": row["municipio"],
                        "uf": row["uf"],
                        "situacao_rf": row["situacao_rf"],
                        "classification_version": COMPANY_CLASSIFICATION_VERSION,
                        "is_falecido": False,
                        "is_cadunico": False,
                        "is_esocial": False,
                        "is_seguro_defeso": False,
                        "is_cnae_farmacia_ausente": bool(cnae_info.get("is_cnae_farmacia_ausente", False)),
                        **get_par_fields(cnpj_ext),
                    }
                
                edge_id = f"{id_socio}->{cnpj_ext}"
                if not any(e["id"] == edge_id for e in n4_edges):
                    n4_edges.append({
                        "id": edge_id,
                        "source": id_socio,
                        "target": cnpj_ext,
                        "label": "sócio",
                        "type": "socio",
                        "network_level": "n4",
                        "is_ativo": row.get("data_exclusao_sociedade") is None,
                        "data_entrada_sociedade": row.get("data_entrada_sociedade"),
                        "data_exclusao_sociedade": row.get("data_exclusao_sociedade"),
                    })
                add_representative_link(
                    row,
                    n4_nodes_dict,
                    n4_edges,
                    active=row.get("data_exclusao_sociedade") is None,
                    network_level="n4"
                )

        # ── Salva Parquets Nível 4 ──────────────────────────────────────────
        n4_node_columns = [
            "id", "label", "type", "network_level", "razao_social", "nome_socio", "nome_fantasia",
            "id_cnae_principal", "cnae_principal", "cnaes_secundarios",
            "municipio", "uf", "situacao_rf", "classification_version",
            "is_falecido", "is_cadunico", "is_esocial", "is_seguro_defeso",
            "is_cnae_farmacia_ausente",
            "is_par", "qtd_processos_par", "par_situacoes", "par_primeira_instauracao",
            "par_ultima_instauracao", "par_ultima_conclusao"
        ]
        pl.DataFrame(project_rows(list(n4_nodes_dict.values()), n4_node_columns) if n4_nodes_dict else [], schema={
            "id": pl.Utf8, "label": pl.Utf8, "type": pl.Utf8, "network_level": pl.Utf8, "razao_social": pl.Utf8,
            "nome_socio": pl.Utf8, "nome_fantasia": pl.Utf8, "id_cnae_principal": pl.Int32,
            "cnae_principal": pl.Utf8, "cnaes_secundarios": CNAES_SECUNDARIOS_DTYPE,
            "municipio": pl.Utf8, "uf": pl.Utf8, "situacao_rf": pl.Utf8,
            "classification_version": pl.Int16, "is_falecido": pl.Boolean, "is_cadunico": pl.Boolean,
            "is_esocial": pl.Boolean,
            "is_seguro_defeso": pl.Boolean,
            "is_cnae_farmacia_ausente": pl.Boolean,
            "is_par": pl.Boolean, "qtd_processos_par": pl.Int32, "par_situacoes": pl.Utf8,
            "par_primeira_instauracao": pl.Date, "par_ultima_instauracao": pl.Date,
            "par_ultima_conclusao": pl.Date,
        }).unique(subset=["id"], keep="first").write_parquet(N4_NODES_PATH, compression="zstd")
        
        pl.DataFrame(n4_edges if n4_edges else [], schema=edge_schema).unique(subset=["id"], keep="first").write_parquet(N4_EDGES_PATH, compression="zstd")

        ms = (time.perf_counter() - t0) * 1000
        print(f"Teia Completa (+Expansao) salva para {cnpj} ({ms:.1f}ms)")

    except Exception as e:
        import traceback
        print(f"Erro ao gerar Teia Societaria para {cnpj}: {e}")
        print(traceback.format_exc())
