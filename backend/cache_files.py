"""Nomes canonicos dos arquivos de cache do Sentinela."""

MODULE_EXT = ".smod"
CRM_RAIOX_TX_CACHE_VERSION = 3
CRM_PRESCRITORES_CACHE_VERSION = 3
CRM_PRESCRICOES_ESTABELECIMENTO_MES_CACHE_VERSION = 3
CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_CACHE_VERSION = 1
CRM_PRESCRICOES_GERENCIAL_CACHE_VERSION = 2
MEMORIA_CALCULO_CACHE_VERSION = 1
PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_CACHE_VERSION = 1


def _module(name: str) -> str:
    return f"{name}{MODULE_EXT}"


MOVIMENTACAO_PARQUET = _module("movimentacao")
LOCALIDADES_PARQUET = _module("localidades")
REDES_FARMACEUTICAS_PARQUET = _module("redes_farmaceuticas")
MATRIZ_RISCO_PARQUET = _module("matriz_risco")
BENCH_CRM_UF_PARQUET = _module("bench_crm_uf")
BENCH_CRM_REGIAO_PARQUET = _module("bench_crm_regiao")
BENCH_CRM_BR_PARQUET = _module("bench_crm_br")
CRM_PRESCRICOES_BRASIL_SEMESTRE_PARQUET = _module("crm_prescricoes_brasil_semestre")
CRM_PRESCRICOES_ESTABELECIMENTO_MES_PARQUET = _module("crm_prescricoes_estabelecimento_mes")
CRM_PRESCRICOES_MEDICO_MUNICIPIO_MES_PARQUET = _module("crm_prescricoes_medico_municipio_mes")
CRM_PRESCRICOES_GERENCIAL_PARQUET = _module("crm_prescricoes_gerencial")
DADOS_MEDICO_PARQUET = _module("dados_medico")
CRM_PRESCRITORES_GLOBAL_PARQUET = _module("crm_prescritores_global")
MEMORIA_CALCULO_GLOBAL_PARQUET = _module("memoria_calculo_global")
FARMACIAS_PARQUET = _module("farmacias")
FARMACIAS_CNAES_SECUNDARIOS_PARQUET = _module("farmacias_cnaes_secundarios")
PERFIL_ESTABELECIMENTO_PARQUET = _module("perfil_estabelecimento")
SOCIOS_PARQUET = _module("socios")
TEIA_FONTE_NIVEL2_PARQUET = _module("teia_fonte_nivel2")
TEIA_FONTE_NIVEL3_PARQUET = _module("teia_fonte_nivel3")
TEIA_FONTE_NIVEL4_PARQUET = _module("teia_fonte_nivel4")
MEDICAMENTOS_PARQUET = _module("medicamentos")
ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET = _module("analise_gtin_inconsistencia_clinica")
ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET = _module("analise_gtin_inconsistencia_clinica_municipio")
ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET = _module("analise_gtin_inconsistencia_clinica_regiao")
DADOS_IBGE_DEMOGRAFIA_PARQUET = _module("dados_ibge_demografia")
VOLUME_ATIPICO_SEMESTRAL_PARQUET = _module("volume_atipico_semestral")
GEOGRAFICO_ORIGEM_UF_PARQUET = _module("geografico_origem_uf")
ESOCIAL_CNPJ_ANO_PARQUET = _module("esocial_cnpj_ano")
ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET = _module("esocial_cnpj_trabalhador_ano")
ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET = _module("esocial_cnpj_movimentacao_ano")
ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET = _module("esocial_cnpj_ultima_movimentacao")
SENTINELA_METADADOS_BASE_PARQUET = _module("sentinela_metadados_base")
DADOS_PAR_PARQUET = _module("dados_par")
PAR_TEIA_ALVOS_PARQUET = _module("par_teia_alvos")

MEMORIA_CALCULO_PARQUET = _module("memoria_calculo")
MOVIMENTACAO_MENSAL_GTIN_PARQUET = _module("movimentacao_mensal_gtin")
FALECIDOS_PARQUET = _module("falecidos")
CRM_PRESCRITORES_PARQUET = _module("crm_prescritores")
GEOGRAFICO_PARQUET = _module("geografico")
CRM_RAIOX_TX_GLOBAL_PARQUET = _module("crm_raiox_tx_global")
CRM_RAIOX_TX_PARQUET = _module("crm_raiox_tx")
CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET = _module("crm_concentracao_unico_alertas")
CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET = _module("crm_concentracao_multiplo_alertas")
CRM_TIMELINE_DIA_PARQUET = _module("crm_timeline_dia")
CRM_TIMELINE_HORA_PARQUET = _module("crm_timeline_hora")
CRM_TIMELINE_EVENTOS_PARQUET = _module("crm_timeline_eventos")
GEOGRAFICO_GLOBAL_PARQUET = _module("geografico_global")
CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET = _module("crm_concentracao_unico_alertas_global")
CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET = _module("crm_concentracao_multiplo_alertas_global")
CRM_TIMELINE_DIA_GLOBAL_PARQUET = _module("crm_timeline_dia_global")
CRM_TIMELINE_HORA_GLOBAL_PARQUET = _module("crm_timeline_hora_global")
CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET = _module("crm_timeline_eventos_global")
MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET = _module("movimentacao_mensal_gtin_global")
PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET = _module("pagamentos_consolidados_farmacia_popular")
TEIA_GRAFO_NIVEL2_NODES_PARQUET = _module("teia_grafo_nivel2_nodes")
TEIA_GRAFO_NIVEL2_EDGES_PARQUET = _module("teia_grafo_nivel2_edges")
TEIA_GRAFO_NIVEL3_NODES_PARQUET = _module("teia_grafo_nivel3_nodes")
TEIA_GRAFO_NIVEL3_EDGES_PARQUET = _module("teia_grafo_nivel3_edges")
TEIA_GRAFO_NIVEL4_NODES_PARQUET = _module("teia_grafo_nivel4_nodes")
TEIA_GRAFO_NIVEL4_EDGES_PARQUET = _module("teia_grafo_nivel4_edges")
