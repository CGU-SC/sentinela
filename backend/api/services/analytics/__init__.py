from ._cache import (
    _get_cnpj_cache_dir,
    _known_cnpj_dirs,
)
from cache_producers.crm import (
    sync_crm_raiox_tx,
)
from cache_producers.network import (
    sync_network,
)
from .crm import (
    get_crm_data,
    get_crm_medico_alertas,
    get_crm_raio_x,
    get_crm_timeline_dataset,
)
from .crm_export import export_crm_raiox_csv, export_crm_raiox_xlsx
from .crm_analysis import get_crm_prescricoes_analise
from .dashboard import (
    get_dashboard_data,
    get_producao_semestral_data,
    get_rede_por_cnpj_raiz,
)
from .bootstrap import get_cnpj_bootstrap
from .falecidos import get_falecidos_data, get_timeline_cpf
from .farmacia import get_cnpj_access_status, get_dados_farmacia, get_movimentacao_data
from .fator_risco import get_fator_risco_data
from .socios import get_socios_farmacia
from .integrity_alerts import get_integrity_alerts
from .alertas_panorama import get_alertas_panorama
from .network import (
    get_teia_grafo_nivel2, 
    get_teia_grafo_nivel3_expansao, 
    get_teia_grafo_nivel4_expansao,
    get_teia_grafo_nivel3_full,
    get_teia_grafo_nivel4_full,
)
from .financeiro import (
    get_evolucao_financeira,
    get_evolucao_mensal_gtin,
    get_gtin_ranking_periodo,
    get_cnpj_repasses,
)
from .indicator_config import (
    INDICATOR_MAPPING,
    INDICATOR_FLAGS as _INDICATOR_FLAGS,
)
from .indicadores import (
    get_indicadores,
    get_indicadores_analise,
    get_indicadores_analise_cnpjs,
    get_indicador_benchmark_local,
    get_indicador_evolucao_benchmark,
)
from .clinico import get_incompatibilidade_patologica_data
from .geografico import get_geografico_benchmark_local, get_geografico_origem_uf
from .regional import (
    get_cnpj_lookup,
    get_metric_percentiles,
    get_metric_percentiles_animation,
    get_regional_benchmarking,
    get_regional_benchmarking_animation,
)
from .nota_tecnica import generate_nota_tecnica
from .nota_tecnica_readiness import get_nota_tecnica_readiness, get_relatorio_pdf_readiness
from .nota_tecnica_prepare import prepare_nota_tecnica_cnpj, prepare_relatorio_pdf_cnpj
from .nota_tecnica_regionais import list_nota_tecnica_regionais
from .volume_atipico import (
    get_volume_atipico_id_cnpjs_df,
    get_volume_atipico_period_metrics,
)

__all__ = ['AnalyticsService', 'INDICATOR_MAPPING', '_INDICATOR_FLAGS']


class AnalyticsService:
    _known_cnpj_dirs = _known_cnpj_dirs
    _get_cnpj_cache_dir = staticmethod(_get_cnpj_cache_dir)
    get_cnpj_bootstrap = staticmethod(get_cnpj_bootstrap)
    get_dashboard_data = staticmethod(get_dashboard_data)
    get_producao_semestral_data = staticmethod(get_producao_semestral_data)
    get_rede_por_cnpj_raiz = staticmethod(get_rede_por_cnpj_raiz)
    get_evolucao_financeira = staticmethod(get_evolucao_financeira)
    get_evolucao_mensal_gtin = staticmethod(get_evolucao_mensal_gtin)
    get_cnpj_repasses = staticmethod(get_cnpj_repasses)
    get_gtin_ranking_periodo = staticmethod(get_gtin_ranking_periodo)
    get_indicadores = staticmethod(get_indicadores)
    get_indicadores_analise = staticmethod(get_indicadores_analise)
    get_indicadores_analise_cnpjs = staticmethod(get_indicadores_analise_cnpjs)
    get_indicador_benchmark_local = staticmethod(get_indicador_benchmark_local)
    get_indicador_evolucao_benchmark = staticmethod(get_indicador_evolucao_benchmark)
    get_incompatibilidade_patologica_data = staticmethod(get_incompatibilidade_patologica_data)
    get_geografico_origem_uf = staticmethod(get_geografico_origem_uf)
    get_geografico_benchmark_local = staticmethod(get_geografico_benchmark_local)
    get_falecidos_data = staticmethod(get_falecidos_data)
    get_timeline_cpf = staticmethod(get_timeline_cpf)
    get_fator_risco_data = staticmethod(get_fator_risco_data)
    get_regional_benchmarking = staticmethod(get_regional_benchmarking)
    get_regional_benchmarking_animation = staticmethod(get_regional_benchmarking_animation)
    get_crm_data = staticmethod(get_crm_data)
    get_crm_prescricoes_analise = staticmethod(get_crm_prescricoes_analise)
    get_crm_medico_alertas = staticmethod(get_crm_medico_alertas)
    get_crm_timeline_dataset = staticmethod(get_crm_timeline_dataset)
    sync_crm_raiox_tx = staticmethod(sync_crm_raiox_tx)
    get_crm_raio_x = staticmethod(get_crm_raio_x)
    export_crm_raiox_csv = staticmethod(export_crm_raiox_csv)
    export_crm_raiox_xlsx = staticmethod(export_crm_raiox_xlsx)
    get_dados_farmacia = staticmethod(get_dados_farmacia)
    get_cnpj_access_status = staticmethod(get_cnpj_access_status)
    get_movimentacao_data = staticmethod(get_movimentacao_data)
    get_socios_farmacia = staticmethod(get_socios_farmacia)
    get_integrity_alerts = staticmethod(get_integrity_alerts)
    get_alertas_panorama = staticmethod(get_alertas_panorama)
    get_teia_grafo_nivel2 = staticmethod(get_teia_grafo_nivel2)
    get_teia_grafo_nivel3_expansao = staticmethod(get_teia_grafo_nivel3_expansao)
    get_teia_grafo_nivel4_expansao = staticmethod(get_teia_grafo_nivel4_expansao)
    get_teia_grafo_nivel3_full = staticmethod(get_teia_grafo_nivel3_full)
    get_teia_grafo_nivel4_full = staticmethod(get_teia_grafo_nivel4_full)
    sync_network = staticmethod(sync_network)
    get_metric_percentiles = staticmethod(get_metric_percentiles)
    get_metric_percentiles_animation = staticmethod(get_metric_percentiles_animation)
    get_cnpj_lookup = staticmethod(get_cnpj_lookup)
    generate_nota_tecnica = staticmethod(generate_nota_tecnica)
    get_nota_tecnica_readiness = staticmethod(get_nota_tecnica_readiness)
    prepare_nota_tecnica_cnpj = staticmethod(prepare_nota_tecnica_cnpj)
    prepare_relatorio_pdf_cnpj = staticmethod(prepare_relatorio_pdf_cnpj)
    get_relatorio_pdf_readiness = staticmethod(get_relatorio_pdf_readiness)
    list_nota_tecnica_regionais = staticmethod(list_nota_tecnica_regionais)
    get_volume_atipico_id_cnpjs_df = staticmethod(get_volume_atipico_id_cnpjs_df)
    get_volume_atipico_period_metrics = staticmethod(get_volume_atipico_period_metrics)
