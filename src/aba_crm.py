import logging
from decimal import Decimal


def buscar_dados_prescritores(cursor, cnpj, data_inicio=None, data_fim=None):
    """
    Busca os KPIs consolidados de prescritores para a farmácia no período.
    Utiliza a crm_export (v5) para garantir consistência com o Dashboard.
    """
    try:
        # Converte datas para formato de competência (YYYYMM) de forma segura
        def to_comp(d):
            if not d: return None
            if isinstance(d, str): return int(d.replace('-', '')[:6])
            return int(d.strftime('%Y%m'))

        comp_ini = to_comp(data_inicio) or 201501
        comp_fim = to_comp(data_fim) or 203012

        cursor.execute(f'''
            WITH Totais AS (
                -- Calcula o faturamento total da farmácia e total de médicos no período
                SELECT 
                    SUM(vl_total_prescricoes) as total_valor, 
                    SUM(nu_prescricoes_mes) as total_prescricoes,
                    COUNT(DISTINCT id_medico) as total_prescritores_distintos
                FROM temp_CGUSC.fp.crm_export E
                INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = E.id_cnpj
                WHERE F.cnpj = ? AND competencia BETWEEN {comp_ini} AND {comp_fim}
            ),
            Ranking AS (
                SELECT 
                    id_medico,
                    SUM(vl_total_prescricoes) as vl_medico,
                    ROW_NUMBER() OVER (ORDER BY SUM(vl_total_prescricoes) DESC) as rk
                FROM temp_CGUSC.fp.crm_export E
                INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = E.id_cnpj
                WHERE F.cnpj = ? AND competencia BETWEEN {comp_ini} AND {comp_fim}
                GROUP BY id_medico
            ),
            Exclusivos AS (
                -- Conta médicos que atuaram em apenas 1 estabelecimento em todos os meses do período
                SELECT COUNT(*) as qtd_exclusivos
                FROM (
                    SELECT id_medico
                    FROM temp_CGUSC.fp.crm_export E
                    INNER JOIN temp_CGUSC.fp.dados_farmacia FAR ON FAR.id = E.id_cnpj
                    WHERE FAR.cnpj = ? AND competencia BETWEEN {comp_ini} AND {comp_fim}
                    GROUP BY id_medico
                    HAVING MAX(nu_estabelecimentos) = 1
                ) t
            ),
            Anomalias AS (
                -- Calcula Ritmo Médio Agregado (Soma Presc / Soma Dias) para decidir se o médico é robô no período
                SELECT 
                    id_medico,
                    MAX(CAST(flag_crm_invalido AS INT)) as flag_crm_invalido,
                    MAX(CAST(flag_prescricao_antes_registro AS INT)) as flag_prescricao_antes_registro,
                    MAX(CAST(flag_distancia_geografica AS INT)) as flag_distancia_geografica,
                    MAX(CAST(flag_concentracao_mesmo_crm AS INT)) as flag_concentracao_mesmo_crm,
                    MAX(CAST(alerta_concentracao_multiplos_crms AS INT)) as alerta_concentracao_multiplos_crms,
                    -- Média Local (Aproximada pelos dias do mês)
                    SUM(nu_prescricoes_mes) / CAST(NULLIF(SUM(
                        CASE 
                            WHEN competencia % 100 IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                            WHEN competencia % 100 IN (4, 6, 9, 11) THEN 30
                            ELSE 28 
                        END
                    ), 0) AS FLOAT) as avg_loc,
                    -- Média Brasil
                    SUM(nu_prescricoes_total_brasil) / CAST(NULLIF(SUM(
                        CASE 
                            WHEN competencia % 100 IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                            WHEN competencia % 100 IN (4, 6, 9, 11) THEN 30
                            ELSE 28 
                        END
                    ), 0) AS FLOAT) as avg_br
                FROM temp_CGUSC.fp.crm_export E
                INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = E.id_cnpj
                WHERE F.cnpj = ? AND competencia BETWEEN {comp_ini} AND {comp_fim}
                GROUP BY id_medico
            ),
            Contagens AS (
                -- Agrega os médicos identificados na CTE acima
                SELECT 
                    COUNT(DISTINCT CASE WHEN flag_crm_invalido = 1 OR flag_prescricao_antes_registro = 1 THEN id_medico END) as qtd_fraudes_crm,
                    COUNT(DISTINCT CASE WHEN avg_loc > 30 THEN id_medico END) as qtd_robos,
                    COUNT(DISTINCT CASE WHEN avg_loc <= 30 AND avg_br > 30 THEN id_medico END) as qtd_robos_rede,
                    COUNT(DISTINCT CASE WHEN flag_distancia_geografica = 1 THEN id_medico END) as qtd_alerta_geo,
                    -- APENAS Rajadas de um único CRM (igual ao Dashboard)
                    COUNT(DISTINCT CASE WHEN flag_concentracao_mesmo_crm = 1 THEN id_medico END) as qtd_tempo_concentrado
                FROM Anomalias
            )
            SELECT 
                T.*,
                R1.id_medico as id_top1_prescritor,
                R1.vl_medico as vl_top1,
                (SELECT SUM(vl_medico) FROM Ranking WHERE rk <= 5) as vl_top5,
                E.qtd_exclusivos,
                C.qtd_fraudes_crm,
                C.qtd_robos,
                C.qtd_robos_rede,
                C.qtd_alerta_geo,
                C.qtd_tempo_concentrado,
                M.razaoSocial, 
                M.municipio, 
                M.uf,
                M.populacao as populacao_cidade,
                M.total_municipio as estabelecimentos_cidade,
                -- Média BR para o card de comparação
                (SELECT AVG(mediana_concentracao_top5_br) FROM temp_CGUSC.fp.indicador_crm_bench_br) as media_concentracao_top5_br
            FROM Totais T
            LEFT JOIN Ranking R1 ON R1.rk = 1
            CROSS JOIN Exclusivos E
            CROSS JOIN Contagens C
            LEFT JOIN temp_CGUSC.fp.matriz_risco_consolidada M ON M.cnpj = ?
        ''', (cnpj, cnpj, cnpj, cnpj, cnpj))
        
        row = cursor.fetchone()
        if not row:
            return None

        cols = [column[0] for column in cursor.description]
        dados = dict(zip(cols, row))

        # Calcula as porcentagens de concentração no Python
        total_valor = float(dados.get('total_valor') or 1)
        dados['pct_concentracao_top1'] = (float(dados.get('vl_top1') or 0) / total_valor) * 100
        dados['pct_concentracao_top5'] = (float(dados.get('vl_top5') or 0) / total_valor) * 100

        return dados

    except Exception as e:
        logging.error(f"Erro ao buscar dados de prescritores para {cnpj}: {e}")
        return None


def buscar_top20_prescritores(cursor, cnpj, data_inicio=None, data_fim=None):
    """
    Busca a lista dos prescritores de interesse a partir da crm_export (v5).
    Agrega os meses para mostrar o volume total e os piores alertas do período.
    """
    try:
        # Converte datas para formato de competência (YYYYMM) de forma segura
        def to_comp(d):
            if not d: return None
            if isinstance(d, str): return int(d.replace('-', '')[:6])
            return int(d.strftime('%Y%m'))

        comp_ini = to_comp(data_inicio) or 201501
        comp_fim = to_comp(data_fim) or 203012

        # Busca e agrega por médico
        cursor.execute(f'''
            SELECT 
                E.id_medico,
                SUM(nu_prescricoes_mes) as nu_prescricoes,
                SUM(vl_total_prescricoes) as vl_total_prescricoes,
                -- MÉDIA REAL LOCAL: Total Presc / Total Dias (Simplificado)
                SUM(nu_prescricoes_mes) / CAST(NULLIF(SUM(
                    CASE 
                        WHEN competencia % 100 IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                        WHEN competencia % 100 IN (4, 6, 9, 11) THEN 30
                        ELSE 28 
                    END
                ), 0) AS FLOAT) as nu_prescricoes_dia,
                SUM(nu_prescricoes_total_brasil) as prescricoes_total_brasil,
                -- MÉDIA REAL BRASIL: Total Presc BR / Total Dias BR (Simplificado)
                SUM(nu_prescricoes_total_brasil) / CAST(NULLIF(SUM(
                    CASE 
                        WHEN competencia % 100 IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                        WHEN competencia % 100 IN (4, 6, 9, 11) THEN 30
                        ELSE 28 
                    END
                ), 0) AS FLOAT) as prescricoes_dia_total_brasil,
                MAX(nu_estabelecimentos) as qtd_estabelecimentos_atua,
                MIN(dt_primeira_prescricao) as dt_primeira_prescricao,
                MAX(dt_inscricao_crm) as dt_inscricao_crm,
                MAX(CASE WHEN M.id_medico IS NULL THEN 0 ELSE 1 END) as crm_existe_dados_medico,
                MAX(CAST(flag_crm_invalido AS INT)) as flag_crm_invalido,
                MAX(CAST(flag_prescricao_antes_registro AS INT)) as flag_prescricao_antes_registro,
                -- Flag Robô Aqui: Média do período > 30
                CASE WHEN (SUM(nu_prescricoes_mes) / CAST(NULLIF(SUM(
                    CASE 
                        WHEN competencia % 100 IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                        WHEN competencia % 100 IN (4, 6, 9, 11) THEN 30
                        ELSE 28 
                    END
                ), 0) AS FLOAT)) > 30 THEN 1 ELSE 0 END as flag_robo,
                -- Flag Robô Rede: Média BR do período > 30
                CASE WHEN (SUM(nu_prescricoes_total_brasil) / CAST(NULLIF(SUM(
                    CASE 
                        WHEN competencia % 100 IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                        WHEN competencia % 100 IN (4, 6, 9, 11) THEN 30
                        ELSE 28 
                    END
                ), 0) AS FLOAT)) > 30 THEN 1 ELSE 0 END as flag_robo_oculto,
                -- Alerta Rajada: Concentração temporal do CRM (Qualquer mês no período)
                MAX(CAST(flag_concentracao_mesmo_crm AS INT)) as alerta_concentracao_unico_crm,
                -- Flag Cross-CRM: Surto geral na farmácia
                MAX(CAST(alerta_concentracao_multiplos_crms AS INT)) as alerta_concentracao_multiplos_crms,
                MAX(CAST(flag_distancia_geografica AS INT)) as alerta_geografico
            FROM temp_CGUSC.fp.crm_export E
            INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = E.id_cnpj
            LEFT JOIN temp_CGUSC.fp.dados_medico M ON M.id_medico = E.id_medico
            WHERE F.cnpj = ? AND competencia BETWEEN {comp_ini} AND {comp_fim}
            GROUP BY E.id_medico
            ORDER BY nu_prescricoes DESC
        ''', cnpj)

        rows = cursor.fetchall()
        if not rows:
            return []

        cols = [column[0] for column in cursor.description]
        top20 = [dict(zip(cols, row)) for row in rows]

        # Calcula Ranking, Participação e Acumulado no Python
        total_vendas_cnpj = sum(float(p['nu_prescricoes']) for p in top20)
        acumulado = 0
        for i, p in enumerate(top20):
            p['ranking'] = i + 1
            p['pct_participacao'] = (float(p['nu_prescricoes']) / total_vendas_cnpj * 100) if total_vendas_cnpj > 0 else 0
            acumulado += p['pct_participacao']
            p['pct_acumulado'] = acumulado
            
            # Helper para o % Aqui vs Total Brasil
            total_br = float(p['prescricoes_total_brasil'] or 1)
            p['pct_volume_aqui_vs_total'] = (float(p['nu_prescricoes']) / total_br * 100) if total_br > 0 else 0

        return top20 # Retorna todos os prescritores encontrados

    except Exception as e:
        logging.error(f"Erro ao buscar prescritores de interesse para {cnpj}: {e}")
        return []


def _get_valor(dados, campo, default=0):
    """Helper para extrair valor de um dict, tratando None e Decimal."""
    val = dados.get(campo, default)
    if val is None:
        return default
    if isinstance(val, Decimal):
        return float(val)
    return val


def gerar_aba_prescritores(wb, cnpj, dados_prescritores, top20_prescritores, cursor=None, data_inicio=None, data_fim=None):
    """
    Gera a aba 'análise de crms' no workbook Excel.

    Args:
        wb: Workbook do xlsxwriter
        cnpj: CNPJ da farmácia (string)
        dados_prescritores: Dict com métricas consolidadas
        top20_prescritores: Lista de dicts com Top 20 prescritores
    """
    if not dados_prescritores:
        logging.warning(f"Sem dados de prescritores para {cnpj}. Aba não será gerada.")
        return

    ws = wb.add_worksheet('Análise de CRMs')
    ws.hide_gridlines(2)

    # =================================================================
    # CONSTANTES DE CRITÉRIOS
    # =================================================================
    LIMITE_ROBO_DIA = 30  # >30 prescrições/dia
    LIMITE_MULTI_FARMACIA = 20  # >20 estabelecimentos

    # =================================================================
    # DEFINIÇÃO DE CORES
    # =================================================================
    COR_AZUL_ESCURO = '#1F4E78'
    COR_CINZA_CLARO = '#F2F2F2'
    COR_VERMELHO = '#860010'
    COR_VERMELHO_BG = '#FFABB5'
    COR_AMARELO = '#FFC000'
    COR_AMARELO_BG = '#FFF2CC'

    COR_VERDE = '#548235'
    COR_VERDE_BG = '#F1F7ED'

    COR_ROXO = '#7030A0'
    COR_ROXO_BG = '#E4DFEC'

    COR_LARANJA = '#B45210'
    COR_LARANJA_BG = '#FFCA7D'

    COR_AZUL_GEO = '#2F75B5'  # Azul forte para texto
    COR_AZUL_GEO_BG = '#DDEBF7'  # Azul claro para fundo

    COR_VERMELHO_CARDS = '#860010'
    COR_VERMELHO_CARDS_BG = '#FFC9CF'

    COR_MAGENTA = '#C00060'  # Um rosa/magenta bem escuro e sério
    COR_MAGENTA_BG = '#FFB9E3'  # Fundo rosa claro

    COR_LINHA_COM_ALERTA = '#FFEBEE'  # Vermelho claro para linhas com problema
    COR_LINHA_SEM_ALERTA = '#F1F7ED'  # Verde bem claro para linhas OK

    # =================================================================
    # FORMATOS
    # =================================================================

    # Títulos
    fmt_titulo = wb.add_format({
        'bold': True, 'font_size': 18, 'font_color': COR_AZUL_ESCURO,
        'align': 'left', 'valign': 'vcenter'
    })
    fmt_subtitulo = wb.add_format({
        'font_size': 10, 'font_color': '#555555', 'align': 'left', 'valign': 'vcenter'
    })

    # Cards
    fmt_card_titulo = wb.add_format({
        'bold': True, 'font_size': 9, 'font_color': '#555555',
        'align': 'center', 'valign': 'vcenter', 'text_wrap': True
    })
    fmt_card_valor_normal = wb.add_format({
        'bold': True, 'font_size': 18, 'font_color': COR_VERDE,
        'align': 'center', 'valign': 'vcenter', 'bg_color': COR_VERDE_BG,
        'border': 1, 'border_color': COR_VERDE
    })
    fmt_card_valor_atencao = wb.add_format({
        'bold': True, 'font_size': 18, 'font_color': '#9C5700',
        'align': 'center', 'valign': 'vcenter', 'bg_color': COR_AMARELO_BG,
        'border': 1, 'border_color': COR_AMARELO
    })
    fmt_card_valor_critico = wb.add_format({
        'bold': True, 'font_size': 18, 'font_color': '#9C0006',
        'align': 'center', 'valign': 'vcenter', 'bg_color': COR_VERMELHO_CARDS_BG,
        'border': 1, 'border_color': COR_VERMELHO_CARDS
    })
    fmt_card_valor_rede = wb.add_format({
        'bold': True, 'font_size': 18, 'font_color': COR_ROXO,
        'align': 'center', 'valign': 'vcenter', 'bg_color': COR_ROXO_BG,
        'border': 1, 'border_color': COR_ROXO
    })
    fmt_card_detalhe = wb.add_format({
        'font_size': 8, 'font_color': '#777777',
        'align': 'center', 'valign': 'vcenter', 'text_wrap': True
    })

    # Seções
    fmt_secao_titulo = wb.add_format({
        'bold': True, 'font_size': 11, 'bg_color': COR_AZUL_ESCURO, 'font_color': 'white',
        'align': 'left', 'valign': 'vcenter', 'indent': 1, 'border': 1
    })

    # Tabelas
    fmt_header_tabela = wb.add_format({
        'bold': True, 'font_size': 9, 'bg_color': COR_CINZA_CLARO, 'font_color': 'black',
        'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True
    })
    fmt_header_rede = wb.add_format({
        'bold': True, 'font_size': 9, 'bg_color': COR_ROXO_BG, 'font_color': COR_ROXO,
        'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True
    })
    fmt_celula = wb.add_format({
        'font_size': 9, 'align': 'left', 'valign': 'vcenter', 'border': 1
    })
    fmt_celula_center = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1
    })
    fmt_celula_numero = wb.add_format({
        'font_size': 9, 'align': 'right', 'valign': 'vcenter', 'border': 1,
        'num_format': '#,##0'
    })
    fmt_celula_moeda = wb.add_format({
        'font_size': 9, 'align': 'right', 'valign': 'vcenter', 'border': 1,
        'num_format': 'R$ #,##0.00'
    })
    fmt_celula_pct = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': '0.00%'
    })
    fmt_celula_decimal = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': '0.00'
    })
    fmt_celula_data = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': 'DD/MM/YYYY'
    })

    # Alertas
    fmt_alerta_vermelho = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_VERMELHO_BG, 'font_color': COR_VERMELHO, 'bold': True
    })
    fmt_alerta_vermelho_data = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_VERMELHO_BG, 'font_color': COR_VERMELHO, 'bold': True,
        'num_format': 'DD/MM/YYYY'
    })
    fmt_alerta_roxo = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_ROXO_BG, 'font_color': COR_ROXO, 'bold': True
    })
    fmt_alerta_laranja = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_LARANJA_BG, 'font_color': COR_LARANJA, 'bold': True
    })

    fmt_alerta_azul_geo = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_AZUL_GEO_BG, 'font_color': COR_AZUL_GEO, 'bold': True
    })

    fmt_alerta_magenta = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_MAGENTA_BG, 'font_color': COR_MAGENTA, 'bold': True
    })

    fmt_alerta_ok = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_VERDE_BG, 'font_color': COR_VERDE
    })

    # Notas
    fmt_nota = wb.add_format({
        'font_size': 9, 'font_color': '#555555', 'italic': True, 'text_wrap': True,
        'valign': 'top', 'border': 1, 'bg_color': '#FAFAFA'
    })

    fmt_alerta_celula = wb.add_format({
        'font_size': 9, 'align': 'left', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_LINHA_COM_ALERTA
    })
    fmt_alerta_celula_center = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_LINHA_COM_ALERTA
    })
    fmt_alerta_celula_numero = wb.add_format({
        'font_size': 9, 'align': 'right', 'valign': 'vcenter', 'border': 1,
        'num_format': '#,##0', 'bg_color': COR_LINHA_COM_ALERTA
    })
    fmt_alerta_celula_moeda = wb.add_format({
        'font_size': 9, 'align': 'right', 'valign': 'vcenter', 'border': 1,
        'num_format': 'R$ #,##0.00', 'bg_color': COR_LINHA_COM_ALERTA
    })
    fmt_alerta_celula_pct = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': '0.00%', 'bg_color': COR_LINHA_COM_ALERTA
    })
    fmt_alerta_celula_decimal = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': '0.00', 'bg_color': COR_LINHA_COM_ALERTA
    })
    fmt_alerta_celula_data = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': 'DD/MM/YYYY', 'bg_color': COR_LINHA_COM_ALERTA
    })

    fmt_ok_celula = wb.add_format({
        'font_size': 9, 'align': 'left', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_LINHA_SEM_ALERTA
    })
    fmt_ok_celula_center = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'bg_color': COR_LINHA_SEM_ALERTA
    })
    fmt_ok_celula_numero = wb.add_format({
        'font_size': 9, 'align': 'right', 'valign': 'vcenter', 'border': 1,
        'num_format': '#,##0', 'bg_color': COR_LINHA_SEM_ALERTA
    })
    fmt_ok_celula_moeda = wb.add_format({
        'font_size': 9, 'align': 'right', 'valign': 'vcenter', 'border': 1,
        'num_format': 'R$ #,##0.00', 'bg_color': COR_LINHA_SEM_ALERTA
    })
    fmt_ok_celula_pct = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': '0.00%', 'bg_color': COR_LINHA_SEM_ALERTA
    })
    fmt_ok_celula_decimal = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': '0.00', 'bg_color': COR_LINHA_SEM_ALERTA
    })
    fmt_ok_celula_data = wb.add_format({
        'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        'num_format': 'DD/MM/YYYY', 'bg_color': COR_LINHA_SEM_ALERTA
    })

    # Função para formato de risco
    def get_formato_risco(valor):
        if valor >= 5:
            return wb.add_format({
                'bg_color': COR_VERMELHO_CARDS_BG, 'font_color': COR_VERMELHO_CARDS, 'bold': True,
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.00x'
            })
        elif valor >= 2:
            return wb.add_format({
                'bg_color': COR_AMARELO_BG, 'font_color': '#9C5700', 'bold': True,
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.00x'
            })
        else:
            return wb.add_format({
                'bg_color': COR_VERDE_BG, 'font_color': '#006100', 'bold': True,
                'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.00x'
            })

    # =================================================================
    # EXTRAÇÃO DE VALORES
    # =================================================================
    pct_top1 = _get_valor(dados_prescritores, 'pct_concentracao_top1')
    pct_top5 = _get_valor(dados_prescritores, 'pct_concentracao_top5')
    id_top1 = dados_prescritores.get('id_top1_prescritor', '') or ''
    # Isso garante que os cards mostrem o TOTAL da farmácia (não só do Top 20)
    qtd_fraudes_crm = int(_get_valor(dados_prescritores, 'qtd_fraudes_crm', 0))
    qtd_robos = int(_get_valor(dados_prescritores, 'qtd_robos', 0))
    qtd_robos_rede = int(_get_valor(dados_prescritores, 'qtd_robos_rede', 0))
    qtd_alerta_geo = int(_get_valor(dados_prescritores, 'qtd_alerta_geo', 0))
    qtd_tempo_concentrado = int(_get_valor(dados_prescritores, 'qtd_tempo_concentrado', 0))

    # NOVA MÉTRICA: CRMs EXCLUSIVOS (Só atuam nesta farmácia)
    # Regra: qtd_estabelecimentos_atua == 1 (Consolidado de toda a farmácia)
    qtd_exclusivos = int(_get_valor(dados_prescritores, 'qtd_exclusivos', 0))

    # Percentuais calculados sobre o total GERAL de prescritores da farmácia
    total_prescritores = int(_get_valor(dados_prescritores, 'total_prescritores_distintos', 1))
    pct_fraudes_crm = (qtd_fraudes_crm / total_prescritores) * 100 if total_prescritores > 0 else 0

    # Médias
    media_top5_br = _get_valor(dados_prescritores, 'media_concentracao_top5_br', 40)

    # =================================================================
    # CABEÇALHO
    # =================================================================
    cnpj_fmt = f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}'

    ws.write('B2', "ANÁLISE DE CRMs", fmt_titulo)
    ws.write('B3', f"{dados_prescritores.get('razaoSocial', '')} | CNPJ: {cnpj_fmt}", fmt_subtitulo)

    # CABEÇALHO DEMOGRÁFICO ENRIQUECIDO (Igual à aba Indicadores)
    mun = dados_prescritores.get('municipio', 'DESCONHECIDO')
    uf = dados_prescritores.get('uf', '')
    pop = int(dados_prescritores.get('populacao_cidade') or 0)
    total_mun = int(dados_prescritores.get('estabelecimentos_cidade') or 0)
    densidade = int(pop / total_mun) if total_mun > 0 else 0
    pop_fmt = f"{pop:,.0f}".replace(",", ".")
    
    texto_demografico = f"📍 {mun} - {uf}   |   👥 População: {pop_fmt}   |   🏥 Estabelecimentos: {total_mun}   |   📊 Densidade: {densidade} hab/farmácia"
    ws.write('B4', texto_demografico, fmt_subtitulo)

    # --- Link para Documentação ---
    fmt_link_doc = wb.add_format({
        'font_size': 9, 'font_color': 'blue', 'underline': True, 
        'align': 'left', 'valign': 'top'
    })
    ws.write_url('B5', 'https://cgu-sc.github.io/sentinela/', fmt_link_doc, string='📘 Acesse a Documentação')

    # =================================================================
    # CARDS DE RESUMO - LINHA 1 (Concentração e Anomalias)
    # =================================================================
    row_cards = 6

    # Card 1: Concentração Top 1
    ws.merge_range(row_cards, 1, row_cards, 2, "CONCENTRAÇÃO TOP 1", fmt_card_titulo)
    fmt_card = fmt_card_valor_critico if pct_top1 > 40 else (
        fmt_card_valor_atencao if pct_top1 > 20 else fmt_card_valor_normal)
    ws.merge_range(row_cards + 1, 1, row_cards + 2, 2, f"{pct_top1:.1f}%", fmt_card)
    ws.merge_range(row_cards + 3, 1, row_cards + 3, 2, f"CRM: {id_top1}", fmt_card_detalhe)

    # Card 2: Concentração Top 5
    ws.merge_range(row_cards, 3, row_cards, 4, "CONCENTRAÇÃO TOP 5", fmt_card_titulo)
    fmt_card = fmt_card_valor_critico if pct_top5 > 70 else (
        fmt_card_valor_atencao if pct_top5 > 50 else fmt_card_valor_normal)
    ws.merge_range(row_cards + 1, 3, row_cards + 2, 4, f"{pct_top5:.1f}%", fmt_card)
    ws.merge_range(row_cards + 3, 3, row_cards + 3, 4, f"Média BR: {media_top5_br:.1f}%", fmt_card_detalhe)

    # Card 3: >30/dia Aqui
    ws.merge_range(row_cards, 5, row_cards, 6, ">30/DIA AQUI", fmt_card_titulo)
    fmt_card = fmt_card_valor_critico if qtd_robos > 0 else fmt_card_valor_normal
    ws.merge_range(row_cards + 1, 5, row_cards + 2, 6, str(qtd_robos), fmt_card)
    ws.merge_range(row_cards + 3, 5, row_cards + 3, 6, "Nesta farmácia", fmt_card_detalhe)

    # Card 4: >30/dia Rede
    ws.merge_range(row_cards, 7, row_cards, 8, ">30/DIA REDE", fmt_card_titulo)
    fmt_card = fmt_card_valor_critico if qtd_robos_rede > 0 else fmt_card_valor_normal
    ws.merge_range(row_cards + 1, 7, row_cards + 2, 8, str(qtd_robos_rede), fmt_card)
    ws.merge_range(row_cards + 3, 7, row_cards + 3, 8, "Em Todos os Estabelecimentos", fmt_card_detalhe)

    # Card 5: Fraudes CRM
    ws.merge_range(row_cards, 9, row_cards, 10, "FRAUDES CRM", fmt_card_titulo)
    fmt_card = fmt_card_valor_critico if qtd_fraudes_crm > 0 else fmt_card_valor_normal
    ws.merge_range(row_cards + 1, 9, row_cards + 2, 10, f"{qtd_fraudes_crm}", fmt_card)
    ws.merge_range(row_cards + 3, 9, row_cards + 3, 10, f"({pct_fraudes_crm:.1f}% do total)", fmt_card_detalhe)

    # Card 6: CRMs EXCLUSIVOS (NOVO - Substituiu Alerta >400km que foi para baixo)
    ws.merge_range(row_cards, 11, row_cards, 12, "CRMs EXCLUSIVOS", fmt_card_titulo)
    fmt_card = fmt_card_valor_atencao if qtd_exclusivos > 0 else fmt_card_valor_normal
    ws.merge_range(row_cards + 1, 11, row_cards + 2, 12, str(qtd_exclusivos), fmt_card)
    ws.merge_range(row_cards + 3, 11, row_cards + 3, 12, "Atuação única nesta farmácia", fmt_card_detalhe)

    # =================================================================
    # CARDS DE RESUMO - LINHA 2
    # =================================================================
    row_cards2 = row_cards + 5

    # Card 7: Presc. Concentradas (Movido para Linha 2)
    ws.merge_range(row_cards2, 1, row_cards2, 2, "PRESC. CONCENTRADAS", fmt_card_titulo)
    fmt_card_tempo = wb.add_format({
        'bold': True, 'font_size': 18, 'font_color': COR_LARANJA,
        'align': 'center', 'valign': 'vcenter', 'bg_color': COR_LARANJA_BG,
        'border': 1, 'border_color': COR_LARANJA
    })
    fmt_card = fmt_card_tempo if qtd_tempo_concentrado > 0 else fmt_card_valor_normal
    ws.merge_range(row_cards2 + 1, 1, row_cards2 + 2, 2, str(qtd_tempo_concentrado), fmt_card)
    ws.merge_range(row_cards2 + 3, 1, row_cards2 + 3, 2, "Presc. em curto período", fmt_card_detalhe)

    # Card 8: Alerta >400km (Movido para Linha 2)
    ws.merge_range(row_cards2, 3, row_cards2, 4, "ALERTA >400KM", fmt_card_titulo)
    fmt_card = fmt_card_valor_critico if qtd_alerta_geo > 0 else fmt_card_valor_normal
    ws.merge_range(row_cards2 + 1, 3, row_cards2 + 2, 4, str(qtd_alerta_geo), fmt_card)
    ws.merge_range(row_cards2 + 3, 3, row_cards2 + 3, 4, "Atividade distante", fmt_card_detalhe)

    # =================================================================
    # TABELA CRMs DE INTERESSE
    # =================================================================
    row_top = row_cards2 + 6
    ws.merge_range(row_top, 1, row_top, 19, "DETALHAMENTO DE TODOS OS PRESCRITORES (CRMs)", fmt_secao_titulo)
    row_top += 1

    # Header - Colunas básicas
    headers_top = [
        "#", "CRM/UF", "1ª Prescrição", "Data Reg. CRM", "Prescrições", "Valor (R$)", "% Part.", "% Acum.", "Presc/Dia"
    ]
    # Header - Colunas de rede (destacadas)
    headers_rede = [
        "Presc. Total BR", "Presc/Dia BR", "% Aqui"
    ]
    # Header - Flags
    # ADICIONADO "Exclusivo?"
    headers_flags = [
        ">30 Aqui?", ">30 Rede?", "Tempo Conc.", "Exclusivo?", "> 400km"
    ]

    col = 1
    for h in headers_top:
        ws.write(row_top, col, h, fmt_header_tabela)
        col += 1
    for h in headers_rede:
        ws.write(row_top, col, h, fmt_header_rede)
        col += 1
    for h in headers_flags:
        ws.write(row_top, col, h, fmt_header_tabela)
        col += 1

    ws.set_row(row_top, 30)
    row_top += 1

    # Dados
    if top20_prescritores:
        for presc in top20_prescritores:
            ranking = int(_get_valor(presc, 'ranking'))
            id_medico = presc.get('id_medico', '') or ''
            nu_prescricoes = int(_get_valor(presc, 'nu_prescricoes'))
            vl_total = _get_valor(presc, 'vl_total_prescricoes')
            pct_part = _get_valor(presc, 'pct_participacao') / 100
            pct_acum = _get_valor(presc, 'pct_acumulado') / 100
            presc_dia = _get_valor(presc, 'nu_prescricoes_dia')

            # Dados de rede
            presc_total_br = int(_get_valor(presc, 'prescricoes_total_brasil'))
            presc_dia_br = _get_valor(presc, 'prescricoes_dia_total_brasil')
            qtd_estabelecimentos = int(_get_valor(presc, 'qtd_estabelecimentos_atua'))
            pct_aqui_vs_total = _get_valor(presc, 'pct_volume_aqui_vs_total') / 100 if _get_valor(presc,
                                                                                                  'pct_volume_aqui_vs_total') else 0

            # LÓGICA DE EXCLUSIVIDADE
            is_exclusivo = (_get_valor(presc, 'qtd_estabelecimentos_atua') == 1)

            # Flags
            flag_robo = int(_get_valor(presc, 'flag_robo'))
            flag_robo_rede = int(_get_valor(presc, 'flag_robo_oculto'))
            flag_crm_inv = int(_get_valor(presc, 'flag_crm_invalido'))

            dt_primeira_prescricao = presc.get('dt_primeira_prescricao', None)

            dt_inscricao_crm = presc.get('dt_inscricao_crm', None)
            crm_existe_dados_medico = int(_get_valor(presc, 'crm_existe_dados_medico'))

            alerta1 = presc.get('alerta1_crm_invalido', '') or presc.get('alerta1', '') or ''
            alerta2 = presc.get('alerta_concentracao_unico_crm', '') or ''
            alerta3 = presc.get('alerta3_robo_estabelecimento', '') or presc.get('alerta3', '') or ''
            alerta4 = presc.get('alerta4_robo_rede', '') or presc.get('alerta4', '') or ''
            alerta_geo = presc.get('alerta5_geografico', '') or presc.get('alerta_geografico', '') or presc.get(
                'alerta5', '') or ''

            flag_prescricao_antes_registro = int(_get_valor(presc, 'flag_prescricao_antes_registro'))
            alerta6 = presc.get('alerta6_prescricao_antes_registro', '') or ''

            tem_alerta_linha = (
                    flag_crm_inv == 1 or
                    flag_robo == 1 or
                    flag_robo_rede == 1 or
                    flag_prescricao_antes_registro == 1 or
                    alerta2 or
                    alerta_geo or
                    is_exclusivo or
                    not dt_inscricao_crm
            )

            if tem_alerta_linha:
                f_celula = fmt_alerta_celula
                f_celula_center = fmt_alerta_celula_center
                f_celula_numero = fmt_alerta_celula_numero
                f_celula_moeda = fmt_alerta_celula_moeda
                f_celula_pct = fmt_alerta_celula_pct
                f_celula_decimal = fmt_alerta_celula_decimal
                f_celula_data = fmt_alerta_celula_data
            else:
                f_celula = fmt_ok_celula
                f_celula_center = fmt_ok_celula_center
                f_celula_numero = fmt_ok_celula_numero
                f_celula_moeda = fmt_ok_celula_moeda
                f_celula_pct = fmt_ok_celula_pct
                f_celula_decimal = fmt_ok_celula_decimal
                f_celula_data = fmt_ok_celula_data

            col = 1

            # Colunas básicas
            ws.write(row_top, col, ranking, f_celula_center);
            col += 1
            ws.write(row_top, col, id_medico, f_celula);
            col += 1

            if dt_primeira_prescricao:
                ws.write(row_top, col, dt_primeira_prescricao, f_celula_data)
            else:
                ws.write(row_top, col, "-", f_celula_center)
            col += 1

            if dt_inscricao_crm:
                # Converte ambas as datas para date() para comparação segura
                try:
                    data_inscricao = dt_inscricao_crm.date() if hasattr(dt_inscricao_crm, 'date') else dt_inscricao_crm
                    data_primeira = dt_primeira_prescricao.date() if hasattr(dt_primeira_prescricao,
                                                                             'date') else dt_primeira_prescricao

                    # Isso significa que o médico prescreveu ANTES de ter CRM registrado = PROBLEMA!
                    if dt_primeira_prescricao and data_inscricao > data_primeira:
                        # Usa formato vermelho COM formato de data (célula com problema)
                        ws.write(row_top, col, dt_inscricao_crm, fmt_alerta_vermelho_data)
                    else:
                        ws.write(row_top, col, dt_inscricao_crm, f_celula_data)
                except (AttributeError, TypeError):
                    # Se houver erro na conversão, exibe normalmente
                    ws.write(row_top, col, dt_inscricao_crm, f_celula_data)
            else:
                texto_sem_registro = "Sem data registro" if crm_existe_dados_medico else "Não localizado"
                ws.write(row_top, col, texto_sem_registro, fmt_alerta_vermelho)
            col += 1

            ws.write(row_top, col, nu_prescricoes, f_celula_numero);
            col += 1
            ws.write(row_top, col, vl_total, f_celula_moeda);
            col += 1
            ws.write(row_top, col, pct_part, f_celula_pct);
            col += 1
            ws.write(row_top, col, pct_acum, f_celula_pct);
            col += 1

            if presc_dia > LIMITE_ROBO_DIA:
                ws.write(row_top, col, presc_dia, fmt_alerta_vermelho)
            elif presc_dia > 20:
                ws.write(row_top, col, presc_dia, fmt_alerta_laranja)
            else:
                ws.write(row_top, col, presc_dia, f_celula_decimal)
            col += 1

            # Colunas de rede
            ws.write(row_top, col, presc_total_br, f_celula_numero);
            col += 1

            # Presc/Dia BR (destacar se alto - célula com problema)
            if presc_dia_br > LIMITE_ROBO_DIA:
                ws.write(row_top, col, presc_dia_br, fmt_alerta_vermelho)

            else:
                ws.write(row_top, col, presc_dia_br, f_celula_decimal)
            col += 1

            ws.write(row_top, col, pct_aqui_vs_total, f_celula_pct);
            col += 1

            # Flags
            if flag_robo == 1:
                ws.write(row_top, col, "SIM", fmt_alerta_magenta)
            else:
                ws.write(row_top, col, "-", f_celula_center)
            col += 1

            if flag_robo_rede == 1:
                ws.write(row_top, col, "SIM", fmt_alerta_roxo)
            else:
                ws.write(row_top, col, "-", f_celula_center)
            col += 1

            if alerta2:
                ws.write(row_top, col, "SIM", fmt_alerta_laranja)
            else:
                ws.write(row_top, col, "-", f_celula_center)
            col += 1

            # NOVO: EXCLUSIVO?
            if is_exclusivo:
                ws.write(row_top, col, "SIM", fmt_alerta_laranja)
            else:
                ws.write(row_top, col, "-", f_celula_center)
            col += 1

            # Detalhe Geo (alerta5 - célula com problema se presente)
            if alerta_geo:
                ws.write(row_top, col, "SIM", fmt_alerta_azul_geo)
            else:
                ws.write(row_top, col, "-", f_celula_center)

            row_top += 1
    else:
        ws.merge_range(row_top, 1, row_top, 18, "Nenhum prescritor encontrado para este CNPJ.", fmt_celula)
        row_top += 1

    # =================================================================
    # SEÇÃO DE EVIDÊNCIAS (DETALHAMENTO TEXTUAL)
    # =================================================================
    # row_top já está no final da tabela, pois foi incrementado no loop
    row_evidencias = row_top + 3 
    ws.merge_range(row_evidencias, 1, row_evidencias, 19, "⚠️ DETALHAMENTO DE EVIDÊNCIAS DOS ALERTAS", fmt_secao_titulo)
    row_evidencias += 2

    # --- 1. EVIDÊNCIAS DE DISTÂNCIA GEOGRÁFICA ---
    if cursor:
        try:
            def to_comp_geo(d):
                if not d: return None
                if isinstance(d, str): return int(d.replace('-', '')[:6])
                return int(d.strftime('%Y%m'))

            comp_ini_geo = to_comp_geo(data_inicio) or 201501
            comp_fim_geo = to_comp_geo(data_fim) or 203012

            cursor.execute(f"""
                SELECT TOP 20
                    G.id_medico,
                    G.competencia,
                    G.cnpj_a,
                    G.no_municipio_a,
                    G.sg_uf_a,
                    G.nu_prescricoes_a,
                    G.cnpj_b,
                    G.no_municipio_b,
                    G.sg_uf_b,
                    G.nu_prescricoes_b,
                    G.distancia_km,
                    G.total_pares
                FROM temp_CGUSC.fp.alertas_crm_geografico G
                INNER JOIN temp_CGUSC.fp.dados_farmacia F
                    ON F.cnpj = G.cnpj_a OR F.cnpj = G.cnpj_b
                WHERE F.cnpj = ?
                  AND G.competencia BETWEEN {comp_ini_geo} AND {comp_fim_geo}
                ORDER BY G.distancia_km DESC, G.total_pares DESC, G.competencia DESC
            """, cnpj)

            evidencias_geo = cursor.fetchall()
            if evidencias_geo:
                ws.merge_range(row_evidencias, 1, row_evidencias, 19, "📍 DISTÂNCIA GEOGRÁFICA (>400KM)", wb.add_format({'bold': True, 'font_color': '#8b5cf6', 'font_size': 11}))
                row_evidencias += 1
                for geo in evidencias_geo:
                    txt = (
                        f"CRM {geo[0]} em {geo[1]}: "
                        f"{geo[3]}/{geo[4]} ({geo[5]} prescrições, CNPJ {geo[2]}) x "
                        f"{geo[7]}/{geo[8]} ({geo[9]} prescrições, CNPJ {geo[6]}), "
                        f"distância {float(geo[10] or 0):,.0f} km; {geo[11]} par(es) distante(s) no mês."
                    )
                    ws.merge_range(row_evidencias, 1, row_evidencias + 1, 19, f"• {txt}", wb.add_format({'text_wrap': True, 'valign': 'top', 'font_size': 9, 'italic': True}))
                    row_evidencias += 2
                row_evidencias += 1
        except Exception as e:
            logging.error(f"Erro ao buscar evidências geográficas para {cnpj}: {e}")

    # --- 2. EVIDÊNCIAS DE RAJADAS (CONCENTRAÇÃO MESMO CRM) ---
    if cursor:
        try:
            # Função auxiliar para extrair YYYYMM de string 'YYYY-MM-DD' ou objeto date
            def to_comp(d):
                if not d: return None
                if isinstance(d, str): return int(d.replace('-', '')[:6])
                return int(d.strftime('%Y%m'))

            comp_ini = to_comp(data_inicio) or 201501
            comp_fim = to_comp(data_fim) or 203012

            # Busca todas as rajadas detalhadas no período (lista completa)
            cursor.execute(f"""
                SELECT TOP 50
                       A.id_medico,
                       A.dt_dia,
                       A.nu_autorizacoes_pior_ritmo,
                       A.janela_pior_ritmo_minutos,
                       CAST(A.taxa_hora_pior_ritmo AS FLOAT) AS taxa_hora_pior_ritmo,
                       A.criterio_pior_ritmo
                FROM temp_CGUSC.fp.crm_concentracao_unico_alertas A
                INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = A.id_cnpj
                WHERE F.cnpj = ?
                  AND A.dt_dia BETWEEN ? AND ?
                  AND A.taxa_hora_pior_ritmo IS NOT NULL
                ORDER BY
                    A.taxa_hora_pior_ritmo DESC,
                    A.nu_autorizacoes_pior_ritmo DESC,
                    A.janela_pior_ritmo_minutos ASC,
                    A.dt_dia DESC
            """, (cnpj, data_inicio, data_fim))
            
            rajadas = cursor.fetchall()
            logging.info(f"[CRM] CNPJ {cnpj}: {len(rajadas)} rajadas de concentração única encontradas para o Excel.")
            if rajadas:
                ws.merge_range(row_evidencias, 1, row_evidencias, 19, "⏱️ LANÇAMENTOS SEQUENCIAIS (MESMO CRM)", wb.add_format({'bold': True, 'font_color': COR_LARANJA, 'font_size': 11}))
                row_evidencias += 1
                for r in rajadas:
                    dt_f = r[1].strftime('%d/%m/%Y') if hasattr(r[1], 'strftime') else str(r[1])
                    txt = f"Médico {r[0]} em {dt_f}: {r[2]} prescrições em uma janela de {r[3]} minutos (Ritmo: {r[4]:.1f}/hora)."
                    ws.merge_range(row_evidencias, 1, row_evidencias, 19, f"• {txt}", wb.add_format({'font_size': 9, 'font_color': '#555555'}))
                    row_evidencias += 1
                row_evidencias += 1

            # --- 3. EVIDÊNCIAS DE RAJADAS (MÚLTIPLOS CRMS) ---
            cursor.execute(f"""
                SELECT TOP 50
                       A.dt_ini_concentracao,
                       A.nu_crms_distintos,
                       A.nu_autorizacoes_pior_ritmo,
                       A.janela_pior_ritmo_minutos,
                       CAST(A.taxa_hora_pior_ritmo AS FLOAT) AS taxa_hora_pior_ritmo,
                       A.criterio_pior_ritmo
                FROM temp_CGUSC.fp.crm_concentracao_multiplo_alertas A
                INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = A.id_cnpj
                WHERE F.cnpj = ?
                  AND A.dt_dia BETWEEN ? AND ?
                  AND A.taxa_hora_pior_ritmo IS NOT NULL
                ORDER BY
                    A.taxa_hora_pior_ritmo DESC,
                    A.nu_autorizacoes_pior_ritmo DESC,
                    A.janela_pior_ritmo_minutos ASC,
                    A.dt_dia DESC
            """, (cnpj, data_inicio, data_fim))
            
            surtos = cursor.fetchall()
            if surtos:
                ws.merge_range(row_evidencias, 1, row_evidencias, 19, "⏱️ LANÇAMENTOS SEQUENCIAIS (MULTIPLOS CRMS)", wb.add_format({'bold': True, 'font_color': '#D97706', 'font_size': 11}))
                row_evidencias += 1
                for s in surtos:
                    dt_f = s[0].strftime('%d/%m/%Y') if hasattr(s[0], 'strftime') else str(s[0])
                    hr_f = s[0].strftime('%H:%M') if hasattr(s[0], 'strftime') else str(s[0])
                    txt = f"Em {dt_f} às {hr_f}: {s[2]} prescrições de {s[1]} CRMs em uma janela de {s[3]} minutos (Ritmo: {s[4]:.1f}/hora)."
                    ws.merge_range(row_evidencias, 1, row_evidencias, 19, f"• {txt}", wb.add_format({'font_size': 9, 'font_color': '#555555'}))
                    row_evidencias += 1
        except Exception as e:
            logging.error(f"Erro ao buscar evidências detalhadas para {cnpj}: {e}")
            pass

    # Ajuste final de colunas para legibilidade
    ws.set_column('A:A', 2)   # Margem
    ws.set_column('B:B', 6)   # Rank
    ws.set_column('C:C', 18)  # CRM
    ws.set_column('D:E', 15)  # Datas
    ws.set_column('F:G', 12)  # Presc/Valor
    ws.set_column('H:I', 10)  # Part/Acum
    ws.set_column('J:L', 10)  # Presc/Dia e BR
    ws.set_column('M:M', 8)   # % Aqui
    ws.set_column('N:T', 15)  # Flags e Alertas

    ws.freeze_panes(6, 0)
    logging.info(f"Aba 'Análise de CRMs' v5.0 gerada com sucesso para CNPJ {cnpj}")

