import sys
import os
import json
import time
import pandas as pd
import polars as pl
from sqlalchemy import text
import cache_registry
from cache_files import (
    CRM_PRESCRICOES_GERENCIAL_CACHE_VERSION,
    CRM_PRESCRICOES_ESTABELECIMENTO_MES_CACHE_VERSION,
    CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_CACHE_VERSION,
    CRM_PRESCRITORES_CACHE_VERSION,
    CRM_RAIOX_TX_CACHE_VERSION,
    MEMORIA_CALCULO_CACHE_VERSION,
    PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_CACHE_VERSION,
)
from datetime import date
from pathlib import Path
from typing import Any

# --- LÓGICA DE CAMINHO PARA CACHE ---
# Se rodando via EXE (PyInstaller), sys.frozen é True
if getattr(sys, 'frozen', False):
    # Pasta onde o executável foi disparado
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Pasta raiz do projeto em desenvolvimento (um nível acima de /backend)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_modules_dir() -> str:
    """Retorna o diretório raiz dos módulos locais do Sentinela."""
    return os.path.join(BASE_DIR, "modules")


def get_cache_dir() -> str:
    """Retorna o diretório dos parquets globais."""
    return os.path.join(get_modules_dir(), "global")


def get_cnpj_cache_root() -> str:
    """Retorna o diretório raiz dos parquets por CNPJ."""
    return os.path.join(get_modules_dir(), "cnpjs")


def get_user_preferences_dir() -> str:
    """Retorna o diretório local das preferências do usuário."""
    return os.path.join(get_modules_dir(), "user_preferences")

_CACHE_DIR = get_cache_dir()
_GLOBAL_PARQUETS = cache_registry.get_global_parquet_files_by_key()
_GLOBAL_PARQUET_SCHEMAS = {
    definition.key: definition.schema
    for definition in cache_registry.GLOBAL_CACHE_DEFINITIONS
    if definition.schema is not None
}
_ON_DEMAND_GLOBAL_CACHE_READY: set[str] = set()

# Todos os módulos globais obrigatórios participam da validação de boot.
_DISABLED_BOOT_MODULES: frozenset[str] = frozenset()

_ON_DEMAND_GLOBAL_REQUIRED_COLUMNS = {
    "teia_fonte_nivel2": {
        "cpf_cnpj_socio",
        "cnpj_empresa",
        "razao_social",
        "nome_fantasia",
        "indicador_socio",
        "descricao_qualificacao",
        "cpf_representante",
        "nome_representante",
        "data_entrada_sociedade",
        "data_exclusao_sociedade",
        "situacao_rf",
        "municipio",
        "uf",
        "is_farmacia_fp",
        "is_cadunico",
        "is_falecido",
    },
    "teia_fonte_nivel3": {
        "cnpj_empresa",
        "cpf_cnpj_socio",
        "nome_socio",
        "indicador_socio",
        "descricao_qualificacao",
        "cpf_representante",
        "nome_representante",
        "data_entrada_sociedade",
        "data_exclusao_sociedade",
        "municipio",
        "uf",
        "is_cadunico",
        "is_esocial",
        "is_seguro_defeso",
        "is_falecido",
    },
    "teia_fonte_nivel4": {
        "cpf_cnpj_socio",
        "cnpj_empresa",
        "razao_social",
        "nome_fantasia",
        "indicador_socio",
        "descricao_qualificacao",
        "cpf_representante",
        "nome_representante",
        "data_entrada_sociedade",
        "data_exclusao_sociedade",
        "situacao_rf",
        "municipio",
        "uf",
        "is_farmacia_fp",
        "is_cadunico",
        "is_falecido",
    },
    "esocial_cnpj_ano": {
        "id_cnpj",
        "ano_base",
        "mes_base",
        "competencia_base",
        "qtd_registros",
        "qtd_trabalhadores",
        "qtd_farmaceuticos",
        "qtd_trabalhadores_cbo_sem_titulo",
        "qtd_registros_farmaceuticos",
        "qtd_registros_cbo_sem_titulo",
        "has_farmaceutico",
        "has_cbo_sem_titulo",
        "is_um_trabalhador",
        "is_um_trabalhador_sem_farmaceutico",
        "is_um_trabalhador_cbo_sem_titulo",
        "cbo_unico_trabalhador",
        "titulo_cbo_unico_trabalhador",
        "qtd_registros_vinculo_ano",
        "qtd_trabalhadores_vinculo_ano",
        "qtd_farmaceuticos_vinculo_ano",
        "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano",
        "dt_carga_fonte",
        "dt_processamento",
    },
    "esocial_cnpj_trabalhador_ano": {
        "id_cnpj",
        "ano_base",
        "mes_base",
        "competencia_base",
        "cpf_trabalhador",
        "matricula",
        "cbo",
        "titulo_cbo",
        "dt_admissao",
        "dt_rescisao",
        "is_farmaceutico",
        "is_cbo_sem_titulo",
        "dt_carga_fonte",
        "dt_processamento",
    },
    "geografico_origem_uf": {
        "id_cnpj",
        "ano_base",
        "uf_farmacia",
        "uf_paciente",
        "is_outra_uf",
        "qtd_autorizacoes",
        "valor_autorizado",
    },
    "crm_raiox_tx_global": {
        "id_cnpj",
        "dt_janela",
        "hr_janela",
        "data_hora",
        "num_autorizacao",
        "id_medico",
        "valor_pago",
        "_crm_raiox_tx_cache_version",
    },
    "pagamentos_consolidados_farmacia_popular": {
        "id_cnpj",
        "data_pagamento",
        "programa_acao",
        "numero_ordem_bancaria",
        "valor_pago",
        "_pagamentos_consolidados_farmacia_popular_cache_version",
    },
    "crm_prescritores_global": {
        "id_cnpj",
        "id_medico",
        "competencia",
        "vl_total_prescricoes",
        "nu_prescricoes_mes",
        "nu_prescricoes_total_brasil",
        "flag_crm_invalido",
        "flag_prescricao_antes_registro",
        "alerta_concentracao_multiplos_crms",
        "flag_concentracao_mesmo_crm",
        "flag_distancia_geografica",
        "dt_inscricao_crm",
        "nu_estabelecimentos",
        "_crm_prescritores_cache_version",
    },
    "memoria_calculo_global": {
        "cnpj",
        "id_processamento",
        "schema_version",
        "memoria_calculo_payload",
        "_memoria_calculo_cache_version",
    },
    "esocial_cnpj_movimentacao_ano": {
        "id_cnpj",
        "ano_base",
        "id_regiao_saude",
        "uf",
        "periodo_min",
        "periodo_max",
        "valor_pfpb_ano",
        "valor_sem_comprovacao_ano",
        "qtd_autorizacoes_ano",
        "qtd_caixas_ano",
        "qtd_caixas_sem_comprovacao_ano",
        "qtd_trabalhadores",
        "qtd_farmaceuticos",
        "valor_pfpb_por_trabalhador",
        "valor_sem_comprovacao_por_trabalhador",
        "autorizacoes_por_trabalhador",
        "caixas_por_trabalhador",
        "p90_referencia_valor_pfpb_ano",
        "p95_referencia_valor_por_trabalhador",
        "qtd_cnpjs_referencia",
        "escopo_referencia",
        "classificacao_mov_trabalhista",
        "motivo_classificacao",
        "dt_processamento",
    },
    "esocial_cnpj_ultima_movimentacao": {
        "id_cnpj",
        "ano_ultima_movimentacao",
        "ano_esocial_referencia_ultima_movimentacao",
        "is_sem_esocial_no_ano_ultima_movimentacao",
        "ultimo_periodo_movimentacao",
        "dt_inicio_ultimo_mes_movimentacao",
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
        "classificacao_mov_sem_funcionario",
        "motivo_mov_sem_funcionario",
        "dt_processamento",
    },
    "analise_gtin_inconsistencia_clinica": {
        "id_cnpj",
        "id_regiao_saude",
        "id_ibge7",
        "patologia",
        "regra_clinica",
        "ano_base",
        "qtd_cpfs_distintos",
        "qtd_cpfs_incompativeis",
        "qtd_autorizacoes",
        "qtd_autorizacoes_incompativeis",
        "valor_total_pago",
        "valor_incompativel_pago",
        "percentual_cpfs_incompativeis",
        "rank_regional_qtd_cpfs_incompativeis",
        "rank_regional_valor_incompativel_pago",
        "percentil_regional_qtd_cpfs_incompativeis",
        "percentil_regional_valor_incompativel_pago",
        "participacao_cpfs_incompativeis_regiao",
        "participacao_valor_incompativel_regiao",
        "percentual_regional_cpfs_incompativeis",
        "razao_percentual_vs_regiao",
        "cpfs_incompativeis_esperados_regiao",
        "excesso_cpfs_incompativeis_vs_regiao",
        "dt_processamento",
    },
    "analise_gtin_inconsistencia_clinica_municipio": {
        "id_ibge7",
        "patologia",
        "regra_clinica",
        "ano_base",
        "qtd_cpfs_distintos_municipio",
        "qtd_cpfs_incompativeis_municipio",
        "qtd_autorizacoes_municipio",
        "qtd_autorizacoes_incompativeis_municipio",
        "valor_total_pago_municipio",
        "valor_incompativel_pago_municipio",
        "dt_processamento",
    },
    "analise_gtin_inconsistencia_clinica_regiao": {
        "id_regiao_saude",
        "patologia",
        "regra_clinica",
        "ano_base",
        "qtd_cnpjs_regiao",
        "qtd_municipios_regiao",
        "qtd_cpfs_distintos_regiao",
        "qtd_cpfs_incompativeis_regiao",
        "qtd_autorizacoes_regiao",
        "qtd_autorizacoes_incompativeis_regiao",
        "valor_total_pago_regiao",
        "valor_incompativel_pago_regiao",
        "percentual_cpfs_incompativeis_regiao",
        "dt_processamento",
    },
    "geografico_global": {
        "cnpj_a",
        "cnpj_b",
        "id_medico",
        "competencia",
        "distancia_km",
    },
    "crm_concentracao_unico_alertas_global": {
        "id_cnpj",
        "id_medico",
        "dt_alerta",
        "hr_janela",
        "severidade",
        "_crm_alerts_cache_version",
    },
    "crm_concentracao_multiplo_alertas_global": {
        "id_cnpj",
        "dt_alerta",
        "hr_janela",
        "severidade",
        "_crm_alerts_cache_version",
    },
    "crm_timeline_dia_global": {
        "id_cnpj",
        "dt_janela",
        "competencia",
    },
    "crm_timeline_hora_global": {
        "id_cnpj",
        "dt_janela",
        "hr_janela",
    },
    "crm_timeline_eventos_global": {
        "id_cnpj",
        "dt_janela",
        "tipo",
    },
    "crm_prescricoes_brasil_semestre": {
        "id_medico",
        "chave_semestre",
        "nu_prescricoes_total_brasil",
        "dias_ativos_brasil",
    },
    "crm_prescricoes_estabelecimento_mes": {
        "id_cnpj",
        "id_medico",
        "competencia",
        "nu_prescricoes_mes",
    },
    "crm_prescricoes_medico_municipio_mes": {
        "id_medico",
        "competencia",
        "id_ibge7",
        "nu_prescricoes_mes",
    },
    "crm_prescricoes_gerencial": {
        "nivel",
        "id_geografico",
        "competencia",
        "nu_prescricoes_total",
        "qtd_crms_ativos",
        "qtd_crms_anomalos",
        "percentual_crms_anomalos",
        "media_prescricoes_dia",
    },
    "dados_medico": {
        "id_medico",
        "nu_crm",
        "sg_uf",
        "no_medico",
        "dt_primeira_inscricao_uf",
    },
}


def _global_cache_path(key: str) -> str:
    return os.path.join(_CACHE_DIR, _GLOBAL_PARQUETS[key])


def _validate_parquet_schema(name: str, path: str, required: set[str] | None = None) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Parquet global {name} nao encontrado em {path}.")
    parquet_schema = pl.scan_parquet(path).limit(0).collect().schema
    schema_columns = set(parquet_schema.keys())
    expected_schema = _GLOBAL_PARQUET_SCHEMAS.get(name)
    required_columns = set(required or set())
    if expected_schema:
        required_columns.update(expected_schema.keys())

    if required_columns and not required_columns.issubset(schema_columns):
        missing_cols = ", ".join(sorted(required_columns - schema_columns))
        raise ValueError(f"schema antigo sem colunas obrigatorias: {missing_cols}")

    if expected_schema:
        type_mismatches = [
            f"{col}: esperado {expected_dtype}, encontrado {parquet_schema[col]}"
            for col, expected_dtype in expected_schema.items()
            if col in parquet_schema and parquet_schema[col] != expected_dtype
        ]
        if type_mismatches:
            raise ValueError(
                "schema antigo com tipos invalidos: "
                + "; ".join(type_mismatches)
            )


def _mark_on_demand_global_cache_ready(name: str, path: str) -> None:
    _validate_parquet_schema(name, path, _ON_DEMAND_GLOBAL_REQUIRED_COLUMNS.get(name))
    _ON_DEMAND_GLOBAL_CACHE_READY.add(name)


def _is_on_demand_global_cache_ready(name: str, path: str) -> bool:
    return name in _ON_DEMAND_GLOBAL_CACHE_READY and os.path.exists(path)


def _scan_on_demand_global_parquet(name: str, path: str) -> pl.LazyFrame:
    _mark_on_demand_global_cache_ready(name, path)
    return pl.scan_parquet(path)


_PARQUET_PATH = _global_cache_path("movimentacao")
_LOCALIDADES_PARQUET_PATH = _global_cache_path("localidades")
_REDE_PARQUET_PATH = _global_cache_path("rede")
_MATRIZ_PARQUET_PATH = _global_cache_path("matriz_risco")
_BENCH_CRM_UF_PATH = _global_cache_path("bench_crm_uf")
_BENCH_CRM_REGIAO_PATH = _global_cache_path("bench_crm_regiao")
_BENCH_CRM_BR_PATH = _global_cache_path("bench_crm_br")
_CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH = _global_cache_path("crm_prescricoes_brasil_semestre")
_CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH = _global_cache_path("crm_prescricoes_estabelecimento_mes")
_CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PATH = _global_cache_path("crm_prescricoes_medico_municipio_mes")
_CRM_PRESCRICOES_GERENCIAL_PATH = _global_cache_path("crm_prescricoes_gerencial")
_DADOS_MEDICO_PARQUET_PATH = _global_cache_path("dados_medico")
_CRM_PRESCRITORES_GLOBAL_PARQUET_PATH = _global_cache_path("crm_prescritores_global")
_MEMORIA_CALCULO_GLOBAL_PARQUET_PATH = _global_cache_path("memoria_calculo_global")
_CRM_RAIOX_TX_GLOBAL_PARQUET_PATH = _global_cache_path("crm_raiox_tx_global")
_PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH = _global_cache_path(
    "pagamentos_consolidados_farmacia_popular"
)
_DADOS_FARMACIA_PARQUET_PATH = _global_cache_path("dados_farmacia")
_DADOS_FARMACIA_CNAES_SECUNDARIOS_PARQUET_PATH = _global_cache_path(
    "dados_farmacia_cnaes_secundarios"
)
_PERFIL_ESTABELECIMENTO_PARQUET_PATH = _global_cache_path("perfil_estabelecimento")
_DADOS_SOCIOS_PARQUET_PATH = _global_cache_path("dados_socios")
_TEIA_FONTE_NIVEL2_PARQUET_PATH = _global_cache_path("teia_fonte_nivel2")
_TEIA_FONTE_NIVEL3_PARQUET_PATH = _global_cache_path("teia_fonte_nivel3")
_TEIA_FONTE_NIVEL4_PARQUET_PATH = _global_cache_path("teia_fonte_nivel4")
_MEDICAMENTOS_PARQUET_PATH = _global_cache_path("medicamentos")
_FALECIDOS_PARQUET_PATH = _global_cache_path("falecidos")
_ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH = _global_cache_path("analise_gtin_inconsistencia_clinica")
_ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH = _global_cache_path("analise_gtin_inconsistencia_clinica_municipio")
_ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH = _global_cache_path("analise_gtin_inconsistencia_clinica_regiao")
_DADOS_IBGE_DEMOGRAFIA_PARQUET_PATH = _global_cache_path("dados_ibge_demografia")
_VOLUME_ATIPICO_SEMESTRAL_PARQUET_PATH = _global_cache_path("volume_atipico_semestral")
_GEOGRAFICO_ORIGEM_UF_PARQUET_PATH = _global_cache_path("geografico_origem_uf")
_ESOCIAL_CNPJ_ANO_PARQUET_PATH = _global_cache_path("esocial_cnpj_ano")
_ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH = _global_cache_path("esocial_cnpj_trabalhador_ano")
_ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH = _global_cache_path("esocial_cnpj_movimentacao_ano")
_ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH = _global_cache_path("esocial_cnpj_ultima_movimentacao")
_SENTINELA_METADADOS_BASE_PARQUET_PATH = _global_cache_path("sentinela_metadados_base")
_DADOS_PAR_PARQUET_PATH = _global_cache_path("dados_par")
_PAR_TEIA_ALVOS_PARQUET_PATH = _global_cache_path("par_teia_alvos")
_GEOGRAFICO_GLOBAL_PARQUET_PATH = _global_cache_path("geografico_global")
_CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH = _global_cache_path("crm_concentracao_unico_alertas_global")
_CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH = _global_cache_path("crm_concentracao_multiplo_alertas_global")
_CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH = _global_cache_path("crm_timeline_dia_global")
_CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH = _global_cache_path("crm_timeline_hora_global")
_CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH = _global_cache_path("crm_timeline_eventos_global")
_MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH = _global_cache_path("movimentacao_mensal_gtin_global")


for _dir in (get_modules_dir(), _CACHE_DIR, get_cnpj_cache_root()):
    if not os.path.exists(_dir):
        os.makedirs(_dir, exist_ok=True)

# Estados Globais
_df_movimentacao: pl.DataFrame | None = None
_df_localidades: pl.DataFrame | None = None
_df_rede: pl.DataFrame | None = None
_df_matriz_risco: pl.DataFrame | None = None
_df_bench_crm_uf: pl.DataFrame | None = None
_df_bench_crm_regiao: pl.DataFrame | None = None
_df_bench_crm_br: pl.DataFrame | None = None
_df_dados_farmacia: pl.DataFrame | None = None
_df_dados_farmacia_cnaes_secundarios: pl.DataFrame | None = None
_df_perfil_estabelecimento: pl.DataFrame | None = None
_df_dados_socios:   pl.DataFrame | None = None
_df_teia_fonte_nivel2: pl.DataFrame | None = None
_df_teia_fonte_nivel3: pl.DataFrame | None = None
_df_teia_fonte_nivel4: pl.DataFrame | None = None
_df_medicamentos:   pl.DataFrame | None = None
_df_falecidos: pl.DataFrame | None = None
_df_analise_gtin_inconsistencia_clinica: pl.DataFrame | None = None
_df_analise_gtin_inconsistencia_clinica_municipio: pl.DataFrame | None = None
_df_analise_gtin_inconsistencia_clinica_regiao: pl.DataFrame | None = None
_df_dados_ibge_demografia: pl.DataFrame | None = None
_df_volume_atipico_semestral: pl.DataFrame | None = None
_df_esocial_cnpj_ano: pl.DataFrame | None = None
_df_esocial_cnpj_trabalhador_ano: pl.DataFrame | None = None
_df_esocial_cnpj_movimentacao_ano: pl.DataFrame | None = None
_df_esocial_cnpj_ultima_movimentacao: pl.DataFrame | None = None
_df_sentinela_metadados_base: pl.DataFrame | None = None
_df_dados_par: pl.DataFrame | None = None
_df_par_teia_alvos: pl.DataFrame | None = None

_cache_progress: int = 0
_cache_status: str = "idle"
_cache_error_message: str = ""
_cache_generation: int = 0

def _get_cache_module_status(loaded: bool, exists: bool) -> str:
    if loaded:
        return "loaded"
    if exists:
        return "error"
    return "missing"

def _empty_dados_par_df() -> pl.DataFrame:
    return pl.DataFrame(schema={
        "cnpj": pl.Utf8,
        "is_par": pl.Boolean,
        "qtd_processos_par": pl.Int32,
        "par_situacoes": pl.Utf8,
        "par_primeira_instauracao": pl.Date,
        "par_ultima_instauracao": pl.Date,
        "par_ultima_conclusao": pl.Date,
    })

def _empty_par_teia_alvos_df() -> pl.DataFrame:
    return pl.DataFrame(schema={
        "cnpj": pl.Utf8,
        "has_par_alvo": pl.Boolean,
        "has_par_n2": pl.Boolean,
        "has_par_n4": pl.Boolean,
        "has_par_qualquer": pl.Boolean,
        "qtd_par_alvo": pl.Int32,
        "qtd_empresas_par_n2": pl.Int32,
        "qtd_empresas_par_n4": pl.Int32,
        "qtd_empresas_par_qualquer": pl.Int32,
    })


def _buscar_cnpjs_matriz(engine) -> list[str]:
    """Busca os CNPJs ativos da matriz de risco para sincronizacao em lote."""
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT DISTINCT F.cnpj
            FROM [temp_CGUSC].[fp].[matriz_risco_consolidada] M
            INNER JOIN [temp_CGUSC].[fp].[dados_farmacia] F
                ON F.id = M.id_cnpj
            ORDER BY F.cnpj
        """))
        return [str(row[0]).strip() for row in res if row[0]]


# --- MOTOR DE SINCRONIZAÇÃO (SYNC ENGINE) ---

def _assert_fp_source_table(engine, table_name: str, required_columns: set[str]) -> int:
    """Valida contrato minimo de uma tabela fonte em temp_CGUSC.fp."""
    full_name = f"temp_CGUSC.fp.{table_name}"
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT OBJECT_ID(:full_name, 'U')"),
            {"full_name": full_name},
        ).scalar()
        if exists is None:
            raise RuntimeError(f"Tabela fonte {full_name} nao encontrada para sincronizacao de cache.")

        rows = conn.execute(text(f"SELECT COUNT_BIG(*) FROM [temp_CGUSC].[fp].[{table_name}]")).scalar()
        if rows == 0:
            raise RuntimeError(f"Tabela fonte {full_name} esta vazia para sincronizacao de cache.")

        cols = {
            row[0]
            for row in conn.execute(text("""
                SELECT COLUMN_NAME
                FROM temp_CGUSC.INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'fp'
                  AND TABLE_NAME = :table_name
            """), {"table_name": table_name})
        }

    missing_cols = required_columns - cols
    if missing_cols:
        raise RuntimeError(
            f"Tabela fonte {full_name} sem colunas obrigatorias: "
            + ", ".join(sorted(missing_cols))
        )
    return int(rows)


def _sync_falecidos(engine, progress_callback=None):
    """Sincroniza o detalhamento global de vendas para pessoas falecidas."""
    global _df_falecidos
    print("Sincronizando Falecidos por Farmacia...")
    required = {
        "cnpj",
        "cpf",
        "nome_falecido",
        "municipio_falecido",
        "uf_falecido",
        "dt_nascimento",
        "dt_obito",
        "fonte_obito",
        "num_autorizacao",
        "data_autorizacao",
        "qtd_itens_na_autorizacao",
        "valor_total_autorizacao",
        "dias_apos_obito",
    }
    total_rows = _assert_fp_source_table(engine, "falecidos_por_farmacia", required)
    sql = """
        SELECT
            cnpj,
            cpf,
            nome_falecido,
            municipio_falecido,
            uf_falecido,
            dt_nascimento,
            dt_obito,
            fonte_obito,
            num_autorizacao,
            data_autorizacao,
            qtd_itens_na_autorizacao,
            CAST(valor_total_autorizacao AS FLOAT) AS valor_total_autorizacao,
            dias_apos_obito
        FROM [temp_CGUSC].[fp].[falecidos_por_farmacia]
    """

    print(f"   -> Registros de falecidos: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    chunk_size = 50_000
    for chunk in pd.read_sql(sql, engine, chunksize=chunk_size):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("cnpj").cast(pl.String).str.replace_all(r"\D", "").str.zfill(14),
            pl.col("cpf").cast(pl.String).str.replace_all(r"\D", "").str.zfill(11),
            pl.col("nome_falecido").cast(pl.String),
            pl.col("municipio_falecido").cast(pl.String),
            pl.col("uf_falecido").cast(pl.String),
            pl.col("dt_nascimento").cast(pl.Date, strict=False),
            pl.col("dt_obito").cast(pl.Date, strict=False),
            pl.col("fonte_obito").cast(pl.String),
            pl.col("num_autorizacao").cast(pl.String),
            pl.col("data_autorizacao").cast(pl.Date, strict=False),
            pl.col("qtd_itens_na_autorizacao").cast(pl.Int64),
            pl.col("valor_total_autorizacao").cast(pl.Float64),
            pl.col("dias_apos_obito").cast(pl.Int64),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100)
        if progress_callback:
            progress_callback(p)

    if not chunk_list:
        raise RuntimeError("Tabela fonte temp_CGUSC.fp.falecidos_por_farmacia nao retornou linhas para sincronizacao.")

    df_falecidos = pl.concat(chunk_list).sort(["cnpj", "cpf", "data_autorizacao"])
    df_falecidos.write_parquet(_FALECIDOS_PARQUET_PATH, compression="zstd")
    _df_falecidos = df_falecidos


def _sync_cnpj_parquets(engine, progress_callback=None, cnpjs: list[str] | None = None):
    """Gera todos os parquets mantidos em modules/cnpjs/<cnpj>/."""
    import cache_manager

    print("Atualizando indicadores PAR antes da teia por CNPJ...")
    _sync_dados_par(engine)

    if not cnpjs:
        cnpjs = _buscar_cnpjs_matriz(engine)

    cache_manager.sync_cnpj_caches(engine, cnpjs, progress_callback)


def _sync_teia_expansao_completa(engine, progress_callback=None):
    """Sincroniza participacoes externas (G2), socios indiretos (G3) e expansao nacional (G4)."""
    print("\n  -> [1/3] Sincronizando Participacoes Externas (Grau 2)...")
    _sync_teia_fonte_nivel2(engine, lambda p: progress_callback(int(p * 0.33)) if progress_callback else None)

    print("\n  -> [2/3] Sincronizando Socios Indiretos (Grau 3)...")
    _sync_teia_fonte_nivel3(engine, lambda p: progress_callback(int(33 + p * 0.33)) if progress_callback else None)

    print("\n  -> [3/3] Sincronizando Expansao Nacional (Grau 4)...")
    _sync_teia_fonte_nivel4(engine, lambda p: progress_callback(int(66 + p * 0.34)) if progress_callback else None)

    if progress_callback:
        progress_callback(100)


def _sync_localidades(engine, progress_callback=None):
    """Tarefa 1: Sincroniza dados geográficos (IBGE)."""
    global _df_localidades
    print("Sincronizando Localidades (IBGE)...")
    sql = """
        SELECT I.sg_uf, I.no_regiao_saude, I.id_regiao_saude, I.no_municipio, I.id_ibge7, I.nu_populacao,
               J.unidade_pf
        FROM [temp_CGUSC].[fp].[dados_ibge] I
        LEFT JOIN (
            SELECT codIBGE, MIN(nome_unidade_PF) as unidade_pf 
            FROM [temp_CGUSC].[fp].[jurisdicoes_pf] 
            GROUP BY codIBGE
        ) J ON J.codIBGE = I.id_ibge7
        WHERE I.sg_uf <> 'BR'
        ORDER BY I.sg_uf, I.no_regiao_saude, I.no_municipio
    """
    pdf = pd.read_sql(sql, engine)
    print(f"   -> Localidades carregadas: {len(pdf):,} registros.")
    if progress_callback: progress_callback(100)
    df_localidades = pl.from_pandas(pdf).with_columns([
        pl.col("sg_uf").cast(pl.Categorical),
        pl.col("no_regiao_saude").cast(pl.Categorical),
        pl.col("no_municipio").cast(pl.Categorical),
        pl.col("unidade_pf").cast(pl.Categorical),
    ])
    df_localidades.write_parquet(_LOCALIDADES_PARQUET_PATH, compression="zstd")
    _df_localidades = df_localidades

def _sync_rede(engine, progress_callback=None):
    """Tarefa 2: Sincroniza a tabela de rede de estabelecimentos."""
    global _df_rede
    print("Sincronizando Rede de Estabelecimentos...")
    sql = "SELECT * FROM [temp_CGUSC].[fp].[rede_estabelecimentos]"
    
    pdf = pd.read_sql(sql, engine)
    print(f"   -> Rede carregada com sucesso: {len(pdf):,} registros.")
    if progress_callback: progress_callback(100)
    
    df_rede = pl.from_pandas(pdf).with_columns([
        pl.col("cnpj_raiz").cast(pl.String),
        pl.col("cnpj").cast(pl.String),
        pl.col("razao_social").cast(pl.String),
        pl.col("uf").cast(pl.Categorical),
        pl.col("municipio").cast(pl.String),
        pl.col("is_matriz").cast(pl.Boolean),
        pl.col("qtd_estabelecimentos_rede").cast(pl.Int64),
        pl.col("is_grande_rede").cast(pl.Boolean),
    ]).sort(["cnpj_raiz", "cnpj"])
    df_rede.write_parquet(_REDE_PARQUET_PATH, compression="zstd")
    _df_rede = df_rede

def _sync_matriz_risco(engine, progress_callback=None):
    """Tarefa 4: Sincroniza a matriz anual de componentes dos indicadores."""
    global _df_matriz_risco
    print("Sincronizando Matriz Anual de Componentes dos Indicadores...")
    sql = "SELECT * FROM [temp_CGUSC].[fp].[matriz_risco_consolidada]"
    
    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[matriz_risco_consolidada]")).scalar()
    
    print(f"   -> Registros na Matriz: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 2_000
    
    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_list.append(pl.from_pandas(chunk))
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso Matriz: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback: progress_callback(p)
            
    if not chunk_list:
        raise RuntimeError("matriz_risco_consolidada nao retornou linhas para sincronizacao.")

    schema = _GLOBAL_PARQUET_SCHEMAS["matriz_risco"]
    cast_exprs = [pl.col(col).cast(dtype, strict=False) for col, dtype in schema.items()]
    typed_chunks = [chunk.with_columns(cast_exprs).select(list(schema.keys())) for chunk in chunk_list]
    df_matriz_risco = (
        pl.concat(typed_chunks)
        .sort(["id_cnpj", "ano_base"])
    )
    df_matriz_risco.write_parquet(_MATRIZ_PARQUET_PATH, compression="zstd")
    _df_matriz_risco = df_matriz_risco

def _sync_volume_atipico_semestral(engine, progress_callback=None):
    """Sincroniza a base semestral crua do filtro dinamico de volume atipico."""
    global _df_volume_atipico_semestral
    print("Sincronizando Volume Atipico Semestral...")
    sql = """
        SELECT
            id_cnpj,
            chave_semestre,
            status_semestre,
            qtd_meses_presentes,
            chave_semestre_anterior,
            aumento_valor_semestre,
            taxa_crescimento_pct
        FROM [temp_CGUSC].[fp].[volume_atipico_semestral]
    """

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[volume_atipico_semestral]")).scalar()

    print(f"   -> Registros semestrais: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 20_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("chave_semestre").cast(pl.Int32),
            pl.col("status_semestre").cast(pl.Int8),
            pl.col("qtd_meses_presentes").cast(pl.Int8),
            pl.col("chave_semestre_anterior").cast(pl.Int32, strict=False),
            pl.col("aumento_valor_semestre").cast(pl.Float64, strict=False),
            pl.col("taxa_crescimento_pct").cast(pl.Float32),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso Volume Atipico: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback:
            progress_callback(p)

    df_volume_atipico_semestral = (
        pl.concat(chunk_list).sort(["id_cnpj", "chave_semestre"])
        if chunk_list else pl.DataFrame()
    )
    df_volume_atipico_semestral.write_parquet(
        _VOLUME_ATIPICO_SEMESTRAL_PARQUET_PATH,
        compression="zstd",
    )
    _df_volume_atipico_semestral = df_volume_atipico_semestral

def _sync_geografico_origem_uf(engine, progress_callback=None):
    """Sincroniza a distribuicao geografica por UF de residencia do paciente."""
    print("Sincronizando Geografico Origem UF...")
    required = {
        "id_cnpj",
        "ano_base",
        "uf_farmacia",
        "uf_paciente",
        "is_outra_uf",
        "qtd_autorizacoes",
        "valor_autorizado",
    }
    total_rows = _assert_fp_source_table(
        engine,
        "indicador_geografico_origem_uf",
        required,
    )

    sql = """
        SELECT
            id_cnpj,
            ano_base,
            uf_farmacia,
            uf_paciente,
            is_outra_uf,
            qtd_autorizacoes,
            valor_autorizado
        FROM [temp_CGUSC].[fp].[indicador_geografico_origem_uf]
    """

    print(f"   -> Registros geografico origem UF: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    chunk_size = 50_000

    for chunk in pd.read_sql(sql, engine, chunksize=chunk_size):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("ano_base").cast(pl.Int16),
            pl.col("uf_farmacia").cast(pl.String),
            pl.col("uf_paciente").cast(pl.String),
            pl.col("is_outra_uf").cast(pl.Boolean),
            pl.col("qtd_autorizacoes").cast(pl.Int32),
            pl.col("valor_autorizado").cast(pl.Float64),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso Geografico Origem UF: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback:
            progress_callback(p)

    df_geografico_origem_uf = (
        pl.concat(chunk_list).sort(["id_cnpj", "ano_base", "uf_paciente"])
    )
    df_geografico_origem_uf.write_parquet(
        _GEOGRAFICO_ORIGEM_UF_PARQUET_PATH,
        compression="zstd",
    )
    _mark_on_demand_global_cache_ready(
        "geografico_origem_uf",
        _GEOGRAFICO_ORIGEM_UF_PARQUET_PATH,
    )


def _sync_crm_prescritores_global(engine, progress_callback=None):
    """Sincroniza prescritores CRM global em partes por competencia retomaveis."""
    print("Sincronizando CRM prescritores global...")
    schema = _GLOBAL_PARQUET_SCHEMAS["crm_prescritores_global"]
    final_path = _CRM_PRESCRITORES_GLOBAL_PARQUET_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "crm_prescritores_global"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def competencia_key(value: int) -> str:
        return str((value))

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        competencias_rows = conn.execute(text("""
            SELECT DISTINCT E.competencia
            FROM temp_CGUSC.fp.app_crm_export E
            WHERE E.competencia IS NOT NULL
            ORDER BY E.competencia
        """)).fetchall()

        competencias = [int(row[0]) for row in competencias_rows]
        if not competencias:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.app_crm_export nao possui competencias para "
                "gerar o cache CRM prescritores global."
            )

        manifest = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "crm_prescritores_global"
            and manifest.get("version") == CRM_PRESCRITORES_CACHE_VERSION
            and manifest.get("start_competencia") == competencia_key(competencias[0])
            and manifest.get("end_competencia") == competencia_key(competencias[-1])
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "crm_prescritores_global",
                "version": CRM_PRESCRITORES_CACHE_VERSION,
                "start_competencia": competencia_key(competencias[0]),
                "end_competencia": competencia_key(competencias[-1]),
                "parts": {},
            }
            write_manifest(manifest)

        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError("manifesto de CRM prescritores global com campo parts invalido")

        query = text("""
            SELECT
                E.id_cnpj,
                E.id_medico,
                E.competencia,
                E.vl_total_prescricoes,
                E.nu_prescricoes_mes,
                E.nu_prescricoes_total_brasil,
                E.flag_crm_invalido,
                E.flag_prescricao_antes_registro,
                E.alerta_concentracao_multiplos_crms,
                E.flag_concentracao_mesmo_crm,
                E.flag_distancia_geografica,
                E.dt_inscricao_crm,
                E.nu_estabelecimentos
            FROM temp_CGUSC.fp.app_crm_export E
            WHERE E.competencia = :competencia
            ORDER BY E.id_cnpj, E.id_medico
        """)

        total_parts = len(competencias)
        for index, competencia in enumerate(competencias, 1):
            key = competencia_key(competencia)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> CRM prescritores global parte {index}/{total_parts}: {key}")
            pdf = pd.read_sql(query, conn, params={"competencia": competencia})
            if pdf.empty:
                df_part = pl.DataFrame(schema=schema)
            else:
                df_part = (
                    pl.from_pandas(pdf)
                    .with_columns([
                        pl.col("id_cnpj").cast(pl.Int32),
                        pl.col("id_medico").cast(pl.Utf8),
                        pl.col("competencia").cast(pl.Int32),
                        pl.col("vl_total_prescricoes").cast(pl.Float64),
                        pl.col("nu_prescricoes_mes").cast(pl.Int32),
                        pl.col("nu_prescricoes_total_brasil").cast(pl.Int32),
                        pl.col("flag_crm_invalido").cast(pl.Int8),
                        pl.col("flag_prescricao_antes_registro").cast(pl.Int8),
                        pl.col("alerta_concentracao_multiplos_crms").cast(pl.Int8),
                        pl.col("flag_concentracao_mesmo_crm").cast(pl.Int8),
                        pl.col("flag_distancia_geografica").cast(pl.Int8),
                        pl.col("dt_inscricao_crm").cast(pl.Date),
                        pl.col("nu_estabelecimentos").cast(pl.Int32),
                    ])
                    .with_columns([
                        pl.lit(CRM_PRESCRITORES_CACHE_VERSION)
                        .alias("_crm_prescritores_cache_version"),
                    ])
                )
            df_part = df_part.select(list(schema.keys()))

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(competencia_key(competencia)) for competencia in competencias]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar crm_prescritores_global: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando CRM prescritores global...")
    final_scan = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(list(schema.keys()))
    )
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["final_rows"] = sum(
        int(info.get("rows", 0))
        for info in parts.values()
    )
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready("crm_prescritores_global", final_path)
    if progress_callback:
        progress_callback(100)


def _sync_memoria_calculo_global(engine, progress_callback=None):
    """Sincroniza a memoria de calculo global em partes por prefixo de CNPJ."""
    print("Sincronizando memoria de calculo global...")
    schema = _GLOBAL_PARQUET_SCHEMAS["memoria_calculo_global"]
    final_path = _MEMORIA_CALCULO_GLOBAL_PARQUET_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "memoria_calculo_global"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def prefix_key(value: str) -> str:
        return (value).zfill(2)

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    def normalize_payload(value: Any) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        if isinstance(value, memoryview):
            return value.tobytes()
        return bytes(value)

    with engine.connect() as conn:
        prefixes_rows = conn.execute(text("""
            SELECT DISTINCT LEFT(CAST(cnpj AS VARCHAR(14)), 2) AS prefixo
            FROM temp_CGUSC.fp.memoria_calculo_consolidada
            WHERE cnpj IS NOT NULL
              AND memoria_calculo_payload IS NOT NULL
            ORDER BY prefixo
        """)).fetchall()

        prefixes = [prefix_key(row[0]) for row in prefixes_rows if row[0] is not None]
        if not prefixes:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.memoria_calculo_consolidada nao possui dados "
                "para gerar o cache memoria_calculo_global."
            )

        manifest = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "memoria_calculo_global"
            and manifest.get("version") == MEMORIA_CALCULO_CACHE_VERSION
            and manifest.get("start_prefix") == prefixes[0]
            and manifest.get("end_prefix") == prefixes[-1]
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "memoria_calculo_global",
                "version": MEMORIA_CALCULO_CACHE_VERSION,
                "start_prefix": prefixes[0],
                "end_prefix": prefixes[-1],
                "parts": {},
            }
            write_manifest(manifest)

        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError("manifesto de memoria_calculo_global com campo parts invalido")

        query = text("""
            WITH ranked AS (
                SELECT
                    CAST(cnpj AS VARCHAR(14)) AS cnpj,
                    CAST(id_processamento AS BIGINT) AS id_processamento,
                    CAST(schema_version AS INT) AS schema_version,
                    memoria_calculo_payload,
                    ROW_NUMBER() OVER (
                        PARTITION BY CAST(cnpj AS VARCHAR(14))
                        ORDER BY id_processamento DESC
                    ) AS rn
                FROM temp_CGUSC.fp.memoria_calculo_consolidada
                WHERE cnpj IS NOT NULL
                  AND memoria_calculo_payload IS NOT NULL
                  AND LEFT(CAST(cnpj AS VARCHAR(14)), 2) = :prefixo
            )
            SELECT
                cnpj,
                id_processamento,
                schema_version,
                memoria_calculo_payload
            FROM ranked
            WHERE rn = 1
            ORDER BY cnpj
        """)

        total_parts = len(prefixes)
        for index, prefix in enumerate(prefixes, 1):
            output_path = part_path(prefix)
            info = parts.get(prefix, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> Memoria calculo global parte {index}/{total_parts}: prefixo {prefix}")
            pdf = pd.read_sql(query, conn, params={"prefixo": prefix})
            if pdf.empty:
                df_part = pl.DataFrame(schema=schema)
            else:
                pdf["memoria_calculo_payload"] = pdf["memoria_calculo_payload"].map(normalize_payload)
                df_part = (
                    pl.from_pandas(pdf)
                    .with_columns([
                        pl.col("cnpj").cast(pl.Utf8),
                        pl.col("id_processamento").cast(pl.Int64),
                        pl.col("schema_version").cast(pl.Int32),
                        pl.col("memoria_calculo_payload").cast(pl.Binary),
                    ])
                    .with_columns([
                        pl.lit(MEMORIA_CALCULO_CACHE_VERSION)
                        .alias("_memoria_calculo_cache_version"),
                    ])
                )
            df_part = df_part.select(list(schema.keys()))

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[prefix] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(prefix) for prefix in prefixes]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar memoria_calculo_global: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando memoria calculo global...")
    final_scan = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(list(schema.keys()))
    )
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["final_rows"] = sum(
        int(info.get("rows", 0))
        for info in parts.values()
    )
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)

    _mark_on_demand_global_cache_ready("memoria_calculo_global", final_path)
    if progress_callback:
        progress_callback(100)



def _sync_geografico_global(engine, progress_callback=None):
    print("Sincronizando CRM Geografico Global...")
    query = text("""
        SELECT A.id_medico, A.competencia,
               A.cnpj_a, A.no_municipio_a, A.sg_uf_a,
               CONVERT(VARCHAR(10), A.dt_ini_a, 23) AS dt_ini_a,
               CONVERT(VARCHAR(10), A.dt_fim_a, 23) AS dt_fim_a,
               A.nu_prescricoes_a, A.vl_autorizacoes_a,
               A.cnpj_b, A.no_municipio_b, A.sg_uf_b,
               CONVERT(VARCHAR(10), A.dt_ini_b, 23) AS dt_ini_b,
               CONVERT(VARCHAR(10), A.dt_fim_b, 23) AS dt_fim_b,
               A.nu_prescricoes_b, A.vl_autorizacoes_b,
               A.vl_autorizacoes_total, A.distancia_km
        FROM temp_CGUSC.fp.app_alertas_crm_geografico A
    """)
    _load_or_sync_global_cache_simple("geografico_global", _GEOGRAFICO_GLOBAL_PARQUET_PATH, query, engine, progress_callback)


def _sync_crm_concentracao_unico_alertas_global(engine, progress_callback=None):
    print("Sincronizando CRM Concentracao Unico Alertas Global...")
    query = text("""
        SELECT A.id_cnpj, A.id_medico, YEAR(A.dt_dia) * 100 + MONTH(A.dt_dia) AS competencia,
               A.dt_dia AS dt_alerta, DATEPART(HOUR, A.dt_ini_concentracao) AS hr_janela,
               A.nu_autorizacoes_pior_ritmo AS nu_prescricoes_dia,
               A.janela_pior_ritmo_minutos AS nu_minutos_dia,
               A.nu_minutos_span AS nu_minutos_intervalo,
               A.taxa_hora_pior_ritmo AS taxa_hora,
               A.dt_ini_concentracao AS dt_ini_hora,
               A.dt_fim_concentracao AS dt_fim_hora,
               A.id_severidade,
               CASE A.id_severidade WHEN 4 THEN 'EXTREMO' WHEN 3 THEN 'CRITICO'
                    WHEN 2 THEN 'GRAVE' WHEN 1 THEN 'ALTO' ELSE 'ALERTA' END AS severidade,
               A.criterio_pior_ritmo, A.nu_5min, A.nu_10min, A.nu_15min,
               A.nu_20min, A.nu_25min, A.nu_30min, A.nu_60min
        FROM temp_CGUSC.fp.app_crm_concentracao_unico_alertas A
    """)
    _load_or_sync_global_cache_simple(
        "crm_concentracao_unico_alertas_global",
        _CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH,
        query, engine, progress_callback,
        extra_columns={"_crm_alerts_cache_version": 4} # _CRM_ALERTS_CACHE_VERSION from crm.py
    )

def _sync_crm_concentracao_multiplo_alertas_global(engine, progress_callback=None):
    print("Sincronizando CRM Concentracao Multiplo Alertas Global...")
    query = text("""
        SELECT A.id_cnpj, YEAR(A.dt_dia) * 100 + MONTH(A.dt_dia) AS competencia,
               A.dt_dia, A.dt_ini_concentracao AS dt_alerta,
               DATEPART(HOUR, A.dt_ini_concentracao) AS hr_janela,
               A.dt_ini_concentracao, A.dt_fim_concentracao,
               A.nu_autorizacoes_pior_ritmo AS nu_prescricoes,
               A.nu_crms_distintos AS nu_crms, A.nu_60min,
               A.nu_minutos_span AS nu_minutos_intervalo,
               A.janela_pior_ritmo_minutos AS nu_minutos_span,
               A.taxa_hora_pior_ritmo AS taxa_hora,
               A.id_severidade,
               A.nu_crms_distintos,
               CASE A.id_severidade WHEN 4 THEN 'EXTREMO' WHEN 3 THEN 'CRITICO'
                    WHEN 2 THEN 'GRAVE' WHEN 1 THEN 'ALTO' ELSE 'ALERTA' END AS severidade,
               A.criterio_pior_ritmo, A.nu_5min, A.nu_10min, A.nu_15min,
               A.nu_20min, A.nu_25min, A.nu_30min
        FROM temp_CGUSC.fp.app_crm_concentracao_multiplo_alertas A
    """)
    _load_or_sync_global_cache_simple(
        "crm_concentracao_multiplo_alertas_global",
        _CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH,
        query, engine, progress_callback,
        extra_columns={"_crm_alerts_cache_version": 4}
    )

def _sync_crm_timeline_dia_global(engine, progress_callback=None):
    """Sincroniza o CRM Timeline Dia global em partes mensais retomaveis."""
    print("Sincronizando CRM Timeline Dia Global...")
    schema = _GLOBAL_PARQUET_SCHEMAS["crm_timeline_dia_global"]
    final_path = _CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "crm_timeline_dia_global"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def month_floor(value) -> date:
        value_date = value.date() if hasattr(value, "date") else value
        return date(value_date.year, value_date.month, 1)

    def next_month(value: date) -> date:
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    def month_key(value: date) -> str:
        return f"{value.year:04d}-{value.month:02d}"

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        bounds = conn.execute(text("""
            SELECT MIN(P.dt_janela) AS dt_min, MAX(P.dt_janela) AS dt_max
            FROM temp_CGUSC.fp.app_crm_timeline_dia P
        """)).mappings().first()

        if not bounds or bounds["dt_min"] is None or bounds["dt_max"] is None:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.app_crm_timeline_dia nao possui periodos para "
                "gerar o cache CRM Timeline Dia global."
            )

        start_month = month_floor(bounds["dt_min"])
        end_month = month_floor(bounds["dt_max"])
        end_exclusive = next_month(end_month)
        month_starts: list[date] = []
        cursor = start_month
        while cursor < end_exclusive:
            month_starts.append(cursor)
            cursor = next_month(cursor)

        manifest: dict[str, Any] = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "crm_timeline_dia_global"
            and manifest.get("start_month") == month_key(start_month)
            and manifest.get("end_month") == month_key(end_month)
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "crm_timeline_dia_global",
                "start_month": month_key(start_month),
                "end_month": month_key(end_month),
                "parts": {},
            }
            write_manifest(manifest)
        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError("manifesto de CRM Timeline Dia global com campo parts invalido")

        query = text("""
            SELECT CONVERT(VARCHAR(10), P.dt_janela, 23) AS dt_janela,
                   P.id_cnpj, P.competencia, P.nu_prescricoes_dia, P.nu_crms_distintos, P.mediana_diaria,
                   P.is_dia_com_volume_horario_anomalo, P.is_anomalo_unico, P.is_crm_multiplo,
                   P.score_crm_unico_hora, P.score_crm_unico_qtd, P.score_crm_unico_minutos,
                   P.score_crm_unico_medico, P.score_crm_multiplo_hora, P.score_crm_multiplo_qtd,
                   P.score_crm_multiplo_minutos, P.score_crm_multiplo_crms
            FROM temp_CGUSC.fp.app_crm_timeline_dia P
            WHERE P.dt_janela >= :dt_inicio AND P.dt_janela < :dt_fim
        """)

        total_parts = len(month_starts)
        for index, dt_inicio in enumerate(month_starts, 1):
            dt_fim = next_month(dt_inicio)
            key = month_key(dt_inicio)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> CRM Timeline Dia global parte {index}/{total_parts}: {key}")
            pdf = pd.read_sql(query, conn, params={"dt_inicio": dt_inicio, "dt_fim": dt_fim})
            if pdf.empty:
                df_part = pl.DataFrame(schema=schema)
            else:
                df_part = pl.from_pandas(pdf).with_columns([
                    pl.col("id_cnpj").cast(pl.Int32),
                    pl.col("dt_janela").cast(pl.Utf8),
                    pl.col("competencia").cast(pl.Int32),
                    pl.col("nu_prescricoes_dia").cast(pl.Int32),
                    pl.col("nu_crms_distintos").cast(pl.Int32),
                    pl.col("mediana_diaria").cast(pl.Float64),
                    pl.col("is_dia_com_volume_horario_anomalo").cast(pl.Int8),
                    pl.col("is_anomalo_unico").cast(pl.Int8),
                    pl.col("is_crm_multiplo").cast(pl.Int8),
                    pl.col("score_crm_unico_hora").cast(pl.Float64),
                    pl.col("score_crm_unico_qtd").cast(pl.Int32),
                    pl.col("score_crm_unico_minutos").cast(pl.Int32),
                    pl.col("score_crm_unico_medico").cast(pl.Utf8),
                    pl.col("score_crm_multiplo_hora").cast(pl.Float64),
                    pl.col("score_crm_multiplo_qtd").cast(pl.Int32),
                    pl.col("score_crm_multiplo_minutos").cast(pl.Int32),
                    pl.col("score_crm_multiplo_crms").cast(pl.Int32),
                ])
            df_part = df_part.select(list(schema.keys()))

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(month_key(dt_inicio)) for dt_inicio in month_starts]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar crm_timeline_dia_global: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando CRM Timeline Dia global...")
    final_scan = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(list(schema.keys()))
    )
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["final_rows"] = sum(
        int(info.get("rows", 0))
        for info in parts.values()
    )
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready("crm_timeline_dia_global", final_path)
    if progress_callback:
        progress_callback(100)

def _sync_crm_timeline_hora_global(engine, progress_callback=None):
    print("Sincronizando CRM Timeline Hora Global...")
    query = text("""
        SELECT CONVERT(VARCHAR(10), P.dt_janela, 23) AS dt_janela,
               P.id_cnpj, P.hr_janela, P.nu_prescricoes, P.nu_crms_diferentes, P.mediana_hora,
               P.mad_hora, P.is_hora_com_alerta, P.is_volume_horario_anomalo,
               P.is_crm_unico, P.is_crm_multiplo
        FROM temp_CGUSC.fp.app_crm_timeline_hora P
    """)
    _load_or_sync_global_cache_simple("crm_timeline_hora_global", _CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH, query, engine, progress_callback)

def _sync_crm_timeline_eventos_global(engine, progress_callback=None):
    print("Sincronizando CRM Timeline Eventos Global...")
    query = text("""
        SELECT CONVERT(VARCHAR(10), P.dt_janela, 23) AS dt_janela,
               P.id_cnpj, P.tipo, P.hora_inicio, P.hora_fim, P.minuto_inicio, P.minuto_fim,
               P.severidade, P.id_medico, P.nu_crms_distintos
        FROM temp_CGUSC.fp.app_crm_timeline_eventos P
    """)
    _load_or_sync_global_cache_simple("crm_timeline_eventos_global", _CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH, query, engine, progress_callback)


def _sync_movimentacao_mensal_gtin_global(engine, progress_callback=None):
    """Sincroniza a movimentacao mensal por GTIN em partes mensais retomaveis."""
    print("Sincronizando Movimentacao Mensal GTIN Global...")
    schema = _GLOBAL_PARQUET_SCHEMAS["movimentacao_mensal_gtin_global"]
    final_path = _MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "movimentacao_mensal_gtin_global"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def month_floor(value) -> date:
        value_date = value.date() if hasattr(value, "date") else value
        return date(value_date.year, value_date.month, 1)

    def next_month(value: date) -> date:
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    def month_key(value: date) -> str:
        return f"{value.year:04d}-{value.month:02d}"

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    def part_is_valid(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            part_columns = set(pl.scan_parquet(str(path)).collect_schema().names())
        except Exception:
            return False
        return set(schema).issubset(part_columns)

    with engine.connect() as conn:
        bounds = conn.execute(text("""
            SELECT MIN(m.periodo) AS dt_min, MAX(m.periodo) AS dt_max
            FROM [temp_CGUSC].[fp].[movimentacao_mensal_gtin] m
            INNER JOIN [temp_CGUSC].[fp].[processamento] p
                ON p.id = m.id_processamento
            WHERE p.situacao = 1
        """)).mappings().first()

        if not bounds or bounds["dt_min"] is None or bounds["dt_max"] is None:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.movimentacao_mensal_gtin nao possui periodos "
                "para gerar o cache movimentacao_mensal_gtin_global."
            )

        start_month = month_floor(bounds["dt_min"])
        end_month = month_floor(bounds["dt_max"])
        end_exclusive = next_month(end_month)
        month_starts: list[date] = []
        cursor = start_month
        while cursor < end_exclusive:
            month_starts.append(cursor)
            cursor = next_month(cursor)

        manifest: dict[str, Any] = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "movimentacao_mensal_gtin_global"
            and manifest.get("start_month") == month_key(start_month)
            and manifest.get("end_month") == month_key(end_month)
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "movimentacao_mensal_gtin_global",
                "start_month": month_key(start_month),
                "end_month": month_key(end_month),
                "parts": {},
            }
            write_manifest(manifest)

        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError("manifesto de movimentacao_mensal_gtin_global com campo parts invalido")

        query = text("""
            SELECT
                F.id AS id_cnpj,
                gtin.codigo_barra,
                CAST(m.periodo AS DATE) AS periodo,
                m.qnt_caixas_vendidas,
                m.qnt_caixas_sem_comprovacao,
                m.num_autorizacoes,
                CAST(m.valor_vendas AS FLOAT) AS valor_vendas,
                CAST(m.valor_sem_comprovacao AS FLOAT) AS valor_sem_comprovacao
            FROM [temp_CGUSC].[fp].[movimentacao_mensal_gtin] m
            INNER JOIN [temp_CGUSC].[fp].[processamento] p
                ON p.id = m.id_processamento
            INNER JOIN [temp_CGUSC].[fp].[medicamentos_patologia_chave] gtin
                ON gtin.id = m.id_gtin
            INNER JOIN [temp_CGUSC].[fp].[dados_farmacia] F
                ON F.cnpj = p.cnpj
            WHERE p.situacao = 1
              AND m.periodo >= :dt_inicio
              AND m.periodo < :dt_fim
            ORDER BY F.id, gtin.codigo_barra, m.periodo
        """)

        total_parts = len(month_starts)
        for index, dt_inicio in enumerate(month_starts, 1):
            dt_fim = next_month(dt_inicio)
            key = month_key(dt_inicio)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and part_is_valid(output_path):
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> GTIN Mensal global parte {index}/{total_parts}: {key}")
            pdf = pd.read_sql(query, conn, params={"dt_inicio": dt_inicio, "dt_fim": dt_fim})
            if pdf.empty:
                df_part = pl.DataFrame(schema=schema)
            else:
                df_part = pl.from_pandas(pdf).with_columns([
                    pl.col("id_cnpj").cast(pl.Int32),
                    pl.col("codigo_barra").cast(pl.Utf8),
                    pl.col("periodo").cast(pl.Date),
                    pl.col("qnt_caixas_vendidas").cast(pl.Int64),
                    pl.col("qnt_caixas_sem_comprovacao").cast(pl.Int64),
                    pl.col("num_autorizacoes").cast(pl.Int64),
                    pl.col("valor_vendas").cast(pl.Float64),
                    pl.col("valor_sem_comprovacao").cast(pl.Float64),
                ])
            df_part = df_part.select(list(schema.keys()))

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(month_key(dt_inicio)) for dt_inicio in month_starts]
    invalid_parts = [path.name for path in part_paths if not part_is_valid(path)]
    if invalid_parts:
        raise RuntimeError(
            "Partes pendentes ou invalidas para consolidar movimentacao_mensal_gtin_global: "
            + ", ".join(invalid_parts)
        )

    print("   -> Consolidando GTIN Mensal global...")
    final_scan = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(list(schema.keys()))
    )
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["final_rows"] = sum(
        int(info.get("rows", 0))
        for info in parts.values()
    )
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready("movimentacao_mensal_gtin_global", final_path)
    if progress_callback:
        progress_callback(100)

def _load_or_sync_global_cache_simple(name, filepath, query, engine, progress_callback=None, extra_columns=None):
    import pandas as pd
    t0 = time.perf_counter()
    with engine.connect() as conn:
        pdf = pd.read_sql(query, conn)

    df = pl.from_pandas(pdf)

    if extra_columns:
        df = df.with_columns([pl.lit(v).alias(k) for k, v in extra_columns.items()])

    schema = _GLOBAL_PARQUET_SCHEMAS.get(name)
    if schema:
        missing_schema_cols = [k for k in schema if k not in df.columns]
        if missing_schema_cols:
            raise ValueError(
                f"[ CACHE ] _load_or_sync_global_cache_simple ({name}): "
                f"colunas obrigatorias ausentes no resultado SQL: {', '.join(missing_schema_cols)}"
            )
        df = df.with_columns([pl.col(k).cast(v) for k, v in schema.items() if k in df.columns])
        df = df.select(list(schema.keys()))

    tmp_path = filepath + ".tmp"
    df.write_parquet(tmp_path, compression="zstd")
    os.replace(tmp_path, filepath)
    _mark_on_demand_global_cache_ready(name, filepath)
    print(f"[{time.perf_counter() - t0:.1f}s] {name} salvo com {df.height} linhas.")
    if progress_callback:
        progress_callback(100)


def _sync_crm_raiox_tx_global(engine, progress_callback=None):
    """Sincroniza o Raio-X CRM global em partes mensais retomaveis."""
    print("Sincronizando CRM Raio-X global...")
    schema = _GLOBAL_PARQUET_SCHEMAS["crm_raiox_tx_global"]
    final_path = _CRM_RAIOX_TX_GLOBAL_PARQUET_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "crm_raiox_tx_global"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def month_floor(value) -> date:
        value_date = value.date() if hasattr(value, "date") else value
        return date(value_date.year, value_date.month, 1)

    def next_month(value: date) -> date:
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    def month_key(value: date) -> str:
        return f"{value.year:04d}-{value.month:02d}"

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        bounds = conn.execute(text("""
            SELECT MIN(P.dt_janela) AS dt_min, MAX(P.dt_janela) AS dt_max
            FROM temp_CGUSC.fp.app_crm_raiox_tx P
        """)).mappings().first()

        if not bounds or bounds["dt_min"] is None or bounds["dt_max"] is None:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.app_crm_raiox_tx nao possui periodos para "
                "gerar o cache CRM Raio-X global."
            )

        start_month = month_floor(bounds["dt_min"])
        end_month = month_floor(bounds["dt_max"])
        end_exclusive = next_month(end_month)
        month_starts: list[date] = []
        cursor = start_month
        while cursor < end_exclusive:
            month_starts.append(cursor)
            cursor = next_month(cursor)

        manifest = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "crm_raiox_tx_global"
            and manifest.get("version") == CRM_RAIOX_TX_CACHE_VERSION
            and manifest.get("start_month") == month_key(start_month)
            and manifest.get("end_month") == month_key(end_month)
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "crm_raiox_tx_global",
                "version": CRM_RAIOX_TX_CACHE_VERSION,
                "start_month": month_key(start_month),
                "end_month": month_key(end_month),
                "parts": {},
            }
            write_manifest(manifest)
        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError("manifesto de CRM Raio-X global com campo parts invalido")

        query = text("""
            SELECT
                P.id_cnpj,
                P.dt_janela,
                P.hr_janela,
                MIN(P.data_hora) AS data_hora,
                P.num_autorizacao,
                P.id_medico,
                SUM(P.valor_pago) AS valor_pago
            FROM temp_CGUSC.fp.app_crm_raiox_tx P
            WHERE P.dt_janela >= :dt_inicio
              AND P.dt_janela < :dt_fim
            GROUP BY
                P.id_cnpj,
                P.dt_janela,
                P.hr_janela,
                P.num_autorizacao,
                P.id_medico
            ORDER BY P.id_cnpj, MIN(P.data_hora), P.num_autorizacao
        """)

        total_parts = len(month_starts)
        for index, dt_inicio in enumerate(month_starts, 1):
            dt_fim = next_month(dt_inicio)
            key = month_key(dt_inicio)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> CRM Raio-X global parte {index}/{total_parts}: {key}")
            pdf = pd.read_sql(query, conn, params={"dt_inicio": dt_inicio, "dt_fim": dt_fim})
            if pdf.empty:
                df_part = pl.DataFrame(schema=schema)
            else:
                df_part = pl.from_pandas(pdf).with_columns([
                    pl.col("id_cnpj").cast(pl.Int32),
                    pl.col("dt_janela").cast(pl.Utf8),
                    pl.col("hr_janela").cast(pl.Int32),
                    pl.col("data_hora").cast(pl.Utf8),
                    pl.col("num_autorizacao").cast(pl.Utf8),
                    pl.col("id_medico").cast(pl.Utf8),
                    pl.col("valor_pago").cast(pl.Float64),
                    pl.lit(CRM_RAIOX_TX_CACHE_VERSION).alias("_crm_raiox_tx_cache_version"),
                ])
            df_part = df_part.select(list(schema.keys()))

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(month_key(dt_inicio)) for dt_inicio in month_starts]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar crm_raiox_tx_global: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando CRM Raio-X global...")
    final_scan = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(list(schema.keys()))
    )
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["final_rows"] = sum(
        int(info.get("rows", 0))
        for info in parts.values()
    )
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready("crm_raiox_tx_global", final_path)
    if progress_callback:
        progress_callback(100)


def _sync_pagamentos_consolidados_farmacia_popular(engine, progress_callback=None):
    """Sincroniza pagamentos consolidados da Farmacia Popular em partes mensais retomaveis."""
    print("Sincronizando pagamentos consolidados Farmacia Popular global...")
    schema = _GLOBAL_PARQUET_SCHEMAS["pagamentos_consolidados_farmacia_popular"]
    final_path = _PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "pagamentos_consolidados_farmacia_popular"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def month_floor(value) -> date:
        value_date = value.date() if hasattr(value, "date") else value
        return date(value_date.year, value_date.month, 1)

    def next_month(value: date) -> date:
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    def month_key(value: date) -> str:
        return f"{value.year:04d}-{value.month:02d}"

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        bounds = conn.execute(text("""
            SELECT MIN(P.data_pagamento) AS dt_min, MAX(P.data_pagamento) AS dt_max
            FROM temp_CGUSC.fp.pagamentos_consolidados_farmacia_popular P
        """)).mappings().first()

        if not bounds or bounds["dt_min"] is None or bounds["dt_max"] is None:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.pagamentos_consolidados_farmacia_popular nao possui "
                "periodos para gerar o cache global de pagamentos."
            )

        start_month = month_floor(bounds["dt_min"])
        end_month = month_floor(bounds["dt_max"])
        end_exclusive = next_month(end_month)
        month_starts: list[date] = []
        cursor = start_month
        while cursor < end_exclusive:
            month_starts.append(cursor)
            cursor = next_month(cursor)

        manifest = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "pagamentos_consolidados_farmacia_popular"
            and manifest.get("version") == PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_CACHE_VERSION
            and manifest.get("start_month") == month_key(start_month)
            and manifest.get("end_month") == month_key(end_month)
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "pagamentos_consolidados_farmacia_popular",
                "version": PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_CACHE_VERSION,
                "start_month": month_key(start_month),
                "end_month": month_key(end_month),
                "parts": {},
            }
            write_manifest(manifest)
        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError(
                "manifesto de pagamentos consolidados Farmacia Popular com campo parts invalido"
            )

        query = text("""
            SELECT
                P.id_farmacia AS id_cnpj,
                P.data_pagamento,
                P.programa_acao,
                P.numero_ordem_bancaria,
                P.valor_pago
            FROM temp_CGUSC.fp.pagamentos_consolidados_farmacia_popular P
            WHERE P.data_pagamento >= :dt_inicio
              AND P.data_pagamento < :dt_fim
            ORDER BY P.id_farmacia, P.data_pagamento, P.numero_ordem_bancaria
        """)

        total_parts = len(month_starts)
        for index, dt_inicio in enumerate(month_starts, 1):
            dt_fim = next_month(dt_inicio)
            key = month_key(dt_inicio)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> Pagamentos FP global parte {index}/{total_parts}: {key}")
            pdf = pd.read_sql(query, conn, params={"dt_inicio": dt_inicio, "dt_fim": dt_fim})
            if pdf.empty:
                df_part = pl.DataFrame(schema=schema)
            else:
                df_part = pl.from_pandas(pdf).with_columns([
                    pl.col("id_cnpj").cast(pl.Int32),
                    pl.col("data_pagamento").cast(pl.Utf8),
                    pl.col("programa_acao").cast(pl.Utf8),
                    pl.col("numero_ordem_bancaria").cast(pl.Utf8),
                    pl.col("valor_pago").cast(pl.Float64),
                    pl.lit(PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_CACHE_VERSION).alias(
                        "_pagamentos_consolidados_farmacia_popular_cache_version"
                    ),
                ])
            df_part = df_part.select(list(schema.keys()))

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(month_key(dt_inicio)) for dt_inicio in month_starts]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar pagamentos_consolidados_farmacia_popular: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando pagamentos consolidados Farmacia Popular global...")
    final_scan = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(list(schema.keys()))
    )
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["final_rows"] = sum(
        int(info.get("rows", 0))
        for info in parts.values()
    )
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready("pagamentos_consolidados_farmacia_popular", final_path)
    if progress_callback:
        progress_callback(100)


def _sync_esocial(engine, progress_callback=None):
    """Sincroniza o contexto trabalhista anual do eSocial para uso analitico."""
    global _df_esocial_cnpj_ano, _df_esocial_cnpj_trabalhador_ano, _df_esocial_cnpj_movimentacao_ano, _df_esocial_cnpj_ultima_movimentacao
    print("Sincronizando contexto trabalhista eSocial...")

    trabalhador_required = {
        "id_cnpj",
        "ano_base",
        "mes_base",
        "competencia_base",
        "cpf_trabalhador",
        "matricula",
        "cbo",
        "titulo_cbo",
        "dt_admissao",
        "dt_rescisao",
        "is_farmaceutico",
        "is_cbo_sem_titulo",
        "dt_carga_fonte",
        "dt_processamento",
    }
    ano_required = {
        "id_cnpj",
        "ano_base",
        "mes_base",
        "competencia_base",
        "qtd_registros",
        "qtd_trabalhadores",
        "qtd_farmaceuticos",
        "qtd_trabalhadores_cbo_sem_titulo",
        "qtd_registros_farmaceuticos",
        "qtd_registros_cbo_sem_titulo",
        "has_farmaceutico",
        "has_cbo_sem_titulo",
        "is_um_trabalhador",
        "is_um_trabalhador_sem_farmaceutico",
        "is_um_trabalhador_cbo_sem_titulo",
        "cbo_unico_trabalhador",
        "titulo_cbo_unico_trabalhador",
        "qtd_registros_vinculo_ano",
        "qtd_trabalhadores_vinculo_ano",
        "qtd_farmaceuticos_vinculo_ano",
        "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano",
        "dt_carga_fonte",
        "dt_processamento",
    }
    movimentacao_required = {
        "id_cnpj",
        "ano_base",
        "id_regiao_saude",
        "uf",
        "periodo_min",
        "periodo_max",
        "valor_pfpb_ano",
        "valor_sem_comprovacao_ano",
        "qtd_autorizacoes_ano",
        "qtd_caixas_ano",
        "qtd_caixas_sem_comprovacao_ano",
        "qtd_trabalhadores",
        "qtd_farmaceuticos",
        "valor_pfpb_por_trabalhador",
        "valor_sem_comprovacao_por_trabalhador",
        "autorizacoes_por_trabalhador",
        "caixas_por_trabalhador",
        "p90_referencia_valor_pfpb_ano",
        "p95_referencia_valor_por_trabalhador",
        "qtd_cnpjs_referencia",
        "escopo_referencia",
        "classificacao_mov_trabalhista",
        "motivo_classificacao",
        "dt_processamento",
    }
    ultima_movimentacao_required = {
        "id_cnpj",
        "ano_ultima_movimentacao",
        "ano_esocial_referencia_ultima_movimentacao",
        "is_sem_esocial_no_ano_ultima_movimentacao",
        "ultimo_periodo_movimentacao",
        "dt_inicio_ultimo_mes_movimentacao",
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
        "classificacao_mov_sem_funcionario",
        "motivo_mov_sem_funcionario",
        "dt_processamento",
    }

    def _assert_source_table(table_name: str, required: set[str]) -> int:
        with engine.connect() as conn:
            exists = conn.execute(text(f"SELECT OBJECT_ID('{table_name}', 'U')")).scalar()
            if exists is None:
                raise RuntimeError(f"Tabela fonte {table_name} nao encontrada para sincronizar eSocial.")

            rows = conn.execute(text(f"SELECT COUNT_BIG(*) FROM {table_name}")).scalar()
            if rows == 0:
                raise RuntimeError(f"Tabela fonte {table_name} esta vazia para sincronizar eSocial.")

            cols = {
                row[0]
                for row in conn.execute(text("""
                    SELECT COLUMN_NAME
                    FROM temp_CGUSC.INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = 'fp'
                      AND TABLE_NAME = :table_name
                """), {"table_name": table_name.split(".")[-1]})
            }

        missing_cols = required - cols
        if missing_cols:
            raise RuntimeError(
                f"Tabela fonte {table_name} sem colunas obrigatorias: "
                + ", ".join(sorted(missing_cols))
            )
        return int(rows)

    total_trabalhador = _assert_source_table(
        "temp_CGUSC.fp.esocial_cnpj_trabalhador_ano",
        trabalhador_required,
    )
    total_ano = _assert_source_table(
        "temp_CGUSC.fp.esocial_cnpj_ano",
        ano_required,
    )
    total_movimentacao = _assert_source_table(
        "temp_CGUSC.fp.esocial_cnpj_movimentacao_ano",
        movimentacao_required,
    )
    total_ultima_movimentacao = _assert_source_table(
        "temp_CGUSC.fp.esocial_cnpj_ultima_movimentacao",
        ultima_movimentacao_required,
    )

    print(f"   -> Registros trabalhador/ano: {total_trabalhador:,}")
    trabalhador_sql = """
        SELECT
            id_cnpj,
            ano_base,
            mes_base,
            competencia_base,
            cpf_trabalhador,
            matricula,
            cbo,
            titulo_cbo,
            dt_admissao,
            dt_rescisao,
            is_farmaceutico,
            is_cbo_sem_titulo,
            dt_carga_fonte,
            dt_processamento
        FROM [temp_CGUSC].[fp].[esocial_cnpj_trabalhador_ano]
    """
    trabalhador_chunks = []
    rows_processed = 0
    for chunk in pd.read_sql(trabalhador_sql, engine, chunksize=50_000):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("ano_base").cast(pl.Int16),
            pl.col("mes_base").cast(pl.Int8),
            pl.col("competencia_base").cast(pl.Int32),
            pl.col("cpf_trabalhador").cast(pl.String),
            pl.col("matricula").cast(pl.String),
            pl.col("cbo").cast(pl.Int32, strict=False),
            pl.col("titulo_cbo").cast(pl.String),
            pl.col("dt_admissao").cast(pl.Date, strict=False),
            pl.col("dt_rescisao").cast(pl.Date, strict=False),
            pl.col("is_farmaceutico").cast(pl.Boolean),
            pl.col("is_cbo_sem_titulo").cast(pl.Boolean),
            pl.col("dt_carga_fonte").cast(pl.Date, strict=False),
            pl.col("dt_processamento").cast(pl.Datetime, strict=False),
        ])
        trabalhador_chunks.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_trabalhador) * 50)
        print(f"   -> Progresso eSocial trabalhador/ano: {p * 2}% ({rows_processed:,} / {total_trabalhador:,})")
        if progress_callback:
            progress_callback(p)

    df_esocial_cnpj_trabalhador_ano = (
        pl.concat(trabalhador_chunks).sort(["id_cnpj", "ano_base", "cpf_trabalhador", "matricula"])
    )
    df_esocial_cnpj_trabalhador_ano.write_parquet(
        _ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH,
        compression="zstd",
    )
    _df_esocial_cnpj_trabalhador_ano = None
    _mark_on_demand_global_cache_ready(
        "esocial_cnpj_trabalhador_ano",
        _ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH,
    )

    print(f"   -> Registros anuais agregados: {total_ano:,}")
    ano_sql = """
        SELECT
            id_cnpj,
            ano_base,
            mes_base,
            competencia_base,
            qtd_registros,
            qtd_trabalhadores,
            qtd_farmaceuticos,
            qtd_trabalhadores_cbo_sem_titulo,
            qtd_registros_farmaceuticos,
            qtd_registros_cbo_sem_titulo,
            has_farmaceutico,
            has_cbo_sem_titulo,
            is_um_trabalhador,
            is_um_trabalhador_sem_farmaceutico,
            is_um_trabalhador_cbo_sem_titulo,
            cbo_unico_trabalhador,
            titulo_cbo_unico_trabalhador,
            qtd_registros_vinculo_ano,
            qtd_trabalhadores_vinculo_ano,
            qtd_farmaceuticos_vinculo_ano,
            qtd_trabalhadores_cbo_sem_titulo_vinculo_ano,
            dt_carga_fonte,
            dt_processamento
        FROM [temp_CGUSC].[fp].[esocial_cnpj_ano]
    """
    pdf_ano = pd.read_sql(ano_sql, engine)
    df_esocial_cnpj_ano = pl.from_pandas(pdf_ano).with_columns([
        pl.col("id_cnpj").cast(pl.Int32),
        pl.col("ano_base").cast(pl.Int16),
        pl.col("mes_base").cast(pl.Int8),
        pl.col("competencia_base").cast(pl.Int32),
        pl.col("qtd_registros").cast(pl.Int64),
        pl.col("qtd_trabalhadores").cast(pl.Int64),
        pl.col("qtd_farmaceuticos").cast(pl.Int64),
        pl.col("qtd_trabalhadores_cbo_sem_titulo").cast(pl.Int64),
        pl.col("qtd_registros_farmaceuticos").cast(pl.Int64),
        pl.col("qtd_registros_cbo_sem_titulo").cast(pl.Int64),
        pl.col("has_farmaceutico").cast(pl.Boolean),
        pl.col("has_cbo_sem_titulo").cast(pl.Boolean),
        pl.col("is_um_trabalhador").cast(pl.Boolean),
        pl.col("is_um_trabalhador_sem_farmaceutico").cast(pl.Boolean),
        pl.col("is_um_trabalhador_cbo_sem_titulo").cast(pl.Boolean),
        pl.col("cbo_unico_trabalhador").cast(pl.Int32, strict=False),
        pl.col("titulo_cbo_unico_trabalhador").cast(pl.String),
        pl.col("qtd_registros_vinculo_ano").cast(pl.Int64),
        pl.col("qtd_trabalhadores_vinculo_ano").cast(pl.Int64),
        pl.col("qtd_farmaceuticos_vinculo_ano").cast(pl.Int64),
        pl.col("qtd_trabalhadores_cbo_sem_titulo_vinculo_ano").cast(pl.Int64),
        pl.col("dt_carga_fonte").cast(pl.Date, strict=False),
        pl.col("dt_processamento").cast(pl.Datetime, strict=False),
    ]).sort(["id_cnpj", "ano_base"])
    df_esocial_cnpj_ano.write_parquet(
        _ESOCIAL_CNPJ_ANO_PARQUET_PATH,
        compression="zstd",
    )
    _df_esocial_cnpj_ano = None
    _mark_on_demand_global_cache_ready(
        "esocial_cnpj_ano",
        _ESOCIAL_CNPJ_ANO_PARQUET_PATH,
    )

    print(f"   -> Registros movimentacao/trabalho: {total_movimentacao:,}")
    movimentacao_sql = """
        SELECT
            id_cnpj,
            ano_base,
            id_regiao_saude,
            uf,
            periodo_min,
            periodo_max,
            valor_pfpb_ano,
            valor_sem_comprovacao_ano,
            qtd_autorizacoes_ano,
            qtd_caixas_ano,
            qtd_caixas_sem_comprovacao_ano,
            qtd_trabalhadores,
            qtd_farmaceuticos,
            valor_pfpb_por_trabalhador,
            valor_sem_comprovacao_por_trabalhador,
            autorizacoes_por_trabalhador,
            caixas_por_trabalhador,
            p90_referencia_valor_pfpb_ano,
            p95_referencia_valor_por_trabalhador,
            qtd_cnpjs_referencia,
            escopo_referencia,
            classificacao_mov_trabalhista,
            motivo_classificacao,
            dt_processamento
        FROM [temp_CGUSC].[fp].[esocial_cnpj_movimentacao_ano]
    """
    pdf_movimentacao = pd.read_sql(movimentacao_sql, engine)
    df_esocial_cnpj_movimentacao_ano = pl.from_pandas(pdf_movimentacao).with_columns([
        pl.col("id_cnpj").cast(pl.Int32),
        pl.col("ano_base").cast(pl.Int16),
        pl.col("id_regiao_saude").cast(pl.Int32),
        pl.col("uf").cast(pl.String),
        pl.col("periodo_min").cast(pl.Date, strict=False),
        pl.col("periodo_max").cast(pl.Date, strict=False),
        pl.col("valor_pfpb_ano").cast(pl.Float64),
        pl.col("valor_sem_comprovacao_ano").cast(pl.Float64),
        pl.col("qtd_autorizacoes_ano").cast(pl.Int64),
        pl.col("qtd_caixas_ano").cast(pl.Int64),
        pl.col("qtd_caixas_sem_comprovacao_ano").cast(pl.Int64),
        pl.col("qtd_trabalhadores").cast(pl.Int64),
        pl.col("qtd_farmaceuticos").cast(pl.Int64),
        pl.col("valor_pfpb_por_trabalhador").cast(pl.Float64, strict=False),
        pl.col("valor_sem_comprovacao_por_trabalhador").cast(pl.Float64, strict=False),
        pl.col("autorizacoes_por_trabalhador").cast(pl.Float64, strict=False),
        pl.col("caixas_por_trabalhador").cast(pl.Float64, strict=False),
        pl.col("p90_referencia_valor_pfpb_ano").cast(pl.Float64),
        pl.col("p95_referencia_valor_por_trabalhador").cast(pl.Float64),
        pl.col("qtd_cnpjs_referencia").cast(pl.Int64),
        pl.col("escopo_referencia").cast(pl.String),
        pl.col("classificacao_mov_trabalhista").cast(pl.String),
        pl.col("motivo_classificacao").cast(pl.String),
        pl.col("dt_processamento").cast(pl.Datetime, strict=False),
    ]).sort(["id_cnpj", "ano_base"])
    df_esocial_cnpj_movimentacao_ano.write_parquet(
        _ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH,
        compression="zstd",
    )
    _df_esocial_cnpj_movimentacao_ano = None
    _mark_on_demand_global_cache_ready(
        "esocial_cnpj_movimentacao_ano",
        _ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH,
    )

    print(f"   -> Registros ultima movimentacao/trabalho: {total_ultima_movimentacao:,}")
    ultima_movimentacao_sql = """
        SELECT
            id_cnpj,
            ano_ultima_movimentacao,
            ano_esocial_referencia_ultima_movimentacao,
            is_sem_esocial_no_ano_ultima_movimentacao,
            ultimo_periodo_movimentacao,
            dt_inicio_ultimo_mes_movimentacao,
            dt_referencia_ultima_movimentacao,
            valor_pfpb_ultimo_mes,
            qtd_autorizacoes_ultimo_mes,
            qtd_trabalhadores_ativos_ultima_movimentacao,
            qtd_farmaceuticos_ativos_ultima_movimentacao,
            dt_ultima_rescisao_antes_ultima_movimentacao,
            dt_ultimo_trabalhador_ativo,
            ultimo_mes_trabalhador_ativo,
            dt_inicio_periodo_sem_funcionario,
            qtd_dias_sem_funcionario_ate_ultima_movimentacao,
            valor_pfpb_periodo_sem_funcionario,
            qtd_autorizacoes_periodo_sem_funcionario,
            has_movimentacao_sem_funcionario_ativo,
            classificacao_mov_sem_funcionario,
            motivo_mov_sem_funcionario,
            dt_processamento
        FROM [temp_CGUSC].[fp].[esocial_cnpj_ultima_movimentacao]
    """
    pdf_ultima_movimentacao = pd.read_sql(ultima_movimentacao_sql, engine)
    df_esocial_cnpj_ultima_movimentacao = pl.from_pandas(pdf_ultima_movimentacao).with_columns([
        pl.col("id_cnpj").cast(pl.Int32),
        pl.col("ano_ultima_movimentacao").cast(pl.Int16),
        pl.col("ano_esocial_referencia_ultima_movimentacao").cast(pl.Int16),
        pl.col("is_sem_esocial_no_ano_ultima_movimentacao").cast(pl.Boolean),
        pl.col("ultimo_periodo_movimentacao").cast(pl.Date, strict=False),
        pl.col("dt_inicio_ultimo_mes_movimentacao").cast(pl.Date, strict=False),
        pl.col("dt_referencia_ultima_movimentacao").cast(pl.Date, strict=False),
        pl.col("valor_pfpb_ultimo_mes").cast(pl.Float64),
        pl.col("qtd_autorizacoes_ultimo_mes").cast(pl.Int64),
        pl.col("qtd_trabalhadores_ativos_ultima_movimentacao").cast(pl.Int64),
        pl.col("qtd_farmaceuticos_ativos_ultima_movimentacao").cast(pl.Int64),
        pl.col("dt_ultima_rescisao_antes_ultima_movimentacao").cast(pl.Date, strict=False),
        pl.col("dt_ultimo_trabalhador_ativo").cast(pl.Date, strict=False),
        pl.col("ultimo_mes_trabalhador_ativo").cast(pl.Date, strict=False),
        pl.col("dt_inicio_periodo_sem_funcionario").cast(pl.Date, strict=False),
        pl.col("qtd_dias_sem_funcionario_ate_ultima_movimentacao").cast(pl.Int64, strict=False),
        pl.col("valor_pfpb_periodo_sem_funcionario").cast(pl.Float64, strict=False),
        pl.col("qtd_autorizacoes_periodo_sem_funcionario").cast(pl.Int64, strict=False),
        pl.col("has_movimentacao_sem_funcionario_ativo").cast(pl.Boolean),
        pl.col("classificacao_mov_sem_funcionario").cast(pl.String),
        pl.col("motivo_mov_sem_funcionario").cast(pl.String),
        pl.col("dt_processamento").cast(pl.Datetime, strict=False),
    ]).sort("id_cnpj")
    df_esocial_cnpj_ultima_movimentacao.write_parquet(
        _ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH,
        compression="zstd",
    )
    _df_esocial_cnpj_ultima_movimentacao = None
    _mark_on_demand_global_cache_ready(
        "esocial_cnpj_ultima_movimentacao",
        _ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH,
    )

    if progress_callback:
        progress_callback(100)

def _sync_sentinela_metadados_base(engine, progress_callback=None):
    """Sincroniza metadados globais de bases processadas pelo Sentinela."""
    global _df_sentinela_metadados_base
    print("Sincronizando metadados das bases Sentinela...")

    required = {
        "nome_base",
        "nome_artefato",
        "fonte_origem",
        "dt_referencia_min",
        "dt_referencia_max",
        "competencia_min",
        "competencia_max",
        "qtd_registros",
        "qtd_chaves",
        "schema_versao",
        "dt_processamento_inicio",
        "dt_processamento_fim",
        "observacao",
    }

    table_name = "temp_CGUSC.fp.sentinela_metadados_base"
    with engine.connect() as conn:
        exists = conn.execute(text(f"SELECT OBJECT_ID('{table_name}', 'U')")).scalar()
        if exists is None:
            raise RuntimeError(f"Tabela fonte {table_name} nao encontrada para sincronizar metadados.")

        total = conn.execute(text(f"SELECT COUNT_BIG(*) FROM {table_name}")).scalar()
        if total == 0:
            raise RuntimeError(f"Tabela fonte {table_name} esta vazia para sincronizar metadados.")

        cols = {
            row[0]
            for row in conn.execute(text("""
                SELECT COLUMN_NAME
                FROM temp_CGUSC.INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'fp'
                  AND TABLE_NAME = 'sentinela_metadados_base'
            """))
        }

    missing_cols = required - cols
    if missing_cols:
        raise RuntimeError(
            "Tabela temp_CGUSC.fp.sentinela_metadados_base sem colunas obrigatorias: "
            + ", ".join(sorted(missing_cols))
        )

    sql = """
        SELECT
            nome_base,
            nome_artefato,
            fonte_origem,
            dt_referencia_min,
            dt_referencia_max,
            competencia_min,
            competencia_max,
            qtd_registros,
            qtd_chaves,
            schema_versao,
            dt_processamento_inicio,
            dt_processamento_fim,
            observacao
        FROM [temp_CGUSC].[fp].[sentinela_metadados_base]
    """
    pdf = pd.read_sql(sql, engine)
    df_sentinela_metadados_base = pl.from_pandas(pdf).with_columns([
        pl.col("nome_base").cast(pl.String),
        pl.col("nome_artefato").cast(pl.String),
        pl.col("fonte_origem").cast(pl.String),
        pl.col("dt_referencia_min").cast(pl.Datetime, strict=False),
        pl.col("dt_referencia_max").cast(pl.Datetime, strict=False),
        pl.col("competencia_min").cast(pl.Int32, strict=False),
        pl.col("competencia_max").cast(pl.Int32, strict=False),
        pl.col("qtd_registros").cast(pl.Int64),
        pl.col("qtd_chaves").cast(pl.Int64, strict=False),
        pl.col("schema_versao").cast(pl.Int32),
        pl.col("dt_processamento_inicio").cast(pl.Datetime, strict=False),
        pl.col("dt_processamento_fim").cast(pl.Datetime, strict=False),
        pl.col("observacao").cast(pl.String),
    ]).sort(["nome_base", "nome_artefato"])
    df_sentinela_metadados_base.write_parquet(
        _SENTINELA_METADADOS_BASE_PARQUET_PATH,
        compression="zstd",
    )
    _df_sentinela_metadados_base = df_sentinela_metadados_base

    if progress_callback:
        progress_callback(100)

def _sync_dados_par(engine, progress_callback=None):
    """Sincroniza uma visão agregada de PAR por CNPJ, sem persistir detalhes sensíveis."""
    global _df_dados_par
    print("Sincronizando indicadores de PAR por CNPJ...")
    sql = """
        WITH par_base AS (
            SELECT DISTINCT
                CNPJ AS cnpj,
                IdProcedimento,
                NULLIF(LTRIM(RTRIM(Situacao)), '') AS situacao,
                CAST(Instauracao AS date) AS instauracao,
                CAST(Conclusao AS date) AS conclusao
            FROM [db_pagamentos_federais].[dbo].[Dados_PAR]
            WHERE CNPJ IS NOT NULL
              AND LEN(CNPJ) = 14
        ),
        par_situacoes AS (
            SELECT
                cnpj,
                STRING_AGG(situacao, ' | ') AS par_situacoes
            FROM (
                SELECT DISTINCT cnpj, situacao
                FROM par_base
                WHERE situacao IS NOT NULL
            ) s
            GROUP BY cnpj
        )
        SELECT
            b.cnpj,
            CAST(1 AS bit) AS is_par,
            COUNT(DISTINCT b.IdProcedimento) AS qtd_processos_par,
            MAX(s.par_situacoes) AS par_situacoes,
            MIN(b.instauracao) AS par_primeira_instauracao,
            MAX(b.instauracao) AS par_ultima_instauracao,
            MAX(b.conclusao) AS par_ultima_conclusao
        FROM par_base b
        LEFT JOIN par_situacoes s ON s.cnpj = b.cnpj
        GROUP BY b.cnpj
    """

    pdf = pd.read_sql(sql, engine)
    print(f"   -> CNPJs com PAR: {len(pdf):,}")
    if progress_callback:
        progress_callback(100)

    if pdf.empty:
        df_dados_par = _empty_dados_par_df()
    else:
        df_dados_par = pl.from_pandas(pdf).with_columns([
            pl.col("cnpj").cast(pl.Utf8),
            pl.col("is_par").cast(pl.Boolean),
            pl.col("qtd_processos_par").cast(pl.Int32),
            pl.col("par_situacoes").cast(pl.Utf8),
            pl.col("par_primeira_instauracao").cast(pl.Date, strict=False),
            pl.col("par_ultima_instauracao").cast(pl.Date, strict=False),
            pl.col("par_ultima_conclusao").cast(pl.Date, strict=False),
        ]).sort("cnpj")

    df_dados_par.write_parquet(_DADOS_PAR_PARQUET_PATH, compression="zstd")
    _df_dados_par = df_dados_par

def _sync_par_teia_alvos(engine, progress_callback=None):
    """Sincroniza flags agregadas de PAR na teia por CNPJ alvo."""
    global _df_par_teia_alvos
    print("Sincronizando indicadores de PAR na teia por CNPJ alvo...")

    temp_sql = """
        DROP TABLE IF EXISTS #par_cnpjs;

        CREATE TABLE #par_cnpjs (
            cnpj VARCHAR(14) COLLATE SQL_Latin1_General_CP1_CI_AI NOT NULL PRIMARY KEY
        );

        INSERT INTO #par_cnpjs (cnpj)
        SELECT DISTINCT
            CNPJ COLLATE SQL_Latin1_General_CP1_CI_AI
        FROM db_pagamentos_federais.dbo.Dados_PAR
        WHERE CNPJ IS NOT NULL
          AND LEN(CNPJ) = 14;
    """

    sql = """
        WITH alvos AS (
            SELECT DISTINCT cnpj
            FROM temp_CGUSC.fp.lista_cnpjs
        ),
        par_alvo AS (
            SELECT
                a.cnpj,
                COUNT(DISTINCT a.cnpj) AS qtd_par_alvo
            FROM alvos a
            INNER JOIN #par_cnpjs p ON p.cnpj = a.cnpj
            GROUP BY a.cnpj
        ),
        par_n2 AS (
            SELECT
                ds.cnpj,
                COUNT(DISTINCT t2.cnpj_empresa) AS qtd_empresas_par_n2
            FROM temp_CGUSC.fp.dados_socios ds
            INNER JOIN temp_CGUSC.fp.teia_fonte_nivel2 t2
                ON t2.cpf_cnpj_socio = ds.cpf_cnpj_socio
            INNER JOIN #par_cnpjs p ON p.cnpj = t2.cnpj_empresa
            GROUP BY ds.cnpj
        ),
        par_n4 AS (
            SELECT
                ds.cnpj,
                COUNT(DISTINCT t4.cnpj_empresa) AS qtd_empresas_par_n4
            FROM temp_CGUSC.fp.dados_socios ds
            INNER JOIN temp_CGUSC.fp.teia_fonte_nivel2 t2
                ON t2.cpf_cnpj_socio = ds.cpf_cnpj_socio
            INNER JOIN temp_CGUSC.fp.teia_fonte_nivel3 t3
                ON t3.cnpj_empresa = t2.cnpj_empresa
            INNER JOIN temp_CGUSC.fp.teia_fonte_nivel4 t4
                ON t4.cpf_cnpj_socio = t3.cpf_cnpj_socio
            INNER JOIN #par_cnpjs p ON p.cnpj = t4.cnpj_empresa
            GROUP BY ds.cnpj
        ),
        par_qualquer AS (
            SELECT
                q.cnpj,
                COUNT(DISTINCT q.cnpj_par) AS qtd_empresas_par_qualquer
            FROM (
                SELECT a.cnpj, a.cnpj AS cnpj_par
                FROM alvos a
                INNER JOIN #par_cnpjs p ON p.cnpj = a.cnpj

                UNION ALL
                SELECT ds.cnpj, t2.cnpj_empresa AS cnpj_par
                FROM temp_CGUSC.fp.dados_socios ds
                INNER JOIN temp_CGUSC.fp.teia_fonte_nivel2 t2
                    ON t2.cpf_cnpj_socio = ds.cpf_cnpj_socio
                INNER JOIN #par_cnpjs p ON p.cnpj = t2.cnpj_empresa

                UNION ALL
                SELECT ds.cnpj, t4.cnpj_empresa AS cnpj_par
                FROM temp_CGUSC.fp.dados_socios ds
                INNER JOIN temp_CGUSC.fp.teia_fonte_nivel2 t2
                    ON t2.cpf_cnpj_socio = ds.cpf_cnpj_socio
                INNER JOIN temp_CGUSC.fp.teia_fonte_nivel3 t3
                    ON t3.cnpj_empresa = t2.cnpj_empresa
                INNER JOIN temp_CGUSC.fp.teia_fonte_nivel4 t4
                    ON t4.cpf_cnpj_socio = t3.cpf_cnpj_socio
                INNER JOIN #par_cnpjs p ON p.cnpj = t4.cnpj_empresa
            ) q
            GROUP BY q.cnpj
        )
        SELECT
            a.cnpj,
            CASE WHEN ISNULL(pa.qtd_par_alvo, 0) > 0 THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS has_par_alvo,
            CASE WHEN ISNULL(p2.qtd_empresas_par_n2, 0) > 0 THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS has_par_n2,
            CASE WHEN ISNULL(p4.qtd_empresas_par_n4, 0) > 0 THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS has_par_n4,
            CASE WHEN ISNULL(pq.qtd_empresas_par_qualquer, 0) > 0 THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS has_par_qualquer,
            ISNULL(pa.qtd_par_alvo, 0) AS qtd_par_alvo,
            ISNULL(p2.qtd_empresas_par_n2, 0) AS qtd_empresas_par_n2,
            ISNULL(p4.qtd_empresas_par_n4, 0) AS qtd_empresas_par_n4,
            ISNULL(pq.qtd_empresas_par_qualquer, 0) AS qtd_empresas_par_qualquer
        FROM alvos a
        LEFT JOIN par_alvo pa ON pa.cnpj = a.cnpj
        LEFT JOIN par_n2 p2 ON p2.cnpj = a.cnpj
        LEFT JOIN par_n4 p4 ON p4.cnpj = a.cnpj
        LEFT JOIN par_qualquer pq ON pq.cnpj = a.cnpj
        ORDER BY a.cnpj
    """

    with engine.begin() as conn:
        conn.exec_driver_sql(temp_sql)
        pdf = pd.read_sql(sql, conn)

    print(f"   -> CNPJs alvo indexados para PAR na teia: {len(pdf):,}")
    if progress_callback:
        progress_callback(100)

    if pdf.empty:
        df_par_teia_alvos = _empty_par_teia_alvos_df()
    else:
        df_par_teia_alvos = pl.from_pandas(pdf).with_columns([
            pl.col("cnpj").cast(pl.Utf8),
            pl.col("has_par_alvo").cast(pl.Boolean),
            pl.col("has_par_n2").cast(pl.Boolean),
            pl.col("has_par_n4").cast(pl.Boolean),
            pl.col("has_par_qualquer").cast(pl.Boolean),
            pl.col("qtd_par_alvo").cast(pl.Int32),
            pl.col("qtd_empresas_par_n2").cast(pl.Int32),
            pl.col("qtd_empresas_par_n4").cast(pl.Int32),
            pl.col("qtd_empresas_par_qualquer").cast(pl.Int32),
        ]).sort("cnpj")

    df_par_teia_alvos.write_parquet(_PAR_TEIA_ALVOS_PARQUET_PATH, compression="zstd")
    _df_par_teia_alvos = df_par_teia_alvos


def _sync_dados_farmacia(engine, progress_callback=None):
    """Tarefa 8: Sincroniza dados cadastrais e geográficos das farmácias."""
    global _df_dados_farmacia
    print("Sincronizando Dados Cadastrais das Farmácias...")
    sql = """
        SELECT D.id as id_cnpj,
               D.cnpj,
               D.indMatriz as is_matriz,
               D.razaoSocial as razao_social,
               D.nomeFantasia as nome_fantasia,
               D.tipoLogradouro as tipo_logradouro,
               D.logradouro as logradouro, 
               D.numero as numero, 
               D.complemento as complemento, 
               D.bairro as bairro, 
               D.cep as cep,
               D.latitude as latitude, 
               D.longitude as longitude,
               D.codibge as id_ibge7,
               D.id_cnae_principal as id_cnae_principal, 
               D.cnae_principal as cnae_principal,
               D.is_cnae_farmacia_ausente as is_cnae_farmacia_ausente,
               D.data_abertura as data_abertura,
               D.data_processamento as data_processamento,
               D.natureza_juridica as natureza_juridica,
               D.capital_social as capital_social,
               D.telefone_1 as telefone_1,
               D.telefone_2 as telefone_2,
               D.correio_eletronico as email,
               D.situacaoReceita as situacao_rf,
               D.ds_porte_empresa as porte_empresa,
               D.uf as uf,
               D.municipio as municipio
        FROM [temp_CGUSC].[fp].[dados_farmacia] D
    """
    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[dados_farmacia]")).scalar()
    
    print(f"   -> Registros Cadastrais: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 5_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("id_cnae_principal").cast(pl.String),
            pl.col("is_cnae_farmacia_ausente").cast(pl.Int8),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso Dados Farmácias: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback:
            progress_callback(int(p * 0.85))

    df_dados_farmacia = pl.concat(chunk_list).with_columns([
        (pl.col("is_matriz") == "M").alias("is_matriz"),
    ]).sort("cnpj")
    df_dados_farmacia.write_parquet(_DADOS_FARMACIA_PARQUET_PATH, compression="zstd")
    _df_dados_farmacia = df_dados_farmacia
    _sync_dados_farmacia_cnaes_secundarios(
        engine,
        (
            (lambda p: progress_callback(85 + int(p * 0.15)))
            if progress_callback
            else None
        ),
    )


def _sync_dados_farmacia_cnaes_secundarios(engine, progress_callback=None):
    """Sincroniza a relacao normalizada de CNAEs secundarios das farmacias."""
    global _df_dados_farmacia_cnaes_secundarios
    print("Sincronizando CNAEs Secundarios das Farmacias...")
    sql = """
        SELECT
            C.id_cnpj,
            C.id_cnae_secundario AS id_cnae,
            C.cnae_secundario AS descricao
        FROM [temp_CGUSC].[fp].[dados_farmacia_cnaes_secundarios] C
        ORDER BY C.id_cnpj, C.id_cnae_secundario
    """
    with engine.connect() as conn:
        total_rows = conn.execute(
            text(
                "SELECT COUNT(*) "
                "FROM [temp_CGUSC].[fp].[dados_farmacia_cnaes_secundarios]"
            )
        ).scalar()

    chunk_list = []
    rows_processed = 0
    chunk_size = 10_000
    for chunk in pd.read_sql(sql, engine, chunksize=chunk_size):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("id_cnae").cast(pl.Int32),
            pl.col("descricao").cast(pl.String),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        if progress_callback:
            progress_callback(
                int((rows_processed / total_rows) * 100) if total_rows else 100
            )

    if chunk_list:
        df_dados_farmacia_cnaes_secundarios = (
            pl.concat(chunk_list)
            .with_columns(pl.col("descricao").cast(pl.Categorical))
            .sort(["id_cnpj", "id_cnae"])
        )
    else:
        df_dados_farmacia_cnaes_secundarios = pl.DataFrame(
            schema={
                "id_cnpj": pl.Int32,
                "id_cnae": pl.Int32,
                "descricao": pl.Categorical,
            }
        )

    df_dados_farmacia_cnaes_secundarios.write_parquet(
        _DADOS_FARMACIA_CNAES_SECUNDARIOS_PARQUET_PATH,
        compression="zstd",
    )
    _df_dados_farmacia_cnaes_secundarios = df_dados_farmacia_cnaes_secundarios
    if progress_callback:
        progress_callback(100)


def _sync_perfil_estabelecimento(engine, progress_callback=None):
    """Sincroniza a dimensao cadastral usada para filtrar/enriquecer a movimentacao."""
    global _df_perfil_estabelecimento
    print("Sincronizando Perfil dos Estabelecimentos...")
    profile_rows = _assert_fp_source_table(
        engine,
        "perfil_consolidado_estabelecimento",
        {
            "cnpj",
            "has_cadunico_direto",
            "has_cadunico_n3",
            "qtd_cadunico_direto",
            "qtd_cadunico_n3",
            "has_seguro_defeso_direto",
            "has_seguro_defeso_n3",
            "qtd_seguro_defeso_direto",
            "qtd_seguro_defeso_n3",
            "has_esocial_direto",
            "has_esocial_n3",
            "qtd_esocial_direto",
            "qtd_esocial_n3",
        },
    )
    sql = """
        SELECT
            D.id AS id_cnpj,
            D.cnpj,
            P.uf,
            IB.id_regiao_saude,
            D.codibge AS id_ibge7,
            P.municipio AS no_municipio,
            P.razao_social,
            P.situacao_rf,
            P.is_conexao_ativa,
            P.porte_empresa,
            P.is_grande_rede,
            P.qtd_estabelecimentos_rede,
            P.is_matriz,
            P.unidade_pf,
            P.is_cnae_incompativel_farmaceutico,
            P.has_cadunico_direto,
            P.has_cadunico_n3,
            P.qtd_cadunico_direto,
            P.qtd_cadunico_n3,
            P.has_seguro_defeso_direto,
            P.has_seguro_defeso_n3,
            P.qtd_seguro_defeso_direto,
            P.qtd_seguro_defeso_n3,
            P.has_esocial_direto,
            P.has_esocial_n3,
            P.qtd_esocial_direto,
            P.qtd_esocial_n3
        FROM [temp_CGUSC].[fp].[dados_farmacia] D
        LEFT JOIN [temp_CGUSC].[fp].[perfil_consolidado_estabelecimento] P
            ON P.cnpj = D.cnpj
        LEFT JOIN [temp_CGUSC].[fp].[dados_ibge] IB
            ON IB.id_ibge7 = D.codibge
    """
    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[dados_farmacia]")).scalar()
    if profile_rows != total_rows:
        raise RuntimeError(
            "Perfil consolidado nao cobre todas as farmacias: "
            f"{profile_rows:,} perfis para {total_rows:,} farmacias."
        )

    print(f"   -> Perfis de estabelecimentos: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 10_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("cnpj").cast(pl.String),
            pl.col("uf").cast(pl.Categorical),
            pl.col("id_regiao_saude").cast(pl.String),
            pl.col("id_ibge7").cast(pl.Int64, strict=False),
            pl.col("no_municipio").cast(pl.Categorical),
            pl.col("razao_social").cast(pl.Categorical),
            pl.col("situacao_rf").cast(pl.Categorical),
            pl.col("porte_empresa").cast(pl.Categorical),
            pl.col("unidade_pf").cast(pl.Categorical),
            pl.col("is_conexao_ativa").cast(pl.Boolean),
            pl.col("is_grande_rede").cast(pl.Boolean),
            pl.col("is_matriz").cast(pl.Boolean),
            pl.col("qtd_estabelecimentos_rede").cast(pl.Int64),
            pl.col("is_cnae_incompativel_farmaceutico").cast(pl.Boolean),
            pl.col("has_cadunico_direto").cast(pl.Boolean),
            pl.col("has_cadunico_n3").cast(pl.Boolean),
            pl.col("qtd_cadunico_direto").cast(pl.Int32),
            pl.col("qtd_cadunico_n3").cast(pl.Int32),
            pl.col("has_seguro_defeso_direto").cast(pl.Boolean),
            pl.col("has_seguro_defeso_n3").cast(pl.Boolean),
            pl.col("qtd_seguro_defeso_direto").cast(pl.Int32),
            pl.col("qtd_seguro_defeso_n3").cast(pl.Int32),
            pl.col("has_esocial_direto").cast(pl.Boolean),
            pl.col("has_esocial_n3").cast(pl.Boolean),
            pl.col("qtd_esocial_direto").cast(pl.Int32),
            pl.col("qtd_esocial_n3").cast(pl.Int32),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso Perfil Estabelecimentos: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback:
            progress_callback(p)

    if not chunk_list:
        raise RuntimeError("Consulta de perfil_estabelecimento nao retornou registros.")

    df_perfil_estabelecimento = (
        pl.concat(chunk_list)
        .unique(subset=["id_cnpj"])
        .sort("id_cnpj")
    )
    alert_columns = [
        "has_cadunico_direto",
        "has_cadunico_n3",
        "qtd_cadunico_direto",
        "qtd_cadunico_n3",
        "has_seguro_defeso_direto",
        "has_seguro_defeso_n3",
        "qtd_seguro_defeso_direto",
        "qtd_seguro_defeso_n3",
        "has_esocial_direto",
        "has_esocial_n3",
        "qtd_esocial_direto",
        "qtd_esocial_n3",
        "is_cnae_incompativel_farmaceutico",
    ]
    null_alert_columns = [
        column
        for column in alert_columns
        if df_perfil_estabelecimento[column].null_count() > 0
    ]
    if null_alert_columns:
        raise RuntimeError(
            "Perfil de estabelecimentos possui alertas societarios nulos: "
            + ", ".join(null_alert_columns)
        )

    df_perfil_estabelecimento.write_parquet(
        _PERFIL_ESTABELECIMENTO_PARQUET_PATH,
        compression="zstd",
    )
    _df_perfil_estabelecimento = df_perfil_estabelecimento


def _sync_dados_socios(engine, progress_callback=None):
    """Tarefa: Sincroniza dados societários das farmácias."""
    global _df_dados_socios
    print("Sincronizando Dados Societários...")
    required = {
        "cnpj",
        "cpf_cnpj_socio",
        "nome_socio",
        "indicador_socio",
        "municipio",
        "uf",
        "data_entrada_sociedade",
        "data_exclusao_sociedade",
        "percentual_qualificacao",
        "descricao_qualificacao",
        "cpf_representante",
        "id_qualificacao_representante",
        "nome_representante",
        "descricao_qualificacao_representante",
        "data_nascimento_socio",
        "data_nascimento_representante",
        "data_processamento",
        "is_cadunico",
        "is_esocial",
        "is_seguro_defeso",
        "is_falecido",
    }
    total_rows = _assert_fp_source_table(engine, "dados_socios", required)
    sql = "SELECT * FROM [temp_CGUSC].[fp].[dados_socios]"

    print(f"   -> Registros Societários: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 5_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_list.append(pl.from_pandas(chunk))
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        if progress_callback:
            progress_callback(p)

    df_full = pl.concat(chunk_list)

    df_dados_socios = df_full.with_columns([
        pl.col("cnpj").cast(pl.String),
        pl.col("cpf_cnpj_socio").cast(pl.String),
        pl.col("nome_socio").cast(pl.String),
        pl.col("municipio").cast(pl.Categorical),
        pl.col("uf").cast(pl.Categorical),
        pl.col("cpf_representante").cast(pl.String),
        pl.col("id_qualificacao_representante").cast(pl.Int8, strict=False),
        pl.col("nome_representante").cast(pl.String),
        pl.col("descricao_qualificacao_representante").cast(pl.Categorical),
        pl.col("data_nascimento_socio").cast(pl.Date),
        pl.col("data_nascimento_representante").cast(pl.Date),
        pl.col("indicador_socio").cast(pl.Categorical),
        pl.col("descricao_qualificacao").cast(pl.Categorical),
        pl.col("data_entrada_sociedade").cast(pl.Date),
        pl.col("data_exclusao_sociedade").cast(pl.Date),
        pl.col("percentual_qualificacao").cast(pl.Float32),
        pl.col("data_processamento").cast(pl.Date),
        pl.col("is_cadunico").cast(pl.Int8),
        pl.col("is_esocial").cast(pl.Int8),
        pl.col("is_seguro_defeso").cast(pl.Int8),
        pl.col("is_falecido").cast(pl.Int8),
    ]).sort("cnpj")

    df_dados_socios.write_parquet(_DADOS_SOCIOS_PARQUET_PATH, compression="zstd")
    _df_dados_socios = df_dados_socios
    print(f"   -> Sincronização de Sócios finalizada ({len(_df_dados_socios):,} registros).")


def _sync_teia_fonte_nivel2(engine, progress_callback=None):
    """Tarefa: Sincroniza participações externas dos sócios encontrados nas farmácias."""
    global _df_teia_fonte_nivel2
    print("Sincronizando Participações Externas dos Sócios...")
    sql = "SELECT * FROM [temp_CGUSC].[fp].[teia_fonte_nivel2]"

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[teia_fonte_nivel2]")).scalar()

    if total_rows == 0:
        print("   -> Nenhuma participação externa encontrada.")
        df_teia_fonte_nivel2 = pl.DataFrame(schema={
            "cpf_cnpj_socio": pl.String, "cnpj_empresa": pl.String, 
            "razao_social": pl.String,
            "nome_fantasia": pl.String,
            "indicador_socio": pl.Categorical,
            "descricao_qualificacao": pl.Categorical,
            "cpf_representante": pl.String,
            "nome_representante": pl.String,
            "data_entrada_sociedade": pl.Date,
            "data_exclusao_sociedade": pl.Date, "situacao_rf": pl.Categorical,
            "municipio": pl.Categorical, "uf": pl.Categorical, "is_farmacia_fp": pl.Int8,
            "is_cadunico": pl.Int8,
            "is_falecido": pl.Int8,
        })
        df_teia_fonte_nivel2.write_parquet(_TEIA_FONTE_NIVEL2_PARQUET_PATH, compression="zstd")
        _df_teia_fonte_nivel2 = None
        _mark_on_demand_global_cache_ready("teia_fonte_nivel2", _TEIA_FONTE_NIVEL2_PARQUET_PATH)
        if progress_callback: progress_callback(100)
        return

    print(f"   -> Registros de Participações Externas: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 10_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        df_chunk = pl.from_pandas(chunk)
        # CAST DIRETO (SEM FALLBACKS)
        df_chunk = df_chunk.with_columns([
            pl.col("data_entrada_sociedade").cast(pl.Date, strict=False),
            pl.col("data_exclusao_sociedade").cast(pl.Date, strict=False)
        ])
            
        chunk_list.append(df_chunk)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        if progress_callback: progress_callback(p)

    df_full = pl.concat(chunk_list)
    
    df_teia_fonte_nivel2 = df_full.with_columns([
        pl.col("cpf_cnpj_socio").cast(pl.String),
        pl.col("cnpj_empresa").cast(pl.String),
        pl.col("razao_social").cast(pl.String),
        pl.col("nome_fantasia").cast(pl.String),
        pl.col("indicador_socio").cast(pl.Categorical),
        pl.col("descricao_qualificacao").cast(pl.Categorical),
        pl.col("cpf_representante").cast(pl.String),
        pl.col("nome_representante").cast(pl.String),
        pl.col("data_entrada_sociedade").cast(pl.Date),
        pl.col("data_exclusao_sociedade").cast(pl.Date),
        pl.col("situacao_rf").cast(pl.Categorical),
        pl.col("municipio").cast(pl.Categorical),
        pl.col("uf").cast(pl.Categorical),
        pl.col("is_farmacia_fp").cast(pl.Int8),
        pl.col("is_cadunico").cast(pl.Int8),
        pl.col("is_falecido").cast(pl.Int8),
    ]).sort("cpf_cnpj_socio")

    row_count = len(df_teia_fonte_nivel2)
    df_teia_fonte_nivel2.write_parquet(_TEIA_FONTE_NIVEL2_PARQUET_PATH, compression="zstd")
    _df_teia_fonte_nivel2 = None
    _mark_on_demand_global_cache_ready("teia_fonte_nivel2", _TEIA_FONTE_NIVEL2_PARQUET_PATH)
    print(f"   -> Sincronização de Participações Externas finalizada ({row_count:,} registros).")


def _sync_teia_fonte_nivel3(engine, progress_callback=None):
    """Tarefa: Sincroniza os sócios das empresas irmãs (Expansão de 3º Grau)."""
    global _df_teia_fonte_nivel3
    print("Sincronizando Sócios das Empresas Irmãs (Expansão Teia)...")
    sql = "SELECT * FROM [temp_CGUSC].[fp].[teia_fonte_nivel3]"

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[teia_fonte_nivel3]")).scalar()

    if total_rows == 0:
        print("   -> Nenhum sócio indireto encontrado.")
        df_teia_fonte_nivel3 = pl.DataFrame(schema={
            "cnpj_empresa": pl.String, "cpf_cnpj_socio": pl.String,
            "nome_socio": pl.String, "indicador_socio": pl.Categorical,
            "descricao_qualificacao": pl.Categorical,
            "cpf_representante": pl.String,
            "nome_representante": pl.String,
            "data_entrada_sociedade": pl.Date, "data_exclusao_sociedade": pl.Date,
            "municipio": pl.String, "uf": pl.String,
            "is_cadunico": pl.Int8, "is_esocial": pl.Int8,
            "is_seguro_defeso": pl.Int8, "is_falecido": pl.Int8,
        })
        df_teia_fonte_nivel3.write_parquet(_TEIA_FONTE_NIVEL3_PARQUET_PATH, compression="zstd")
        _df_teia_fonte_nivel3 = None
        _mark_on_demand_global_cache_ready("teia_fonte_nivel3", _TEIA_FONTE_NIVEL3_PARQUET_PATH)
        if progress_callback: progress_callback(100)
        return

    print(f"   -> Registros de Sócios Indiretos: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 25_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        df_chunk = pl.from_pandas(chunk)
        # CAST DIRETO
        df_chunk = df_chunk.with_columns([
            pl.col("data_entrada_sociedade").cast(pl.Date, strict=False),
            pl.col("data_exclusao_sociedade").cast(pl.Date, strict=False)
        ])

        chunk_list.append(df_chunk)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        if progress_callback: progress_callback(p)

    df_teia_fonte_nivel3 = pl.concat(chunk_list).with_columns([
        pl.col("cnpj_empresa").cast(pl.String),
        pl.col("cpf_cnpj_socio").cast(pl.String),
        pl.col("indicador_socio").cast(pl.Categorical),
        pl.col("descricao_qualificacao").cast(pl.Categorical),
        pl.col("cpf_representante").cast(pl.String),
        pl.col("nome_representante").cast(pl.String),
        pl.col("municipio").cast(pl.String),
        pl.col("uf").cast(pl.String),
        pl.col("is_cadunico").cast(pl.Int8),
        pl.col("is_esocial").cast(pl.Int8),
        pl.col("is_seguro_defeso").cast(pl.Int8),
        pl.col("is_falecido").cast(pl.Int8),
    ]).sort(["cnpj_empresa", "cpf_cnpj_socio"])

    df_teia_fonte_nivel3.write_parquet(_TEIA_FONTE_NIVEL3_PARQUET_PATH, compression="zstd")
    _df_teia_fonte_nivel3 = None
    _mark_on_demand_global_cache_ready("teia_fonte_nivel3", _TEIA_FONTE_NIVEL3_PARQUET_PATH)
    print(f"   -> Sincronização de Sócios Indiretos finalizada.")


def _sync_teia_fonte_nivel4(engine, progress_callback=None):
    """Tarefa: Sincroniza participações de 4º grau (Empresas dos sócios de 3º grau)."""
    global _df_teia_fonte_nivel4
    print("Sincronizando Expansão de 4º Grau (Teia Nacional)...")
    sql = "SELECT * FROM [temp_CGUSC].[fp].[teia_fonte_nivel4]"

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[teia_fonte_nivel4]")).scalar()

    if total_rows == 0:
        print("   -> Nenhuma participação de 4º grau encontrada.")
        df_teia_fonte_nivel4 = pl.DataFrame(schema={
            "cpf_cnpj_socio": pl.String, "cnpj_empresa": pl.String, 
            "razao_social": pl.String,
            "nome_fantasia": pl.String,
            "indicador_socio": pl.Categorical,
            "descricao_qualificacao": pl.Categorical,
            "cpf_representante": pl.String,
            "nome_representante": pl.String,
            "data_entrada_sociedade": pl.Date,
            "data_exclusao_sociedade": pl.Date, "situacao_rf": pl.Categorical,
            "municipio": pl.Categorical, "uf": pl.Categorical, "is_farmacia_fp": pl.Int8,
            "is_cadunico": pl.Int8,
            "is_falecido": pl.Int8
        })
        df_teia_fonte_nivel4.write_parquet(_TEIA_FONTE_NIVEL4_PARQUET_PATH, compression="zstd")
        _df_teia_fonte_nivel4 = None
        _mark_on_demand_global_cache_ready("teia_fonte_nivel4", _TEIA_FONTE_NIVEL4_PARQUET_PATH)
        if progress_callback: progress_callback(100)
        return

    print(f"   -> Registros de 4º Grau: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 50_000 # Chunk maior para processar os 4M de linhas com eficiência

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        df_chunk = pl.from_pandas(chunk)
        # CAST DIRETO
        df_chunk = df_chunk.with_columns([
            pl.col("data_entrada_sociedade").cast(pl.Date, strict=False),
            pl.col("data_exclusao_sociedade").cast(pl.Date, strict=False)
        ])
            
        chunk_list.append(df_chunk)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        if progress_callback: progress_callback(p)

    df_full = pl.concat(chunk_list)

    df_teia_fonte_nivel4 = df_full.with_columns([
        pl.col("cpf_cnpj_socio").cast(pl.String),
        pl.col("cnpj_empresa").cast(pl.String),
        pl.col("razao_social").cast(pl.String),
        pl.col("nome_fantasia").cast(pl.String),
        pl.col("indicador_socio").cast(pl.Categorical),
        pl.col("descricao_qualificacao").cast(pl.Categorical),
        pl.col("cpf_representante").cast(pl.String),
        pl.col("nome_representante").cast(pl.String),
        pl.col("data_entrada_sociedade").cast(pl.Date),
        pl.col("data_exclusao_sociedade").cast(pl.Date),
        pl.col("situacao_rf").cast(pl.Categorical),
        pl.col("municipio").cast(pl.Categorical),
        pl.col("uf").cast(pl.Categorical),
        pl.col("is_farmacia_fp").cast(pl.Int8),
        pl.col("is_cadunico").cast(pl.Int8),
        pl.col("is_falecido").cast(pl.Int8),
    ]).sort("cpf_cnpj_socio")

    row_count = len(df_teia_fonte_nivel4)
    df_teia_fonte_nivel4.write_parquet(_TEIA_FONTE_NIVEL4_PARQUET_PATH, compression="zstd")
    _df_teia_fonte_nivel4 = None
    _mark_on_demand_global_cache_ready("teia_fonte_nivel4", _TEIA_FONTE_NIVEL4_PARQUET_PATH)
    print(f"   -> Sincronização de 4º Grau finalizada ({row_count:,} registros).")


def _sync_medicamentos(engine, progress_callback=None):
    """Tarefa 9: Sincroniza a tabela mestra de medicamentos e patologias."""
    global _df_medicamentos
    print("Sincronizando Cadastro de Medicamentos (Dicionário GTIN)...")
    sql = "SELECT codigo_barra, principio_ativo, produto, descricao, laboratorio, Patologia as patologia FROM [temp_CGUSC].[fp].[medicamentos_patologia]"
    
    pdf = pd.read_sql(sql, engine)
    print(f"   -> Cadastro carregado: {len(pdf):,} medicamentos.")
    if progress_callback: progress_callback(100)
    
    df_medicamentos = pl.from_pandas(pdf).with_columns([
        pl.col("codigo_barra").cast(pl.String),
        pl.col("principio_ativo").cast(pl.Categorical),
        pl.col("produto").cast(pl.Categorical),
        pl.col("laboratorio").cast(pl.Categorical),
        pl.col("patologia").cast(pl.Categorical),
    ]).sort("codigo_barra")
    df_medicamentos.write_parquet(_MEDICAMENTOS_PARQUET_PATH, compression="zstd")
    _df_medicamentos = df_medicamentos


def _sync_analise_gtin_inconsistencia_clinica(engine, progress_callback=None):
    """Sincroniza o agregado CNPJ com contexto regional da inconsistencia clinica."""
    global _df_analise_gtin_inconsistencia_clinica
    print("Sincronizando Analise GTIN x Inconsistencia Clinica...")
    required = {
        "id_cnpj",
        "id_regiao_saude",
        "id_ibge7",
        "patologia",
        "regra_clinica",
        "ano_base",
        "qtd_cpfs_distintos",
        "qtd_cpfs_incompativeis",
        "qtd_autorizacoes",
        "qtd_autorizacoes_incompativeis",
        "valor_total_pago",
        "valor_incompativel_pago",
        "percentual_cpfs_incompativeis",
        "rank_regional_qtd_cpfs_incompativeis",
        "rank_regional_valor_incompativel_pago",
        "percentil_regional_qtd_cpfs_incompativeis",
        "percentil_regional_valor_incompativel_pago",
        "participacao_cpfs_incompativeis_regiao",
        "participacao_valor_incompativel_regiao",
        "percentual_regional_cpfs_incompativeis",
        "razao_percentual_vs_regiao",
        "cpfs_incompativeis_esperados_regiao",
        "excesso_cpfs_incompativeis_vs_regiao",
        "dt_processamento",
    }
    total_rows = _assert_fp_source_table(engine, "analise_gtin_inconsistencia_clinica", required)
    sql = """
        SELECT
            id_cnpj,
            id_regiao_saude,
            id_ibge7,
            patologia,
            regra_clinica,
            ano_base,
            qtd_cpfs_distintos,
            qtd_cpfs_incompativeis,
            qtd_autorizacoes,
            qtd_autorizacoes_incompativeis,
            CAST(valor_total_pago AS FLOAT) AS valor_total_pago,
            CAST(valor_incompativel_pago AS FLOAT) AS valor_incompativel_pago,
            CAST(percentual_cpfs_incompativeis AS FLOAT) AS percentual_cpfs_incompativeis,
            rank_regional_qtd_cpfs_incompativeis,
            rank_regional_valor_incompativel_pago,
            CAST(percentil_regional_qtd_cpfs_incompativeis AS FLOAT) AS percentil_regional_qtd_cpfs_incompativeis,
            CAST(percentil_regional_valor_incompativel_pago AS FLOAT) AS percentil_regional_valor_incompativel_pago,
            CAST(participacao_cpfs_incompativeis_regiao AS FLOAT) AS participacao_cpfs_incompativeis_regiao,
            CAST(participacao_valor_incompativel_regiao AS FLOAT) AS participacao_valor_incompativel_regiao,
            CAST(percentual_regional_cpfs_incompativeis AS FLOAT) AS percentual_regional_cpfs_incompativeis,
            CAST(razao_percentual_vs_regiao AS FLOAT) AS razao_percentual_vs_regiao,
            CAST(cpfs_incompativeis_esperados_regiao AS FLOAT) AS cpfs_incompativeis_esperados_regiao,
            CAST(excesso_cpfs_incompativeis_vs_regiao AS FLOAT) AS excesso_cpfs_incompativeis_vs_regiao,
            dt_processamento
        FROM [temp_CGUSC].[fp].[analise_gtin_inconsistencia_clinica]
    """
    print(f"   -> Registros clinicos anuais: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 50_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("id_regiao_saude").cast(pl.Int64, strict=False),
            pl.col("id_ibge7").cast(pl.String),
            pl.col("patologia").cast(pl.Categorical),
            pl.col("regra_clinica").cast(pl.Categorical),
            pl.col("ano_base").cast(pl.Int16),
            pl.col("qtd_cpfs_distintos").cast(pl.Int32),
            pl.col("qtd_cpfs_incompativeis").cast(pl.Int32),
            pl.col("qtd_autorizacoes").cast(pl.Int32),
            pl.col("qtd_autorizacoes_incompativeis").cast(pl.Int32),
            pl.col("valor_total_pago").cast(pl.Float64),
            pl.col("valor_incompativel_pago").cast(pl.Float64),
            pl.col("percentual_cpfs_incompativeis").cast(pl.Float64),
            pl.col("rank_regional_qtd_cpfs_incompativeis").cast(pl.Int32, strict=False),
            pl.col("rank_regional_valor_incompativel_pago").cast(pl.Int32, strict=False),
            pl.col("percentil_regional_qtd_cpfs_incompativeis").cast(pl.Float64),
            pl.col("percentil_regional_valor_incompativel_pago").cast(pl.Float64),
            pl.col("participacao_cpfs_incompativeis_regiao").cast(pl.Float64),
            pl.col("participacao_valor_incompativel_regiao").cast(pl.Float64),
            pl.col("percentual_regional_cpfs_incompativeis").cast(pl.Float64),
            pl.col("razao_percentual_vs_regiao").cast(pl.Float64),
            pl.col("cpfs_incompativeis_esperados_regiao").cast(pl.Float64),
            pl.col("excesso_cpfs_incompativeis_vs_regiao").cast(pl.Float64),
            pl.col("dt_processamento").cast(pl.Datetime, strict=False),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100)
        if progress_callback:
            progress_callback(p)

    df_analise_gtin_inconsistencia_clinica = (
        pl.concat(chunk_list).sort(["id_regiao_saude", "patologia", "regra_clinica", "ano_base", "id_cnpj"])
    )
    df_analise_gtin_inconsistencia_clinica.write_parquet(
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH,
        compression="zstd",
    )
    _df_analise_gtin_inconsistencia_clinica = None
    _mark_on_demand_global_cache_ready(
        "analise_gtin_inconsistencia_clinica",
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH,
    )


def _sync_analise_gtin_inconsistencia_clinica_municipio(engine, progress_callback=None):
    """Sincroniza a evolucao anual por municipio e patologia da inconsistencia clinica."""
    global _df_analise_gtin_inconsistencia_clinica_municipio
    print("Sincronizando Analise GTIN x Inconsistencia Clinica Municipal...")
    required = {
        "id_ibge7",
        "patologia",
        "regra_clinica",
        "ano_base",
        "qtd_cpfs_distintos_municipio",
        "qtd_cpfs_incompativeis_municipio",
        "qtd_autorizacoes_municipio",
        "qtd_autorizacoes_incompativeis_municipio",
        "valor_total_pago_municipio",
        "valor_incompativel_pago_municipio",
        "dt_processamento",
    }
    total_rows = _assert_fp_source_table(engine, "analise_gtin_inconsistencia_clinica_municipio", required)
    sql = """
        SELECT
            id_ibge7,
            patologia,
            regra_clinica,
            ano_base,
            qtd_cpfs_distintos_municipio,
            qtd_cpfs_incompativeis_municipio,
            qtd_autorizacoes_municipio,
            qtd_autorizacoes_incompativeis_municipio,
            CAST(valor_total_pago_municipio AS FLOAT) AS valor_total_pago_municipio,
            CAST(valor_incompativel_pago_municipio AS FLOAT) AS valor_incompativel_pago_municipio,
            dt_processamento
        FROM [temp_CGUSC].[fp].[analise_gtin_inconsistencia_clinica_municipio]
    """
    print(f"   -> Registros clinicos municipais anuais: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 50_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_ibge7").cast(pl.Int64, strict=False),
            pl.col("patologia").cast(pl.Categorical),
            pl.col("regra_clinica").cast(pl.Categorical),
            pl.col("ano_base").cast(pl.Int16),
            pl.col("qtd_cpfs_distintos_municipio").cast(pl.Int32),
            pl.col("qtd_cpfs_incompativeis_municipio").cast(pl.Int32),
            pl.col("qtd_autorizacoes_municipio").cast(pl.Int32),
            pl.col("qtd_autorizacoes_incompativeis_municipio").cast(pl.Int32),
            pl.col("valor_total_pago_municipio").cast(pl.Float64),
            pl.col("valor_incompativel_pago_municipio").cast(pl.Float64),
            pl.col("dt_processamento").cast(pl.Datetime, strict=False),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100)
        if progress_callback:
            progress_callback(p)

    df_analise_gtin_inconsistencia_clinica_municipio = (
        pl.concat(chunk_list).sort(["id_ibge7", "patologia", "ano_base"])
    )
    df_analise_gtin_inconsistencia_clinica_municipio.write_parquet(
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH,
        compression="zstd",
    )
    _df_analise_gtin_inconsistencia_clinica_municipio = None
    _mark_on_demand_global_cache_ready(
        "analise_gtin_inconsistencia_clinica_municipio",
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH,
    )


def _sync_analise_gtin_inconsistencia_clinica_regiao(engine, progress_callback=None):
    """Sincroniza o agregado por regiao de saude da inconsistencia clinica."""
    global _df_analise_gtin_inconsistencia_clinica_regiao
    print("Sincronizando Analise GTIN x Inconsistencia Clinica Regional...")
    required = {
        "id_regiao_saude",
        "patologia",
        "regra_clinica",
        "ano_base",
        "qtd_cnpjs_regiao",
        "qtd_municipios_regiao",
        "qtd_cpfs_distintos_regiao",
        "qtd_cpfs_incompativeis_regiao",
        "qtd_autorizacoes_regiao",
        "qtd_autorizacoes_incompativeis_regiao",
        "valor_total_pago_regiao",
        "valor_incompativel_pago_regiao",
        "percentual_cpfs_incompativeis_regiao",
        "dt_processamento",
    }
    total_rows = _assert_fp_source_table(engine, "analise_gtin_inconsistencia_clinica_regiao", required)
    sql = """
        SELECT
            id_regiao_saude,
            patologia,
            regra_clinica,
            ano_base,
            qtd_cnpjs_regiao,
            qtd_municipios_regiao,
            qtd_cpfs_distintos_regiao,
            qtd_cpfs_incompativeis_regiao,
            qtd_autorizacoes_regiao,
            qtd_autorizacoes_incompativeis_regiao,
            CAST(valor_total_pago_regiao AS FLOAT) AS valor_total_pago_regiao,
            CAST(valor_incompativel_pago_regiao AS FLOAT) AS valor_incompativel_pago_regiao,
            CAST(percentual_cpfs_incompativeis_regiao AS FLOAT) AS percentual_cpfs_incompativeis_regiao,
            dt_processamento
        FROM [temp_CGUSC].[fp].[analise_gtin_inconsistencia_clinica_regiao]
    """
    print(f"   -> Registros clinicos por regiao anuais: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 50_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_regiao_saude").cast(pl.Int64, strict=False),
            pl.col("patologia").cast(pl.Categorical),
            pl.col("regra_clinica").cast(pl.Categorical),
            pl.col("ano_base").cast(pl.Int16),
            pl.col("qtd_cnpjs_regiao").cast(pl.Int32),
            pl.col("qtd_municipios_regiao").cast(pl.Int32),
            pl.col("qtd_cpfs_distintos_regiao").cast(pl.Int32),
            pl.col("qtd_cpfs_incompativeis_regiao").cast(pl.Int32),
            pl.col("qtd_autorizacoes_regiao").cast(pl.Int32),
            pl.col("qtd_autorizacoes_incompativeis_regiao").cast(pl.Int32),
            pl.col("valor_total_pago_regiao").cast(pl.Float64),
            pl.col("valor_incompativel_pago_regiao").cast(pl.Float64),
            pl.col("percentual_cpfs_incompativeis_regiao").cast(pl.Float64),
            pl.col("dt_processamento").cast(pl.Datetime, strict=False),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100)
        if progress_callback:
            progress_callback(p)

    df_analise_gtin_inconsistencia_clinica_regiao = (
        pl.concat(chunk_list).sort(["id_regiao_saude", "patologia", "regra_clinica", "ano_base"])
    )
    df_analise_gtin_inconsistencia_clinica_regiao.write_parquet(
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH,
        compression="zstd",
    )
    _df_analise_gtin_inconsistencia_clinica_regiao = None
    _mark_on_demand_global_cache_ready(
        "analise_gtin_inconsistencia_clinica_regiao",
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH,
    )


def _sync_dados_ibge_demografia(engine, progress_callback=None):
    """Sincroniza os dados demograficos do Censo IBGE por municipio, idade e sexo."""
    global _df_dados_ibge_demografia
    print("Sincronizando Demografia IBGE...")
    required = {
        "id_ibge7",
        "grupo_idade",
        "sexo",
        "nu_populacao",
        "ano_censo",
        "idade_min",
        "idade_max",
        "ordem",
    }
    total_rows = _assert_fp_source_table(engine, "dados_ibge_demografia", required)
    sql = """
        SELECT
            id_ibge7,
            grupo_idade,
            sexo,
            nu_populacao,
            ano_censo,
            idade_min,
            idade_max,
            ordem
        FROM [temp_CGUSC].[fp].[dados_ibge_demografia]
    """
    print(f"   -> Registros demograficos: {total_rows:,}")
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 100_000

    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_ibge7").cast(pl.String),
            pl.col("grupo_idade").cast(pl.Categorical),
            pl.col("sexo").cast(pl.Categorical),
            pl.col("nu_populacao").cast(pl.Int32, strict=False),
            pl.col("ano_censo").cast(pl.Int16),
            pl.col("idade_min").cast(pl.Int16, strict=False),
            pl.col("idade_max").cast(pl.Int16, strict=False),
            pl.col("ordem").cast(pl.Int16, strict=False),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100)
        if progress_callback:
            progress_callback(p)

    df_dados_ibge_demografia = (
        pl.concat(chunk_list).sort(["id_ibge7", "ano_censo", "ordem", "sexo"])
    )
    df_dados_ibge_demografia.write_parquet(
        _DADOS_IBGE_DEMOGRAFIA_PARQUET_PATH,
        compression="zstd",
    )
    _df_dados_ibge_demografia = df_dados_ibge_demografia


def _sync_movimentacao(engine, progress_callback):
    """Tarefa 2: Sincroniza a movimentação mensal (Tabela Grande)."""
    global _df_movimentacao
    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM [temp_CGUSC].[fp].[movimentacao_mensal_cnpj]")).scalar()
        missing_id_cnpj = conn.execute(text("""
            SELECT TOP 1 1
            FROM [temp_CGUSC].[fp].[movimentacao_mensal_cnpj] M
            LEFT JOIN [temp_CGUSC].[fp].[dados_farmacia] DF
                ON DF.cnpj = M.cnpj
            WHERE DF.id IS NULL
        """)).scalar()

    if missing_id_cnpj:
        raise RuntimeError("movimentacao_mensal_cnpj possui CNPJs sem id correspondente em dados_farmacia.")
    
    # Tabela fato mensal enxuta. Perfil/geografia ficam no modulo perfil_estabelecimento.
    sql = """
        SELECT DF.id AS id_cnpj,
               M.periodo,
               CAST(M.total_vendas AS FLOAT) AS total_vendas,
               CAST(M.total_sem_comprovacao AS FLOAT) AS total_sem_comprovacao,
               M.total_qnt_caixas_vendidas,
               M.total_qnt_caixas_sem_comprovacao,
               M.total_num_autorizacoes
        FROM [temp_CGUSC].[fp].[movimentacao_mensal_cnpj] M
        INNER JOIN [temp_CGUSC].[fp].[dados_farmacia] DF ON DF.cnpj = M.cnpj
    """
    
    chunk_list = []
    rows_processed = 0
    CHUNK_SIZE = 250_000
    
    print(f"Total de registros a baixar: {total_rows:,}")
    
    for chunk in pd.read_sql(sql, engine, chunksize=CHUNK_SIZE):
        chunk_list.append(pl.from_pandas(chunk))
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso Movimentação: {p}% ({rows_processed:,} / {total_rows:,})")
        progress_callback(p)

    print("   -> Organizando e otimizando dados (Polars)...")
    df_movimentacao = pl.concat(chunk_list).with_columns([
        pl.col("id_cnpj").cast(pl.Int32),
        pl.col("periodo").cast(pl.Date),
        pl.col("total_qnt_caixas_vendidas").cast(pl.Int64),
        pl.col("total_qnt_caixas_sem_comprovacao").cast(pl.Int64),
        pl.col("total_num_autorizacoes").cast(pl.Int64),
        pl.col("total_vendas").cast(pl.Float64),
        pl.col("total_sem_comprovacao").cast(pl.Float64),
    ]).sort(["id_cnpj", "periodo"])  # ORDENAÇÃO é a chave para compressão Parquet
    df_movimentacao.write_parquet(_PARQUET_PATH, compression="zstd")
    _df_movimentacao = df_movimentacao

def _sync_crm_benchmarks(engine, progress_callback=None):
    """Tarefa 5: Gera bench_uf, bench_regiao e bench_br como parquets a partir das tabelas de indicadores do banco."""
    print("Sincronizando Benchmarks CRM (Nacional, Estadual e Regional)...")
    
    tab_map = {
        "BR":     {"table": "temp_CGUSC.fp.app_indicador_crm_bench_br",     "path": _BENCH_CRM_BR_PATH},
        "UF":     {"table": "temp_CGUSC.fp.app_indicador_crm_bench_uf",     "path": _BENCH_CRM_UF_PATH},
        "REGIAO": {"table": "temp_CGUSC.fp.app_indicador_crm_bench_regiao", "path": _BENCH_CRM_REGIAO_PATH},
    }

    total = len(tab_map)
    for i, (key, info) in enumerate(tab_map.items()):
        try:
            sql = f"SELECT * FROM {info['table']}"
            pdf = pd.read_sql(sql, engine)
            
            df = pl.from_pandas(pdf).with_columns([
                pl.col("competencia").cast(pl.Int32)
            ])
            
            # Remove redundância (caso o SQL tenha retornado uma linha por CNPJ sem DISTINCT)
            subset_cols = ["competencia"]
            if "uf" in df.columns: subset_cols.append("uf")
            if "id_regiao_saude" in df.columns: subset_cols.append("id_regiao_saude")
            
            df = df.unique(subset=subset_cols)
            
            # UF e Região de Saúde são categóricos
            if "uf" in df.columns:
                df = df.with_columns(pl.col("uf").cast(pl.Categorical))
            if "id_regiao_saude" in df.columns:
                df = df.with_columns(pl.col("id_regiao_saude").cast(pl.String))
                
            df.write_parquet(info['path'], compression="zstd")
            print(f"   -> Benchmark {key} exportado: {len(df):,} registros únicos.")
            
            if progress_callback:
                progress_callback(int(((i+1)/total) * 100))
        except Exception as e:
            print(f"   [AVISO] Erro ao exportar benchmark {key}: {e}")

    if progress_callback:
        progress_callback(100)


def _sync_crm_prescricoes_brasil_semestre(engine, progress_callback=None):
    """Sincroniza o resumo nacional semestral de prescricoes por CRM."""
    print("Sincronizando prescricoes Brasil por CRM/Semestre...")
    required = {
        "id_medico",
        "chave_semestre",
        "nu_prescricoes_total_brasil",
        "dias_ativos_brasil",
    }
    total_rows = _assert_fp_source_table(
        engine,
        "app_crm_prescricoes_brasil_semestre",
        required,
    )

    sql = """
        SELECT
            id_medico,
            chave_semestre,
            nu_prescricoes_total_brasil,
            dias_ativos_brasil
        FROM [temp_CGUSC].[fp].[app_crm_prescricoes_brasil_semestre]
    """

    chunk_list = []
    rows_processed = 0
    chunk_size = 100_000
    print(f"   -> Registros CRM Brasil/Semestre: {total_rows:,}")

    for chunk in pd.read_sql(sql, engine, chunksize=chunk_size):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_medico").cast(pl.String),
            pl.col("chave_semestre").cast(pl.Int32),
            pl.col("nu_prescricoes_total_brasil").cast(pl.Int32),
            pl.col("dias_ativos_brasil").cast(pl.Int16),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso CRM Brasil/Semestre: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback:
            progress_callback(p)

    if not chunk_list:
        raise RuntimeError("Fonte app_crm_prescricoes_brasil_semestre sem registros para sincronizacao.")

    df_crm_prescricoes_brasil_semestre = pl.concat(chunk_list).sort(["id_medico", "chave_semestre"])
    df_crm_prescricoes_brasil_semestre.write_parquet(
        _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH,
        compression="zstd",
    )
    _mark_on_demand_global_cache_ready(
        "crm_prescricoes_brasil_semestre",
        _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH,
    )


def _sync_crm_prescricoes_estabelecimento_mes(engine, progress_callback=None):
    """Sincroniza a relacao mensal completa entre estabelecimento e medico."""
    print("Sincronizando prescricoes por estabelecimento/medico/mes...")
    schema = _GLOBAL_PARQUET_SCHEMAS["crm_prescricoes_estabelecimento_mes"]
    final_path = _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "crm_prescricoes_estabelecimento_mes"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def competencia_key(value: int) -> str:
        return str(value)

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        total_rows = _assert_fp_source_table(
            engine,
            "app_crm_prescricoes_estabelecimento_mes",
            set(schema.keys()),
        )
        competencias_rows = conn.execute(text("""
            SELECT DISTINCT competencia
            FROM temp_CGUSC.fp.app_crm_prescricoes_estabelecimento_mes
            WHERE competencia IS NOT NULL
            ORDER BY competencia
        """)).fetchall()
        competencias = [int(row[0]) for row in competencias_rows]
        if not competencias:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.app_crm_prescricoes_estabelecimento_mes "
                "nao possui competencias para gerar o cache."
            )

        manifest = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "crm_prescricoes_estabelecimento_mes"
            and manifest.get("version") == CRM_PRESCRICOES_ESTABELECIMENTO_MES_CACHE_VERSION
            and manifest.get("start_competencia") == competencia_key(competencias[0])
            and manifest.get("end_competencia") == competencia_key(competencias[-1])
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "crm_prescricoes_estabelecimento_mes",
                "version": CRM_PRESCRICOES_ESTABELECIMENTO_MES_CACHE_VERSION,
                "start_competencia": competencia_key(competencias[0]),
                "end_competencia": competencia_key(competencias[-1]),
                "parts": {},
            }
            write_manifest(manifest)

        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError(
                "manifesto de prescricoes por estabelecimento com campo parts invalido"
            )

        query = text("""
            SELECT
                id_cnpj,
                id_medico,
                competencia,
                nu_prescricoes_mes
            FROM temp_CGUSC.fp.app_crm_prescricoes_estabelecimento_mes
            WHERE competencia = :competencia
            ORDER BY id_cnpj, id_medico
        """)

        total_competencias = len(competencias)
        for index, competencia in enumerate(competencias, 1):
            key = competencia_key(competencia)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_competencias) * 90))
                continue

            print(f"   -> Prescricoes por estabelecimento parte {index}/{total_competencias}: {key}")
            chunks = []
            for chunk in pd.read_sql(
                query,
                conn,
                params={"competencia": competencia},
                chunksize=100_000,
            ):
                chunks.append(
                    pl.from_pandas(chunk).with_columns([
                        pl.col("id_cnpj").cast(pl.Int32),
                        pl.col("id_medico").cast(pl.Utf8),
                        pl.col("competencia").cast(pl.Int32),
                        pl.col("nu_prescricoes_mes").cast(pl.Int32),
                    ])
                )
            if not chunks:
                raise RuntimeError(
                    "Fonte app_crm_prescricoes_estabelecimento_mes sem registros "
                    f"para competencia {competencia}."
                )
            df_part = pl.concat(chunks).select(list(schema.keys()))
            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)
            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)
            if progress_callback:
                progress_callback(int((index / total_competencias) * 90))

    part_paths = [part_path(competencia_key(competencia)) for competencia in competencias]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar crm_prescricoes_estabelecimento_mes: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando prescricoes por estabelecimento...")
    final_scan = pl.scan_parquet([str(path) for path in part_paths]).select(list(schema.keys()))
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["source_rows"] = total_rows
    manifest["final_rows"] = sum(int(info.get("rows", 0)) for info in parts.values())
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready(
        "crm_prescricoes_estabelecimento_mes",
        final_path,
    )
    if progress_callback:
        progress_callback(100)


def _sync_crm_prescricoes_medico_municipio_mes(engine, progress_callback=None):
    """Sincroniza prescricoes agregadas por medico, municipio e mes."""
    print("Sincronizando prescricoes por medico/municipio/mes...")
    schema = _GLOBAL_PARQUET_SCHEMAS["crm_prescricoes_medico_municipio_mes"]
    final_path = _CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "crm_prescricoes_medico_municipio_mes"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def competencia_key(value: int) -> str:
        return str(value)

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        total_rows = _assert_fp_source_table(
            engine,
            "app_crm_prescricoes_medico_municipio_mes",
            set(schema.keys()),
        )
        competencia_rows = conn.execute(text("""
            SELECT DISTINCT competencia
            FROM [temp_CGUSC].[fp].[app_crm_prescricoes_medico_municipio_mes]
            WHERE competencia IS NOT NULL
            ORDER BY competencia
        """)).fetchall()
        competencias = [int(row[0]) for row in competencia_rows]
        if not competencias:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.app_crm_prescricoes_medico_municipio_mes "
                "nao possui competencias para gerar o cache."
            )

        manifest = read_manifest()
        manifest_valid = (
            manifest.get("cache_key") == "crm_prescricoes_medico_municipio_mes"
            and manifest.get("version") == CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_CACHE_VERSION
            and manifest.get("start_competencia") == competencia_key(competencias[0])
            and manifest.get("end_competencia") == competencia_key(competencias[-1])
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {
                "cache_key": "crm_prescricoes_medico_municipio_mes",
                "version": CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_CACHE_VERSION,
                "start_competencia": competencia_key(competencias[0]),
                "end_competencia": competencia_key(competencias[-1]),
                "parts": {},
            }
            write_manifest(manifest)

        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError(
                "manifesto de prescricoes por medico/municipio com campo parts invalido"
            )

        query = text("""
            SELECT
                id_medico,
                competencia,
                id_ibge7,
                nu_prescricoes_mes
            FROM [temp_CGUSC].[fp].[app_crm_prescricoes_medico_municipio_mes]
            WHERE competencia = :competencia
            ORDER BY id_medico, id_ibge7
        """)

        total_competencias = len(competencias)
        for index, competencia in enumerate(competencias, 1):
            key = competencia_key(competencia)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_competencias) * 90))
                continue

            print(f"   -> Prescricoes por medico/municipio parte {index}/{total_competencias}: {key}")
            chunks = []
            for chunk in pd.read_sql(
                query,
                conn,
                params={"competencia": competencia},
                chunksize=100_000,
            ):
                chunks.append(
                    pl.from_pandas(chunk).with_columns([
                        pl.col("id_medico").cast(pl.Utf8),
                        pl.col("competencia").cast(pl.Int32),
                        pl.col("id_ibge7").cast(pl.Int64),
                        pl.col("nu_prescricoes_mes").cast(pl.Int64),
                    ])
                )
            if not chunks:
                raise RuntimeError(
                    "Fonte app_crm_prescricoes_medico_municipio_mes sem registros "
                    f"para competencia {competencia}."
                )

            df_part = pl.concat(chunks).select(list(schema.keys()))
            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)
            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)
            if progress_callback:
                progress_callback(int((index / total_competencias) * 90))

    part_paths = [part_path(competencia_key(competencia)) for competencia in competencias]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar crm_prescricoes_medico_municipio_mes: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando prescricoes por medico/municipio...")
    final_scan = pl.scan_parquet([str(path) for path in part_paths]).select(list(schema.keys()))
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["source_rows"] = total_rows
    manifest["final_rows"] = sum(int(info.get("rows", 0)) for info in parts.values())
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready(
        "crm_prescricoes_medico_municipio_mes",
        final_path,
    )
    if progress_callback:
        progress_callback(100)


def _sync_crm_prescricoes_gerencial(engine, progress_callback=None):
    """Sincroniza os indicadores pre-calculados do mapa gerencial de CRMs."""
    print("Sincronizando prescricoes gerenciais por nivel e mes...")
    schema = _GLOBAL_PARQUET_SCHEMAS["crm_prescricoes_gerencial"]
    final_path = _CRM_PRESCRICOES_GERENCIAL_PATH
    parts_dir = Path(_CACHE_DIR) / ".parts" / "crm_prescricoes_gerencial"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "manifest.json"

    def competencia_key(value: int) -> str:
        return str(value)

    def part_path(key: str) -> Path:
        return parts_dir / f"{key}.smod.part"

    def read_manifest() -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(data: dict[str, Any]) -> None:
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, manifest_path)

    with engine.connect() as conn:
        total_rows = _assert_fp_source_table(
            engine,
            "app_crm_prescricoes_gerencial",
            set(schema.keys()),
        )
        competencia_rows = conn.execute(text("""
            SELECT DISTINCT competencia
            FROM [temp_CGUSC].[fp].[app_crm_prescricoes_gerencial]
            WHERE competencia IS NOT NULL
            ORDER BY competencia
        """)).fetchall()
        competencias = [int(row[0]) for row in competencia_rows]
        if not competencias:
            raise RuntimeError(
                "A fonte temp_CGUSC.fp.app_crm_prescricoes_gerencial "
                "nao possui competencias mensais para gerar o cache."
            )

        manifest = read_manifest()
        expected_manifest = {
            "cache_key": "crm_prescricoes_gerencial",
            "version": CRM_PRESCRICOES_GERENCIAL_CACHE_VERSION,
            "start_competencia": competencia_key(competencias[0]),
            "end_competencia": competencia_key(competencias[-1]),
        }
        manifest_valid = (
            all(manifest.get(key) == value for key, value in expected_manifest.items())
            and manifest.get("status") != "done"
        )
        if not manifest_valid:
            manifest = {**expected_manifest, "parts": {}}
            write_manifest(manifest)

        parts = manifest["parts"]
        if not isinstance(parts, dict):
            raise RuntimeError("manifesto de CRM gerencial com campo parts invalido")

        query = text("""
            SELECT
                nivel,
                id_geografico,
                competencia,
                nu_prescricoes_total,
                qtd_crms_ativos,
                qtd_crms_anomalos,
                percentual_crms_anomalos,
                media_prescricoes_dia
            FROM [temp_CGUSC].[fp].[app_crm_prescricoes_gerencial]
            WHERE competencia = :competencia
            ORDER BY nivel, id_geografico
        """)

        total_parts = len(competencias)
        for index, competencia in enumerate(competencias, 1):
            key = competencia_key(competencia)
            output_path = part_path(key)
            info = parts.get(key, {})
            if info.get("status") == "done" and output_path.exists():
                if progress_callback:
                    progress_callback(int((index / total_parts) * 90))
                continue

            print(f"   -> CRM prescricoes gerencial parte {index}/{total_parts}: {key}")
            pdf = pd.read_sql(query, conn, params={"competencia": competencia})
            if pdf.empty:
                raise RuntimeError(
                    "Fonte app_crm_prescricoes_gerencial sem registros "
                    f"para competencia {competencia}."
                )

            df_part = (
                pl.from_pandas(pdf)
                .with_columns([
                    pl.col("nivel").cast(pl.Utf8),
                    pl.col("id_geografico").cast(pl.Utf8),
                    pl.col("competencia").cast(pl.Int32),
                    pl.col("nu_prescricoes_total").cast(pl.Int64),
                    pl.col("qtd_crms_ativos").cast(pl.Int32),
                    pl.col("qtd_crms_anomalos").cast(pl.Int32),
                    pl.col("percentual_crms_anomalos").cast(pl.Float64),
                    pl.col("media_prescricoes_dia").cast(pl.Float64),
                ])
                .select(list(schema.keys()))
            )

            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            df_part.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, output_path)

            parts[key] = {
                "status": "done",
                "rows": df_part.height,
                "file": output_path.name,
            }
            write_manifest(manifest)

            if progress_callback:
                progress_callback(int((index / total_parts) * 90))

    part_paths = [part_path(competencia_key(value)) for value in competencias]
    missing_parts = [path.name for path in part_paths if not path.exists()]
    if missing_parts:
        raise RuntimeError(
            "Partes pendentes para consolidar crm_prescricoes_gerencial: "
            + ", ".join(missing_parts)
        )

    print("   -> Consolidando indicadores gerenciais de prescricoes...")
    final_scan = pl.scan_parquet([str(path) for path in part_paths]).select(list(schema.keys()))
    tmp_final = final_path + ".tmp"
    final_scan.sink_parquet(tmp_final, compression="zstd")
    os.replace(tmp_final, final_path)

    manifest["status"] = "done"
    manifest["source_rows"] = total_rows
    manifest["final_rows"] = sum(int(info.get("rows", 0)) for info in parts.values())
    manifest["final_file"] = os.path.basename(final_path)
    write_manifest(manifest)
    _mark_on_demand_global_cache_ready("crm_prescricoes_gerencial", final_path)
    if progress_callback:
        progress_callback(100)


def _sync_dados_medico(engine, progress_callback=None):
    """Sincroniza a dimensao global de medicos por CRM/UF."""
    print("Sincronizando dados dos medicos por CRM/UF...")
    required = {
        "id_medico",
        "nu_crm",
        "sg_uf",
        "no_medico",
        "dt_primeira_inscricao_uf",
    }
    total_rows = _assert_fp_source_table(
        engine,
        "app_dados_medico",
        required,
    )

    sql = """
        SELECT
            id_medico,
            nu_crm,
            sg_uf,
            no_medico,
            dt_primeira_inscricao_uf
        FROM [temp_CGUSC].[fp].[app_dados_medico]
    """

    chunk_list = []
    rows_processed = 0
    chunk_size = 100_000
    print(f"   -> Registros dados_medico: {total_rows:,}")

    for chunk in pd.read_sql(sql, engine, chunksize=chunk_size):
        chunk_df = pl.from_pandas(chunk).with_columns([
            pl.col("id_medico").cast(pl.String),
            pl.col("nu_crm").cast(pl.Int64),
            pl.col("sg_uf").cast(pl.String),
            pl.col("no_medico").cast(pl.String),
            pl.col("dt_primeira_inscricao_uf").cast(pl.Date),
        ])
        chunk_list.append(chunk_df)
        rows_processed += len(chunk)
        p = int((rows_processed / total_rows) * 100) if total_rows > 0 else 100
        print(f"   -> Progresso dados_medico: {p}% ({rows_processed:,} / {total_rows:,})")
        if progress_callback:
            progress_callback(p)

    if not chunk_list:
        raise RuntimeError("Fonte app_dados_medico sem registros para sincronizacao.")

    df_dados_medico = pl.concat(chunk_list).sort(["id_medico"])
    df_dados_medico.write_parquet(
        _DADOS_MEDICO_PARQUET_PATH,
        compression="zstd",
    )
    _mark_on_demand_global_cache_ready(
        "dados_medico",
        _DADOS_MEDICO_PARQUET_PATH,
    )


def _sync_crm_parquets(engine, progress_callback=None, cnpjs: list[str] | None = None):
    """Tarefa: Gera todos os parquets (médicos, diário, horário, alertas) para os CNPJs selecionados."""
    import cache_manager
    
    # Se não informar CNPJs, busca os que já processaram o índice de risco (ativos)
    if not cnpjs:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("""
                    SELECT DISTINCT F.cnpj
                    FROM temp_CGUSC.fp.matriz_risco_consolidada M
                    INNER JOIN temp_CGUSC.fp.dados_farmacia F
                        ON F.id = M.id_cnpj
                    ORDER BY F.cnpj
                """))
                cnpjs = [r[0] for r in res]
        except Exception as e:
            print(f"[ERRO] Erro ao buscar lista de CNPJs: {e}")
            return

    total = len(cnpjs)
    print(f"Sincronizando parquets de CRMs para {total} estabelecimento(s)...")

    for i, cnpj in enumerate(cnpjs, 1):
        try:
            # 1. Alertas associados a CRMs.
            cache_manager.sync_cnpj_cache("geografico", cnpj, engine)
            cache_manager.sync_cnpj_cache("crm_concentracao_unico_alertas", cnpj, engine)
            cache_manager.sync_cnpj_cache("crm_concentracao_multiplo_alertas", cnpj, engine)

            cache_manager.sync_cnpj_cache("crm_timeline_dia", cnpj, engine)
            cache_manager.sync_cnpj_cache("crm_timeline_hora", cnpj, engine)
            cache_manager.sync_cnpj_cache("crm_timeline_eventos", cnpj, engine)

            # 2. Transacoes Raio-X
            cache_manager.sync_cnpj_cache("crm_raiox_tx", cnpj, engine)

            if progress_callback:
                p = int((i / total) * 100)
                progress_callback(p)
        except Exception as e:
            print(f"\n[AVISO]  Erro ao sincronizar CNPJ {cnpj}: {e}")
            raise

    if progress_callback:
        progress_callback(100)


# --- GERENCIADOR DE CACHE ---

def load_cache(engine, force_refresh: bool = False) -> None:
    global _df_movimentacao, _df_localidades, _df_rede, _df_matriz_risco, _df_bench_crm_uf, _df_bench_crm_regiao, _df_bench_crm_br, _df_dados_farmacia, _df_dados_farmacia_cnaes_secundarios, _df_perfil_estabelecimento, _df_dados_socios, _df_teia_fonte_nivel2, _df_teia_fonte_nivel3, _df_teia_fonte_nivel4, _df_medicamentos, _df_falecidos, _df_analise_gtin_inconsistencia_clinica, _df_analise_gtin_inconsistencia_clinica_municipio, _df_analise_gtin_inconsistencia_clinica_regiao, _df_dados_ibge_demografia, _df_volume_atipico_semestral, _df_esocial_cnpj_ano, _df_esocial_cnpj_trabalhador_ano, _df_esocial_cnpj_movimentacao_ano, _df_esocial_cnpj_ultima_movimentacao, _df_sentinela_metadados_base, _df_dados_par, _df_par_teia_alvos, _cache_progress, _cache_status, _cache_error_message, _cache_generation
    import time
    _ON_DEMAND_GLOBAL_CACHE_READY.clear()

    # 1. Boot Rápido (carrega cada Parquet individualmente)
    if not force_refresh:
        _cache_status = "loading_parquet"
        missing = []
        required_columns = {
            "movimentacao": {
                "id_cnpj",
                "periodo",
                "total_vendas",
                "total_sem_comprovacao",
                "total_qnt_caixas_vendidas",
                "total_qnt_caixas_sem_comprovacao",
                "total_num_autorizacoes",
            },
            "perfil_estabelecimento": {
                "id_cnpj",
                "cnpj",
                "uf",
                "id_regiao_saude",
                "id_ibge7",
                "no_municipio",
                "razao_social",
                "situacao_rf",
                "is_conexao_ativa",
                "porte_empresa",
                "is_grande_rede",
                "qtd_estabelecimentos_rede",
                "is_matriz",
                "unidade_pf",
                "has_cadunico_direto",
                "has_cadunico_n3",
                "qtd_cadunico_direto",
                "qtd_cadunico_n3",
                "has_seguro_defeso_direto",
                "has_seguro_defeso_n3",
                "qtd_seguro_defeso_direto",
                "qtd_seguro_defeso_n3",
            },
            "dados_farmacia": {
                "id_cnpj",
                "id_cnae_principal",
                "cnae_principal",
                "is_cnae_farmacia_ausente",
            },
            "dados_farmacia_cnaes_secundarios": {
                "id_cnpj",
                "id_cnae",
                "descricao",
            },
            "dados_socios": {"is_cadunico", "is_esocial", "is_seguro_defeso", "is_falecido"},
            "teia_fonte_nivel2": {"is_cadunico", "is_falecido"},
            "teia_fonte_nivel3": {"is_cadunico", "is_esocial", "is_seguro_defeso", "is_falecido"},
            "teia_fonte_nivel4": {"is_cadunico", "is_falecido"},
            "analise_gtin_inconsistencia_clinica": {
                "id_cnpj",
                "id_regiao_saude",
                "id_ibge7",
                "patologia",
                "regra_clinica",
                "ano_base",
                "qtd_cpfs_distintos",
                "qtd_cpfs_incompativeis",
                "qtd_autorizacoes",
                "qtd_autorizacoes_incompativeis",
                "valor_total_pago",
                "valor_incompativel_pago",
                "percentual_cpfs_incompativeis",
                "rank_regional_qtd_cpfs_incompativeis",
                "rank_regional_valor_incompativel_pago",
                "percentil_regional_qtd_cpfs_incompativeis",
                "percentil_regional_valor_incompativel_pago",
                "participacao_cpfs_incompativeis_regiao",
                "participacao_valor_incompativel_regiao",
                "percentual_regional_cpfs_incompativeis",
                "razao_percentual_vs_regiao",
                "cpfs_incompativeis_esperados_regiao",
                "excesso_cpfs_incompativeis_vs_regiao",
                "dt_processamento",
            },
            "analise_gtin_inconsistencia_clinica_municipio": {
                "id_ibge7",
                "patologia",
                "regra_clinica",
                "ano_base",
                "qtd_cpfs_distintos_municipio",
                "qtd_cpfs_incompativeis_municipio",
                "qtd_autorizacoes_municipio",
                "qtd_autorizacoes_incompativeis_municipio",
                "valor_total_pago_municipio",
                "valor_incompativel_pago_municipio",
                "dt_processamento",
            },
            "analise_gtin_inconsistencia_clinica_regiao": {
                "id_regiao_saude",
                "patologia",
                "regra_clinica",
                "ano_base",
                "qtd_cnpjs_regiao",
                "qtd_municipios_regiao",
                "qtd_cpfs_distintos_regiao",
                "qtd_cpfs_incompativeis_regiao",
                "qtd_autorizacoes_regiao",
                "qtd_autorizacoes_incompativeis_regiao",
                "valor_total_pago_regiao",
                "valor_incompativel_pago_regiao",
                "percentual_cpfs_incompativeis_regiao",
                "dt_processamento",
            },
            "dados_ibge_demografia": {
                "id_ibge7",
                "grupo_idade",
                "sexo",
                "nu_populacao",
                "ano_censo",
                "idade_min",
                "idade_max",
                "ordem",
            },
            "volume_atipico_semestral": {
                "id_cnpj",
                "chave_semestre",
                "status_semestre",
                "qtd_meses_presentes",
                "chave_semestre_anterior",
                "taxa_crescimento_pct",
                "aumento_valor_semestre",
            },
            "geografico_origem_uf": {
                "id_cnpj",
                "ano_base",
                "uf_farmacia",
                "uf_paciente",
                "is_outra_uf",
                "qtd_autorizacoes",
                "valor_autorizado",
            },
            "crm_raiox_tx_global": {
                "id_cnpj",
                "dt_janela",
                "hr_janela",
                "data_hora",
                "num_autorizacao",
                "id_medico",
                "valor_pago",
                "_crm_raiox_tx_cache_version",
            },
            "pagamentos_consolidados_farmacia_popular": {
                "id_cnpj",
                "data_pagamento",
                "programa_acao",
                "numero_ordem_bancaria",
                "valor_pago",
                "_pagamentos_consolidados_farmacia_popular_cache_version",
            },
            "crm_prescritores_global": {
                "id_cnpj",
                "id_medico",
                "competencia",
                "vl_total_prescricoes",
                "nu_prescricoes_mes",
                "nu_prescricoes_total_brasil",
                "flag_crm_invalido",
                "flag_prescricao_antes_registro",
                "alerta_concentracao_multiplos_crms",
                "flag_concentracao_mesmo_crm",
                "flag_distancia_geografica",
                "dt_inscricao_crm",
                "nu_estabelecimentos",
                "_crm_prescritores_cache_version",
            },
            "memoria_calculo_global": {
                "cnpj",
                "id_processamento",
                "schema_version",
                "memoria_calculo_payload",
                "_memoria_calculo_cache_version",
            },
            "esocial_cnpj_ano": {
                "id_cnpj",
                "ano_base",
                "mes_base",
                "competencia_base",
                "qtd_registros",
                "qtd_trabalhadores",
                "qtd_farmaceuticos",
                "qtd_trabalhadores_cbo_sem_titulo",
                "qtd_registros_farmaceuticos",
                "qtd_registros_cbo_sem_titulo",
                "has_farmaceutico",
                "has_cbo_sem_titulo",
                "is_um_trabalhador",
                "is_um_trabalhador_sem_farmaceutico",
                "is_um_trabalhador_cbo_sem_titulo",
                "cbo_unico_trabalhador",
                "titulo_cbo_unico_trabalhador",
                "qtd_registros_vinculo_ano",
                "qtd_trabalhadores_vinculo_ano",
                "qtd_farmaceuticos_vinculo_ano",
                "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano",
                "dt_carga_fonte",
                "dt_processamento",
            },
            "esocial_cnpj_trabalhador_ano": {
                "id_cnpj",
                "ano_base",
                "mes_base",
                "competencia_base",
                "cpf_trabalhador",
                "matricula",
                "cbo",
                "titulo_cbo",
                "dt_admissao",
                "dt_rescisao",
                "is_farmaceutico",
                "is_cbo_sem_titulo",
                "dt_carga_fonte",
                "dt_processamento",
            },
            "esocial_cnpj_movimentacao_ano": {
                "id_cnpj",
                "ano_base",
                "id_regiao_saude",
                "uf",
                "periodo_min",
                "periodo_max",
                "valor_pfpb_ano",
                "valor_sem_comprovacao_ano",
                "qtd_autorizacoes_ano",
                "qtd_caixas_ano",
                "qtd_caixas_sem_comprovacao_ano",
                "qtd_trabalhadores",
                "qtd_farmaceuticos",
                "valor_pfpb_por_trabalhador",
                "valor_sem_comprovacao_por_trabalhador",
                "autorizacoes_por_trabalhador",
                "caixas_por_trabalhador",
                "p90_referencia_valor_pfpb_ano",
                "p95_referencia_valor_por_trabalhador",
                "qtd_cnpjs_referencia",
                "escopo_referencia",
                "classificacao_mov_trabalhista",
                "motivo_classificacao",
                "dt_processamento",
            },
            "esocial_cnpj_ultima_movimentacao": {
                "id_cnpj",
                "ano_ultima_movimentacao",
                "ano_esocial_referencia_ultima_movimentacao",
                "is_sem_esocial_no_ano_ultima_movimentacao",
                "ultimo_periodo_movimentacao",
                "dt_inicio_ultimo_mes_movimentacao",
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
                "classificacao_mov_sem_funcionario",
                "motivo_mov_sem_funcionario",
                "dt_processamento",
            },
            "sentinela_metadados_base": {
                "nome_base",
                "nome_artefato",
                "fonte_origem",
                "dt_referencia_min",
                "dt_referencia_max",
                "competencia_min",
                "competencia_max",
                "qtd_registros",
                "qtd_chaves",
                "schema_versao",
                "dt_processamento_inicio",
                "dt_processamento_fim",
                "observacao",
            },
            "falecidos": {
                "cnpj",
                "cpf",
                "nome_falecido",
                "municipio_falecido",
                "uf_falecido",
                "dt_nascimento",
                "dt_obito",
                "fonte_obito",
                "num_autorizacao",
                "data_autorizacao",
                "qtd_itens_na_autorizacao",
                "valor_total_autorizacao",
                "dias_apos_obito",
            },
            "dados_par": {
                "cnpj",
                "is_par",
                "qtd_processos_par",
                "par_situacoes",
                "par_primeira_instauracao",
                "par_ultima_instauracao",
                "par_ultima_conclusao",
            },
            "par_teia_alvos": {
                "cnpj",
                "has_par_alvo",
                "has_par_n2",
                "has_par_n4",
                "has_par_qualquer",
                "qtd_par_alvo",
                "qtd_empresas_par_n2",
                "qtd_empresas_par_n4",
                "qtd_empresas_par_qualquer",
            },
        }
        def _try_load(name, path):
            if not os.path.exists(path):
                missing.append(name)
                return None
            try:
                df = pl.read_parquet(path)
                required = required_columns.get(name)
                if required and not required.issubset(set(df.columns)):
                    missing_cols = ", ".join(sorted(required - set(df.columns)))
                    raise ValueError(f"schema antigo sem colunas obrigatorias: {missing_cols}")
                return df
            except Exception as e:
                print(f"[ CACHE ] GLOBAL - {name} - [AVISO] ERRO DE LEITURA ({e})")
                missing.append(name)
                return None

        def _try_mark_on_demand(name, path):
            try:
                _mark_on_demand_global_cache_ready(name, path)
            except Exception as e:
                print(f"[ CACHE ] GLOBAL - {name} - [AVISO] ERRO DE LEITURA ({e})")
                missing.append(name)

        _df_movimentacao    = _try_load("movimentacao",    _PARQUET_PATH)
        _df_localidades     = _try_load("localidades",     _LOCALIDADES_PARQUET_PATH)
        _df_rede            = _try_load("rede",            _REDE_PARQUET_PATH)
        _df_matriz_risco    = _try_load("matriz_risco",    _MATRIZ_PARQUET_PATH)
        _df_bench_crm_uf    = _try_load("bench_crm_uf",   _BENCH_CRM_UF_PATH)
        _df_bench_crm_regiao= _try_load("bench_crm_regiao", _BENCH_CRM_REGIAO_PATH)
        _df_bench_crm_br    = _try_load("bench_crm_br",   _BENCH_CRM_BR_PATH)
        _df_dados_farmacia  = _try_load("dados_farmacia",  _DADOS_FARMACIA_PARQUET_PATH)
        _df_dados_farmacia_cnaes_secundarios = _try_load(
            "dados_farmacia_cnaes_secundarios",
            _DADOS_FARMACIA_CNAES_SECUNDARIOS_PARQUET_PATH,
        )
        _df_perfil_estabelecimento = _try_load("perfil_estabelecimento", _PERFIL_ESTABELECIMENTO_PARQUET_PATH)
        _df_dados_socios    = _try_load("dados_socios",    _DADOS_SOCIOS_PARQUET_PATH)
        _df_teia_fonte_nivel2 = None
        _df_teia_fonte_nivel3 = None
        _df_teia_fonte_nivel4 = None
        _try_mark_on_demand("teia_fonte_nivel2", _TEIA_FONTE_NIVEL2_PARQUET_PATH)
        _try_mark_on_demand("teia_fonte_nivel3", _TEIA_FONTE_NIVEL3_PARQUET_PATH)
        _try_mark_on_demand("teia_fonte_nivel4", _TEIA_FONTE_NIVEL4_PARQUET_PATH)
        _df_medicamentos    = _try_load("medicamentos",    _MEDICAMENTOS_PARQUET_PATH)
        _df_analise_gtin_inconsistencia_clinica = None
        _df_analise_gtin_inconsistencia_clinica_municipio = None
        _df_analise_gtin_inconsistencia_clinica_regiao = None
        _try_mark_on_demand("analise_gtin_inconsistencia_clinica", _ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH)
        _try_mark_on_demand("analise_gtin_inconsistencia_clinica_municipio", _ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH)
        _try_mark_on_demand("analise_gtin_inconsistencia_clinica_regiao", _ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH)
        _df_dados_ibge_demografia = _try_load("dados_ibge_demografia", _DADOS_IBGE_DEMOGRAFIA_PARQUET_PATH)
        _df_volume_atipico_semestral = _try_load("volume_atipico_semestral", _VOLUME_ATIPICO_SEMESTRAL_PARQUET_PATH)
        _try_mark_on_demand("crm_prescricoes_brasil_semestre", _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH)
        if "crm_prescricoes_estabelecimento_mes" not in _DISABLED_BOOT_MODULES:
            _try_mark_on_demand("crm_prescricoes_estabelecimento_mes", _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH)
        if "crm_prescricoes_medico_municipio_mes" not in _DISABLED_BOOT_MODULES:
            _try_mark_on_demand("crm_prescricoes_medico_municipio_mes", _CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PATH)
        if "crm_prescricoes_gerencial" not in _DISABLED_BOOT_MODULES:
            _try_mark_on_demand("crm_prescricoes_gerencial", _CRM_PRESCRICOES_GERENCIAL_PATH)
        _try_mark_on_demand("dados_medico", _DADOS_MEDICO_PARQUET_PATH)
        _try_mark_on_demand("crm_prescritores_global", _CRM_PRESCRITORES_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("memoria_calculo_global", _MEMORIA_CALCULO_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("geografico_origem_uf", _GEOGRAFICO_ORIGEM_UF_PARQUET_PATH)
        _try_mark_on_demand("crm_raiox_tx_global", _CRM_RAIOX_TX_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand(
            "pagamentos_consolidados_farmacia_popular",
            _PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH,
        )
        _try_mark_on_demand("geografico_global", _GEOGRAFICO_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("crm_concentracao_unico_alertas_global", _CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("crm_concentracao_multiplo_alertas_global", _CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("crm_timeline_dia_global", _CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("crm_timeline_hora_global", _CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("crm_timeline_eventos_global", _CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH)
        _try_mark_on_demand("movimentacao_mensal_gtin_global", _MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH)
        _df_esocial_cnpj_ano = None
        _df_esocial_cnpj_trabalhador_ano = None
        _df_esocial_cnpj_movimentacao_ano = None
        _df_esocial_cnpj_ultima_movimentacao = None
        _try_mark_on_demand("esocial_cnpj_ano", _ESOCIAL_CNPJ_ANO_PARQUET_PATH)
        _try_mark_on_demand("esocial_cnpj_trabalhador_ano", _ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH)
        _try_mark_on_demand("esocial_cnpj_movimentacao_ano", _ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH)
        _try_mark_on_demand("esocial_cnpj_ultima_movimentacao", _ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH)
        _df_sentinela_metadados_base = _try_load("sentinela_metadados_base", _SENTINELA_METADADOS_BASE_PARQUET_PATH)
        _df_falecidos = _try_load("falecidos", _FALECIDOS_PARQUET_PATH)
        dados_par_loaded = _try_load("dados_par", _DADOS_PAR_PARQUET_PATH)
        _df_dados_par = dados_par_loaded
        par_teia_alvos_loaded = _try_load("par_teia_alvos", _PAR_TEIA_ALVOS_PARQUET_PATH)
        _df_par_teia_alvos = par_teia_alvos_loaded

        if missing:
            print(f"[AVISO]  Cache incompleto — módulos ausentes: {', '.join(missing)}")
            print("[INFO]  Sistema iniciado em modo degradado. Sincronize pela interface para carregar os dados.")
            _cache_status = "idle"
            _cache_progress = 0
        else:
            _cache_progress = 100
            _cache_status = "ready"
            _cache_generation += 1
            print(f"[OK] Caches carregados via Parquet.")
        return

    from typing import TypedDict, Callable, List

    class SyncTask(TypedDict):
        name: str
        weight: int
        func: Callable[[Callable[[int], None]], None]

    TASKS: List[SyncTask] = [
        {"name": "Cadastro Medicamentos", "weight": 5,  "func": lambda cb: _sync_medicamentos(engine, cb)},
        {"name": "Localidades",           "weight": 2,  "func": lambda cb: _sync_localidades(engine, cb)},
        {"name": "Rede Estabelecimentos", "weight": 3,  "func": lambda cb: _sync_rede(engine, cb)},
        {"name": "Matriz de Risco",       "weight": 11, "func": lambda cb: _sync_matriz_risco(engine, cb)},
        {"name": "Analise Clinica por Patologia", "weight": 2, "func": lambda cb: _sync_analise_gtin_inconsistencia_clinica(engine, cb)},
        {"name": "Analise Clinica Municipal", "weight": 2, "func": lambda cb: _sync_analise_gtin_inconsistencia_clinica_municipio(engine, cb)},
        {"name": "Analise Clinica Regiao", "weight": 2, "func": lambda cb: _sync_analise_gtin_inconsistencia_clinica_regiao(engine, cb)},
        {"name": "Demografia IBGE",       "weight": 2,  "func": lambda cb: _sync_dados_ibge_demografia(engine, cb)},
        {"name": "Volume Atipico Semestral", "weight": 5, "func": lambda cb: _sync_volume_atipico_semestral(engine, cb)},
        {"name": "CRM Brasil Semestral",    "weight": 1,  "func": lambda cb: _sync_crm_prescricoes_brasil_semestre(engine, cb)},
        {"name": "CRM Prescricoes Estabelecimento/Mes", "weight": 5, "func": lambda cb: _sync_crm_prescricoes_estabelecimento_mes(engine, cb)},
        {"name": "CRM Prescricoes Medico/Municipio/Mes", "weight": 3, "func": lambda cb: _sync_crm_prescricoes_medico_municipio_mes(engine, cb)},
        {"name": "CRM Prescricoes Gerencial", "weight": 2, "func": lambda cb: _sync_crm_prescricoes_gerencial(engine, cb)},
        {"name": "Dados Medico",            "weight": 1,  "func": lambda cb: _sync_dados_medico(engine, cb)},
        {"name": "Geografico Origem UF",  "weight": 2,  "func": lambda cb: _sync_geografico_origem_uf(engine, cb)},
        {"name": "Contexto eSocial",      "weight": 3,  "func": lambda cb: _sync_esocial(engine, cb)},
        {"name": "Metadados das Bases",   "weight": 1,  "func": lambda cb: _sync_sentinela_metadados_base(engine, cb)},
        {"name": "Falecidos",             "weight": 2,  "func": lambda cb: _sync_falecidos(engine, cb)},
        {"name": "Indicadores PAR",       "weight": 1,  "func": lambda cb: _sync_dados_par(engine, cb)},
        {"name": "Dados das Farmácias",   "weight": 5,  "func": lambda cb: _sync_dados_farmacia(engine, cb)},
        {"name": "Perfil Estabelecimentos", "weight": 5, "func": lambda cb: _sync_perfil_estabelecimento(engine, cb)},
        {"name": "Dados dos Sócios",      "weight": 5,  "func": lambda cb: _sync_dados_socios(engine, cb)},
        {"name": "Participações e Representantes", "weight": 5, "func": lambda cb: _sync_teia_fonte_nivel2(engine, cb)},
        {"name": "Sócios Indiretos (Expansão)", "weight": 4, "func": lambda cb: _sync_teia_fonte_nivel3(engine, cb)},
        {"name": "Expansão Nacional (N4)",  "weight": 8, "func": lambda cb: _sync_teia_fonte_nivel4(engine, cb)},
        {"name": "PAR na Teia dos Alvos",   "weight": 1,  "func": lambda cb: _sync_par_teia_alvos(engine, cb)},
        {"name": "Movimentação (Vendas)", "weight": 42, "func": lambda cb: _sync_movimentacao(engine, cb)},
        {"name": "CRM Geografico Global", "weight": 2, "func": lambda cb: _sync_geografico_global(engine, cb)},
        {"name": "CRM Conc. Unico Global", "weight": 2, "func": lambda cb: _sync_crm_concentracao_unico_alertas_global(engine, cb)},
        {"name": "CRM Conc. Multiplo Global", "weight": 2, "func": lambda cb: _sync_crm_concentracao_multiplo_alertas_global(engine, cb)},
        {"name": "CRM Timeline Hora Global", "weight": 2, "func": lambda cb: _sync_crm_timeline_hora_global(engine, cb)},
        {"name": "CRM Timeline Eventos Global", "weight": 2, "func": lambda cb: _sync_crm_timeline_eventos_global(engine, cb)},
        {"name": "Movimentacao Mensal GTIN Global", "weight": 5, "func": lambda cb: _sync_movimentacao_mensal_gtin_global(engine, cb)},
    ]

    t0 = time.perf_counter()
    total_weight = sum(task["weight"] for task in TASKS)
    acumulado_weight = 0

    try:
        for task in TASKS:
            _cache_status = task["name"]
            current_weight = task["weight"]
            print(f"[*] {task['name']}...")

            def update_global_progress(p_int: int, _base=acumulado_weight, _w=current_weight):
                global _cache_progress
                progresso_ponderado = _base + (p_int / 100 * _w)
                _cache_progress = min(100, int(progresso_ponderado / total_weight * 100))

            task["func"](update_global_progress)
            acumulado_weight += current_weight

        _cache_progress = 100
        _cache_status = "ready"
        print(f"[OK] Sincronização concluída em {time.perf_counter() - t0:.1f}s")

        _cache_generation += 1

    except Exception as e:
        _cache_status = "error"
        _cache_progress = 0
        _cache_error_message = str(e)
        import traceback
        print(f"[ERRO] Erro Crítico na Sincronização: {e}")
        print(traceback.format_exc())

def refresh_cache(engine) -> None:
    """Força re-leitura do SQL e regera os Parquets."""
    load_cache(engine, force_refresh=True)

def get_cache_generation() -> int:
    """Retorna a geracao dos dados globais carregados em memoria."""
    return _cache_generation

def get_df() -> pl.DataFrame:
    if _df_movimentacao is None: 
        raise RuntimeError("Cache de Movimentação não carregado. Verifique a sincronização.")
    return _df_movimentacao

def get_rede_df() -> pl.DataFrame:
    if _df_rede is None:
        raise RuntimeError("Cache de Rede de Estabelecimentos não carregado. Verifique a sincronização.")
    return _df_rede

def get_localidades_df() -> pl.DataFrame:
    if _df_localidades is None:
        raise RuntimeError("Cache de Localidades não carregado. Verifique a sincronização.")
    return _df_localidades

def get_df_matriz_risco() -> pl.DataFrame:
    if _df_matriz_risco is None:
        raise RuntimeError("Cache de Matriz de Risco não carregado. Execute uma sincronização.")
    return _df_matriz_risco


def get_df_bench_crm_regiao() -> pl.DataFrame:
    if _df_bench_crm_regiao is None:
        raise RuntimeError("Cache de Benchmark CRM (Região) não carregado. Execute uma sincronização.")
    return _df_bench_crm_regiao

def get_df_bench_crm_br() -> pl.DataFrame:
    if _df_bench_crm_br is None:
        raise RuntimeError("Cache de Benchmark CRM (Brasil) não carregado. Execute uma sincronização.")
    return _df_bench_crm_br

def get_df_dados_farmacia() -> pl.DataFrame:
    if _df_dados_farmacia is None:
        raise RuntimeError("Cache de Dados das Farmácias não carregado. Execute uma sincronização.")
    return _df_dados_farmacia

def get_df_dados_farmacia_cnaes_secundarios() -> pl.DataFrame:
    if _df_dados_farmacia_cnaes_secundarios is None:
        raise RuntimeError(
            "Cache de CNAEs secundarios das farmacias nao carregado. "
            "Execute uma sincronizacao."
        )
    return _df_dados_farmacia_cnaes_secundarios

def get_df_perfil_estabelecimento() -> pl.DataFrame:
    if _df_perfil_estabelecimento is None:
        raise RuntimeError("Cache de Perfil dos Estabelecimentos nao carregado. Execute uma sincronizacao.")
    return _df_perfil_estabelecimento

def get_df_dados_socios() -> pl.DataFrame:
    if _df_dados_socios is None:
        raise RuntimeError("Cache de Dados dos Sócios não carregado. Execute uma sincronização.")
    return _df_dados_socios

def scan_teia_fonte_nivel2() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("teia_fonte_nivel2", _TEIA_FONTE_NIVEL2_PARQUET_PATH)

def scan_teia_fonte_nivel3() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("teia_fonte_nivel3", _TEIA_FONTE_NIVEL3_PARQUET_PATH)

def scan_teia_fonte_nivel4() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("teia_fonte_nivel4", _TEIA_FONTE_NIVEL4_PARQUET_PATH)


def scan_crm_prescricoes_brasil_semestre() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "crm_prescricoes_brasil_semestre",
        _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH,
    )


def scan_crm_prescricoes_estabelecimento_mes() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "crm_prescricoes_estabelecimento_mes",
        _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH,
    )


def scan_crm_prescricoes_medico_municipio_mes() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "crm_prescricoes_medico_municipio_mes",
        _CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PATH,
    )


def scan_crm_prescricoes_gerencial() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "crm_prescricoes_gerencial",
        _CRM_PRESCRICOES_GERENCIAL_PATH,
    )


def scan_dados_medico() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("dados_medico", _DADOS_MEDICO_PARQUET_PATH)


def get_medicamentos_df() -> pl.DataFrame:
    global _df_medicamentos
    if _df_medicamentos is None:
        # Se não carregado, tentamos ler do parquet direto se existir
        if os.path.exists(_MEDICAMENTOS_PARQUET_PATH):
            try:
                _df_medicamentos = pl.read_parquet(_MEDICAMENTOS_PARQUET_PATH)
                return _df_medicamentos
            except Exception as e:
                print(f"[ CACHE ] GLOBAL - medicamentos - [AVISO] ERRO DE LEITURA ({e})")
        raise RuntimeError("Cache de Medicamentos não carregado. Execute uma sincronização.")
    return _df_medicamentos

def scan_analise_gtin_inconsistencia_clinica() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "analise_gtin_inconsistencia_clinica",
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH,
    )

def scan_analise_gtin_inconsistencia_clinica_municipio() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "analise_gtin_inconsistencia_clinica_municipio",
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH,
    )

def scan_analise_gtin_inconsistencia_clinica_regiao() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "analise_gtin_inconsistencia_clinica_regiao",
        _ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH,
    )


def get_df_dados_ibge_demografia() -> pl.DataFrame:
    if _df_dados_ibge_demografia is None:
        raise RuntimeError("Cache de Demografia IBGE nao carregado. Execute uma sincronizacao.")
    return _df_dados_ibge_demografia

def get_df_volume_atipico_semestral() -> pl.DataFrame:
    if _df_volume_atipico_semestral is None:
        raise RuntimeError("Cache de Volume Atipico Semestral nao carregado. Execute uma sincronizacao.")
    return _df_volume_atipico_semestral

def scan_esocial_cnpj_ano() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("esocial_cnpj_ano", _ESOCIAL_CNPJ_ANO_PARQUET_PATH)

def scan_esocial_cnpj_trabalhador_ano() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "esocial_cnpj_trabalhador_ano",
        _ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH,
    )

def scan_geografico_origem_uf() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "geografico_origem_uf",
        _GEOGRAFICO_ORIGEM_UF_PARQUET_PATH,
    )


def scan_geografico_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("geografico_global", _GEOGRAFICO_GLOBAL_PARQUET_PATH)

def scan_crm_concentracao_unico_alertas_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("crm_concentracao_unico_alertas_global", _CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH)

def scan_crm_concentracao_multiplo_alertas_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("crm_concentracao_multiplo_alertas_global", _CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH)

def scan_crm_timeline_dia_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("crm_timeline_dia_global", _CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH)

def scan_crm_timeline_hora_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("crm_timeline_hora_global", _CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH)

def scan_crm_timeline_eventos_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("crm_timeline_eventos_global", _CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH)

def scan_movimentacao_mensal_gtin_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet("movimentacao_mensal_gtin_global", _MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH)

def scan_crm_raiox_tx_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "crm_raiox_tx_global",
        _CRM_RAIOX_TX_GLOBAL_PARQUET_PATH,
    )


def scan_pagamentos_consolidados_farmacia_popular() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "pagamentos_consolidados_farmacia_popular",
        _PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH,
    )


def scan_crm_prescritores_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "crm_prescritores_global",
        _CRM_PRESCRITORES_GLOBAL_PARQUET_PATH,
    )

def scan_memoria_calculo_global() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "memoria_calculo_global",
        _MEMORIA_CALCULO_GLOBAL_PARQUET_PATH,
    )

def scan_esocial_cnpj_movimentacao_ano() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "esocial_cnpj_movimentacao_ano",
        _ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH,
    )

def scan_esocial_cnpj_ultima_movimentacao() -> pl.LazyFrame:
    return _scan_on_demand_global_parquet(
        "esocial_cnpj_ultima_movimentacao",
        _ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH,
    )


def get_df_sentinela_metadados_base() -> pl.DataFrame:
    if _df_sentinela_metadados_base is None:
        raise RuntimeError("Cache de metadados das bases Sentinela nao carregado. Execute uma sincronizacao.")
    return _df_sentinela_metadados_base

def get_df_falecidos() -> pl.DataFrame:
    if _df_falecidos is None:
        raise RuntimeError("Cache global de falecidos nao carregado. Execute uma sincronizacao.")
    return _df_falecidos

def get_df_dados_par() -> pl.DataFrame:
    if _df_dados_par is None:
        raise RuntimeError("Cache de Indicadores PAR nao carregado. Execute uma sincronizacao.")
    return _df_dados_par

def get_df_par_teia_alvos() -> pl.DataFrame:
    if _df_par_teia_alvos is None:
        raise RuntimeError("Cache de PAR na Teia dos Alvos nao carregado. Execute uma sincronizacao.")
    return _df_par_teia_alvos


def get_cache_status() -> dict:
    """Retorna o estado atual da sincronização para o frontend."""
    optional_modules = {
        "crm_prescritores_global",
        "memoria_calculo_global",
        "crm_raiox_tx_global",
        "pagamentos_consolidados_farmacia_popular",
        "crm_timeline_dia_global",
        "crm_timeline_hora_global",
        "crm_timeline_eventos_global",
        "crm_concentracao_multiplo_alertas_global",
        "crm_concentracao_unico_alertas_global",
        "movimentacao_mensal_gtin_global",
    }
    modules = {
        "movimentacao":   {"label": "Movimentação Mensal",     "path": _PARQUET_PATH,             "loaded": _df_movimentacao is not None},
        "localidades":    {"label": "Localidades (IBGE)",      "path": _LOCALIDADES_PARQUET_PATH, "loaded": _df_localidades is not None},
        "rede":           {"label": "Rede de Estabelecimentos","path": _REDE_PARQUET_PATH,        "loaded": _df_rede is not None},
        "matriz_risco":   {"label": "Matriz de Risco",         "path": _MATRIZ_PARQUET_PATH,      "loaded": _df_matriz_risco is not None},
        "bench_crm_uf":    {"label": "Benchmark CRM (UF)",      "path": _BENCH_CRM_UF_PATH,        "loaded": _df_bench_crm_uf is not None},
        "bench_crm_regiao":{"label": "Benchmark CRM (Região)", "path": _BENCH_CRM_REGIAO_PATH,    "loaded": _df_bench_crm_regiao is not None},
        "bench_crm_br":    {"label": "Benchmark CRM (Brasil)", "path": _BENCH_CRM_BR_PATH,        "loaded": _df_bench_crm_br is not None},
        "crm_prescricoes_brasil_semestre": {"label": "CRM Brasil Semestral", "path": _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH, "loaded": _is_on_demand_global_cache_ready("crm_prescricoes_brasil_semestre", _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH)},
        "crm_prescricoes_estabelecimento_mes": {"label": "CRM Prescricoes Estabelecimento/Mes", "path": _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH, "loaded": _is_on_demand_global_cache_ready("crm_prescricoes_estabelecimento_mes", _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH)},
        "crm_prescricoes_medico_municipio_mes": {"label": "CRM Prescricoes Medico/Municipio/Mes", "path": _CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PATH, "loaded": _is_on_demand_global_cache_ready("crm_prescricoes_medico_municipio_mes", _CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PATH)},
        "crm_prescricoes_gerencial": {"label": "CRM Prescricoes Gerencial/Mensal", "path": _CRM_PRESCRICOES_GERENCIAL_PATH, "loaded": _is_on_demand_global_cache_ready("crm_prescricoes_gerencial", _CRM_PRESCRICOES_GERENCIAL_PATH)},
        "dados_medico": {"label": "Dados Medico", "path": _DADOS_MEDICO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("dados_medico", _DADOS_MEDICO_PARQUET_PATH)},
        "crm_prescritores_global": {"label": "CRM Prescritores Global", "path": _CRM_PRESCRITORES_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_prescritores_global", _CRM_PRESCRITORES_GLOBAL_PARQUET_PATH)},
        "memoria_calculo_global": {"label": "Memoria Calculo Global", "path": _MEMORIA_CALCULO_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("memoria_calculo_global", _MEMORIA_CALCULO_GLOBAL_PARQUET_PATH)},
        "crm_raiox_tx_global": {"label": "CRM Raio-X Global", "path": _CRM_RAIOX_TX_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_raiox_tx_global", _CRM_RAIOX_TX_GLOBAL_PARQUET_PATH)},
        "pagamentos_consolidados_farmacia_popular": {
            "label": "Pagamentos FP Global",
            "path": _PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH,
            "loaded": _is_on_demand_global_cache_ready(
                "pagamentos_consolidados_farmacia_popular",
                _PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH,
            ),
        },
        "geografico_global": {"label": "CRM Geografico Global", "path": _GEOGRAFICO_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("geografico_global", _GEOGRAFICO_GLOBAL_PARQUET_PATH)},
        "crm_concentracao_unico_alertas_global": {"label": "CRM Concentracao Unico Global", "path": _CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_concentracao_unico_alertas_global", _CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH)},
        "crm_concentracao_multiplo_alertas_global": {"label": "CRM Concentracao Multiplo Global", "path": _CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_concentracao_multiplo_alertas_global", _CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH)},
        "crm_timeline_dia_global": {"label": "CRM Timeline Dia Global", "path": _CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_timeline_dia_global", _CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH)},
        "crm_timeline_hora_global": {"label": "CRM Timeline Hora Global", "path": _CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_timeline_hora_global", _CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH)},
        "crm_timeline_eventos_global": {"label": "CRM Timeline Eventos Global", "path": _CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("crm_timeline_eventos_global", _CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH)},
        "movimentacao_mensal_gtin_global": {"label": "GTIN Mensal Global", "path": _MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("movimentacao_mensal_gtin_global", _MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH)},
        "dados_farmacia": {"label": "Dados das Farmácias",     "path": _DADOS_FARMACIA_PARQUET_PATH,  "loaded": _df_dados_farmacia is not None},
        "dados_farmacia_cnaes_secundarios": {
            "label": "CNAEs Secundarios das Farmacias",
            "path": _DADOS_FARMACIA_CNAES_SECUNDARIOS_PARQUET_PATH,
            "loaded": _df_dados_farmacia_cnaes_secundarios is not None,
        },
        "perfil_estabelecimento": {"label": "Perfil Estabelecimentos", "path": _PERFIL_ESTABELECIMENTO_PARQUET_PATH, "loaded": _df_perfil_estabelecimento is not None},
        "dados_socios":   {"label": "Dados dos Sócios",        "path": _DADOS_SOCIOS_PARQUET_PATH,    "loaded": _df_dados_socios is not None},
        "teia_fonte_nivel2":{"label": "Participações Externas",  "path": _TEIA_FONTE_NIVEL2_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("teia_fonte_nivel2", _TEIA_FONTE_NIVEL2_PARQUET_PATH)},
        "teia_fonte_nivel3":{"label": "Sócios Indiretos",        "path": _TEIA_FONTE_NIVEL3_PARQUET_PATH,   "loaded": _is_on_demand_global_cache_ready("teia_fonte_nivel3", _TEIA_FONTE_NIVEL3_PARQUET_PATH)},
        "teia_fonte_nivel4":{"label": "Expansão Nacional (N4)",  "path": _TEIA_FONTE_NIVEL4_PARQUET_PATH,   "loaded": _is_on_demand_global_cache_ready("teia_fonte_nivel4", _TEIA_FONTE_NIVEL4_PARQUET_PATH)},
        "medicamentos":   {"label": "Cadastro Medicamentos",   "path": _MEDICAMENTOS_PARQUET_PATH,    "loaded": _df_medicamentos is not None},
        "analise_gtin_inconsistencia_clinica": {"label": "Analise Clinica por Patologia", "path": _ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("analise_gtin_inconsistencia_clinica", _ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH)},
        "analise_gtin_inconsistencia_clinica_municipio": {"label": "Analise Clinica Municipal", "path": _ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("analise_gtin_inconsistencia_clinica_municipio", _ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH)},
        "analise_gtin_inconsistencia_clinica_regiao": {"label": "Analise Clinica Regiao", "path": _ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("analise_gtin_inconsistencia_clinica_regiao", _ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH)},
        "dados_ibge_demografia": {"label": "Demografia IBGE", "path": _DADOS_IBGE_DEMOGRAFIA_PARQUET_PATH, "loaded": _df_dados_ibge_demografia is not None},
        "volume_atipico_semestral": {"label": "Volume Atipico Semestral", "path": _VOLUME_ATIPICO_SEMESTRAL_PARQUET_PATH, "loaded": _df_volume_atipico_semestral is not None},
        "geografico_origem_uf": {"label": "Geografico Origem UF", "path": _GEOGRAFICO_ORIGEM_UF_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("geografico_origem_uf", _GEOGRAFICO_ORIGEM_UF_PARQUET_PATH)},
        "esocial_cnpj_ano": {"label": "eSocial CNPJ/Ano", "path": _ESOCIAL_CNPJ_ANO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("esocial_cnpj_ano", _ESOCIAL_CNPJ_ANO_PARQUET_PATH)},
        "esocial_cnpj_trabalhador_ano": {"label": "eSocial Trabalhador/Ano", "path": _ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("esocial_cnpj_trabalhador_ano", _ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH)},
        "esocial_cnpj_movimentacao_ano": {"label": "eSocial Movimentacao/Ano", "path": _ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("esocial_cnpj_movimentacao_ano", _ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH)},
        "esocial_cnpj_ultima_movimentacao": {"label": "eSocial Ultima Movimentacao", "path": _ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH, "loaded": _is_on_demand_global_cache_ready("esocial_cnpj_ultima_movimentacao", _ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH)},
        "sentinela_metadados_base": {"label": "Metadados das Bases", "path": _SENTINELA_METADADOS_BASE_PARQUET_PATH, "loaded": _df_sentinela_metadados_base is not None},
        "falecidos": {"label": "Falecidos", "path": _FALECIDOS_PARQUET_PATH, "loaded": _df_falecidos is not None},
        "dados_par":      {"label": "Indicadores PAR",          "path": _DADOS_PAR_PARQUET_PATH,       "loaded": _df_dados_par is not None},
        "par_teia_alvos": {"label": "PAR na Teia dos Alvos",     "path": _PAR_TEIA_ALVOS_PARQUET_PATH,  "loaded": _df_par_teia_alvos is not None},
    }
    for module_name in _DISABLED_BOOT_MODULES:
        modules.pop(module_name, None)

    modules_status = {}
    for key, v in modules.items():
        path = str(v["path"])
        label = str(v["label"])
        loaded = bool(v["loaded"])
        exists = os.path.exists(path)
        optional = key in optional_modules
        modules_status[key] = {
            "label": label,
            "exists": exists,
            "loaded": loaded,
            "optional": optional,
            "status": _get_cache_module_status(loaded, exists),
        }

    total_modules = len(modules_status)
    loaded_modules = sum(1 for v in modules_status.values() if v["loaded"])
    required_modules = [v for v in modules_status.values() if not v["optional"]]
    total_required_modules = len(required_modules)
    loaded_required_modules = sum(1 for v in required_modules if v["loaded"])
    unavailable_modules = total_required_modules - loaded_required_modules
    is_ready = all(v["loaded"] for v in required_modules)
    return {
        "progress": _cache_progress,
        "status": _cache_status,
        "is_ready": is_ready,
        "loaded_modules": loaded_modules,
        "total_modules": total_modules,
        "loaded_required_modules": loaded_required_modules,
        "total_required_modules": total_required_modules,
        "unavailable_modules": unavailable_modules,
        "modules_summary_label": f"{loaded_required_modules}/{total_required_modules} modulos obrigatorios carregados",
        "error_message": _cache_error_message if _cache_status == "error" else "",
        "modules": modules_status,
    }
