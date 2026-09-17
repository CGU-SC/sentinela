"""
check_parquet_schema.py
-----------------------
Utilitário profissional para inspeção de módulos de cache do Sentinela.
Permite visualizar colunas, tipos de dados, contagem de registros e amostras.

Uso:
    python src/scripts/check_parquet_schema.py                   # menu interativo
    python src/scripts/check_parquet_schema.py --teia            # inspeciona N2/N3/N4 globais
    python src/scripts/check_parquet_schema.py --cnpj 00447821001223  # parquets de um CNPJ
"""

import sys
import os
import polars as pl
from datetime import datetime

# Adiciona o backend ao path para importar as constantes de path do data_cache
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT_DIR, 'backend'))

try:
    from data_cache import (
        _CACHE_DIR,
        get_cnpj_cache_root,
        _PARQUET_PATH,
        _LOCALIDADES_PARQUET_PATH,
        _REDE_PARQUET_PATH,
        _MATRIZ_PARQUET_PATH,
        _BENCH_CRM_UF_PATH,
        _BENCH_CRM_REGIAO_PATH,
        _BENCH_CRM_BR_PATH,
        _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH,
        _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH,
        _DADOS_FARMACIA_PARQUET_PATH,
        _DADOS_SOCIOS_PARQUET_PATH,
        _TEIA_FONTE_NIVEL2_PARQUET_PATH,
        _TEIA_FONTE_NIVEL3_PARQUET_PATH,
        _TEIA_FONTE_NIVEL4_PARQUET_PATH,
        _MEDICAMENTOS_PARQUET_PATH,
    )
    from cache_files import (
        TEIA_GRAFO_NIVEL2_NODES_PARQUET,
        TEIA_GRAFO_NIVEL2_EDGES_PARQUET,
        TEIA_GRAFO_NIVEL3_NODES_PARQUET,
        TEIA_GRAFO_NIVEL3_EDGES_PARQUET,
        TEIA_GRAFO_NIVEL4_NODES_PARQUET,
        TEIA_GRAFO_NIVEL4_EDGES_PARQUET,
    )
except ImportError as e:
    print(f"Erro: Nao foi possivel importar as definicoes do backend.\n   Detalhe: {e}")
    sys.exit(1)

CNPJ_PARQUET_NAMES = [
    TEIA_GRAFO_NIVEL2_NODES_PARQUET,
    TEIA_GRAFO_NIVEL2_EDGES_PARQUET,
    TEIA_GRAFO_NIVEL3_NODES_PARQUET,
    TEIA_GRAFO_NIVEL3_EDGES_PARQUET,
    TEIA_GRAFO_NIVEL4_NODES_PARQUET,
    TEIA_GRAFO_NIVEL4_EDGES_PARQUET,
]

# ── Configuração dos Arquivos ──────────────────────────────────────────────────

ARQUIVOS = [
    {"id": 1, "name": "Movimentação Mensal",      "path": _PARQUET_PATH},
    {"id": 2, "name": "Localidades (IBGE)",       "path": _LOCALIDADES_PARQUET_PATH},
    {"id": 3, "name": "Rede de Estabelecimentos", "path": _REDE_PARQUET_PATH},
    {"id": 4, "name": "Matriz de Risco",          "path": _MATRIZ_PARQUET_PATH},
    {"id": 5, "name": "Benchmark CRM (UF)",       "path": _BENCH_CRM_UF_PATH},
    {"id": 6, "name": "Benchmark CRM (Região)",   "path": _BENCH_CRM_REGIAO_PATH},
    {"id": 7, "name": "Benchmark CRM (Brasil)",   "path": _BENCH_CRM_BR_PATH},
    {"id": 14, "name": "CRM Brasil Semestral",    "path": _CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH},
    {"id": 15, "name": "CRM Prescricoes Estab./Mes", "path": _CRM_PRESCRICOES_ESTABELECIMENTO_MES_PATH},
    {"id": 8, "name": "Dados das Farmácias",      "path": _DADOS_FARMACIA_PARQUET_PATH},
    {"id": 9, "name": "Dados dos Sócios",         "path": _DADOS_SOCIOS_PARQUET_PATH},
    {"id": 10, "name": "Teia Fonte G2 (Participações)", "path": _TEIA_FONTE_NIVEL2_PARQUET_PATH},
    {"id": 11, "name": "Teia Fonte G3 (Indiretos)",    "path": _TEIA_FONTE_NIVEL3_PARQUET_PATH},
    {"id": 12, "name": "Teia Fonte G4 (Nacional)",     "path": _TEIA_FONTE_NIVEL4_PARQUET_PATH},
    {"id": 13, "name": "Cadastro de Medicamentos", "path": _MEDICAMENTOS_PARQUET_PATH},
]

# ── Funções de Interface ───────────────────────────────────────────────────────

def exibir_menu():
    print("\n" + "=" * 60)
    print("   SENTINELA - INSPECAO DE MODULOS DE CACHE")
    print("=" * 60)
    for a in ARQUIVOS:
        status = "[OK]" if os.path.exists(a["path"]) else "[--]"
        print(f"  [{a['id']}] {status} {a['name']:<30}")
    print("-" * 60)
    print("  [C] Inspecionar parquets de um CNPJ especifico")
    print("  [0] Sair")
    print("=" * 60)

def inspecionar_cnpj(cnpj: str):
    cnpj = cnpj.strip().zfill(14)
    cnpj_dir = os.path.join(get_cnpj_cache_root(), cnpj)

    if not os.path.isdir(cnpj_dir):
        print(f"\n[!] Diretorio nao encontrado para CNPJ {cnpj}: {cnpj_dir}")
        return

    arquivos_cnpj = [
        {"name": nome, "path": os.path.join(cnpj_dir, nome)}
        for nome in CNPJ_PARQUET_NAMES
    ]

    print(f"\n{'=' * 60}")
    print(f"   CNPJ: {cnpj}")
    print(f"   Dir:  {cnpj_dir}")
    print(f"{'=' * 60}")

    for item in arquivos_cnpj:
        inspecionar_arquivo(item, pausar=False)

def inspecionar_arquivo(item: dict, pausar: bool = True):
    path = item["path"]
    nome = item["name"]

    if not os.path.exists(path):
        print(f"\n[!] Arquivo nao encontrado: {path}")
        return

    try:
        # Configura o Polars para exibir TUDO sem truncar colunas
        pl.Config.set_tbl_cols(-1)
        pl.Config.set_tbl_width_chars(200)
        pl.Config.set_fmt_str_lengths(50)

        df = pl.read_parquet(path)
        
        info = os.stat(path)
        data_mod = datetime.fromtimestamp(info.st_mtime).strftime('%d/%m/%Y %H:%M:%S')
        tamanho_mb = info.st_size / (1024 * 1024)

        print("-" * 60)
        print(f"\n[ INSPECIONANDO: {nome} ]")
        print(f"  Path: {path}")
        print(f"  Modificado em: {data_mod}")
        print(f"  Tamanho: {tamanho_mb:.2f} MB")
        print(f"  Registros: {len(df):,}")
        print("-" * 60)

        print("\nESQUEMA COMPLETO (ORDEM ALFABETICA):")
        schema = df.schema
        sorted_cols = sorted(schema.keys())
        for col in sorted_cols:
            dtype = schema[col]
            print(f"  - {col:<30} | {dtype}")

        print("\nAMOSTRA DE DADOS (TOP 3):")
        # Se for muito larga, mostra cada registro como um bloco vertical
        if len(df.columns) > 8:
            for i in range(min(3, len(df))):
                print(f"\n--- [ Registro #{i+1} ] ---")
                row_dict = df.row(i, named=True)
                for k, v in row_dict.items():
                    print(f"  {k:<30}: {v}")
        else:
            print(df.head(3))
        
        if pausar:
            input("\nPressione ENTER para voltar ao menu...")

    except Exception as e:
        print(f"\n[ERRO] Erro ao ler arquivo: {e}")
        if pausar:
            input("\nPressione ENTER para voltar ao menu...")

# ── Loop Principal ─────────────────────────────────────────────────────────────

def main():
    # Modo --teia: inspeciona os parquets globais N2/N3/N4 sem interação
    if "--teia" in sys.argv:
        for item in ARQUIVOS:
            if item["id"] in {10, 11, 12}:
                inspecionar_arquivo(item, pausar=False)
        return

    # Modo --cnpj <CNPJ>: inspeciona os 6 parquets do CNPJ sem interação
    if "--cnpj" in sys.argv:
        idx = sys.argv.index("--cnpj")
        if idx + 1 >= len(sys.argv):
            print("[!] Informe o CNPJ apos --cnpj. Ex: --cnpj 00447821001223")
            sys.exit(1)
        inspecionar_cnpj(sys.argv[idx + 1])
        return

    while True:
        exibir_menu()
        opcao = input("\nSelecione um arquivo para inspecionar: ").strip()

        if opcao == '0':
            print("\nEncerrando inspetor.")
            break

        if opcao.upper() == 'C':
            cnpj = input("Digite o CNPJ (so numeros): ").strip()
            inspecionar_cnpj(cnpj)
            continue

        try:
            op_int = int(opcao)
            selecionado = next((a for a in ARQUIVOS if a["id"] == op_int), None)

            if selecionado:
                inspecionar_arquivo(selecionado)
            else:
                print("\n[!] Opcao invalida.")
        except ValueError:
            print("\n[!] Digite um numero valido.")
        except KeyboardInterrupt:
            print("\n\nEncerrando.")
            break

if __name__ == '__main__':
    main()
