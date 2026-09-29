-- ============================================================================
-- TEMPORARIO - FINALIZA A RETOMADA DO PRE-GLOBAL CRM
-- ============================================================================
-- Executar uma vez, depois que crms_etapa1b_retomar_por_ano.sql terminar
-- (loop de 2015 a 2024, todos os anos gravados).
--
-- Confere as 11 tabelas da etapa 1 que a etapa 6 promove juntas: todos os
-- meses nas mensais, anuais com os mesmos anos e totais das mensais, dimensao
-- de medicos e farmacia x medico x ano, limiar P95 de todos os meses e tabelas
-- do mapa. Se tudo bater, marca a metadata da etapa 1 como OK (exigido pela
-- etapa 6). Nao processa dados.
--
-- Depois de concluir: seguir com as etapas 2 a 6. Excluir este arquivo e
-- crms_etapa1b_retomar_por_ano.sql quando a etapa 1 voltar a ser executada
-- inteira.
-- ============================================================================

SET NOCOUNT ON;
SET XACT_ABORT ON;

-- Devem ser iguais aos de crms_etapa1b_retomar_por_ano.sql.
DECLARE @DataInicio DATE = '2015-07-01';
DECLARE @DataFim    DATE = '2024-12-31';

DECLARE @CompIni INT = YEAR(@DataInicio) * 100 + MONTH(@DataInicio);
DECLARE @CompFim INT = YEAR(@DataFim) * 100 + MONTH(@DataFim);
DECLARE @Mes DATE;
DECLARE @Faltando NVARCHAR(2000);

BEGIN TRY

PRINT '>> [RETOMADA PRE-GLOBAL CRM] Finalizando...';

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_dados_medico') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_estabelecimento_mes') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_limiar_p95_mes') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_mes') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_territorio_mes') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_ano') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_territorio_ano') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_dim') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_farmacia_medico_ano') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_mapa_uf_periodo') IS NULL
    THROW 51100, 'Falta alguma tabela da etapa 1 (com nome build_). Rode crms_etapa1b_retomar_por_ano.sql antes.', 1;

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
    WHERE id_pipeline = 1
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
)
    THROW 51101, 'Periodo diferente do periodo da execucao interrompida (metadata).', 1;

-- ---------------------------------------------------------------------------
-- Todos os meses do periodo gravados nas duas tabelas (e em cada nivel)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS #meses_esperados;
CREATE TABLE #meses_esperados (competencia INT NOT NULL PRIMARY KEY);

SET @Mes = DATEFROMPARTS(YEAR(@DataInicio), MONTH(@DataInicio), 1);
WHILE @Mes <= @DataFim
BEGIN
    INSERT INTO #meses_esperados VALUES (YEAR(@Mes) * 100 + MONTH(@Mes));
    SET @Mes = DATEADD(MONTH, 1, @Mes);
END;

DROP TABLE IF EXISTS #meses_gravados;

-- VARCHAR(16): o literal sozinho criaria VARCHAR(6) e truncaria 'municipio'.
SELECT DISTINCT CAST('brasil' AS VARCHAR(16)) AS nivel, competencia
INTO #meses_gravados
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes;

INSERT INTO #meses_gravados (nivel, competencia)
SELECT DISTINCT nivel, competencia
FROM temp_CGUSC.fp.build_crm_medico_territorio_mes;

IF EXISTS (
    SELECT 1 FROM #meses_gravados
    WHERE nivel NOT IN ('brasil', 'municipio', 'regiao_saude', 'uf')
       OR competencia NOT BETWEEN @CompIni AND @CompFim
)
    THROW 51108, 'Tabelas finais com nivel invalido ou mes fora do periodo.', 1;

SELECT @Faltando = STRING_AGG(CAST(X.falta AS NVARCHAR(40)), ', ')
FROM (
    SELECT TOP (40) CONCAT(N.nivel, ' ', E.competencia) AS falta
    FROM #meses_esperados E
    CROSS JOIN (VALUES ('brasil'), ('municipio'), ('regiao_saude'), ('uf')) N(nivel)
    WHERE NOT EXISTS (
        SELECT 1 FROM #meses_gravados G
        WHERE G.nivel = N.nivel AND G.competencia = E.competencia
    )
    ORDER BY E.competencia, N.nivel
) X;

IF @Faltando IS NOT NULL
BEGIN
    SET @Faltando = LEFT(N'Meses faltando (rode os anos correspondentes): ' + @Faltando, 2000);
    THROW 51109, @Faltando, 1;
END;

DROP TABLE #meses_gravados;

-- Limiar P95: um por mes do periodo, sem lacunas nem meses a mais, com valor valido.
IF EXISTS (
    SELECT 1
    FROM #meses_esperados E
    FULL JOIN temp_CGUSC.fp.build_crm_limiar_p95_mes L
        ON L.competencia = E.competencia
    WHERE E.competencia IS NULL
       OR L.competencia IS NULL
       OR L.p95_taxa_dia IS NULL
       OR L.p95_taxa_dia < 1
)
    THROW 51115, 'build_crm_limiar_p95_mes nao tem exatamente um P95 valido para cada mes do periodo.', 1;

IF EXISTS (
    SELECT competencia
    FROM temp_CGUSC.fp.build_crm_limiar_p95_mes
    GROUP BY competencia
    HAVING COUNT_BIG(*) > 1
)
    THROW 51115, 'build_crm_limiar_p95_mes com mes repetido.', 1;

DROP TABLE #meses_esperados;

-- ---------------------------------------------------------------------------
-- Tabelas anuais: mesmos anos e mesmos totais das mensais, em cada nivel
-- (prescricoes, dias com prescricao e meses ativos = linhas mensais).
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS #totais_mes;
DROP TABLE IF EXISTS #totais_ano;

SELECT
    CAST('brasil' AS VARCHAR(16)) AS nivel,
    competencia / 100 AS ano,
    SUM(CAST(nu_prescricoes_mes AS BIGINT)) AS nu_prescricoes,
    SUM(CAST(qtd_dias_com_prescricao_mes AS BIGINT)) AS qtd_dias,
    COUNT_BIG(*) AS qtd_meses
INTO #totais_mes
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes
GROUP BY competencia / 100;

INSERT INTO #totais_mes (nivel, ano, nu_prescricoes, qtd_dias, qtd_meses)
SELECT
    nivel,
    competencia / 100,
    SUM(CAST(nu_prescricoes_mes AS BIGINT)),
    SUM(CAST(qtd_dias_com_prescricao_mes AS BIGINT)),
    COUNT_BIG(*)
FROM temp_CGUSC.fp.build_crm_medico_territorio_mes
GROUP BY nivel, competencia / 100;

SELECT
    CAST('brasil' AS VARCHAR(16)) AS nivel,
    CAST(ano AS INT) AS ano,
    SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes,
    SUM(CAST(qtd_dias_com_prescricao AS BIGINT)) AS qtd_dias,
    SUM(CAST(qtd_meses_ativos AS BIGINT)) AS qtd_meses
INTO #totais_ano
FROM temp_CGUSC.fp.build_crm_medico_brasil_ano
GROUP BY ano;

INSERT INTO #totais_ano (nivel, ano, nu_prescricoes, qtd_dias, qtd_meses)
SELECT
    nivel,
    ano,
    SUM(CAST(nu_prescricoes AS BIGINT)),
    SUM(CAST(qtd_dias_com_prescricao AS BIGINT)),
    SUM(CAST(qtd_meses_ativos AS BIGINT))
FROM temp_CGUSC.fp.build_crm_medico_territorio_ano
GROUP BY nivel, ano;

IF EXISTS (
    SELECT 1
    FROM #totais_mes M
    FULL JOIN #totais_ano A
        ON A.nivel = M.nivel
       AND A.ano = M.ano
    WHERE M.ano IS NULL
       OR A.ano IS NULL
       OR M.nu_prescricoes <> A.nu_prescricoes
       OR M.qtd_dias <> A.qtd_dias
       OR M.qtd_meses <> A.qtd_meses
)
    THROW 51112, 'Tabelas anuais (build_crm_medico_*_ano) divergem das mensais em anos ou totais.', 1;

DROP TABLE #totais_mes;
DROP TABLE #totais_ano;

-- ---------------------------------------------------------------------------
-- Dimensao de medicos: codigos 0..N-1 sem lacunas e todo medico com codigo.
-- Farmacia x medico x ano: mesmos anos e mesmo total de prescricoes do Brasil.
-- ---------------------------------------------------------------------------
IF (SELECT COUNT_BIG(*) FROM temp_CGUSC.fp.build_crm_medico_dim)
       <> (SELECT ISNULL(MAX(CAST(id_medico_num AS BIGINT)), -1) + 1 FROM temp_CGUSC.fp.build_crm_medico_dim)
   OR (SELECT MIN(id_medico_num) FROM temp_CGUSC.fp.build_crm_medico_dim) <> 0
   OR EXISTS (
        SELECT 1
        FROM (SELECT DISTINCT id_medico FROM temp_CGUSC.fp.build_crm_medico_brasil_ano) B
        WHERE NOT EXISTS (
            SELECT 1 FROM temp_CGUSC.fp.build_crm_medico_dim D WHERE D.id_medico = B.id_medico
        )
   )
    THROW 51113, 'Dimensao de medicos com lacunas nos codigos ou sem algum medico do ranking.', 1;

IF EXISTS (
    SELECT 1
    FROM (
        SELECT ano, SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes
        FROM temp_CGUSC.fp.build_crm_medico_brasil_ano
        GROUP BY ano
    ) B
    FULL JOIN (
        SELECT ano, SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes
        FROM temp_CGUSC.fp.build_crm_farmacia_medico_ano
        GROUP BY ano
    ) F
        ON F.ano = B.ano
    WHERE B.ano IS NULL
       OR F.ano IS NULL
       OR B.nu_prescricoes <> F.nu_prescricoes
)
    THROW 51114, 'Farmacia x medico x ano diverge do total anual de prescricoes do Brasil.', 1;

-- ---------------------------------------------------------------------------
-- Tabelas do mapa (verificacao final da etapa 1, que o reinicio impediu)
-- ---------------------------------------------------------------------------
IF (SELECT MIN(competencia_inicio) FROM temp_CGUSC.fp.build_crm_mapa_uf_periodo) <> @CompIni
   OR (SELECT MAX(competencia_fim) FROM temp_CGUSC.fp.build_crm_mapa_uf_periodo) <> @CompFim
   OR (SELECT MIN(competencia_inicio) FROM temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo) <> @CompIni
   OR (SELECT MAX(competencia_fim) FROM temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo) <> @CompFim
    THROW 51103, 'Tabelas do mapa nao cobrem o periodo completo.', 1;

IF EXISTS (
    SELECT 1 FROM temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo
    WHERE qtd_medicos_alta_intensidade < 0
       OR qtd_medicos_alta_intensidade > qtd_medicos_ativos
)
    THROW 51016, 'Contagens incoerentes na tabela de municipio/regiao do mapa CRM.', 1;

IF EXISTS (
    SELECT 1 FROM temp_CGUSC.fp.build_crm_mapa_uf_periodo
    WHERE qtd_medicos_alta_intensidade < 0
       OR qtd_medicos_alta_intensidade > qtd_medicos_ativos
)
    THROW 51017, 'Contagens incoerentes na tabela de UF/Brasil do mapa CRM.', 1;

-- Remove as tabelas descontinuadas, se existirem de execucoes antigas.
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_medico_municipio_mes;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos;

UPDATE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
SET status = 'OK',
    dt_atualizacao = GETDATE(),
    observacao = 'Pre-global finalizado com sucesso (retomada por ano das tabelas medico/mes).'
WHERE id_pipeline = 1;

PRINT '==========================================================';
PRINT '   RETOMADA FINALIZADA. Siga com as etapas 2 a 6.';
PRINT '==========================================================';

SELECT 'build_crm_medico_brasil_mes' AS tabela, COUNT_BIG(*) AS linhas,
       MIN(competencia) AS primeiro_periodo, MAX(competencia) AS ultimo_periodo
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes
UNION ALL
SELECT 'build_crm_medico_territorio_mes', COUNT_BIG(*), MIN(competencia), MAX(competencia)
FROM temp_CGUSC.fp.build_crm_medico_territorio_mes
UNION ALL
SELECT 'build_crm_medico_brasil_ano', COUNT_BIG(*), MIN(ano), MAX(ano)
FROM temp_CGUSC.fp.build_crm_medico_brasil_ano
UNION ALL
SELECT 'build_crm_medico_territorio_ano', COUNT_BIG(*), MIN(ano), MAX(ano)
FROM temp_CGUSC.fp.build_crm_medico_territorio_ano
UNION ALL
SELECT 'build_crm_farmacia_medico_ano', COUNT_BIG(*), MIN(ano), MAX(ano)
FROM temp_CGUSC.fp.build_crm_farmacia_medico_ano
UNION ALL
SELECT 'build_crm_medico_dim', COUNT_BIG(*), MIN(id_medico_num), MAX(id_medico_num)
FROM temp_CGUSC.fp.build_crm_medico_dim;

END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    DECLARE @mensagem_erro NVARCHAR(4000) = CONCAT(
        'Erro ', ERROR_NUMBER(),
        ' | Linha ', ERROR_LINE(),
        ' | ', ERROR_MESSAGE()
    );

    PRINT '   ERRO ao finalizar a retomada do pre-global CRM (metadata nao foi marcada como OK).';
    PRINT '   ' + @mensagem_erro;
    THROW;
END CATCH;
