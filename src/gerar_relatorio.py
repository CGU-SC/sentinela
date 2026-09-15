"""
SENTINELA - Gerador de Relatórios a partir da Memória de Cálculo
================================================================
Este script lê os dados compactados da tabela memoria_calculo_consolidada
e gera relatórios Excel idênticos aos gerados pelo script original.

Uso: python gerar_relatorio_memoria.py <CNPJ> [tipo_relatorio]
     tipo_relatorio: 1 = Completo (padrão), 2 = Resumido (só irregularidades)
     
Exemplo: python gerar_relatorio_memoria.py 98669864000103 1
"""

from datetime import date, datetime
import copy
import os
import zlib
import json
from decimal import Decimal, ROUND_HALF_UP
import sys
import pyodbc
import pandas as pd
import logging


# Adiciona o diretório atual ao sys.path para garantir que os módulos locais sejam encontrados
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from aba_crm import (
    buscar_dados_prescritores,
    buscar_top20_prescritores,
    gerar_aba_prescritores
)
from aba_falecidos import (
    buscar_dados_falecidos,
    gerar_aba_falecidos
)
from aba_regiao import gerar_aba_regiao, buscar_farmacias_regiao
# =============================================================================
# CONFIGURAÇÃO DE LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# =============================================================================
# CONSTANTES GLOBAIS
# =============================================================================
# Versão do Sistema (usada para verificação de atualização obrigatória)
VERSION = "3.1.0"

DATA_INICIAL_ANALISE = '2015-07-01'
DATA_FINAL_ANALISE = datetime.strptime('2024-12-10', '%Y-%m-%d').date()
CRITERIO_ESTOQUE_INICIAL = 'Critério para estimativa do estoque inicial: Soma das duas últimas aquisições, considerando os 6 meses anteriores à primeira venda.'




data_referencia = pd.to_datetime(DATA_FINAL_ANALISE)


# 2. Definir a função lógica
def verificar_status(data_venda):
    # Verifica se a data é válida (não é NaT/Null)
    if pd.isnull(data_venda):
        return 'Inativa'

    # Calcula a diferença de dias
    dias_sem_comprar = (data_referencia - data_venda).days

    # Se a diferença for maior que 30 dias da data de corte, é Inativa
    if dias_sem_comprar > 30:
        return 'Inativa'
    else:
        return 'Ativa'
# =============================================================================
# FUNÇÃO: CONECTAR AO BANCO DE DADOS
# =============================================================================
def conectar_bd():
    try:
        conn_str = (
            'Driver={ODBC Driver 17 for SQL Server};'
            'Server=SDH-DIE-BD;'
            'Database=temp_CGUSC;'
            'Trusted_Connection=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        logging.info("Conexão com o banco de dados estabelecida com sucesso.")
        return conn, cursor
    except pyodbc.Error as ex:
        logging.critical(f"CRÍTICO: Falha ao conectar ao banco de dados. Erro: {ex}")
        raise ConnectionError(f"Não foi possível conectar ao banco de dados: {ex}")


# =============================================================================
# FUNÇÃO: CARREGAR DADOS AUXILIARES
# =============================================================================
def carregar_dados_auxiliares(cursor):
    """Carrega tabelas auxiliares necessárias para o relatório."""
    dados_farmacias = {}
    dados_medicamentos = {}
    
    try:
        cursor.execute('select cnpj, razaoSocial, municipio, uf from temp_CGUSC.[fp].dados_farmacia')
        cols = [column[0] for column in cursor.description]
        for row in cursor.fetchall():
            dados_farmacias[row[0]] = dict(zip(cols, row))
        
        cursor.execute('select codigo_barra, principio_ativo from temp_CGUSC.[fp].medicamentos_patologia')
        cols = [column[0] for column in cursor.description]
        for row in cursor.fetchall():
            dados_medicamentos[row[0]] = dict(zip(cols, row))
            
        logging.info("Dados auxiliares carregados com sucesso.")
        return dados_farmacias, dados_medicamentos
        
    except Exception as e:
        logging.error(f"Erro ao carregar dados auxiliares: {e}")
        return {}, {}


# =============================================================================
# FUNÇÃO: DESCOMPACTAR E CARREGAR MEMÓRIA DE CÁLCULO
# =============================================================================
def carregar_memoria_calculo(cursor, cnpj):
    """
    Busca os dados compactados da tabela memoria_calculo_consolidada,
    descompacta e retorna como lista de dicionários.
    """
    try:
        cursor.execute('''
            SELECT TOP 1 dados_comprimidos, id_processamento
            FROM temp_CGUSC.fp.memoria_calculo_consolidada 
            WHERE cnpj = ?
            ORDER BY id_processamento DESC
        ''', cnpj)
        
        row = cursor.fetchone()
        
        if not row or not row[0]:
            logging.warning(f"Nenhum dado encontrado para CNPJ {cnpj}")
            return None, None
        
        dados_comprimidos = row[0]
        id_processamento = row[1]
        
        # Descompacta os dados
        json_str = zlib.decompress(dados_comprimidos).decode('utf-8')
        dados = json.loads(json_str)
        
        # Converte strings de data de volta para objetos date/datetime
        for item in dados:
            for key in ['periodo_inicial', 'periodo_final', 'periodo_inicial_nao_comprovacao', 
                       'data_aquis_dev_estoq', 'data_estoque_inicial', 'data_aquisicao', 'data_devolucao']:
                if key in item and item[key] and isinstance(item[key], str):
                    try:
                        if 'T' in item[key]:
                            item[key] = datetime.fromisoformat(item[key]).date()
                        else:
                            item[key] = datetime.strptime(item[key], '%Y-%m-%d').date()
                    except:
                        pass
            
            # Converte valores numéricos para Decimal onde apropriado
            for key in ['valor_movimentado', 'valor_sem_comprovacao']:
                if key in item and item[key] is not None:
                    item[key] = Decimal(str(item[key]))
        
        tamanho_kb = len(dados_comprimidos) / 1024
        logging.info(f"Dados carregados para CNPJ {cnpj}: {len(dados)} registros ({tamanho_kb:.1f} KB comprimido)")
        
        return dados, id_processamento
        
    except Exception as e:
        logging.error(f"Erro ao carregar memória de cálculo para {cnpj}: {e}")
        return None, None


# =============================================================================
# FUNÇÃO: BUSCAR DADOS DA MATRIZ DE RISCO
# =============================================================================
def buscar_dados_risco(cursor, cnpj):
    """Busca os indicadores da Matriz de Risco."""
    try:
        cursor.execute('SELECT * FROM temp_CGUSC.fp.matriz_risco_consolidada WHERE cnpj = ?', cnpj)
        row = cursor.fetchone()
        
        if row:
            cols = [column[0] for column in cursor.description]
            return dict(zip(cols, row))
        return None
        
    except Exception as e:
        logging.error(f"Erro ao buscar matriz de risco para {cnpj}: {e}")
        return None





# =============================================================================
# FUNÇÃO: GERAR RELATÓRIO DE MOVIMENTAÇÃO (ADAPTADA)
# =============================================================================
def gerarRelatorioMovimentacao(cnpj_analise, dados_memoria, tipo_relatorio, cursor,
                                dados_farmacias, dados_medicamentos, dados_risco=None,
                                dados_prescritores=None, top20_prescritores=None,
                                id_processamento=None, dados_falecidos=None):
    """
    Gera o Excel processando a lista 'dados_memoria'.
    Versão adaptada para funcionar sem dependência do script original.
    """
    results = copy.deepcopy(dados_memoria)

    # =================================================================
    # 1. PROCESSAMENTO LÓGICO DAS VENDAS
    # =================================================================
    contador = 0
    for i, j in enumerate(results):
        if j['tipo'] in ('c', 'd'):
            contador += 1
        if j['tipo'] in ('s', 'h'):
            contador = 0
        if j['tipo'] == 'v':
            lista = []
            for idx in range(1, contador + 1):
                item_ant = results[i - idx]
                if item_ant['tipo'] == 'c':
                    dt = item_ant['data_aquis_dev_estoq'].strftime("%d/%m/%Y") if item_ant['data_aquis_dev_estoq'] else ""
                    qtd = int(item_ant['qnt_aquis_dev']) if item_ant.get('qnt_aquis_dev') else 0
                    lista.append(f"NF Aquisição: {item_ant['numero_nfe']} - {dt} | Qtde: {qtd}")
                elif item_ant['tipo'] == 'd':
                    dt = item_ant['data_aquis_dev_estoq'].strftime("%d/%m/%Y") if item_ant['data_aquis_dev_estoq'] else ""
                    qtd = int(item_ant['qnt_aquis_dev']) if item_ant.get('qnt_aquis_dev') else 0
                    lista.append(f"NF Transferência: {item_ant['numero_nfe']} - {dt} | Qtde: {qtd}")
                elif item_ant['tipo'] == 'e':
                    est = int(item_ant.get('estoque_inicial', 0))
                    lista.append(f"Estoque Inicial Estimado: {est} - 01/07/2015")
            if not lista and i > 0:
                for idx in range(i - 1, -1, -1):
                    if results[idx]['tipo'] == 'e':
                        est = int(results[idx].get('estoque_inicial', 0))
                        lista.append(f"Estoque Inicial Estimado: {est} - 01/07/2015")
                        break
                    elif results[idx]['tipo'] == 'h':
                        break
            results[i]['notas'] = ", ".join(lista)
            contador = 0

    lista_vendas_sem_comprovacao = []

    # Carrega Dados Auxiliares do Estoque Inicial
    try:
        cursor.execute(
            'select * from temp_CGUSC.[fp].estoque_inicial_notas where cnpj_estabelecimento = ? order by codigo_barra',
            cnpj_analise)
        estoque_inicial_notas = {}
        lista_temp = []
        codigo_barra_registro_anterior = -1
        for row in cursor.fetchall():
            codigo_barra_atual = row[2]
            if codigo_barra_atual != codigo_barra_registro_anterior:
                estoque_inicial_notas[codigo_barra_registro_anterior] = copy.deepcopy(lista_temp)
                lista_temp.clear()
            dt = row[3].strftime("%d/%m/%Y") if row[3] else ""
            lista_temp.append(f'NF {row[4]} - {dt} - | Qtde: {row[1]}')
            codigo_barra_registro_anterior = codigo_barra_atual
        if codigo_barra_registro_anterior != -1:
            estoque_inicial_notas[codigo_barra_registro_anterior] = copy.deepcopy(lista_temp)
    except:
        estoque_inicial_notas = {}

    tabela_codigo_barra_estoque_inicial = {}
    try:
        cursor.execute(
            'select codigo_barra, estoque_inicial from temp_CGUSC.[fp].estoque_inicial where cnpj_estabelecimento = ?',
            cnpj_analise)
        tabela_codigo_barra_estoque_inicial = {row.codigo_barra: row.estoque_inicial for row in cursor.fetchall()}
    except:
        pass

    cnpj_fmt = f'{cnpj_analise[:2]}.{cnpj_analise[2:5]}.{cnpj_analise[5:8]}/{cnpj_analise[8:12]}-{cnpj_analise[12:14]}'
    razao = dados_farmacias.get(cnpj_analise, {}).get('razaoSocial', 'DESCONHECIDO')
    mun = dados_farmacias.get(cnpj_analise, {}).get('municipio', '')
    uf = dados_farmacias.get(cnpj_analise, {}).get('uf', '')
    dt_ini_fmt = datetime.strptime(DATA_INICIAL_ANALISE, '%Y-%m-%d').strftime('%d/%m/%Y')
    dt_fim_fmt = DATA_FINAL_ANALISE.strftime('%d/%m/%Y')

    texto_cabecalho_1 = f'Estabelecimento: {cnpj_fmt} - {razao} - {mun}/{uf} | Período: {dt_ini_fmt} a {dt_fim_fmt}'
    texto_cabecalho_2 = CRITERIO_ESTOQUE_INICIAL

    lista_vendas_sem_comprovacao.append({'periodo_inicial': texto_cabecalho_1, '_tipo_linha': 'cabecalho_principal'})
    lista_vendas_sem_comprovacao.append({'periodo_inicial': texto_cabecalho_2, '_tipo_linha': 'cabecalho_principal'})

    vendas_total_sem_comprovacao_cnpj = 0
    vendas_total_cnpj = 0
    valor_total_cnpj = Decimal(0)
    valor_total_sem_comprovacao_cnpj = Decimal(0)
    numero_vendas_gtin = 0
    lista_parcial = []
    ultimo_estoque_valido = 0
    dados_para_grafico = []

    for i, j in enumerate(results):
        if j['tipo'] == 'v':
            vendas_total_cnpj += j.get('vendas_periodo', 0)
            vendas_total_sem_comprovacao_cnpj += j.get('vendas_sem_comprovacao', 0)
            valor_total_cnpj += j.get('valor_movimentado', Decimal(0))
            valor_total_sem_comprovacao_cnpj += j.get('valor_sem_comprovacao', Decimal(0))
            # dados_para_grafico.append({
            #     'data': j['periodo_inicial'],
            #     'valor_total': float(j['valor_movimentado']),
            #     'valor_sem_comp': float(j['valor_sem_comprovacao'])
            # })

        if j['tipo'] == 'h':
            numero_vendas_gtin = 0
            cod = int(j['codigo_barra'])
            principio = dados_medicamentos.get(float(cod), {}).get('principio_ativo', 'DESCONHECIDO')
            notas = ', '.join(estoque_inicial_notas.get(cod, []))
            est = tabela_codigo_barra_estoque_inicial.get(cod, 0)
            ultimo_estoque_valido = est
            j_copy = copy.deepcopy(j)
            j_copy['periodo_inicial'] = f'GTIN: {cod} - {principio}. Estoque Inicial Estimado: {est} unidade(s). {notas}'
            j_copy['_tipo_linha'] = 'header_medicamento'
            for k in ['vendas_periodo', 'vendas_sem_comprovacao', 'valor_movimentado', 'valor_sem_comprovacao']:
                j_copy[k] = ""
            lista_parcial.append(j_copy)
            lista_parcial.append({
                'periodo_inicial': 'Data Primeira Venda',
                'periodo_inicial_nao_comprovacao': 'Data Início Não Comprovação',
                'periodo_final': 'Data Última Venda',
                'estoque_inicial': 'Estoque Inicial',
                'estoque_final': 'Estoque Final',
                'vendas_periodo': 'Vendas',
                'vendas_sem_comprovacao': 'Vendas sem Comprov.',
                'valor_movimentado': 'Valor Vendas',
                'valor_sem_comprovacao': 'Valor sem Comprov.',
                'notas': 'Notas Fiscais',
                '_tipo_linha': 'header_colunas'
            })

        elif j['tipo'] == 'e':
            ultimo_estoque_valido = j.get('estoque_inicial', 0)

        elif j['tipo'] == 'v':
            ultimo_estoque_valido = j.get('estoque_final', 0)
            tem_irregularidade = j.get('valor_sem_comprovacao', 0) > 0
            exibir = (tipo_relatorio == 1) or (tipo_relatorio == 2 and tem_irregularidade)
            if exibir:
                numero_vendas_gtin += 1
                j_copy = copy.deepcopy(j)
                j_copy['estoque_inicial'] = int(j.get('estoque_inicial', 0))
                j_copy['estoque_final'] = int(j.get('estoque_final', 0))
                j_copy['vendas_periodo'] = int(j.get('vendas_periodo', 0))
                j_copy['vendas_sem_comprovacao'] = int(j.get('vendas_sem_comprovacao', 0))
                j_copy['valor_movimentado'] = float(
                    Decimal(str(j.get('valor_movimentado', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                j_copy['valor_sem_comprovacao'] = float(
                    Decimal(str(j.get('valor_sem_comprovacao', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                j_copy['periodo_inicial'] = j['periodo_inicial'].strftime("%d/%m/%Y") if j.get('periodo_inicial') else "-"
                dt_nc = j.get('periodo_inicial_nao_comprovacao')
                j_copy['periodo_inicial_nao_comprovacao'] = '-' if str(dt_nc) == '9999-01-01' else (dt_nc.strftime("%d/%m/%Y") if dt_nc else "-")
                j_copy['periodo_final'] = j['periodo_final'].strftime("%d/%m/%Y") if j.get('periodo_final') else "-"
                j_copy['_tipo_linha'] = 'venda_irregular' if tem_irregularidade else 'venda_normal'
                lista_parcial.append(j_copy)

        elif j['tipo'] in ('c', 'd'):
            ultimo_estoque_valido = j.get('estoque_final', 0)

        elif j['tipo'] == 's':
            j_copy = copy.deepcopy(j)
            estoque_visual_final = int(ultimo_estoque_valido)
            if lista_parcial:
                for item_rev in reversed(lista_parcial):
                    if 'estoque_final' in item_rev and isinstance(item_rev['estoque_final'], (int, float)):
                        estoque_visual_final = item_rev['estoque_final']
                        break
            j_copy['estoque_final'] = int(estoque_visual_final)
            j_copy['vendas_periodo'] = int(j.get('vendas_periodo', 0))
            j_copy['vendas_sem_comprovacao'] = int(j.get('vendas_sem_comprovacao', 0))
            j_copy['valor_movimentado'] = float(
                Decimal(str(j.get('valor_movimentado', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            j_copy['valor_sem_comprovacao'] = float(
                Decimal(str(j.get('valor_sem_comprovacao', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            j_copy['periodo_inicial'] = "Resumo Parcial"
            j_copy['_tipo_linha'] = 'resumo_parcial'
            lista_parcial.append(j_copy)
            lista_parcial.append({'_tipo_linha': 'spacer'})
            if numero_vendas_gtin > 0:
                lista_vendas_sem_comprovacao.extend(copy.deepcopy(lista_parcial))
            lista_parcial.clear()
            numero_vendas_gtin = 0

    lista_vendas_sem_comprovacao.append({
        'periodo_inicial': 'Total Geral',
        'vendas_sem_comprovacao': int(vendas_total_sem_comprovacao_cnpj),
        'vendas_periodo': int(vendas_total_cnpj),
        'valor_movimentado': float(valor_total_cnpj.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'valor_sem_comprovacao': float(valor_total_sem_comprovacao_cnpj.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        '_tipo_linha': 'total_geral'
    })


    df_analise = None
    try:
        if id_processamento:
            query_grafico = '''
                    SELECT 
                        periodo as data,
                        SUM(valor_vendas) as valor_total,
                        SUM(valor_sem_comprovacao) as valor_sem_comp
                    FROM temp_CGUSC.fp.movimentacao_mensal_gtin
                    WHERE id_processamento = ?
                    GROUP BY periodo
                    ORDER BY periodo
                '''
            df_temp = pd.read_sql(query_grafico, cursor.connection, params=[id_processamento])

            if not df_temp.empty:
                df_temp['data'] = pd.to_datetime(df_temp['data'])
                df_temp = df_temp.set_index('data')

                # Agrupa por Semestre (6 Meses)
                df_semestral = df_temp.resample('6MS').sum().reset_index()

                def format_semestre(date):
                    return f'{1 if date.month <= 6 else 2}S/{date.year}'

                df_semestral['periodo_fmt'] = df_semestral['data'].apply(format_semestre)
                df_semestral['valor_com_comp'] = df_semestral['valor_total'] - df_semestral['valor_sem_comp']

                df_semestral['pct_sem_comp_valor'] = (
                        df_semestral['valor_sem_comp'] / df_semestral['valor_total'].replace(0, 1)
                ).apply(lambda x: round(x, 4))

                df_semestral['valor_sem_comp'] = df_semestral['valor_sem_comp'].round(2)
                df_semestral['valor_total'] = df_semestral['valor_total'].round(2)

                df_analise = df_semestral[
                    ['periodo_fmt', 'valor_com_comp', 'valor_sem_comp', 'pct_sem_comp_valor', 'valor_total']]
    except Exception as e:
        logging.error(f"Erro ao calcular dados do gráfico via SQL: {e}")
        df_analise = None

    if vendas_total_cnpj == 0:
        return "SEM_VENDAS"

    # =================================================================
    # INÍCIO DA ESCRITA DO EXCEL
    # =================================================================
    output = f"{cnpj_analise} ({'Completo' if tipo_relatorio == 1 else 'Resumido'}).xlsx"
    
    try:
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
    except PermissionError:
        print(f"\n❌ ERRO: O arquivo '{output}' parece estar aberto.")
        print("   ⚠️  Por favor, FECHE O ARQUIVO EXCEL e tente novamente.")
        return "ARQUIVO_ABERTO"
    except Exception as e:
        print(f"Erro ao criar arquivo Excel: {e}")
        return "ERRO_CRIACAO"

    try:
        wb = writer.book

        # ESTILOS GERAIS
        fmt_cabecalho = wb.add_format({
            'bold': True, 'font_size': 12, 'bg_color': '#1F4E78', 'font_color': 'white',
            'align': 'left', 'valign': 'vcenter', 'text_wrap': True
        })
        fmt_header_medicamento = wb.add_format({
            'bold': True, 'font_size': 11, 'bg_color': '#777777', 'font_color': 'white',
            'align': 'left', 'valign': 'vcenter', 'text_wrap': True, 'border': 1
        })
        fmt_header_colunas = wb.add_format({
            'bold': True, 'font_size': 10, 'bg_color': '#F2F2F2', 'align': 'center',
            'valign': 'vcenter', 'text_wrap': True, 'border': 1
        })
        fmt_header_colunas_left = wb.add_format({
            'bold': True, 'font_size': 10, 'bg_color': '#F2F2F2', 'align': 'left',
            'valign': 'vcenter', 'text_wrap': True, 'border': 1
        })
        fmt_venda_normal = wb.add_format({'bg_color': '#F1F7ED', 'align': 'left', 'valign': 'vcenter', 'border': 1})
        fmt_venda_irregular = wb.add_format({'bg_color': '#FFEBEE', 'align': 'left', 'valign': 'vcenter', 'border': 1})
        fmt_resumo = wb.add_format({
            'bold': True, 'bg_color': '#F2F2F2', 'font_color': 'black',
            'align': 'left', 'valign': 'vcenter', 'border': 1
        })
        fmt_resumo_int = wb.add_format({
            'bold': True, 'bg_color': '#F2F2F2', 'font_color': 'black',
            'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0', 'border': 1
        })
        fmt_resumo_moeda = wb.add_format({
            'bold': True, 'bg_color': '#F2F2F2', 'font_color': 'black',
            'align': 'right', 'valign': 'vcenter', 'num_format': 'R$ #,##0.00', 'border': 1
        })
        fmt_total = wb.add_format({
            'bold': True, 'font_size': 11, 'bg_color': '#203764', 'font_color': 'white',
            'align': 'left', 'valign': 'vcenter', 'left': 2, 'right': 2, 'top': 2, 'bottom': 2
        })
        fmt_total_int = wb.add_format({
            'bold': True, 'font_size': 11, 'bg_color': '#203764', 'font_color': 'white',
            'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0',
            'left': 2, 'right': 2, 'top': 2, 'bottom': 2
        })
        fmt_total_moeda = wb.add_format({
            'bold': True, 'font_size': 11, 'bg_color': '#203764', 'font_color': 'white',
            'align': 'right', 'valign': 'vcenter', 'num_format': 'R$ #,##0.00',
            'left': 2, 'right': 2, 'top': 2, 'bottom': 2
        })
        fmt_cell_center = wb.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        fmt_int_norm = wb.add_format({'num_format': '#,##0', 'align': 'right', 'bg_color': '#F1F7ED', 'border': 1})
        fmt_int_irreg = wb.add_format({'num_format': '#,##0', 'align': 'right', 'bg_color': '#FFEBEE', 'border': 1})
        fmt_cur_norm = wb.add_format({'num_format': 'R$ #,##0.00', 'align': 'right', 'bg_color': '#F1F7ED', 'border': 1})
        fmt_cur_irreg = wb.add_format({'num_format': 'R$ #,##0.00', 'align': 'right', 'bg_color': '#FFEBEE', 'border': 1})
        fmt_cur_alert = wb.add_format({
            'num_format': 'R$ #,##0.00', 'align': 'right', 'bg_color': '#FFEBEE',
            'font_color': '#C00000', 'bold': True, 'border': 1
        })

        # =================================================================
        # ABA 1: MOVIMENTAÇÃO
        # =================================================================
        df = pd.DataFrame.from_records(lista_vendas_sem_comprovacao)
        cols_drop = ['numero_nfe', 'qnt_aquis_dev', 'data_aquis_dev_estoq', 'tipo', 'codigo_barra',
                     'data_estoque_inicial', 'data_aquisicao', 'data_devolucao']
        for c in cols_drop:
            if c in df.columns:
                df.drop(c, axis=1, inplace=True)
        tipo_linha = df['_tipo_linha'].tolist() if '_tipo_linha' in df.columns else []
        if '_tipo_linha' in df.columns:
            df.drop('_tipo_linha', axis=1, inplace=True)
        cols_order = ['periodo_inicial', 'periodo_inicial_nao_comprovacao', 'periodo_final', 'estoque_inicial',
                      'estoque_final', 'vendas_periodo', 'vendas_sem_comprovacao', 'valor_movimentado',
                      'valor_sem_comprovacao', 'notas']
        df = df.reindex([c for c in cols_order if c in df.columns], axis=1)
        df.to_excel(writer, sheet_name='Movimentacao', index=False, header=False)
        ws = writer.sheets['Movimentacao']

        col_map = {name: idx for idx, name in enumerate(df.columns)}
        last_col = len(df.columns) - 1

        for r, tipo in enumerate(tipo_linha):
            txt = df.iloc[r]['periodo_inicial'] if 'periodo_inicial' in df.columns else ''
            if tipo == 'cabecalho_principal':
                ws.merge_range(r, 0, r, last_col, txt, fmt_cabecalho)
                ws.set_row(r, 25)
            elif tipo == 'header_medicamento':
                ws.merge_range(r, 0, r, last_col, txt, fmt_header_medicamento)
                ws.set_row(r, 30)
            elif tipo == 'header_colunas':
                ws.set_row(r, 35, fmt_header_colunas)
                if 'notas' in col_map:
                    texto_nota = df.iloc[r]['notas']
                    ws.write(r, col_map['notas'], texto_nota, fmt_header_colunas_left)
            elif tipo == 'spacer':
                ws.set_row(r, 15)
            elif tipo == 'venda_normal':
                ws.set_row(r, 20, fmt_venda_normal)
                if 'estoque_inicial' in col_map:
                    ws.write(r, col_map['estoque_inicial'], df.iloc[r]['estoque_inicial'], fmt_int_norm)
                if 'estoque_final' in col_map:
                    ws.write(r, col_map['estoque_final'], df.iloc[r]['estoque_final'], fmt_int_norm)
                if 'vendas_periodo' in col_map:
                    ws.write(r, col_map['vendas_periodo'], df.iloc[r]['vendas_periodo'], fmt_int_norm)
                if 'vendas_sem_comprovacao' in col_map:
                    ws.write(r, col_map['vendas_sem_comprovacao'], df.iloc[r]['vendas_sem_comprovacao'], fmt_int_norm)
                if 'valor_movimentado' in col_map:
                    ws.write(r, col_map['valor_movimentado'], df.iloc[r]['valor_movimentado'], fmt_cur_norm)
                if 'valor_sem_comprovacao' in col_map:
                    ws.write(r, col_map['valor_sem_comprovacao'], df.iloc[r]['valor_sem_comprovacao'], fmt_cur_norm)
            elif tipo == 'venda_irregular':
                ws.set_row(r, 20, fmt_venda_irregular)
                if 'estoque_inicial' in col_map:
                    ws.write(r, col_map['estoque_inicial'], df.iloc[r]['estoque_inicial'], fmt_int_irreg)
                if 'estoque_final' in col_map:
                    ws.write(r, col_map['estoque_final'], df.iloc[r]['estoque_final'], fmt_int_irreg)
                if 'vendas_periodo' in col_map:
                    ws.write(r, col_map['vendas_periodo'], df.iloc[r]['vendas_periodo'], fmt_int_irreg)
                if 'vendas_sem_comprovacao' in col_map:
                    ws.write(r, col_map['vendas_sem_comprovacao'], df.iloc[r]['vendas_sem_comprovacao'], fmt_int_irreg)
                if 'valor_movimentado' in col_map:
                    ws.write(r, col_map['valor_movimentado'], df.iloc[r]['valor_movimentado'], fmt_cur_irreg)
                if 'valor_sem_comprovacao' in col_map:
                    ws.write(r, col_map['valor_sem_comprovacao'], df.iloc[r]['valor_sem_comprovacao'], fmt_cur_alert)
            elif tipo == 'resumo_parcial':
                ws.set_row(r, 25, fmt_resumo)
                if 'estoque_final' in col_map:
                    ws.write(r, col_map['estoque_final'], df.iloc[r]['estoque_final'], fmt_resumo_int)
                if 'vendas_periodo' in col_map:
                    ws.write(r, col_map['vendas_periodo'], df.iloc[r]['vendas_periodo'], fmt_resumo_int)
                if 'vendas_sem_comprovacao' in col_map:
                    ws.write(r, col_map['vendas_sem_comprovacao'], df.iloc[r]['vendas_sem_comprovacao'], fmt_resumo_int)
                if 'valor_movimentado' in col_map:
                    ws.write(r, col_map['valor_movimentado'], df.iloc[r]['valor_movimentado'], fmt_resumo_moeda)
                if 'valor_sem_comprovacao' in col_map:
                    ws.write(r, col_map['valor_sem_comprovacao'], df.iloc[r]['valor_sem_comprovacao'], fmt_resumo_moeda)
            elif tipo == 'total_geral':
                ws.set_row(r, 30, fmt_total)
                if 'vendas_periodo' in col_map:
                    ws.write(r, col_map['vendas_periodo'], df.iloc[r]['vendas_periodo'], fmt_total_int)
                if 'vendas_sem_comprovacao' in col_map:
                    ws.write(r, col_map['vendas_sem_comprovacao'], df.iloc[r]['vendas_sem_comprovacao'], fmt_total_int)
                if 'valor_movimentado' in col_map:
                    ws.write(r, col_map['valor_movimentado'], df.iloc[r]['valor_movimentado'], fmt_total_moeda)
                if 'valor_sem_comprovacao' in col_map:
                    ws.write(r, col_map['valor_sem_comprovacao'], df.iloc[r]['valor_sem_comprovacao'], fmt_total_moeda)

        # Ajuste de largura das colunas
        ws.set_column(0, 0, 25)
        if 'periodo_inicial_nao_comprovacao' in col_map:
            ws.set_column(col_map['periodo_inicial_nao_comprovacao'], col_map['periodo_inicial_nao_comprovacao'], 25)
        if 'periodo_final' in col_map:
            ws.set_column(col_map['periodo_final'], col_map['periodo_final'], 20)
        if 'estoque_inicial' in col_map:
            ws.set_column(col_map['estoque_inicial'], col_map['estoque_inicial'], 15)
        if 'estoque_final' in col_map:
            ws.set_column(col_map['estoque_final'], col_map['estoque_final'], 15)
        if 'vendas_periodo' in col_map:
            ws.set_column(col_map['vendas_periodo'], col_map['vendas_periodo'], 12)
        if 'vendas_sem_comprovacao' in col_map:
            ws.set_column(col_map['vendas_sem_comprovacao'], col_map['vendas_sem_comprovacao'], 18)
        if 'valor_movimentado' in col_map:
            ws.set_column(col_map['valor_movimentado'], col_map['valor_movimentado'], 18)
        if 'valor_sem_comprovacao' in col_map:
            ws.set_column(col_map['valor_sem_comprovacao'], col_map['valor_sem_comprovacao'], 20)
        if 'notas' in col_map:
            ws.set_column(col_map['notas'], col_map['notas'], 800)
        ws.freeze_panes(1, 0)

        # =================================================================
        # ABA 2: EVOLUÇÃO FINANCEIRA
        # =================================================================
        if df_analise is not None and not df_analise.empty:
            ws_analise = wb.add_worksheet('Evolucao_Financeira')
            ws_analise.hide_gridlines(2)

            fmt_linha_infinita = wb.add_format({'bg_color': '#1F4E78'})
            fmt_header = wb.add_format({
                'bold': True, 'font_size': 10, 'bg_color': '#E4E4E4', 'font_color': '#2E2E2E',
                'align': 'center', 'valign': 'vcenter', 'border': 1
            })
            fmt_moeda = wb.add_format({'num_format': 'R$ #,##0.00', 'align': 'right', 'border': 1})
            fmt_pct = wb.add_format({'num_format': '0.00%', 'align': 'center', 'border': 1})
            fmt_semestre = wb.add_format({'align': 'center', 'border': 1})
            fmt_cabecalho_dash = wb.add_format({
                'bold': True, 'font_size': 12, 'bg_color': '#1F4E78', 'font_color': 'white',
                'align': 'left', 'valign': 'vcenter', 'text_wrap': True, 'border': 1
            })

            ws_analise.set_row(0, 25, fmt_linha_infinita)
            ws_analise.merge_range('A1:AG1', texto_cabecalho_1, fmt_cabecalho_dash)

            start_row = 2
            start_col = 1
            headers = ['Semestre', 'Total', 'Vendas Regulares', 'Vendas Irreg.', '% Irregular']
            for c, h in enumerate(headers):
                ws_analise.write(start_row, start_col + c, h, fmt_header)

            for r, row_data in enumerate(df_analise.values):
                current_row = start_row + 1 + r
                ws_analise.write(current_row, start_col + 0, row_data[0], fmt_semestre)
                ws_analise.write(current_row, start_col + 1, row_data[4], fmt_moeda)
                ws_analise.write(current_row, start_col + 2, row_data[1], fmt_moeda)
                ws_analise.write(current_row, start_col + 3, row_data[2], fmt_moeda)
                ws_analise.write(current_row, start_col + 4, row_data[3], fmt_pct)

            row_total = start_row + 1 + len(df_analise)
            sum_regular = df_analise['valor_com_comp'].sum()
            sum_irregular = df_analise['valor_sem_comp'].sum()
            sum_total = df_analise['valor_total'].sum()
            pct_total = (sum_irregular / sum_total) if sum_total > 0 else 0

            fmt_total_label = wb.add_format({
                'bold': True, 'bg_color': '#E4E4E4', 'font_color': '#2E2E2E',
                'align': 'center', 'border': 1
            })
            fmt_total_moeda_ev = wb.add_format({
                'bold': True, 'bg_color': '#E4E4E4', 'font_color': '#2E2E2E',
                'num_format': 'R$ #,##0.00', 'align': 'right', 'border': 1
            })
            fmt_total_moeda_red = wb.add_format({
                'bold': True, 'bg_color': '#E4E4E4', 'num_format': 'R$ #,##0.00',
                'align': 'right', 'font_color': '#2E2E2E', 'border': 1
            })
            fmt_total_pct = wb.add_format({
                'bold': True, 'bg_color': '#E4E4E4', 'font_color': '#2E2E2E',
                'num_format': '0.00%', 'align': 'center', 'border': 1
            })

            ws_analise.write(row_total, start_col, "TOTAL", fmt_total_label)
            ws_analise.write(row_total, start_col + 1, sum_total, fmt_total_moeda_ev)
            ws_analise.write(row_total, start_col + 2, sum_regular, fmt_total_moeda_ev)
            ws_analise.write(row_total, start_col + 3, sum_irregular, fmt_total_moeda_red)
            ws_analise.write(row_total, start_col + 4, pct_total, fmt_total_pct)

            ws_analise.set_column('A:A', 4)
            ws_analise.set_column('B:B', 10)
            ws_analise.set_column('C:C', 17)
            ws_analise.set_column('D:D', 17)
            ws_analise.set_column('E:E', 15)
            ws_analise.set_column('F:F', 10)
            ws_analise.set_column('G:G', 3)
            ws_analise.set_column('H:H', 25)
            ws_analise.set_column('I:I', 2)
            ws_analise.set_column('J:J', 25)
            ws_analise.set_column('K:K', 2)
            ws_analise.set_column('L:L', 25)

            max_row = row_total
            chart1 = wb.add_chart({'type': 'column', 'subtype': 'stacked'})
            chart1.add_series({
                'name': f'=Evolucao_Financeira!$D${start_row + 1}',
                'categories': f'=Evolucao_Financeira!$B${start_row + 2}:$B${max_row}',
                'values': f'=Evolucao_Financeira!$D${start_row + 2}:$D${max_row}',
                'fill': {'color': '#F1F7ED'}, 'border': {'color': '#D9D9D9'}, 'gap': 30
            })
            chart1.add_series({
                'name': f'=Evolucao_Financeira!$E${start_row + 1}',
                'categories': f'=Evolucao_Financeira!$B${start_row + 2}:$B${max_row}',
                'values': f'=Evolucao_Financeira!$E${start_row + 2}:$E${max_row}',
                'fill': {'color': '#C00000'}, 'border': {'color': '#BFBFBF'}
            })
            chart1.set_title({'name': 'Volume Financeiro Auditado (R$)'})
            chart1.set_size({'width': 1000, 'height': 380})
            chart1.set_y_axis({'name': 'Volume (R$)', 'major_gridlines': {'visible': True, 'line': {'color': '#E0E0E0'}}})
            chart1.set_legend({'position': 'bottom'})
            chart1.set_chartarea({'border': {'none': True}})
            ws_analise.insert_chart('H6', chart1, {'x_offset': 10, 'y_offset': 10})

            chart2 = wb.add_chart({'type': 'area'})
            chart2.add_series({
                # Mudou de $F$ (Porcentagem) para $E$ (Valor Irregular)
                'name': f'=Evolucao_Financeira!$E${start_row + 1}',
                'categories': f'=Evolucao_Financeira!$B${start_row + 2}:$B${max_row}',
                'values': f'=Evolucao_Financeira!$E${start_row + 2}:$E${max_row}',

                'fill': {'color': '#B4C6E7'},
                'border': {'color': '#203764', 'width': 2},
                'marker': {'type': 'circle', 'size': 5, 'fill': {'color': '#203764'}}
            })

            # Atualiza o título para refletir que agora é R$
            chart2.set_title({'name': 'Evolução dos Valores Irregulares (R$)'})
            chart2.set_size({'width': 1000, 'height': 380})

            # Removemos 'min': 0, 'max': 1.0 pois agora são valores monetários
            chart2.set_y_axis({
                'name': 'Valor Irregular (R$)',
                'major_gridlines': {'visible': True, 'line': {'color': '#E0E0E0'}}
            })

            chart2.set_legend({'none': True})
            chart2.set_chartarea({'border': {'none': True}})
            ws_analise.insert_chart('H27', chart2, {'x_offset': 10, 'y_offset': 10})

            # Cards de resumo
            fmt_card_t = wb.add_format({'font_size': 9, 'font_color': '#777777', 'align': 'center'})
            ws_analise.write('H3', 'TOTAL IRREGULAR', fmt_card_t)
            ws_analise.write('H4', sum_irregular, wb.add_format({
                'font_size': 14, 'font_color': '#C00000', 'bold': True,
                'align': 'center', 'num_format': 'R$ #,##0.00'
            }))
            ws_analise.write('J3', '% MÉDIA IRREGULARIDADE', fmt_card_t)
            ws_analise.write('J4', pct_total, wb.add_format({
                'font_size': 14, 'font_color': '#000000', 'bold': True,
                'align': 'center', 'num_format': '0.00%'
            }))
            ws_analise.write('L3', 'TOTAL MOVIMENTADO', fmt_card_t)
            ws_analise.write('L4', sum_total, wb.add_format({
                'font_size': 14, 'font_color': '#203764', 'bold': True,
                'align': 'center', 'num_format': 'R$ #,##0.00'
            }))

        # =================================================================
        # ABA 3: INDICADORES DE RISCO
        # =================================================================
        if dados_risco:
            ws_ind = wb.add_worksheet('Indicadores')
            ws_ind.hide_gridlines(2)

            COR_AZUL_ESCURO = '#1F4E78'
            COR_CINZA_CLARO = '#F2F2F2'
            COR_VERMELHO = '#C00000'
            COR_AMARELO = '#FFC000'
            COR_VERDE = '#548235'

            fmt_titulo = wb.add_format({
                'bold': True, 'font_size': 18, 'font_color': COR_AZUL_ESCURO,
                'align': 'left', 'valign': 'vcenter'
            })
            fmt_subtitulo = wb.add_format({
                'font_size': 10, 'font_color': '#555555', 'align': 'left', 'valign': 'vcenter'
            })
            fmt_score_label = wb.add_format({
                'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'top', 'font_color': '#555555'
            })
            fmt_header_grupo = wb.add_format({
                'bold': True, 'font_size': 11, 'bg_color': COR_AZUL_ESCURO, 'font_color': 'white',
                'align': 'left', 'valign': 'vcenter', 'indent': 1, 'border': 1
            })
            fmt_header_col = wb.add_format({
                'bold': True, 'font_size': 9, 'bg_color': COR_CINZA_CLARO, 'font_color': 'black',
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True
            })
            fmt_label = wb.add_format({
                'font_size': 10, 'align': 'left', 'valign': 'vcenter',
                'indent': 1, 'border': 1, 'bg_color': 'white'
            })

            fmt_pct_ind = wb.add_format({'num_format': '0.00%', 'align': 'center', 'valign': 'vcenter', 'border': 1})
            fmt_pct_ind_3 = wb.add_format({'num_format': '0.000%', 'align': 'center', 'valign': 'vcenter', 'border': 1})
            fmt_dec = wb.add_format({'num_format': '0.00', 'align': 'center', 'valign': 'vcenter', 'border': 1})
            fmt_val = wb.add_format({'num_format': 'R$ #,##0.00', 'align': 'center', 'valign': 'vcenter', 'border': 1})

            fmt_risco_verde = wb.add_format({
                'bg_color': '#E2EFDA', 'font_color': '#006100', 'bold': True,
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.0x'
            })
            fmt_risco_amarelo = wb.add_format({
                'bg_color': '#FFF2CC', 'font_color': '#9C5700', 'bold': True,
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.0x'
            })
            fmt_risco_vermelho = wb.add_format({
                'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'bold': True,
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.0x'
            })

            # Explicações Metodológicas (Profundas)
            explicacoes = {
                "Vendas p/ Falecidos": "METODOLOGIA: Confronto direto entre a data da dispensação do medicamento e a data oficial de óbito registrada nas bases governamentais (SIM/SIRC/SISOBI).",

                "Incompatibilidade Patológica": "METODOLOGIA: Confronta a indicação terapêutica com os dados do beneficiário (Idade e Sexo). O indicador sinaliza dispensações que violam padrões esperados, aplicando quatro filtros: 1. Osteoporose em pacientes do sexo Masculino; 2. Parkinson em pacientes com menos de 50 anos; 3. Hipertensão em pacientes com menos de 20 anos; 4. Diabetes em pacientes com menos de 20 anos.",

                "Dispensação em Teto Máximo": "METODOLOGIA: Percentual de dispensações onde a quantidade vendida atinge exatamente o limite máximo permitido por medicamento. Em um cenário orgânico, as vendas variam conforme a necessidade.",

                "4+ Itens por Autorização": "METODOLOGIA: Percentual de autorizações (cupons fiscais) que contêm 4 ou mais medicamentos distintos dispensados no mesmo ato.",


                "Valor do Ticket Médio": "METODOLOGIA: Valor monetário médio de cada autorização de venda.",

                "Faturamento Médio Mensal por Cliente": "METODOLOGIA: Faturamento médio mensal da farmácia dividido pelo número de CPFs distintos atendidos (normalizado pelo tempo de atividade).",

                "Venda Per Capita Mensal Municipal": "METODOLOGIA: Faturamento médio mensal da farmácia dividido pela população total do município (estimativa IBGE).",

                "Vendas Rápidas (<60s)": "METODOLOGIA: Percentual de vendas consecutivas realizadas em intervalo de tempo inferior a 60 segundos entre uma autorização e outra.",

                "Volume Atípico": "METODOLOGIA: Mede explosões de crescimento semestral atípicos no faturamento do programa, avaliando a frequência e a magnitude desses saltos artificiais.",

                "Recorrência Sistêmica": "METODOLOGIA: Avalia o percentual de compras sequenciais de medicamentos de uso contínuo realizadas precisamente na linha de corte do sistema (ex: 30 dias cravados). Alta recorrência exata pode indicar a atuação de scripts automatizados de renovação virtual, em contraste com a flutuação natural do comportamento humano de visita à farmácia.",

                "Dispersão Geográfica Interestadual": "METODOLOGIA: Percentual de vendas realizadas para pacientes cuja Unidade da Federação (UF) de residência difere da UF da farmácia.",

                "Medicamentos de Alto Custo": "METODOLOGIA: Percentual do faturamento total da farmácia que provém exclusivamente de medicamentos classificados no topo da tabela de preços (90º percentil).",

                "Concentração em Dias de Pico": "METODOLOGIA: Mede o percentual do faturamento mensal que ocorre concentrado nos 3 dias de maior movimento do mês. Farmácias normais diluem vendas.",

                "Concentração de CRMs (HHI)": "METODOLOGIA: Utiliza o Índice Herfindahl-Hirschman (HHI) para medir a concentração de prescrições. Calcula a soma dos quadrados das participações de cada médico no faturamento da farmácia. O quadrado penaliza exponencialmente a concentração. Um HHI elevado indica que a farmácia depende excessivamente de poucos CRMs.",


                "Irregularidade de CRMs":"Identifica o percentual do faturamento vinculado a CRMs com irregularidades cadastrais. Duas anomalias são detectadas: (1) CRM/UF não localizado na base oficial do Conselho Federal de Medicina (CFM); (2) Prescrições realizadas ANTES da data de inscrição do médico no CFM. Ambas indicam uso de CRMs não localizados ou fraudulentos."

            }

            ws_ind.write('B2', "INDICADORES DE RISCO & FRAUDE", fmt_titulo)
            ws_ind.write('B3', f"{dados_risco.get('razaoSocial', '')} | CNPJ: {cnpj_analise}", fmt_subtitulo)


            # ws_ind.write('B4', f"{dados_risco.get('municipio', '')} - {dados_risco.get('uf', '')}", fmt_subtitulo)

            # =================================================================
            # NOVO: CABEÇALHO DEMOGRÁFICO ENRIQUECIDO
            # =================================================================
            mun = dados_risco.get('municipio', 'DESCONHECIDO')
            uf = dados_risco.get('uf', '')
            pop_mun = int(dados_risco.get('populacao') or 0)
            pop_reg = int(dados_risco.get('populacao_total_regiao') or 0)
            
            total_mun = int(dados_risco.get('total_municipio') or 0)
            total_reg = int(dados_risco.get('total_regiao_saude') or 0)

            # Centraliza a lógica de limiares para evitar divergência entre checklist e tabela
            def get_limiares_indicador(nome):
                """
                Limiares de classificação de risco por indicador (ratio = valor / mediana).
                Um registro por indicador — sem fallback implícito.
                DEVE estar sincronizado com: riskConfig.js → INDICATOR_THRESHOLDS
                                         e: analytics.py  → _INDICATOR_THRESHOLDS
                """
            def get_limiares_indicador(nome):
                """
                Define os limiares de risco (Atenção e Crítico) para cada indicador.
                Valores sincronizados com o arquivo frontend/src/config/riskConfig.js
                """
                # Mapeamento de Nome do Relatório -> (Limiar Atenção, Limiar Crítico)
                # Ratio = Valor da Farmácia / Mediana Regional
                _THRESHOLDS = {
                    "Percentual de Não Comprovação":        (2.0, 3.0),
                    "Vendas p/ Falecidos":                  (2.0, 3.0),
                    "Incompatibilidade Patológica":         (2.0, 3.0),
                    "Dispensação em Teto Máximo":           (1.2, 1.39),
                    "4+ Itens por Autorização":             (2.0, 3.0),
                    "Valor do Ticket Médio":                (2.0, 3.0),
                    "Faturamento Médio por Cliente":        (2.0, 3.0),
                    "Venda Per Capita Mensal":              (2.0, 3.0),
                    "Medicamentos de Alto Custo":           (1.4, 1.7),
                    "Vendas Rápidas (<60s)":                (2.0, 3.0),
                    "Volume Atípico":                       (2.0, 3.0),
                    "Recorrência Sistêmica":                (1.4, 1.7),
                    "Concentração em Dias de Pico":         (1.4, 1.7),
                    "Dispersão Geográfica Interestadual":   (2.0, 3.0),
                    "Concentração de CRMs (HHI)":           (2.0, 3.0),
                    "Faturamento Atrelado a CRMs Irregulares": (2.0, 3.0),
                }

                return _THRESHOLDS.get(nome.strip(), (2.0, 3.0))
            
            # --- DEFINIÇÃO ÚNICA DOS GRUPOS DE INDICADORES ---
            # Formato: (Nome amigável, col_valor, col_med_reg, col_med_uf, col_med_br, col_risco_reg, col_risco_uf, col_risco_br, tipo_fmt)
            # Sincronizado com INDICATOR_GROUPS do riskConfig.js
            grupos_sentinela = [
                ("1. Auditoria Financeira", [
                    ("Percentual de Não Comprovação", "pct_sem_comprovacao", "med_sem_comprovacao_reg", "med_sem_comprovacao_uf", "med_sem_comprovacao_br", "risco_sem_comprovacao_reg", "risco_sem_comprovacao_uf", "risco_sem_comprovacao_br", "pct"),
                ]),
                ("2. Elegibilidade & Clínica", [
                    ("Vendas p/ Falecidos", "pct_falecidos", "med_falecidos_reg", "med_falecidos_uf", "med_falecidos_br", "risco_falecidos_reg", "risco_falecidos_uf", "risco_falecidos_br", "pct3"),
                    ("Incompatibilidade Patológica", "pct_clinico", "med_clinico_reg", "med_clinico_uf", "med_clinico_br", "risco_clinico_reg", "risco_clinico_uf", "risco_clinico_br", "pct"),
                ]),
                ("3. Padrões de Quantidade", [
                    ("Dispensação em Teto Máximo", "pct_teto", "med_teto_reg", "med_teto_uf", "med_teto_br", "risco_teto_reg", "risco_teto_uf", "risco_teto_br", "pct"),
                    ("4+ Itens por Autorização", "pct_polimedicamento", "med_polimedicamento_reg", "med_polimedicamento_uf", "med_polimedicamento_br", "risco_polimedicamento_reg", "risco_polimedicamento_uf", "risco_polimedicamento_br", "pct"),
                ]),
                ("4. Padrões Financeiros", [
                    ("Valor do Ticket Médio", "val_ticket_medio", "med_ticket_reg", "med_ticket_uf", "med_ticket_br", "risco_ticket_reg", "risco_ticket_uf", "risco_ticket_br", "val"),
                    ("Faturamento Médio por Cliente", "val_receita_paciente", "med_receita_paciente_reg", "med_receita_paciente_uf", "med_receita_paciente_br", "risco_receita_paciente_reg", "risco_receita_paciente_uf", "risco_receita_paciente_br", "val"),
                    ("Venda Per Capita Mensal", "val_per_capita", "med_per_capita_reg", "med_per_capita_uf", "med_per_capita_br", "risco_per_capita_reg", "risco_per_capita_uf", "risco_per_capita_br", "val"),
                    ("Medicamentos de Alto Custo", "pct_alto_custo", "med_alto_custo_reg", "med_alto_custo_uf", "med_alto_custo_br", "risco_alto_custo_reg", "risco_alto_custo_uf", "risco_alto_custo_br", "pct"),
                ]),
                ("5. Automação & Geografia", [
                    ("Vendas Rápidas (<60s)", "pct_vendas_rapidas", "med_vendas_rapidas_reg", "med_vendas_rapidas_uf", "med_vendas_rapidas_br", "risco_vendas_rapidas_reg", "risco_vendas_rapidas_uf", "risco_vendas_rapidas_br", "pct"),
                    ("Volume Atípico", "val_volume_atipico", "med_volume_atipico_reg", "med_volume_atipico_uf", "med_volume_atipico_br", "risco_volume_atipico_reg", "risco_volume_atipico_uf", "risco_volume_atipico_br", "dec"),
                    ("Recorrência Sistêmica", "pct_recorrencia_sistemica", "med_recorrencia_sistemica_reg", "med_recorrencia_sistemica_uf", "med_recorrencia_sistemica_br", "risco_recorrencia_sistemica_reg", "risco_recorrencia_sistemica_uf", "risco_recorrencia_sistemica_br", "pct"),
                    ("Concentração em Dias de Pico", "pct_pico", "med_pico_reg", "med_pico_uf", "med_pico_br", "risco_pico_reg", "risco_pico_uf", "risco_pico_br", "pct"),
                    ("Dispersão Geográfica Interestadual", "pct_geografico", "med_geografico_reg", "med_geografico_uf", "med_geografico_br", "risco_geografico_reg", "risco_geografico_uf", "risco_geografico_br", "pct"),
                ]),
                ("6. Integridade Médica", [
                    ("Concentração de CRMs (HHI)", "val_hhi_crm", "med_hhi_crm_reg", "med_hhi_crm_uf", "med_hhi_crm_br", "risco_crm_reg", "risco_crm_uf", "risco_crm_br", "dec"),
                    ("Faturamento Atrelado a CRMs Irregulares", "pct_crms_irregulares", "med_crms_irregulares_reg", "med_crms_irregulares_uf", "med_crms_irregulares_br", "risco_crms_irregulares_reg", "risco_crms_irregulares_uf", "risco_crms_irregulares_br", "pct"),
                ]),
            ]

            nome_regiao = dados_risco.get('no_regiao_saude', 'N/A')

            # Cálculos de Densidade
            dens_mun = int(pop_mun / total_mun) if total_mun > 0 else 0
            dens_reg = int(pop_reg / total_reg) if total_reg > 0 else 0
            
            pop_fmt = f"{pop_mun:,.0f}".replace(",", ".")

            # Movemos os dados de Score para o topo para uso no cabeçalho
            score = float(dados_risco.get('score_risco_final', 0))
            classificacao = dados_risco.get('classificacao_risco', 'RISCO BAIXO')

            rank_mun = int(dados_risco.get('rank_municipio') or 0)
            total_mun_estab = int(dados_risco.get('total_municipio') or 0)

            # Monta a string final (Barra Demográfica - B4)
            texto_demografico = (
                f"📍 {mun}-{uf}  |  👥 Pop: {pop_fmt}  |  "
                f"🏥 Região: {nome_regiao}  |  🏥 Estab. Reg: {total_reg}  |  📊 Dens: {dens_mun} hab/farm"
            )

            # Escreve na célula B4
            ws_ind.write('B4', texto_demografico, fmt_subtitulo)

            # --- NOVO: BARRA DE RANKINGS E PERFORMANCE (B5) ---
            rank_nacional = int(dados_risco.get('rank_nacional') or 0)
            total_nacional = int(dados_risco.get('total_nacional') or 0)
            rank_uf = int(dados_risco.get('rank_uf') or 0)
            total_uf = int(dados_risco.get('total_uf') or 0)
            rank_regiao = int(dados_risco.get('rank_regiao_saude', 0))
            total_regiao = int(dados_risco.get('total_regiao_saude') or 0)
            mediana_regiao = float(dados_risco.get('avg_score_regiao_saude', 0))
            vezes_pior = (score / mediana_regiao) if mediana_regiao > 0 else 1.0

            # Prepara a string de status regional (Badge visual)
            txt_status_reg = ""
            if rank_regiao == 1: txt_status_reg = " (🥇 LÍDER EM RISCO)"

            texto_ranking = (
                f"🏆 RANKINGS:  Nacional: #{rank_nacional:,}  |  Estadual: #{rank_uf:,}  |  "
                f"Regional: #{rank_regiao} de {total_regiao}  |  Municipal: {rank_mun}º de {total_mun_estab}  "
                f"|  📊 Score: {score:.1f}"
            ).replace(',', '.')

            ws_ind.write('B5', texto_ranking, fmt_subtitulo)
            
            # --- Link para Documentação (B6) ---
            fmt_link_doc = wb.add_format({
                'font_size': 9, 'font_color': 'blue', 'underline': True, 
                'align': 'left', 'valign': 'top'
            })
            ws_ind.write_url('B6', 'https://cgu-sc.github.io/sentinela/', fmt_link_doc, string='📘 Acesse a Documentação')

            # --- LINHA DE ESPAÇAMENTO (Respiro Visual) ---
            ws_ind.set_row(6, 5) # Linha 7 com altura 5

            # =================================================================





            mapeamento_classificacao = {
                'RISCO CRÍTICO': (COR_VERMELHO, '🔴 RISCO CRÍTICO'),
                'RISCO CRITICO': (COR_VERMELHO, '🔴 RISCO CRÍTICO'),
                'RISCO ALTO': (COR_VERMELHO, '🔴 RISCO ALTO'),
                'RISCO MÉDIO': (COR_AMARELO, '🟡 RISCO MÉDIO'),
                'RISCO MEDIO': (COR_AMARELO, '🟡 RISCO MÉDIO'),
                'RISCO BAIXO': (COR_VERDE, '🟢 BAIXO RISCO'),
                'RISCO MÍNIMO': (COR_VERDE, '🟢 RISCO MÍNIMO'),
                'RISCO MINIMO': (COR_VERDE, '🟢 RISCO MÍNIMO')
            }

            classificacao_limpa = str(classificacao).upper().strip()
            cor_score, txt_score = mapeamento_classificacao.get(classificacao_limpa, (COR_VERMELHO, '⚪ N/A'))


            fmt_score_num = wb.add_format({
                'bold': True, 'font_size': 48, 'align': 'center', 'valign': 'vcenter',
                'font_color': cor_score, 'border': 0, 'num_format': '0.00'
            })
            fmt_score_txt = wb.add_format({
                'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'vcenter',
                'font_color': cor_score, 'border': 0, 'text_wrap': True
            })

            ws_ind.merge_range('L2:Q4', score, fmt_score_num)
            ws_ind.merge_range('L5:Q6', txt_score, fmt_score_txt)
            ws_ind.merge_range('L7:Q7', "SCORE GERAL", fmt_score_label)


            # =================================================================
            # TABELA TOP 15 (COM COLUNA RISCO - J18)
            # =================================================================

            # =================================================================
            # TABELA TOP 15 (ESTENDIDA ATÉ COLUNA R - J18)
            # =================================================================

            # 1. Buscar os dados no banco
            id_regiao = dados_risco.get('id_regiao_saude')
            nome_regiao = dados_risco.get('no_regiao_saude', 'REGIÃO DESCONHECIDA')
            top10_lista = buscar_farmacias_regiao(cursor, id_regiao)[:10]

            # Título (Barra Azul Unificada)
            fmt_top10_header = wb.add_format({
                'bold': True, 'font_size': 9, 'bg_color': COR_AZUL_ESCURO, 'font_color': 'white',
                'align': 'left', 'valign': 'vcenter', 'indent': 1, 'border': 1
            })
            ws_ind.merge_range('L8:T8', f"TOP 10 PIORES FARMÁCIAS NA REGIÃO: {nome_regiao.upper()}", fmt_top10_header)
            ws_ind.set_row(7, 20) # Altura da barra de título

            # Cabeçalhos da Tabela
            fmt_th = wb.add_format(
                {'bold': True, 'font_size': 8, 'align': 'center', 'bg_color': '#F2F2F2', 'border': 1})
            fmt_th_esq = wb.add_format(
                {'bold': True, 'font_size': 8, 'align': 'left', 'bg_color': '#F2F2F2', 'border': 1})

            # LAYOUT DE COLUNAS (L até T)
            ws_ind.write('L9', "SCORE", fmt_th)              # L
            ws_ind.merge_range('M9:N9', "FARMÁCIA", fmt_th_esq)  # M-N
            ws_ind.write('O9', "MUNICÍPIO", fmt_th_esq)     # O
            ws_ind.write('P9', "RISCO", fmt_th)             # P
            ws_ind.write('Q9', "CONEXÃO", fmt_th)          # Q
            ws_ind.write('R9', "R$ S/ COMP.", fmt_th)       # R
            ws_ind.merge_range('S9:T9', "% S/ COMP.", fmt_th)  # S-T

            linha_atual = 8

            # Formatos
            bg_destaque = '#FFF2CC'
            font_destaque = '#9C0006'

            meu_cnpj_limpo = str(cnpj_analise).strip()

            if top10_lista:
                for idx, item in enumerate(top10_lista):
                    linha_atual += 1

                    cnpj_item = str(item.get('cnpj', '')).strip()
                    eh_eu = (cnpj_item == meu_cnpj_limpo)

                    if eh_eu:
                        pass

                    # --- LÓGICA DE DESTAQUE ---
                    # 1. Negrito se for eu
                    is_bold = True if eh_eu else False

                    # 2. Borda Normal (1) e Preta (Padrão)
                    # Se quiser borda grossa, mude para 2. Se quiser "normal", é 1.
                    border_style = 1
                    border_color = '#000000'

                    # Formatos base da linha
                    f_base = {
                        'font_size': 8,
                        'border': border_style,
                        'border_color': border_color,
                        'bold': is_bold,
                        'bg_color': '#FFFFFF',
                        'font_color': '#000000'
                    }

                    f_c = wb.add_format({**f_base, 'align': 'center', 'num_format': '0.00'})
                    f_l = wb.add_format({**f_base, 'align': 'left'})
                    f_m = wb.add_format({**f_base, 'align': 'right', 'num_format': '#,##0'})
                    f_p = wb.add_format({**f_base, 'align': 'center', 'num_format': '0.00%'})

                    # --- LÓGICA DA SETA NA COLUNA I ---
                    seta_char = "►" if eh_eu else ""

                    f_seta = wb.add_format({
                        'font_size': 14,
                        'bold': True,
                        'font_color': '#FF0000',  # <--- SETA VERMELHA (COMO ANTES)
                        'align': 'right',
                        'valign': 'vcenter',
                        'bg_color': '#FFFFFF',
                        'border': 0
                    })

                    # --- LÓGICA DE RISCO (5 NÍVEIS) ---
                    # --- LÓGICA DE RISCO (5 NÍVEIS) ---
                    raw_risco = str(item.get('CLASSIFICACAO_RISCO', '')).upper().strip()

                    txt_risco = "N/A"
                    bg_risco = '#F2F2F2'
                    font_risco = '#000000'

                    if raw_risco in ('RISCO CRÍTICO', 'RISCO CRITICO'):
                        txt_risco = "CRÍTICO"
                        bg_risco = '#FFC7CE'  # Vermelho "Forte" (Padrão Excel Bad)
                        font_risco = '#9C0006'

                    elif raw_risco == 'RISCO ALTO':
                        txt_risco = "ALTO"
                        bg_risco = '#FFE1E1'  # <--- VERMELHO MAIS CLARO
                        font_risco = '#9C0006'  # Fonte Vinho (mesma do crítico para leitura)

                    elif raw_risco in ('RISCO MÉDIO', 'RISCO MEDIO'):
                        txt_risco = "MÉDIO"
                        bg_risco = '#FFF2CC'  # Amarelo
                        font_risco = '#9C5700'

                    elif raw_risco in ('RISCO MÍNIMO', 'RISCO MINIMO'):
                        txt_risco = "MÍNIMO"
                        bg_risco = '#F6FAF4'
                        font_risco = '#548235'

                    elif raw_risco == 'RISCO BAIXO':
                        txt_risco = "BAIXO"
                        bg_risco = '#E2EFDA'
                        font_risco = '#006100'

                    f_risco = wb.add_format({
                        'font_size': 7, 'bold': True, 'align': 'center',
                        'border': border_style,
                        'border_color': border_color,
                        'bg_color': bg_risco, 'font_color': font_risco
                    })

                    # --- LÓGICA DE STATUS ---
                    data_bd = item.get('data_ultima_venda')
                    status_texto = "-"
                    cor_status_bg = '#F2F2F2'
                    cor_status_font = '#000000'

                    if data_bd:
                        if isinstance(data_bd, str):
                            try:
                                data_bd = datetime.strptime(data_bd, '%Y-%m-%d').date()
                            except:
                                pass
                        if isinstance(data_bd, datetime): data_bd = data_bd.date()
                        if isinstance(data_bd, date):
                            try:
                                dias_sem_comprar = (DATA_FINAL_ANALISE - data_bd).days
                                if dias_sem_comprar > 30:
                                    status_texto = "INATIVA"
                                    cor_status_bg = '#FFC7CE'
                                    cor_status_font = '#9C0006'
                                else:
                                    status_texto = "ATIVA"
                                    cor_status_bg = '#E2EFDA'
                                    cor_status_font = '#006100'
                            except:
                                status_texto = "ERRO"

                    f_status = wb.add_format({
                        'font_size': 7, 'bold': True, 'align': 'center',
                        'border': border_style,
                        'border_color': border_color,
                        'bg_color': cor_status_bg, 'font_color': cor_status_font
                    })

                    # Dados
                    nome_raw = item.get('razaoSocial', '')
                    nome = nome_raw[:28] + '...' if len(nome_raw) > 28 else nome_raw

                    score_item = float(item.get('SCORE_RISCO_FINAL', 0))
                    val_irreg = float(item.get('valor_sem_comprovacao', 0))
                    val_mov = float(item.get('valor_vendas', 0))
                    pct_irregular = (val_irreg / val_mov) if val_mov > 0 else 0.0

                    # --- ESCRITA NAS CÉLULAS ---

                    # 1. SETA (Coluna K / Index 10)
                    ws_ind.write(linha_atual, 10, seta_char, f_seta)

                    # 2. Tabela (Coluna L / Index 11 em diante)
                    ws_ind.write(linha_atual, 11, score_item, f_c)
                    ws_ind.merge_range(linha_atual, 12, linha_atual, 13, f"{nome}", f_l)
                    ws_ind.write(linha_atual, 14, item.get('municipio', ''), f_l)
                    ws_ind.write(linha_atual, 15, txt_risco, f_risco)
                    ws_ind.write(linha_atual, 16, status_texto, f_status)
                    ws_ind.write(linha_atual, 17, val_irreg, f_m)
                    ws_ind.merge_range(linha_atual, 18, linha_atual, 19, pct_irregular, f_p)

                # Captura a primeira e última linha de dados para a formatação condicional
                primeira_linha_top10 = 9
                ultima_linha_top10 = linha_atual

                # Data Bars (Cols 18 e 19 / S e T) - Agora dinâmico
                ws_ind.conditional_format(primeira_linha_top10, 18, ultima_linha_top10, 19, {
                    'type': 'data_bar', 'bar_color': '#63C384', 'bar_solid': True,
                    'min_type': 'num', 'min_value': 0, 'max_type': 'num', 'max_value': 1, 'bar_no_border': True
                })
            else:
                # Merge até a coluna 17 (R)
                ws_ind.merge_range(linha_atual + 1, 11, linha_atual + 1, 19, "Sem dados comparativos.", fmt_cell_center)
                linha_atual += 1

            # --- RESUMO PARA AUDITORIA (CHECKLIST DINÂMICO) ---
            achados_criticos = []
            for titulo_g, indicadores_g in grupos_sentinela:
                for nome, col_v, col_m_r, col_m_u, col_m_b, col_r_r, col_r_u, col_r_b, t_fmt in indicadores_g:
                    
                    # Usa a função centralizada
                    at_lim, cr_lim = get_limiares_indicador(nome)
                    
                    # Usamos o arredondamento para bater com o visual da tabela
                    r_u_raw = float(dados_risco.get(col_r_u) or 0)
                    r_u_base = round(r_u_raw, 1)

                    if r_u_base >= cr_lim:
                        v_f = float(dados_risco.get(col_v) or 0)
                        m_f = float(dados_risco.get(col_m_r) or 0) # Mediana Regional
                        r_r = float(dados_risco.get(col_r_r) or 0)
                        
                        # Formatação inteligente para os dois valores
                        if t_fmt == 'pct': 
                            v_str = f"{v_f:.2f}%"
                            m_str = f"{m_f:.2f}%"
                        elif t_fmt == 'val': 
                            # Formatação R$ para o valor
                            v_str = f"R$ {v_f:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                            m_str = f"R$ {m_f:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                        else: 
                            v_str = f"{v_f:.2f}"
                            m_str = f"{m_f:.2f}"
                        
                        achados_criticos.append({
                            'risco': r_r,
                            'texto': f"{nome}: operação {r_r:.1f}x acima da mediana regional (Farmácia: {v_str} | Mediana: {m_str})"
                        })

            if achados_criticos:
                row_check = linha_atual + 2
                # Estilo Alerta Suave (Monocromático Vermelho/Rosa)
                fmt_ch_header = wb.add_format({
                    'bold': True, 'font_size': 11, 'bg_color': '#FFC7CE', 'font_color': '#9C0006',
                    'align': 'left', 'valign': 'vcenter', 'indent': 1, 'border': 1, 'border_color': '#D99594'
                })
                fmt_ch_item = wb.add_format({
                    'font_size': 9, 'bg_color': '#FFF4F4', 'align': 'left', 'valign': 'vcenter',
                    'indent': 1, 'border': 1, 'border_color': '#D99594', 'text_wrap': True
                })
                
                ws_ind.merge_range(row_check, 11, row_check, 19, "📝 RESUMO PARA AUDITORIA (PONTOS CRÍTICOS)", fmt_ch_header)
                ws_ind.set_row(row_check, 20)
                
                achados_criticos = sorted(achados_criticos, key=lambda x: x['risco'], reverse=True)
                for i, achado in enumerate(achados_criticos):
                    curr_r = row_check + 1 + i
                    ws_ind.merge_range(curr_r, 11, curr_r, 19, f"• {achado['texto']}", fmt_ch_item)
                    ws_ind.set_row(curr_r, 20) # Altura suavizada
                







            # =================================================================
            # FIM DO NOVO BLOCO
            # =================================================================

            row = 7
            for titulo_grupo, indicadores in grupos_sentinela:
                ws_ind.merge_range(row, 1, row, 9, titulo_grupo, fmt_header_grupo)
                ws_ind.set_row(row, 20) # Altura padrão para barras de título azul
                row += 1
                ws_ind.write(row, 1, "INDICADOR",  fmt_header_col)
                ws_ind.write(row, 2, "FARMÁCIA",   fmt_header_col)
                ws_ind.write(row, 3, "MEDIANA\nREGIÃO",   fmt_header_col)
                ws_ind.write(row, 4, "MEDIANA\nUF",    fmt_header_col)
                ws_ind.write(row, 5, "MEDIANA\nBR",    fmt_header_col)
                ws_ind.write(row, 6, "RISCO\nREGIÃO",  fmt_header_col)
                ws_ind.write(row, 7, "RISCO\nUF",   fmt_header_col)
                ws_ind.write(row, 8, "RISCO\nBR",   fmt_header_col)
                ws_ind.write(row, 9, "STATUS",     fmt_header_col)
                ws_ind.set_row(row, 26)
                row += 1

                for nome, col_val, col_med_mun, col_med_uf, col_med_br, col_r_mun, col_r_uf, col_r_br, tipo_fmt in indicadores:

                    # --- NOVA LÓGICA DE DADOS AUSENTES ---
                    raw_valor   = dados_risco.get(col_val)
                    raw_med_mun = dados_risco.get(col_med_mun)
                    raw_med_uf  = dados_risco.get(col_med_uf)
                    raw_med_br  = dados_risco.get(col_med_br)
                    raw_r_mun   = dados_risco.get(col_r_mun)
                    raw_r_uf    = dados_risco.get(col_r_uf)
                    raw_r_br    = dados_risco.get(col_r_br)

                    # Se o valor principal for None, consideramos SEM DADOS
                    tem_dados = (raw_valor is not None)

                    if tem_dados:
                        valor   = float(raw_valor)
                        med_mun = float(raw_med_mun or 0)
                        med_uf  = float(raw_med_uf  or 0)
                        med_br  = float(raw_med_br  or 0)
                        r_mun   = float(raw_r_mun   or 0)
                        r_uf    = float(raw_r_uf    or 0)
                        r_br    = float(raw_r_br    or 0)

                        if tipo_fmt in ['pct', 'pct3']:
                            valor   /= 100.0
                            med_mun /= 100.0
                            med_uf  /= 100.0
                            med_br  /= 100.0

                        # Usa a função centralizada de limiares e status
                        limiar_atencao, limiar_critico = get_limiares_indicador(nome)

                        # Arredondamos para 1 casa decimal para bater com o visual do Excel (1.49 -> 1.5)
                        # IMPORTANTE: O status é baseado no Risco REGIONAL (r_mun)
                        risco_base = round(r_mun, 1) 
                        
                        fmt_risco_usado = fmt_risco_verde
                        texto_status = "NORMAL"
                        if risco_base >= limiar_atencao:
                            fmt_risco_usado = fmt_risco_amarelo
                            texto_status = "ATENÇÃO"
                        if risco_base >= limiar_critico:
                            fmt_risco_usado = fmt_risco_vermelho
                            texto_status = "CRÍTICO"

                        if tipo_fmt == 'pct3':
                            fmt_usado = fmt_pct_ind_3
                        else:
                            fmt_usado = fmt_pct_ind if tipo_fmt == 'pct' else fmt_val if tipo_fmt == 'val' else fmt_dec

                    else:
                        # Caso SEM DADOS
                        valor   = "-"
                        med_mun = "-"
                        med_uf  = "-"
                        med_br  = "-"
                        r_mun   = "-"
                        r_uf    = "-"
                        r_br    = "-"
                        texto_status = "SEM DADOS"

                        # Formato neutro para texto
                        fmt_usado = wb.add_format(
                            {'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_color': '#808080'})
                        fmt_risco_usado = fmt_usado

                    # Adiciona ícone se houver explicação
                    nome_display = f"{nome} ℹ️" if nome in explicacoes else nome

                    ws_ind.write(row, 1, nome_display, fmt_label)
                    ws_ind.write(row, 2, valor,         fmt_usado)
                    ws_ind.write(row, 3, med_mun,       fmt_usado)
                    ws_ind.write(row, 4, med_uf,        fmt_usado)
                    ws_ind.write(row, 5, med_br,        fmt_usado)
                    ws_ind.write(row, 6, r_mun,         fmt_risco_usado)
                    ws_ind.write(row, 7, r_uf,          fmt_risco_usado)
                    ws_ind.write(row, 8, r_br,          fmt_risco_usado)
                    ws_ind.write(row, 9, texto_status,  fmt_risco_usado)

                    if nome in explicacoes:
                        ws_ind.write_comment(row, 1, explicacoes[nome],
                                             {'width': 400, 'height': 120, 'font_name': 'Tahoma', 'font_size': 9})
                    
                    ws_ind.set_row(row, 20) # Altura padrão para linhas de dados
                    row += 1
                row += 1

            ws_ind.set_column('A:A', 2)
            ws_ind.set_column('B:B', 35)
            ws_ind.set_column('C:J', 10)
            ws_ind.set_column('K:K', 3)
            ws_ind.set_column('L:L', 6)
            ws_ind.set_column('M:N', 13)
            ws_ind.set_column('O:O', 14)
            ws_ind.set_column('P:Q', 8)
            ws_ind.set_column('R:T', 10)


        if dados_prescritores:
            try:
                gerar_aba_prescritores(wb, cnpj_analise, dados_prescritores, top20_prescritores or [], cursor=cursor, data_inicio=DATA_INICIAL_ANALISE, data_fim=DATA_FINAL_ANALISE)
                print("   ✅ Aba 'Prescritores' gerada")
            except Exception as e:
                logging.error(f"Erro ao gerar aba de prescritores: {e}")
                print(f"   ⚠️ Erro na aba de prescritores: {e}")

        if dados_falecidos:
            try:
                gerar_aba_falecidos(
                    wb, cnpj_analise, dados_falecidos,
                    dados_farmacias,
                    valor_total_auditado=float(valor_total_cnpj)
                )
                print("   ✅ Aba 'Falecidos' gerada")
            except Exception as e:
                logging.error(f"Erro ao gerar aba de falecidos: {e}")
                print(f"   ⚠️ Erro na aba de falecidos: {e}")

        if dados_risco and dados_risco.get('id_regiao_saude'):
            try:
                id_regiao = dados_risco.get('id_regiao_saude')
                nome_reg = dados_risco.get('no_regiao_saude', 'N/A')
                gerar_aba_regiao(wb, cursor, id_regiao, nome_reg, cnpj_analise=cnpj_analise, municipio_analise=mun)
                print("   ✅ Aba 'Região de Saúde' gerada")
            except Exception as e:
                logging.error(f"Erro ao gerar aba da região de saúde: {e}")
                print(f"   ⚠️ Erro na aba da região de saúde: {e}")

    except Exception as e:
        print(f"\n❌ ERRO AO SALVAR EXCEL {output}: {e}")
        logging.error(f"Erro ao gerar Excel para {cnpj_analise}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        try:
            writer.close()
        except:
            pass

    return "SALVO"

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================
def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("SENTINELA v8 - Gerador de Relatórios")
        print("=" * 60)
        print("\nUso: python gerar_relatorio_memoriav8.py <CNPJ> [tipo_relatorio]")
        print("\nParâmetros:")
        print("  CNPJ           - CNPJ da farmácia (apenas números)")
        print("  tipo_relatorio - 1 = Completo (padrão), 2 = Resumido")
        print("\nAbas geradas:")
        print("  1. Movimentação de Estoque")
        print("  2. Evolução Financeira")
        print("  3. Indicadores de Risco")
        print("  4. Análise de Prescritores")
        print("  5. Falecidos (condicional — só aparece se houver registros)")

        print("\nExemplo:")
        print("  python gerar_relatorio_memoriav8.py 98669864000103 1")
        print("=" * 60)
        sys.exit(1)

    cnpj = sys.argv[1].replace('.', '').replace('/', '').replace('-', '')
    tipo_relatorio = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    print("=" * 60)
    print("SENTINELA v8 - Gerador de Relatórios")
    print("=" * 60)
    print(f"\nCNPJ: {cnpj}")
    print(f"Tipo: {'Completo' if tipo_relatorio == 1 else 'Resumido'}")
    print("-" * 60)

    # Conectar ao banco
    conn, cursor = conectar_bd()

    try:
        # Carregar dados auxiliares
        print("\n📊 Carregando dados auxiliares...")
        dados_farmacias, dados_medicamentos = carregar_dados_auxiliares(cursor)

        # Carregar memória de cálculo
        print(f"\n🔍 Buscando memória de cálculo para CNPJ {cnpj}...")
        dados_memoria, id_proc = carregar_memoria_calculo(cursor, cnpj)

        if not dados_memoria:
            print(f"\n❌ ERRO: Não foram encontrados dados para o CNPJ {cnpj}")
            print("   Verifique se o CNPJ foi processado pelo script original.")
            sys.exit(1)

        print(f"   ✅ Encontrados {len(dados_memoria)} registros (ID Processamento: {id_proc})")

        # Buscar dados de risco
        print("\n📈 Buscando indicadores de risco...")
        dados_risco = buscar_dados_risco(cursor, cnpj)
        if dados_risco:
            print(f"   ✅ Score de risco: {dados_risco.get('SCORE_RISCO_FINAL', 'N/A')}")
        else:
            print("   ⚠️ Dados de risco não encontrados")

        # Buscar dados de prescritores
        print("\n👨‍⚕️ Buscando dados de prescritores...")
        dados_prescritores = buscar_dados_prescritores(cursor, cnpj, DATA_INICIAL_ANALISE, DATA_FINAL_ANALISE)
        top20_prescritores = buscar_top20_prescritores(cursor, cnpj, DATA_INICIAL_ANALISE, DATA_FINAL_ANALISE)
        if dados_prescritores:
            print(f"   ✅ Score de prescritores: {dados_prescritores.get('score_prescritores', 'N/A')}")
            print(f"   ✅ Top 20: {len(top20_prescritores)} prescritores encontrados")
        else:
            print("   ⚠️ Dados de prescritores não encontrados")

        # Buscar dados de falecidos
        print("\n☠️  Buscando vendas para falecidos...")
        dados_falecidos = buscar_dados_falecidos(cursor, cnpj)
        if dados_falecidos:
            print(f"   ✅ {len(dados_falecidos)} transação(ões) de falecidos encontradas")
        else:
            print("   ℹ️ Nenhuma venda para falecidos (aba não será gerada)")

        # Gerar relatório
        print("\n📝 Gerando relatório Excel...")
        resultado = gerarRelatorioMovimentacao(
            cnpj, dados_memoria, tipo_relatorio, cursor,
            dados_farmacias, dados_medicamentos, dados_risco,
            dados_prescritores, top20_prescritores,
            id_processamento=id_proc,
            dados_falecidos=dados_falecidos
        )


        if resultado == "SEM_VENDAS":
            print("\n⚠️ CNPJ sem vendas no período analisado.")
        else:
            nome_arquivo = f"{cnpj} ({'Completo' if tipo_relatorio == 1 else 'Resumido'}).xlsx"
            print(f"\n✅ Relatório gerado com sucesso!")
            print(f"   📁 Arquivo: {nome_arquivo}")

    except Exception as e:
        logging.error(f"Erro no processamento: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()
        print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

