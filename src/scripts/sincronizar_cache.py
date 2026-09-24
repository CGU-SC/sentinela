"""
sincronizar_cache.py
--------------------
Script interativo para sincronizar modulos do cache Sentinela com o CGUData.
Permite escolher exatamente quais modulos atualizar, sem precisar rodar tudo.

Uso:
    python src/scripts/sincronizar_cache.py

Dependencias:
    pip install sqlalchemy pyodbc pandas polars
"""

import os
import sys
import time

# Adiciona o backend ao path para importar data_cache e database.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

from sqlalchemy import text

from database import engine
from data_cache import (
    _sync_analise_gtin_inconsistencia_clinica,
    _sync_analise_gtin_inconsistencia_clinica_municipio,
    _sync_analise_gtin_inconsistencia_clinica_regiao,
    _sync_crm_benchmarks,
    _sync_crm_prescritores_global,
    _sync_crm_prescricoes_brasil_semestre,
    _sync_crm_medico_estabelecimento_mes,
    _sync_crm_medico_brasil_mes,
    _sync_crm_prescricoes_medico_municipio_mes,
    _sync_crm_contagem_medicos_municipio_regiao_periodo,
    _sync_crm_contagem_medicos_uf_brasil_periodo,
    _sync_crm_raiox_tx_global,
    _sync_pagamentos_consolidados_farmacia_popular,
    _sync_dados_farmacia,
    _sync_dados_ibge_demografia,
    _sync_dados_medico,
    _sync_dados_par,
    _sync_dados_socios,
    _sync_esocial,
    _sync_falecidos,
    _sync_geografico_origem_uf,
    _sync_localidades,
    _sync_matriz_risco,
    _sync_medicamentos,
    _sync_memoria_calculo_global,
    _sync_movimentacao,
    _sync_par_teia_alvos,
    _sync_perfil_estabelecimento,
    _sync_rede,
    _sync_sentinela_metadados_base,
    _sync_teia_expansao_completa,
    _sync_volume_atipico_semestral,
    _sync_geografico_global,
    _sync_crm_concentracao_unico_alertas_global,
    _sync_crm_concentracao_multiplo_alertas_global,
    _sync_crm_timeline_dia_global,
    _sync_crm_timeline_hora_global,
    _sync_crm_timeline_eventos_global,
    _sync_movimentacao_mensal_gtin_global,
)


CRM_CNPJ_CACHE_KEYS = [
    ("geografico", "CRM geografico"),
    ("crm_concentracao_unico_alertas", "CRM concentracao unico"),
    ("crm_concentracao_multiplo_alertas", "CRM concentracao multiplo"),
    ("crm_timeline_dia", "CRM timeline dia"),
    ("crm_timeline_hora", "CRM timeline hora"),
    ("crm_timeline_eventos", "CRM timeline eventos"),
]

CRM_UF_CACHE_KEYS = [
    ("crm_prescritores", "CRM prescritores"),
    ("crm_raiox_tx", "CRM Raio-X transacoes"),
    *CRM_CNPJ_CACHE_KEYS,
]

CRM_COMPLETO_ID = 9
CRM_INDIVIDUAL_IDS: frozenset[int] = frozenset()  # Módulos legados 10-15 removidos; globais 33-38 são o padrão.


def _buscar_cnpjs_crm(engine) -> list[str]:
    """Retorna os CNPJs elegiveis para sincronizacao de modulos CRM por CNPJ."""
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT DISTINCT F.cnpj
            FROM temp_CGUSC.fp.matriz_risco_consolidada M
            INNER JOIN temp_CGUSC.fp.dados_farmacia F
                ON F.id = M.id_cnpj
            ORDER BY F.cnpj
        """))
        return [str(r[0]).strip() for r in res if str(r[0]).strip()]


def _sync_crm_cnpj_unit(cache_key: str, cnpj: str, engine) -> None:
    import cache_manager

    cache_manager.sync_cnpj_cache(cache_key, cnpj, engine)


def _ensure_crm_runtime_caches_loaded() -> None:
    """Carrega em memoria os caches globais minimos exigidos pelos producers CRM por CNPJ."""
    import polars as pl
    import data_cache

    try:
        data_cache.get_df_perfil_estabelecimento()
        return
    except RuntimeError:
        pass

    perfil_path = data_cache._PERFIL_ESTABELECIMENTO_PARQUET_PATH
    if not os.path.exists(perfil_path):
        raise RuntimeError(
            f"Modulo perfil_estabelecimento ausente em {perfil_path}. "
            "Sincronize a opcao 18 antes de materializar CRM por CNPJ."
        )

    df_perfil = pl.read_parquet(perfil_path)
    required_columns = {"id_cnpj", "cnpj"}
    missing_columns = sorted(required_columns - set(df_perfil.columns))
    if missing_columns:
        raise RuntimeError(
            "Modulo perfil_estabelecimento sem colunas obrigatorias para CRM por CNPJ: "
            + ", ".join(missing_columns)
        )

    data_cache._df_perfil_estabelecimento = df_perfil


def _sync_crm_cnpj_completo(engine, progress_callback=None) -> None:
    """Sincroniza somente os modulos CRM ativos por CNPJ."""
    _ensure_crm_runtime_caches_loaded()
    cnpjs_sync = _buscar_cnpjs_crm(engine)

    total = len(cnpjs_sync)
    if total == 0:
        if progress_callback:
            progress_callback(100)
        return

    print(
        "Sincronizando pacote CRM por CNPJ: "
        f"{len(CRM_CNPJ_CACHE_KEYS)} modulo(s), {total} estabelecimento(s)..."
    )

    total_steps = total * len(CRM_CNPJ_CACHE_KEYS)
    step = 0
    for cnpj in cnpjs_sync:
        for cache_key, label in CRM_CNPJ_CACHE_KEYS:
            try:
                _sync_crm_cnpj_unit(cache_key, cnpj, engine)
                step += 1
                if progress_callback:
                    progress_callback(int((step / total_steps) * 100))
            except Exception as e:
                print(f"\n[AVISO] Erro ao sincronizar {label} para CNPJ {cnpj}: {e}")
                raise

    if progress_callback:
        progress_callback(100)


def _sync_clinica_anual_completa(engine, progress_callback=None):
    """Sincroniza os modulos clinicos anual por CNPJ, municipio e regiao."""
    def progress_cnpj(p: int):
        if progress_callback:
            progress_callback(int(p / 3))

    def progress_municipio(p: int):
        if progress_callback:
            progress_callback(33 + int(p / 3))

    def progress_regiao(p: int):
        if progress_callback:
            progress_callback(66 + int(p / 3))

    _sync_analise_gtin_inconsistencia_clinica(engine, progress_cnpj)
    _sync_analise_gtin_inconsistencia_clinica_municipio(engine, progress_municipio)
    _sync_analise_gtin_inconsistencia_clinica_regiao(engine, progress_regiao)

    if progress_callback:
        progress_callback(100)


def _buscar_cnpjs_por_uf(engine, ufs: list[str]) -> list[str]:
    """Retorna os CNPJs elegiveis para uma lista de UFs."""
    with engine.connect() as conn:
        in_clause = ", ".join(f":uf_{i}" for i in range(len(ufs)))
        params = {f"uf_{i}": uf for i, uf in enumerate(ufs)}
        query = text(f"""
            SELECT DISTINCT F.cnpj
            FROM temp_CGUSC.fp.matriz_risco_consolidada M
            INNER JOIN temp_CGUSC.fp.dados_farmacia F
                ON F.id = M.id_cnpj
            WHERE F.uf IN ({in_clause})
            ORDER BY F.cnpj
        """)
        res = conn.execute(query, params)
        return [str(r[0]).strip() for r in res if str(r[0]).strip()]


def _sync_memoria_calculo_ufs(engine, progress_callback=None) -> None:
    """Sincroniza o modulo memoria_calculo para CNPJs de UFs especificas."""
    print()
    entrada = input("Digite as UFs desejadas separadas por virgula (ex: SC, RJ) ou ENTER para pular: ").strip().upper()
    if not entrada:
        print("Operacao cancelada (nenhuma UF informada).")
        if progress_callback:
            progress_callback(100)
        return

    ufs = [uf.strip() for uf in entrada.split(",") if uf.strip()]
    cnpjs_sync = _buscar_cnpjs_por_uf(engine, ufs)

    total = len(cnpjs_sync)
    if total == 0:
        print(f"Nenhum CNPJ elegivel encontrado para as UFs: {', '.join(ufs)}.")
        if progress_callback:
            progress_callback(100)
        return

    print(f"Encontrados {total} estabelecimentos nas UFs: {', '.join(ufs)}.")
    
    import os
    import polars as pl
    from data_cache import scan_memoria_calculo_global
    from cache_producers.farmacia import (
        _decode_memoria_payload,
        _load_medicamentos_map_from_cache,
        _build_memoria_calculo_df,
        _global_cache_path,
        _cache_path
    )
    from cache_files import MEMORIA_CALCULO_CACHE_VERSION
    
    global_path = _global_cache_path()
    if not os.path.exists(global_path):
        print(f"Erro: O cache global {global_path} não existe. Execute a opção 21 primeiro.")
        if progress_callback: progress_callback(100)
        return

    print("Lendo cache global...")
    df_global = (
        scan_memoria_calculo_global()
        .filter(pl.col("cnpj").is_in(cnpjs_sync))
        .select(["cnpj", "memoria_calculo_payload", "_memoria_calculo_cache_version"])
        .collect()
    )
    
    if df_global.is_empty():
        print("Nenhum payload encontrado no cache global para esses CNPJs.")
        if progress_callback: progress_callback(100)
        return

    print("Carregando mapa de medicamentos...")
    medicamentos_map = _load_medicamentos_map_from_cache()

    print("Processando e salvando parquet por CNPJ...")
    step = 0
    total_found = df_global.height
    
    for row in df_global.iter_rows(named=True):
        cnpj = row["cnpj"]
        version = int(row["_memoria_calculo_cache_version"] or 0)
        
        if version < MEMORIA_CALCULO_CACHE_VERSION:
            print(f"\n[AVISO] {cnpj} ignorado. Versao do cache global ({version}) inferior a {MEMORIA_CALCULO_CACHE_VERSION}.")
            continue
            
        payload = row["memoria_calculo_payload"]
        try:
            dados = _decode_memoria_payload(payload)
            df_result = _build_memoria_calculo_df(dados, medicamentos_map)
            
            if not df_result.is_empty():
                cache_path = _cache_path(cnpj)
                df_result.write_parquet(cache_path, compression="zstd")
        except Exception as e:
            print(f"\n[AVISO] Erro ao processar memoria de calculo para {cnpj}: {e}")
            
        step += 1
        if progress_callback:
            progress_callback(int((step / total_found) * 100))

    if progress_callback:
        progress_callback(100)


def _sync_crm_ufs(engine, progress_callback=None) -> None:
    """Sincroniza os modulos CRM por CNPJ para CNPJs de UFs especificas."""
    print()
    entrada = input("Digite as UFs desejadas separadas por virgula (ex: SC, RJ) ou ENTER para pular: ").strip().upper()
    if not entrada:
        print("Operacao cancelada (nenhuma UF informada).")
        if progress_callback:
            progress_callback(100)
        return

    ufs = [uf.strip() for uf in entrada.split(",") if uf.strip()]
    cnpjs_sync = _buscar_cnpjs_por_uf(engine, ufs)

    total = len(cnpjs_sync)
    if total == 0:
        print(f"Nenhum CNPJ elegivel encontrado para as UFs: {', '.join(ufs)}.")
        if progress_callback:
            progress_callback(100)
        return

    _ensure_crm_runtime_caches_loaded()

    print(f"Encontrados {total} estabelecimentos nas UFs: {', '.join(ufs)}.")
    print(
        "Sincronizando pacote CRM por UF: "
        f"{len(CRM_UF_CACHE_KEYS)} modulo(s), {total} estabelecimento(s)..."
    )

    total_steps = total * len(CRM_UF_CACHE_KEYS)
    step = 0
    for cnpj in cnpjs_sync:
        for cache_key, label in CRM_UF_CACHE_KEYS:
            try:
                _sync_crm_cnpj_unit(cache_key, cnpj, engine)
                step += 1
                if progress_callback:
                    progress_callback(int((step / total_steps) * 100))
            except Exception as e:
                print(f"\n[AVISO] Erro ao sincronizar {label} para CNPJ {cnpj}: {e}")
                raise

    if progress_callback:
        progress_callback(100)


MODULOS = sorted([
    {"id": 1, "name": "Localidades", "func": _sync_localidades, "peso": "rapido", "ordem": 1},
    {"id": 2, "name": "Rede", "func": _sync_rede, "peso": "rapido", "ordem": 2},
    {"id": 3, "name": "Matriz risco", "func": _sync_matriz_risco, "peso": "medio", "ordem": 3},
    {"id": 4, "name": "Falecidos global", "func": _sync_falecidos, "peso": "medio", "ordem": 4},
    {"id": 5, "name": "Bench CRM", "func": _sync_crm_benchmarks, "peso": "rapido", "ordem": 5},
    {"id": 6, "name": "CRM Brasil Semestral", "func": _sync_crm_prescricoes_brasil_semestre, "peso": "rapido", "ordem": 6},
    {"id": 7, "name": "Dados medico", "func": _sync_dados_medico, "peso": "rapido", "ordem": 7},
    {"id": 8, "name": "CRM prescritores global", "func": _sync_crm_prescritores_global, "peso": "muito pesado", "ordem": 8},
    {"id": 9, "name": "CRM Completo", "func": _sync_crm_cnpj_completo, "peso": "pesado", "ordem": 9},
    {"id": 16, "name": "CRM Raio-X global", "func": _sync_crm_raiox_tx_global, "peso": "muito pesado", "ordem": 16},
    {"id": 43, "name": "Pagamentos FP global", "func": _sync_pagamentos_consolidados_farmacia_popular, "peso": "muito pesado", "ordem": 43},
    {"id": 44, "name": "CRM Medico/Estabelecimento/Mes (5 campos)", "func": _sync_crm_medico_estabelecimento_mes, "peso": "muito pesado", "ordem": 44},
    {"id": 47, "name": "CRM Medico/Brasil/Mes (4 campos)", "func": _sync_crm_medico_brasil_mes, "peso": "pesado", "ordem": 47},
    {"id": 46, "name": "CRM Prescricoes medico/municipio", "func": _sync_crm_prescricoes_medico_municipio_mes, "peso": "pesado", "ordem": 46},
    {"id": 45, "name": "CRM Contagem Medicos/Municipio-Regiao/Periodo", "func": _sync_crm_contagem_medicos_municipio_regiao_periodo, "peso": "pesado", "ordem": 45},
    {"id": 48, "name": "CRM Contagem Medicos/UF-Brasil/Periodo", "func": _sync_crm_contagem_medicos_uf_brasil_periodo, "peso": "rapido", "ordem": 48},
    {"id": 17, "name": "Farmacias e CNAEs", "func": _sync_dados_farmacia, "peso": "medio", "ordem": 17},
    {"id": 18, "name": "Perfil estab.", "func": _sync_perfil_estabelecimento, "peso": "medio", "ordem": 18},
    {"id": 19, "name": "Movimentacao", "func": _sync_movimentacao, "peso": "muito pesado", "ordem": 19},
    {"id": 20, "name": "Medicamentos", "func": _sync_medicamentos, "peso": "rapido", "ordem": 20},
    {"id": 21, "name": "Memoria calculo global", "func": _sync_memoria_calculo_global, "peso": "muito pesado", "ordem": 21},
    {"id": 22, "name": "Socios", "func": _sync_dados_socios, "peso": "medio", "ordem": 22},
    {"id": 23, "name": "Teia completa", "func": _sync_teia_expansao_completa, "peso": "pesado", "ordem": 23},
    {"id": 24, "name": "Volume atipico", "func": _sync_volume_atipico_semestral, "peso": "medio", "ordem": 24},
    {"id": 25, "name": "PAR", "func": _sync_dados_par, "peso": "rapido", "ordem": 25},
    {"id": 26, "name": "PAR teia", "func": _sync_par_teia_alvos, "peso": "rapido", "ordem": 26},
    {"id": 27, "name": "eSocial", "func": _sync_esocial, "peso": "rapido", "ordem": 27},
    {"id": 28, "name": "Metadados", "func": _sync_sentinela_metadados_base, "peso": "rapido", "ordem": 28},
    {"id": 29, "name": "Clinica anual completa", "func": _sync_clinica_anual_completa, "peso": "rapido", "ordem": 29},
    {"id": 30, "name": "Demografia", "func": _sync_dados_ibge_demografia, "peso": "rapido", "ordem": 30},
    {"id": 31, "name": "Clinica municipal", "func": _sync_analise_gtin_inconsistencia_clinica_municipio, "peso": "rapido", "ordem": 31},
    {"id": 32, "name": "Clinica regiao", "func": _sync_analise_gtin_inconsistencia_clinica_regiao, "peso": "rapido", "ordem": 32},
    {"id": 33, "name": "Geo origem UF", "func": _sync_geografico_origem_uf, "peso": "rapido", "ordem": 33},
    {"id": 34, "name": "CRM Geo Global", "func": _sync_geografico_global, "peso": "pesado", "ordem": 34},
    {"id": 35, "name": "CRM ConcUnico Global", "func": _sync_crm_concentracao_unico_alertas_global, "peso": "pesado", "ordem": 35},
    {"id": 36, "name": "CRM ConcMulti Global", "func": _sync_crm_concentracao_multiplo_alertas_global, "peso": "pesado", "ordem": 36},
    {"id": 37, "name": "CRM Dia Global", "func": _sync_crm_timeline_dia_global, "peso": "pesado", "ordem": 37},
    {"id": 38, "name": "CRM Hora Global", "func": _sync_crm_timeline_hora_global, "peso": "pesado", "ordem": 38},
    {"id": 39, "name": "CRM Eventos Global", "func": _sync_crm_timeline_eventos_global, "peso": "pesado", "ordem": 39},
    {"id": 40, "name": "Mem. Calc. por UF", "func": _sync_memoria_calculo_ufs, "peso": "pesado", "ordem": 40},
    {"id": 41, "name": "CRM por UF", "func": _sync_crm_ufs, "peso": "pesado", "ordem": 41},
    {"id": 42, "name": "GTIN Mensal Global", "func": _sync_movimentacao_mensal_gtin_global, "peso": "muito pesado", "ordem": 42},
], key=lambda modulo: modulo["ordem"])


DEPENDENCIAS_MODULOS = {
    8: {7},
    9: {7, 8, 16, 34, 35, 36, 37, 38, 39, 44, 45, 46},
    21: {20},
    23: {22},
}


def _incluir_dependencias(selecionados: list[dict]) -> list[dict]:
    ids = {modulo["id"] for modulo in selecionados}
    if CRM_COMPLETO_ID in ids:
        ids.difference_update(CRM_INDIVIDUAL_IDS)

    pendentes = list(ids)

    while pendentes:
        modulo_id = pendentes.pop()
        for dependencia_id in DEPENDENCIAS_MODULOS.get(modulo_id, set()):
            if dependencia_id not in ids:
                ids.add(dependencia_id)
                pendentes.append(dependencia_id)

    return sorted(
        [modulo for modulo in MODULOS if modulo["id"] in ids],
        key=lambda modulo: modulo.get("ordem", modulo["id"]),
    )


def exibir_menu():
    print("\n" + "=" * 46)
    print(" SENTINELA - SYNC CACHE")
    print("=" * 46)
    for m in MODULOS:
        print(f" [{m['id']:>2}] {m['name']:<18} {m['peso']}")
    print("-" * 46)
    print("  [0] Sincronizar TODOS os modulos")
    print("=" * 46)


def selecionar_modulos() -> list[dict]:
    exibir_menu()
    entrada = input("\nDigite os numeros separados por virgula (ex: 1,3,7): ").strip()

    if entrada == "0":
        modulos_todos = [
            modulo for modulo in MODULOS
            if modulo["id"] not in CRM_INDIVIDUAL_IDS
        ]
        return _incluir_dependencias(modulos_todos)

    ids_validos = {m["id"] for m in MODULOS}
    selecionados = []
    erros = []

    for parte in entrada.split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            num = int(parte)
            if num in ids_validos:
                selecionados.append(next(m for m in MODULOS if m["id"] == num))
            else:
                erros.append(parte)
        except ValueError:
            erros.append(parte)

    if erros:
        print(f"\nAviso: opcoes ignoradas (invalidas): {', '.join(erros)}")

    return _incluir_dependencias(selecionados)


def confirmar(selecionados: list[dict]) -> bool:
    print("\nModulos selecionados para sincronizacao:")
    for m in selecionados:
        print(f"  - {m['name']}")
    resposta = input("\nConfirmar? [S/n]: ").strip().lower()
    return resposta in ("", "s", "sim", "y", "yes")


def progresso_console(nome: str, p: int):
    barra = int(p / 5)
    print(f"\r  {'#' * barra}{'.' * (20 - barra)} {p:>3}%  {nome}", end="", flush=True)


def executar(selecionados: list[dict]):
    total = len(selecionados)
    print(f"\nIniciando sincronizacao de {total} modulo(s)...\n")
    t_inicio = time.perf_counter()

    for i, modulo in enumerate(selecionados, 1):
        nome = modulo["name"]
        print(f"[{i}/{total}] {nome}")

        def callback(p, _nome=nome):
            progresso_console(_nome, p)

        t0 = time.perf_counter()
        try:
            modulo["func"](engine, callback)
            elapsed = time.perf_counter() - t0
            print(f"\r  OK {nome:<35} concluido em {elapsed:.1f}s")
        except Exception as e:
            print(f"\r  ERRO {nome:<33} {e}")

    total_elapsed = time.perf_counter() - t_inicio
    print(f"\n{'=' * 55}")
    print(f"  Sincronizacao concluida em {total_elapsed:.1f}s")
    print(f"{'=' * 55}\n")


def main():
    try:
        selecionados = selecionar_modulos()

        if not selecionados:
            print("\nAviso: nenhum modulo selecionado. Encerrando.")
            return

        if not confirmar(selecionados):
            print("\nOperacao cancelada.")
            return

        executar(selecionados)

    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuario.")


if __name__ == "__main__":
    main()
