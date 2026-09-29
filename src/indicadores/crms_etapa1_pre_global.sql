-- ============================================================================
-- PRE-PROCESSAMENTO GLOBAL PARA INDICADOR DE CRMs
-- ============================================================================
-- Este script prepara tabelas globais reutilizaveis pelo fluxo loteado do
-- crms_detalhado_test.sql.
--
-- Saidas persistentes:
--   0. temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
--      Metadados de versao, periodo e status consumidos pelo script loteado.
--
--   1. temp_CGUSC.fp.build_dados_medico
--      Mapa CFM normalizado por id_medico.
--
--   2. temp_CGUSC.fp.build_crm_medico_estabelecimento_mes
--      Relacao completa por (id_cnpj, id_medico, competencia), com o total
--      mensal de prescricoes e de dias com prescricao no estabelecimento.
--
--   3. temp_CGUSC.fp.build_crm_medico_territorio_mes
--      Prescricoes e dias distintos com prescricao por (nivel, territorio,
--      id_medico, competencia) para municipio, regiao de saude e UF. Base do
--      ranking de medicos com filtro geografico.
--
--   4. temp_CGUSC.fp.build_crm_medico_brasil_mes
--      Totais nacionais, dias distintos com prescricao e quantidade de
--      farmacias por (id_medico, competencia). Usada pelo ranking nacional de
--      medicos e pelas etapas 4 e 5 (substitui a antiga
--      build_crm_prescricoes_todos_estabelecimentos).
--
--   5. temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo
--      Contagens de medicos distintos (ativos e de alta intensidade) por
--      municipio e regiao de saude para todos os intervalos.
--      IDs de medicos ficam somente em temporarias.
--
--   6. temp_CGUSC.fp.build_crm_mapa_uf_periodo
--      As mesmas contagens por UF e Brasil para o mapa nacional.
--
--   7. temp_CGUSC.fp.build_crm_limiar_p95_mes
--      Limiar mensal de alta intensidade (P95 nacional da taxa por dia com
--      prescricao) e quantidade de medicos do mes, para ranking e legenda.
--
--   8. temp_CGUSC.fp.build_crm_medico_brasil_ano
--   9. temp_CGUSC.fp.build_crm_medico_territorio_ano
--      Somas anuais das tabelas 4 e 3 (prescricoes, dias com prescricao, meses
--      ativos e meses de alta intensidade). O ranking de medicos le os anos
--      inteiros do periodo destas tabelas e os meses soltos das mensais.
--
--  10. temp_CGUSC.fp.build_crm_medico_dim
--  11. temp_CGUSC.fp.build_crm_farmacia_medico_ano
--      Codigo inteiro denso por medico e prescricoes por farmacia x medico x ano.
--      Base do indice de bitmaps dos filtros de farmacia (tela de analises),
--      montado na sincronizacao.
--
-- Observacao:
--   build_alertas_crm_geografico e benchmarks dependem de build_dados_crm_detalhado
--   completo, entao ficam para o script pos-global.
-- ============================================================================

SET NOCOUNT ON;

DECLARE @DataInicio DATE = '2015-07-01';
DECLARE @DataFim    DATE = '2024-12-31';
-- Mapa de CRMs: o limiar de alta intensidade e este percentil nacional da taxa
-- mensal (prescricoes / dias com prescricao) entre todos os medicos do mes.
DECLARE @PercentilAltaIntensidade DECIMAL(5, 4) = 0.9500;
DECLARE @t0         DATETIME = GETDATE();
DECLARE @t1         DATETIME;
DECLARE @pipeline_nome   VARCHAR(80) = 'crms_detalhado_pre_global';
DECLARE @pipeline_versao VARCHAR(40) = 'v9_crm_distinct_dias';
DECLARE @nu_registros BIGINT;

IF OBJECT_ID('db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP') IS NULL
BEGIN
    RAISERROR('Tabela fonte db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024') IS NULL
BEGIN
    RAISERROR('Tabela fonte db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024 nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao encontrada.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'cnpj') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'uf') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id_regiao_saude') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'codibge') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'municipio') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao possui o schema minimo esperado: id, cnpj, uf, id_regiao_saude, codibge, municipio.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.medicamentos_patologia') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.medicamentos_patologia nao encontrada.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.medicamentos_patologia', 'codigo_barra') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.medicamentos_patologia', 'qnt_comprimidos_caixa') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.medicamentos_patologia sem colunas obrigatorias codigo_barra/qnt_comprimidos_caixa.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP', 'qnt_autorizada') IS NULL
BEGIN
    RAISERROR('Tabela db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP sem coluna obrigatoria qnt_autorizada.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024', 'qnt_autorizada') IS NULL
BEGIN
    RAISERROR('Tabela db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024 sem coluna obrigatoria qnt_autorizada.', 16, 1);
    RETURN;
END;

SELECT @nu_registros = ISNULL(SUM(P.rows), 0)
FROM (
    SELECT object_id, rows
    FROM db_FarmaciaPopular.sys.partitions
    WHERE object_id = OBJECT_ID('db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP')
      AND index_id IN (0, 1)
    UNION ALL
    SELECT object_id, rows
    FROM db_FarmaciaPopular.sys.partitions
    WHERE object_id = OBJECT_ID('db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024')
      AND index_id IN (0, 1)
) P;

PRINT '>> [PRE-GLOBAL CRM] Iniciando pre-processamento global...';
PRINT '   Fonte: BRASIL';
PRINT '   Periodo: ' + CAST(@DataInicio AS VARCHAR(10)) + ' -> ' + CAST(@DataFim AS VARCHAR(10));

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata;

CREATE TABLE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata (
    id_pipeline       TINYINT      NOT NULL,
    pipeline_nome     VARCHAR(80)  NOT NULL,
    pipeline_versao   VARCHAR(40)  NOT NULL,
    dt_data_inicio    DATE         NOT NULL,
    dt_data_fim       DATE         NOT NULL,
    nu_registros      BIGINT NOT NULL,
    dt_criacao        DATETIME     NOT NULL,
    dt_atualizacao    DATETIME     NULL,
    status            VARCHAR(20)  NOT NULL,
    observacao        VARCHAR(400) NULL,
    CONSTRAINT PK_BuildCrmPipelinePreGlobalMetadata PRIMARY KEY CLUSTERED (id_pipeline),
    CONSTRAINT CK_BuildCrmPipelinePreGlobalMetadata_Id CHECK (id_pipeline = 1)
);

EXEC sp_executesql
    N'INSERT INTO temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
          (id_pipeline, pipeline_nome, pipeline_versao, dt_data_inicio, dt_data_fim,
           nu_registros, dt_criacao, dt_atualizacao, status, observacao)
      VALUES
          (1, @nome, @versao, @inicio, @fim,
           @nu_mov, GETDATE(), GETDATE(), ''PROCESSANDO'', ''Pre-global em processamento.'');',
    N'@nome VARCHAR(80), @versao VARCHAR(40), @inicio DATE, @fim DATE, @nu_mov BIGINT',
    @nome = @pipeline_nome,
    @versao = @pipeline_versao,
    @inicio = @DataInicio,
    @fim = @DataFim,
    @nu_mov = @nu_registros;

BEGIN TRY

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle (
        uf_farmacia          CHAR(2)       NOT NULL,
        pipeline_versao      VARCHAR(40)   NOT NULL,
        dt_data_inicio       DATE          NOT NULL,
        dt_data_fim          DATE          NOT NULL,
        status               VARCHAR(20)   NOT NULL,
        etapa                VARCHAR(80)   NULL,
        dt_inicio            DATETIME      NULL,
        dt_fim               DATETIME      NULL,
        dt_atualizacao       DATETIME      NULL,
        nu_registros_fonte   BIGINT        NULL,
        nu_cnpjs_fonte       INT           NULL,
        mensagem_erro        NVARCHAR(4000) NULL,
        dt_erro              DATETIME      NULL,
        CONSTRAINT PK_BuildCrmPipelineUfControle PRIMARY KEY CLUSTERED (uf_farmacia)
    );
END;

UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
SET pipeline_versao = @pipeline_versao,
    dt_data_inicio = @DataInicio,
    dt_data_fim = @DataFim,
    status = 'PENDENTE',
    etapa = 'AGUARDANDO_MATERIALIZACAO',
    dt_inicio = NULL,
    dt_fim = NULL,
    dt_atualizacao = GETDATE(),
    nu_registros_fonte = NULL,
    nu_cnpjs_fonte = NULL,
    mensagem_erro = NULL,
    dt_erro = NULL
WHERE pipeline_versao <> @pipeline_versao
   OR dt_data_inicio <> @DataInicio
   OR dt_data_fim <> @DataFim;

INSERT INTO temp_CGUSC.fp.build_crm_pipeline_uf_controle
    (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, status, etapa, dt_atualizacao)
SELECT DISTINCT
    CAST(F.uf AS CHAR(2)),
    @pipeline_versao,
    @DataInicio,
    @DataFim,
    'PENDENTE',
    'AGUARDANDO_MATERIALIZACAO',
    GETDATE()
FROM temp_CGUSC.fp.dados_farmacia F
WHERE F.uf IS NOT NULL
  AND LEN(LTRIM(RTRIM(F.uf))) = 2
  AND NOT EXISTS (
      SELECT 1
      FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle C
      WHERE C.uf_farmacia = CAST(F.uf AS CHAR(2))
  );

-- ============================================================================
-- PASSO 1: MAPA DE MEDICOS PARA ID INT
-- ============================================================================
PRINT '>> Passo 1: Criando temp_CGUSC.fp.build_dados_medico...';
SET @t1 = GETDATE();

IF COL_LENGTH('temp_CFM.dbo.medicos_jul_2025_mod', 'prim_inscricao_uf') IS NULL
BEGIN
    RAISERROR('Tabela temp_CFM.dbo.medicos_jul_2025_mod sem coluna obrigatoria prim_inscricao_uf.', 16, 1);
    RETURN;
END;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_dados_medico;

WITH MedicosNormalizados AS (
    SELECT
        TRY_CAST(NU_CRM AS BIGINT) AS nu_crm,
        CAST(UPPER(LTRIM(RTRIM(CAST(SG_UF AS VARCHAR(2))))) AS VARCHAR(2)) AS sg_uf,
        CAST(MAX(CAST(NM_MEDICO AS VARCHAR(255))) AS VARCHAR(255)) AS no_medico,
        MIN(TRY_CONVERT(DATE, prim_inscricao_uf, 103)) AS dt_primeira_inscricao_uf
    FROM temp_CFM.dbo.medicos_jul_2025_mod
    WHERE NU_CRM IS NOT NULL
      AND TRY_CAST(NU_CRM AS BIGINT) > 0
    GROUP BY
        TRY_CAST(NU_CRM AS BIGINT),
        CAST(UPPER(LTRIM(RTRIM(CAST(SG_UF AS VARCHAR(2))))) AS VARCHAR(2))
)
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY nu_crm, sg_uf) AS INT) AS id,
    CAST(CAST(nu_crm AS VARCHAR(10)) + '/' + sg_uf AS VARCHAR(13)) AS id_medico,
    nu_crm,
    sg_uf,
    no_medico,
    dt_primeira_inscricao_uf
INTO temp_CGUSC.fp.build_dados_medico
FROM MedicosNormalizados;

CREATE CLUSTERED INDEX IDX_Join_Medico
    ON temp_CGUSC.fp.build_dados_medico(id_medico);

CREATE NONCLUSTERED INDEX IDX_ID_Medico
    ON temp_CGUSC.fp.build_dados_medico(id);

PRINT '   temp_CGUSC.fp.build_dados_medico concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);


-- ============================================================================
-- PASSO 2: TOTAIS NACIONAIS POR MEDICO / COMPETENCIA
-- ============================================================================
-- Preserva o grain do fluxo atual:
--   1. deduplica autorizacoes por (cnpj, medico, competencia, data) e
--      preserva o agregado diario;
--   2. materializa o total mensal por estabelecimento, medico e mes;
--   3. o bloco do mapa (mais abaixo) agrega por medico e data em municipio,
--      regiao de saude, UF e Brasil, calcula os limiares P95 mensais e as
--      contagens por intervalo, e persiste medico x territorio x mes.
-- Tambem materializa a relacao completa por estabelecimento, medico e mes,
-- que sera usada por analises globais com os filtros da aplicacao.
-- ============================================================================
PRINT '>> Passo 2: Criando caches de prescricoes por estabelecimento e nacionais...';
SET @t1 = GETDATE();

IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia', 'U') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao encontrada.', 16, 1);
END;

IF COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'cnpj') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'codibge') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'uf') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id_regiao_saude') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia sem as colunas obrigatorias.', 16, 1);
END;

DROP TABLE IF EXISTS #base_crm_cnpj;
DROP TABLE IF EXISTS #base_crm_cnpj_dia;
DROP TABLE IF EXISTS #base_crm_cnpj_agregado;
DROP TABLE IF EXISTS #base_crm_cnpj_dias_mes;
DROP TABLE IF EXISTS #base_crm_cnpj_autorizacoes_dia;

;WITH Movimentacao AS (
    SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, valor_pago, qnt_autorizada, codigo_barra
    FROM db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP
    UNION ALL
    SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, valor_pago, qnt_autorizada, codigo_barra
    FROM db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024
), Elegiveis AS (
    SELECT
        CAST(M.cnpj AS CHAR(14)) AS nu_cnpj,
        CAST(CAST(M.crm AS VARCHAR(10)) + '/' + M.crm_uf AS VARCHAR(13)) AS id_medico,
        YEAR(M.data_hora) * 100 + MONTH(M.data_hora) AS competencia,
        CAST(M.data_hora AS DATE) AS dt_prescricao,
        M.num_autorizacao
    FROM Movimentacao M
    WHERE M.crm_uf IS NOT NULL
      AND M.crm IS NOT NULL
      AND M.crm_uf <> 'BR'
      AND M.data_hora >= @DataInicio
      AND M.data_hora < DATEADD(DAY, 1, @DataFim)
      AND M.num_autorizacao IS NOT NULL
      AND M.qnt_autorizada IS NOT NULL
      AND EXISTS (
          SELECT 1
          FROM temp_CGUSC.fp.medicamentos_patologia PAT
          WHERE PAT.codigo_barra = M.codigo_barra
            AND TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0)) IS NOT NULL
            AND TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0)) <> 0
            AND (M.qnt_autorizada / TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0))) <> 0
      )
)
SELECT DISTINCT
    E.nu_cnpj,
    E.id_medico,
    E.competencia,
    E.dt_prescricao,
    E.num_autorizacao
INTO #base_crm_cnpj_autorizacoes_dia
FROM Elegiveis E;

CREATE CLUSTERED INDEX IDX_BaseCrmCnpjAutorizacoesDia
    ON #base_crm_cnpj_autorizacoes_dia
       (nu_cnpj, id_medico, competencia, num_autorizacao, dt_prescricao);

-- A mesma autorizacao nao pode representar dois dias de prescricao no
-- mesmo estabelecimento/medico/mes. O fluxo anterior tambem falhava nesse caso.
IF EXISTS (
    SELECT 1
    FROM #base_crm_cnpj_autorizacoes_dia
    GROUP BY nu_cnpj, id_medico, competencia, num_autorizacao
    HAVING COUNT_BIG(*) > 1
)
    THROW 51011, 'Prescricoes diarias divergem do total mensal: autorizacao em datas diferentes ou fonte inconsistente.', 1;

-- Uma contagem simples substitui dois COUNT(DISTINCT) sobre a fonte bruta.
-- Mantemos as duas granularidades porque o mapa consome #base_crm_cnpj_dia.
SELECT
    A.nu_cnpj,
    A.id_medico,
    A.competencia,
    A.dt_prescricao,
    COUNT_BIG(*) AS nu_prescricoes_medico,
    CAST(GROUPING(A.dt_prescricao) AS BIT) AS is_total_mes
INTO #base_crm_cnpj_agregado
FROM #base_crm_cnpj_autorizacoes_dia A
GROUP BY GROUPING SETS (
    (A.nu_cnpj, A.id_medico, A.competencia, A.dt_prescricao),
    (A.nu_cnpj, A.id_medico, A.competencia)
);

DROP TABLE #base_crm_cnpj_autorizacoes_dia;

SELECT nu_cnpj, id_medico, competencia, nu_prescricoes_medico
INTO #base_crm_cnpj
FROM #base_crm_cnpj_agregado
WHERE is_total_mes = 1;

SELECT nu_cnpj, id_medico, competencia, dt_prescricao, nu_prescricoes_medico
INTO #base_crm_cnpj_dia
FROM #base_crm_cnpj_agregado
WHERE is_total_mes = 0;

DROP TABLE #base_crm_cnpj_agregado;

CREATE CLUSTERED INDEX IDX_BaseCrmCnpj
    ON #base_crm_cnpj(nu_cnpj, id_medico, competencia);

CREATE CLUSTERED INDEX IDX_BaseCrmCnpjDia
    ON #base_crm_cnpj_dia(nu_cnpj, id_medico, competencia, dt_prescricao);

-- Cada linha diaria corresponde a uma data distinta no mesmo CNPJ/medico/mes.
SELECT
    nu_cnpj,
    id_medico,
    competencia,
    SUM(CAST(nu_prescricoes_medico AS BIGINT)) AS nu_prescricoes_dias,
    COUNT_BIG(*) AS qtd_dias_com_prescricao_mes
INTO #base_crm_cnpj_dias_mes
FROM #base_crm_cnpj_dia
GROUP BY nu_cnpj, id_medico, competencia;

CREATE UNIQUE CLUSTERED INDEX IDX_BaseCrmCnpjDiasMes
    ON #base_crm_cnpj_dias_mes(nu_cnpj, id_medico, competencia);

IF EXISTS (
    SELECT 1
    FROM #base_crm_cnpj B
    LEFT JOIN #base_crm_cnpj_dias_mes D ON D.nu_cnpj = B.nu_cnpj
       AND D.id_medico = B.id_medico
       AND D.competencia = B.competencia
    WHERE D.nu_prescricoes_dias IS NULL
       OR D.nu_prescricoes_dias <> B.nu_prescricoes_medico
)
    THROW 51011, 'Prescricoes diarias divergem do total mensal: autorizacao em datas diferentes ou fonte inconsistente.', 1;

IF EXISTS (
    SELECT 1
    FROM #base_crm_cnpj B
    INNER JOIN #base_crm_cnpj_dias_mes D ON D.nu_cnpj = B.nu_cnpj
        AND D.id_medico = B.id_medico
        AND D.competencia = B.competencia
    WHERE B.nu_prescricoes_medico NOT BETWEEN 1 AND 32767
       OR D.qtd_dias_com_prescricao_mes NOT BETWEEN 1 AND 31
       OR D.qtd_dias_com_prescricao_mes > B.nu_prescricoes_medico
)
    THROW 51020, 'Prescricoes ou dias por CNPJ/medico/mes fora dos limites de SMALLINT/TINYINT.', 1;

IF NOT EXISTS (SELECT 1 FROM #base_crm_cnpj)
BEGIN
    RAISERROR('Nenhuma prescricao CRM valida foi encontrada no periodo informado.', 16, 1);
END;

IF EXISTS (
    SELECT F.id
    FROM temp_CGUSC.fp.dados_farmacia F
    GROUP BY F.id
    HAVING COUNT_BIG(*) > 1
)
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia possui IDs duplicados.', 16, 1);
END;

IF EXISTS (
    SELECT F.cnpj
    FROM temp_CGUSC.fp.dados_farmacia F
    WHERE F.cnpj IS NOT NULL
    GROUP BY F.cnpj
    HAVING COUNT_BIG(*) > 1
)
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia possui CNPJs duplicados.', 16, 1);
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.dados_farmacia F
    WHERE F.id IS NULL
       OR F.cnpj IS NULL
       OR F.codibge IS NULL
       OR NULLIF(LTRIM(RTRIM(CAST(F.uf AS VARCHAR(2)))), '') IS NULL
       OR F.id_regiao_saude IS NULL
)
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia possui valores obrigatorios nulos.', 16, 1);
END;

IF EXISTS (
    SELECT F.codibge
    FROM temp_CGUSC.fp.dados_farmacia F
    GROUP BY F.codibge
    HAVING COUNT(DISTINCT UPPER(LTRIM(RTRIM(CAST(F.uf AS VARCHAR(2)))))) > 1
        OR COUNT(DISTINCT CAST(F.id_regiao_saude AS VARCHAR(20))) > 1
)
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia possui geografia inconsistente para o mesmo municipio.', 16, 1);
END;

IF EXISTS (
    SELECT 1
    FROM #base_crm_cnpj B
    LEFT JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.cnpj = B.nu_cnpj
    WHERE F.id IS NULL
)
BEGIN
    RAISERROR('Existem CNPJs com prescricoes sem correspondencia em temp_CGUSC.fp.dados_farmacia.', 16, 1);
END;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_medico_estabelecimento_mes;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_medico_municipio_mes; -- tabela descontinuada
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_medico_territorio_mes;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos; -- tabela descontinuada
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_medico_brasil_mes;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_medico_brasil_ano;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_medico_territorio_ano;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_medico_dim;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_farmacia_medico_ano;

SELECT
    CAST(F.id AS INT) AS id_cnpj,
    B.id_medico,
    B.competencia,
    CAST(B.nu_prescricoes_medico AS SMALLINT) AS nu_prescricoes_mes,
    CAST(D.qtd_dias_com_prescricao_mes AS TINYINT) AS qtd_dias_com_prescricao_mes
INTO temp_CGUSC.fp.build_crm_medico_estabelecimento_mes
FROM #base_crm_cnpj B
INNER JOIN #base_crm_cnpj_dias_mes D
    ON D.nu_cnpj = B.nu_cnpj
   AND D.id_medico = B.id_medico
   AND D.competencia = B.competencia
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.cnpj = B.nu_cnpj;

CREATE CLUSTERED INDEX IDX_CrmMedicoEstabMes_Key
    ON temp_CGUSC.fp.build_crm_medico_estabelecimento_mes(id_cnpj, id_medico, competencia);

CREATE NONCLUSTERED INDEX IDX_CrmMedicoEstabMes_Medico
    ON temp_CGUSC.fp.build_crm_medico_estabelecimento_mes(id_medico, competencia, id_cnpj);

DROP TABLE #base_crm_cnpj_dias_mes;
DROP TABLE #base_crm_cnpj;


-- ============================================================================
-- MAPA DE CRMs: MEDICOS DE ALTA INTENSIDADE POR TERRITORIO E PERIODO
-- ============================================================================
-- Definicoes (valem para municipio, regiao de saude, UF e Brasil):
--   * taxa do medico no mes = prescricoes / dias com prescricao no territorio;
--   * limiar do mes = P95 nacional (posto mais proximo) da taxa entre todos
--     os medico-mes do Brasil;
--   * mes de alta intensidade = taxa acima do limiar do mes, com qualquer
--     quantidade de dias (1 dia com 200 prescricoes = taxa 200);
--   * no intervalo, o medico e contado em cada grupo se tiver pelo menos um
--     mes correspondente (ativo, alta intensidade).
-- Somente tabelas temporarias; IDs de medicos nao chegam as tabelas finais.
-- ============================================================================
DROP TABLE IF EXISTS #crm_competencias;
DROP TABLE IF EXISTS #crm_municipio_geo;
DROP TABLE IF EXISTS #crm_dia_municipio;
DROP TABLE IF EXISTS #crm_dia_regiao;
DROP TABLE IF EXISTS #crm_dia_uf;
DROP TABLE IF EXISTS #crm_dia_brasil;
DROP TABLE IF EXISTS #crm_medico_mes_territorio;
DROP TABLE IF EXISTS #crm_taxa_brasil;
DROP TABLE IF EXISTS #crm_taxa_brasil_ordem;
DROP TABLE IF EXISTS #crm_limiar_base;
DROP TABLE IF EXISTS #crm_limiar_mes;
DROP TABLE IF EXISTS #crm_nivel_mensal;
DROP TABLE IF EXISTS #crm_eventos_mes;
DROP TABLE IF EXISTS #crm_deltas_brutos;
DROP TABLE IF EXISTS #crm_territorio_deltas;
DROP TABLE IF EXISTS #crm_territorios;
DROP TABLE IF EXISTS #crm_intervalos;
DROP TABLE IF EXISTS #crm_primeira_ocorrencia;

-- ---------------------------------------------------------------------------
-- Grade de meses do pipeline (laco simples; sem CTE recursiva)
-- ---------------------------------------------------------------------------
CREATE TABLE #crm_competencias (
    competencia INT NOT NULL,
    competencia_data DATE NOT NULL,
    dias_mes TINYINT NOT NULL,
    ordem_mes SMALLINT NOT NULL,
    PRIMARY KEY CLUSTERED (competencia)
);

DECLARE @mes_corrente DATE = DATEFROMPARTS(YEAR(@DataInicio), MONTH(@DataInicio), 1);
DECLARE @mes_final DATE = DATEFROMPARTS(YEAR(@DataFim), MONTH(@DataFim), 1);
DECLARE @ordem_corrente SMALLINT = 1;

WHILE @mes_corrente <= @mes_final
BEGIN
    INSERT INTO #crm_competencias (competencia, competencia_data, dias_mes, ordem_mes)
    VALUES (
        YEAR(@mes_corrente) * 100 + MONTH(@mes_corrente),
        @mes_corrente,
        DAY(EOMONTH(@mes_corrente)),
        @ordem_corrente
    );
    SET @mes_corrente = DATEADD(MONTH, 1, @mes_corrente);
    SET @ordem_corrente = @ordem_corrente + 1;
END;

CREATE UNIQUE NONCLUSTERED INDEX IX_CrmCompetencias_Ordem
    ON #crm_competencias(ordem_mes);

-- ---------------------------------------------------------------------------
-- Geografia por municipio (a consistencia UF/regiao por municipio ja foi
-- validada no Passo 2).
-- ---------------------------------------------------------------------------
SELECT DISTINCT
    CAST(F.codibge AS VARCHAR(20)) AS id_municipio,
    CAST(F.id_regiao_saude AS VARCHAR(20)) AS id_regiao_saude,
    CAST(UPPER(LTRIM(RTRIM(F.uf))) AS VARCHAR(2)) AS uf
INTO #crm_municipio_geo
FROM temp_CGUSC.fp.dados_farmacia F;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMunicipioGeo
    ON #crm_municipio_geo(id_municipio);

IF (SELECT COUNT(DISTINCT uf) FROM #crm_municipio_geo) <> 27
    THROW 51012, 'O mapa Brasil exige as 27 UFs na dimensao de farmacias.', 1;

-- ---------------------------------------------------------------------------
-- Prescricoes por medico e DATA em cada nivel. Cada nivel parte do anterior
-- (mais enxuto que reler a base por CNPJ) e conta a mesma data uma unica vez
-- quando o medico prescreveu em mais de um lugar do territorio.
-- ---------------------------------------------------------------------------
SELECT
    CAST(F.codibge AS VARCHAR(20)) AS id_municipio,
    D.id_medico,
    D.competencia,
    D.dt_prescricao,
    SUM(CAST(D.nu_prescricoes_medico AS INT)) AS nu_prescricoes_dia
INTO #crm_dia_municipio
FROM #base_crm_cnpj_dia D
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.cnpj = D.nu_cnpj
GROUP BY
    CAST(F.codibge AS VARCHAR(20)),
    D.id_medico,
    D.competencia,
    D.dt_prescricao;

DROP TABLE #base_crm_cnpj_dia;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmDiaMunicipio
    ON #crm_dia_municipio(id_municipio, id_medico, competencia, dt_prescricao);

SELECT
    G.id_regiao_saude,
    M.id_medico,
    M.competencia,
    M.dt_prescricao,
    SUM(M.nu_prescricoes_dia) AS nu_prescricoes_dia
INTO #crm_dia_regiao
FROM #crm_dia_municipio M
INNER JOIN #crm_municipio_geo G
    ON G.id_municipio = M.id_municipio
GROUP BY G.id_regiao_saude, M.id_medico, M.competencia, M.dt_prescricao;

SELECT
    G.uf,
    M.id_medico,
    M.competencia,
    M.dt_prescricao,
    SUM(M.nu_prescricoes_dia) AS nu_prescricoes_dia
INTO #crm_dia_uf
FROM #crm_dia_municipio M
INNER JOIN #crm_municipio_geo G
    ON G.id_municipio = M.id_municipio
GROUP BY G.uf, M.id_medico, M.competencia, M.dt_prescricao;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmDiaUf
    ON #crm_dia_uf(id_medico, competencia, dt_prescricao, uf);

SELECT
    U.id_medico,
    U.competencia,
    U.dt_prescricao,
    SUM(U.nu_prescricoes_dia) AS nu_prescricoes_dia
INTO #crm_dia_brasil
FROM #crm_dia_uf U
GROUP BY U.id_medico, U.competencia, U.dt_prescricao;

-- ---------------------------------------------------------------------------
-- Medico x territorio x mes: total, dias com prescricao e taxa.
-- ---------------------------------------------------------------------------
CREATE TABLE #crm_medico_mes_territorio (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    id_medico VARCHAR(50) NOT NULL,
    competencia INT NOT NULL,
    nu_prescricoes_mes INT NOT NULL,
    qtd_dias_com_prescricao_mes INT NOT NULL,
    taxa_dia DECIMAL(19, 6) NOT NULL
);

INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
SELECT 'municipio', id_municipio, id_medico, competencia,
       SUM(nu_prescricoes_dia), COUNT(*),
       CAST(CAST(SUM(nu_prescricoes_dia) AS DECIMAL(19, 6)) / COUNT(*) AS DECIMAL(19, 6))
FROM #crm_dia_municipio
GROUP BY id_municipio, id_medico, competencia;

DROP TABLE #crm_dia_municipio;

INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
SELECT 'regiao_saude', id_regiao_saude, id_medico, competencia,
       SUM(nu_prescricoes_dia), COUNT(*),
       CAST(CAST(SUM(nu_prescricoes_dia) AS DECIMAL(19, 6)) / COUNT(*) AS DECIMAL(19, 6))
FROM #crm_dia_regiao
GROUP BY id_regiao_saude, id_medico, competencia;

DROP TABLE #crm_dia_regiao;

INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
SELECT 'uf', uf, id_medico, competencia,
       SUM(nu_prescricoes_dia), COUNT(*),
       CAST(CAST(SUM(nu_prescricoes_dia) AS DECIMAL(19, 6)) / COUNT(*) AS DECIMAL(19, 6))
FROM #crm_dia_uf
GROUP BY uf, id_medico, competencia;

DROP TABLE #crm_dia_uf;

INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
SELECT 'brasil', 'BR', id_medico, competencia,
       SUM(nu_prescricoes_dia), COUNT(*),
       CAST(CAST(SUM(nu_prescricoes_dia) AS DECIMAL(19, 6)) / COUNT(*) AS DECIMAL(19, 6))
FROM #crm_dia_brasil
GROUP BY id_medico, competencia;

DROP TABLE #crm_dia_brasil;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMedicoMesTerritorio
    ON #crm_medico_mes_territorio(nivel, id_geografico, id_medico, competencia);

IF EXISTS (
    SELECT 1
    FROM #crm_medico_mes_territorio T
    INNER JOIN #crm_competencias C ON C.competencia = T.competencia
    WHERE T.qtd_dias_com_prescricao_mes NOT BETWEEN 1 AND C.dias_mes
       OR T.nu_prescricoes_mes < T.qtd_dias_com_prescricao_mes
)
    THROW 51013, 'Dias com prescricao invalidos no agregado mensal do mapa.', 1;

IF EXISTS (
    SELECT 1
    FROM #crm_medico_mes_territorio T
    LEFT JOIN #crm_competencias C ON C.competencia = T.competencia
    WHERE C.competencia IS NULL
)
    THROW 51014, 'Agregado mensal do mapa com competencia fora da grade do pipeline.', 1;

-- ---------------------------------------------------------------------------
-- Limiar mensal: P95 nacional por posto mais proximo (k = teto(0,95 * n)).
-- O indice clusterizado ja entrega a ordem da taxa, evitando nova ordenacao.
-- ---------------------------------------------------------------------------
SELECT competencia, taxa_dia
INTO #crm_taxa_brasil
FROM #crm_medico_mes_territorio
WHERE nivel = 'brasil';

CREATE CLUSTERED INDEX IDX_CrmTaxaBrasil
    ON #crm_taxa_brasil(competencia, taxa_dia);

SELECT
    competencia,
    COUNT_BIG(*) AS qtd_medicos_ativos,
    CAST(CEILING(@PercentilAltaIntensidade * COUNT_BIG(*)) AS BIGINT) AS posto_percentil
INTO #crm_limiar_base
FROM #crm_taxa_brasil
GROUP BY competencia;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmLimiarBase
    ON #crm_limiar_base(competencia);

SELECT
    competencia,
    taxa_dia,
    ROW_NUMBER() OVER (PARTITION BY competencia ORDER BY taxa_dia) AS posto
INTO #crm_taxa_brasil_ordem
FROM #crm_taxa_brasil;

DROP TABLE #crm_taxa_brasil;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmTaxaBrasilOrdem
    ON #crm_taxa_brasil_ordem(competencia, posto);

SELECT
    B.competencia,
    CAST(B.qtd_medicos_ativos AS INT) AS qtd_medicos_ativos,
    O.taxa_dia AS p95_taxa_dia
INTO #crm_limiar_mes
FROM #crm_limiar_base B
INNER JOIN #crm_taxa_brasil_ordem O
    ON O.competencia = B.competencia
   AND O.posto = B.posto_percentil;

DROP TABLE #crm_taxa_brasil_ordem;
DROP TABLE #crm_limiar_base;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmLimiarMes
    ON #crm_limiar_mes(competencia);

-- Sem limiar nao ha como classificar o mes: falha visivel, nunca zero implicito.
IF EXISTS (
    SELECT 1
    FROM #crm_competencias C
    LEFT JOIN #crm_limiar_mes L ON L.competencia = C.competencia
    WHERE L.competencia IS NULL
)
    THROW 51015, 'Existe competencia sem medicos para calcular o P95 nacional.', 1;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_limiar_p95_mes;

CREATE TABLE temp_CGUSC.fp.build_crm_limiar_p95_mes (
    competencia INT NOT NULL,
    qtd_medicos_ativos INT NOT NULL,
    p95_taxa_dia DECIMAL(19, 6) NOT NULL,
    CONSTRAINT PK_BuildCrmLimiarP95Mes PRIMARY KEY CLUSTERED (competencia)
);

INSERT INTO temp_CGUSC.fp.build_crm_limiar_p95_mes (
    competencia, qtd_medicos_ativos, p95_taxa_dia
)
SELECT competencia, qtd_medicos_ativos, p95_taxa_dia
FROM #crm_limiar_mes;

COMMIT TRANSACTION;

PRINT '   temp_CGUSC.fp.build_crm_limiar_p95_mes concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

-- ---------------------------------------------------------------------------
-- Classificacao mensal por territorio.
-- ---------------------------------------------------------------------------
CREATE TABLE #crm_nivel_mensal (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    id_medico VARCHAR(50) NOT NULL,
    ordem_mes SMALLINT NOT NULL,
    is_mes_alta_intensidade BIT NOT NULL
);

INSERT INTO #crm_nivel_mensal WITH (TABLOCK)
SELECT
    T.nivel,
    T.id_geografico,
    T.id_medico,
    C.ordem_mes,
    CAST(CASE WHEN T.taxa_dia > L.p95_taxa_dia THEN 1 ELSE 0 END AS BIT)
FROM #crm_medico_mes_territorio T
INNER JOIN #crm_competencias C ON C.competencia = T.competencia
INNER JOIN #crm_limiar_mes L ON L.competencia = T.competencia;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmNivelMensal
    ON #crm_nivel_mensal(nivel, id_geografico, id_medico, ordem_mes);

-- ---------------------------------------------------------------------------
-- Eventos: para cada mes do medico, o mes anterior do mesmo grupo. A janela
-- segue a ordem do indice clusterizado (sem ordenacao adicional).
-- ---------------------------------------------------------------------------
SELECT
    nivel,
    id_geografico,
    ordem_mes,
    is_mes_alta_intensidade,
    ISNULL(MAX(ordem_mes) OVER (
        PARTITION BY nivel, id_geografico, id_medico ORDER BY ordem_mes
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ), 0) AS ordem_anterior_ativo,
    ISNULL(MAX(CASE WHEN is_mes_alta_intensidade = 1 THEN ordem_mes END) OVER (
        PARTITION BY nivel, id_geografico, id_medico ORDER BY ordem_mes
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ), 0) AS ordem_anterior_alta
INTO #crm_eventos_mes
FROM #crm_nivel_mensal;

DROP TABLE #crm_nivel_mensal;

-- Um medico so entra uma vez por intervalo em cada grupo: sua contribuicao
-- vale para inicios entre o mes do grupo anterior + 1 e o mes atual.
CREATE TABLE #crm_deltas_brutos (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    ordem_inicio SMALLINT NOT NULL,
    ordem_primeira SMALLINT NOT NULL,
    delta_ativos INT NOT NULL,
    delta_alta_intensidade INT NOT NULL
);

INSERT INTO #crm_deltas_brutos WITH (TABLOCK)
SELECT nivel, id_geografico, CAST(ordem_anterior_ativo + 1 AS SMALLINT), ordem_mes, 1, 0
FROM #crm_eventos_mes;

INSERT INTO #crm_deltas_brutos WITH (TABLOCK)
SELECT nivel, id_geografico, CAST(ordem_anterior_alta + 1 AS SMALLINT), ordem_mes, 0, 1
FROM #crm_eventos_mes
WHERE is_mes_alta_intensidade = 1;

DROP TABLE #crm_eventos_mes;

SELECT
    nivel,
    id_geografico,
    ordem_inicio,
    ordem_primeira,
    SUM(delta_ativos) AS delta_ativos,
    SUM(delta_alta_intensidade) AS delta_alta_intensidade
INTO #crm_territorio_deltas
FROM #crm_deltas_brutos
GROUP BY nivel, id_geografico, ordem_inicio, ordem_primeira;

DROP TABLE #crm_deltas_brutos;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmTerritorioDeltas
    ON #crm_territorio_deltas(nivel, id_geografico, ordem_primeira, ordem_inicio);

-- ---------------------------------------------------------------------------
-- Territorios (inclusive sem prescricao: contagens zero) e intervalos.
-- ---------------------------------------------------------------------------
CREATE TABLE #crm_territorios (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    PRIMARY KEY CLUSTERED (nivel, id_geografico)
);

INSERT INTO #crm_territorios (nivel, id_geografico)
SELECT DISTINCT 'municipio', id_municipio FROM #crm_municipio_geo;

INSERT INTO #crm_territorios (nivel, id_geografico)
SELECT DISTINCT 'regiao_saude', id_regiao_saude FROM #crm_municipio_geo;

INSERT INTO #crm_territorios (nivel, id_geografico)
SELECT DISTINCT 'uf', uf FROM #crm_municipio_geo;

INSERT INTO #crm_territorios (nivel, id_geografico)
VALUES ('brasil', 'BR');

IF EXISTS (SELECT 1 FROM #crm_territorios WHERE NULLIF(id_geografico, '') IS NULL)
    THROW 51033, 'Territorio CRM sem municipio, regiao de saude ou UF.', 1;

SELECT
    I.ordem_mes AS ordem_inicio,
    P.ordem_mes AS ordem_primeira
INTO #crm_intervalos
FROM #crm_competencias I
INNER JOIN #crm_competencias P
    ON P.ordem_mes >= I.ordem_mes;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmIntervalos
    ON #crm_intervalos(ordem_primeira, ordem_inicio);

-- Medicos cuja primeira ocorrencia (a partir do inicio) cai em ordem_primeira.
SELECT
    T.nivel,
    T.id_geografico,
    G.ordem_inicio,
    G.ordem_primeira,
    SUM(ISNULL(D.delta_ativos, 0)) OVER (
        PARTITION BY T.nivel, T.id_geografico, G.ordem_primeira
        ORDER BY G.ordem_inicio
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS primeira_ativos,
    SUM(ISNULL(D.delta_alta_intensidade, 0)) OVER (
        PARTITION BY T.nivel, T.id_geografico, G.ordem_primeira
        ORDER BY G.ordem_inicio
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS primeira_alta_intensidade
INTO #crm_primeira_ocorrencia
FROM #crm_territorios T
CROSS JOIN #crm_intervalos G
LEFT JOIN #crm_territorio_deltas D
    ON D.nivel = T.nivel
   AND D.id_geografico = T.id_geografico
   AND D.ordem_primeira = G.ordem_primeira
   AND D.ordem_inicio = G.ordem_inicio;

DROP TABLE #crm_territorio_deltas;

-- Ordem da segunda janela (acumulado ate o fim do intervalo).
CREATE UNIQUE CLUSTERED INDEX IDX_CrmPrimeiraOcorrencia
    ON #crm_primeira_ocorrencia(nivel, id_geografico, ordem_inicio, ordem_primeira);

-- ---------------------------------------------------------------------------
-- Tabelas finais (sem id_medico).
-- ---------------------------------------------------------------------------
BEGIN TRANSACTION;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo;

CREATE TABLE temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    competencia_inicio INT NOT NULL,
    competencia_fim INT NOT NULL,
    qtd_medicos_ativos INT NOT NULL,
    qtd_medicos_alta_intensidade INT NOT NULL
);

INSERT INTO temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo WITH (TABLOCK) (
    nivel, id_geografico, competencia_inicio, competencia_fim,
    qtd_medicos_ativos, qtd_medicos_alta_intensidade
)
SELECT
    P.nivel,
    P.id_geografico,
    CI.competencia,
    CF.competencia,
    SUM(P.primeira_ativos) OVER (
        PARTITION BY P.nivel, P.id_geografico, P.ordem_inicio
        ORDER BY P.ordem_primeira
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    SUM(P.primeira_alta_intensidade) OVER (
        PARTITION BY P.nivel, P.id_geografico, P.ordem_inicio
        ORDER BY P.ordem_primeira
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
FROM #crm_primeira_ocorrencia P
INNER JOIN #crm_competencias CI ON CI.ordem_mes = P.ordem_inicio
INNER JOIN #crm_competencias CF ON CF.ordem_mes = P.ordem_primeira
WHERE P.nivel IN ('municipio', 'regiao_saude');

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMapaMunicipioRegiaoPeriodo
    ON temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo(
        competencia_inicio, competencia_fim, nivel, id_geografico
    );

COMMIT TRANSACTION;

PRINT '   temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

BEGIN TRANSACTION;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_mapa_uf_periodo;

CREATE TABLE temp_CGUSC.fp.build_crm_mapa_uf_periodo (
    nivel VARCHAR(6) NOT NULL,
    id_geografico VARCHAR(2) NOT NULL,
    competencia_inicio INT NOT NULL,
    competencia_fim INT NOT NULL,
    qtd_medicos_ativos INT NOT NULL,
    qtd_medicos_alta_intensidade INT NOT NULL
);

INSERT INTO temp_CGUSC.fp.build_crm_mapa_uf_periodo WITH (TABLOCK) (
    nivel, id_geografico, competencia_inicio, competencia_fim,
    qtd_medicos_ativos, qtd_medicos_alta_intensidade
)
SELECT
    CAST(P.nivel AS VARCHAR(6)),
    CAST(P.id_geografico AS VARCHAR(2)),
    CI.competencia,
    CF.competencia,
    SUM(P.primeira_ativos) OVER (
        PARTITION BY P.nivel, P.id_geografico, P.ordem_inicio
        ORDER BY P.ordem_primeira
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    SUM(P.primeira_alta_intensidade) OVER (
        PARTITION BY P.nivel, P.id_geografico, P.ordem_inicio
        ORDER BY P.ordem_primeira
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
FROM #crm_primeira_ocorrencia P
INNER JOIN #crm_competencias CI ON CI.ordem_mes = P.ordem_inicio
INNER JOIN #crm_competencias CF ON CF.ordem_mes = P.ordem_primeira
WHERE P.nivel IN ('uf', 'brasil');

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMapaUfPeriodo
    ON temp_CGUSC.fp.build_crm_mapa_uf_periodo(
        competencia_inicio, competencia_fim, nivel, id_geografico
    );

COMMIT TRANSACTION;

PRINT '   temp_CGUSC.fp.build_crm_mapa_uf_periodo concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

DROP TABLE #crm_primeira_ocorrencia;
DROP TABLE #crm_intervalos;
DROP TABLE #crm_territorios;
DROP TABLE #crm_municipio_geo;

-- Coerencia das contagens: 0 <= alta intensidade <= ativos.
IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo
    WHERE qtd_medicos_alta_intensidade < 0
       OR qtd_medicos_alta_intensidade > qtd_medicos_ativos
)
    THROW 51016, 'Contagens incoerentes na tabela de municipio/regiao do mapa CRM.', 1;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_mapa_uf_periodo
    WHERE qtd_medicos_alta_intensidade < 0
       OR qtd_medicos_alta_intensidade > qtd_medicos_ativos
)
    THROW 51017, 'Contagens incoerentes na tabela de UF/Brasil do mapa CRM.', 1;


-- Validado antes das duas tabelas nacionais: o total por medico/mes e o mesmo
-- nas duas, e o CAST para SMALLINT nao pode estourar com erro generico.
IF EXISTS (
    SELECT 1
    FROM #crm_medico_mes_territorio
    WHERE nivel = 'brasil'
      AND nu_prescricoes_mes NOT BETWEEN 1 AND 32767
)
    THROW 51025, 'Prescricoes nacionais por medico/mes fora do limite de SMALLINT.', 1;

-- Quantidade de farmacias por medico/mes (a tabela por estabelecimento e unica
-- por id_cnpj/id_medico/competencia, logo COUNT = farmacias distintas).
DROP TABLE IF EXISTS #crm_estabelecimentos_medico_mes;

SELECT
    id_medico,
    competencia,
    COUNT_BIG(*) AS nu_estabelecimentos_mes,
    SUM(CAST(nu_prescricoes_mes AS BIGINT)) AS nu_prescricoes_estabelecimentos
INTO #crm_estabelecimentos_medico_mes
FROM temp_CGUSC.fp.build_crm_medico_estabelecimento_mes
GROUP BY id_medico, competencia;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmEstabelecimentosMedicoMes
    ON #crm_estabelecimentos_medico_mes(id_medico, competencia);

-- O total nacional por medico/mes tem de ser o mesmo pelos dois caminhos
-- (soma das farmacias e soma das datas no Brasil); divergencia = erro.
IF EXISTS (
    SELECT 1
    FROM (
        SELECT id_medico, competencia, nu_prescricoes_mes
        FROM #crm_medico_mes_territorio
        WHERE nivel = 'brasil'
    ) T
    FULL JOIN #crm_estabelecimentos_medico_mes E
        ON E.id_medico = T.id_medico
       AND E.competencia = T.competencia
    WHERE T.id_medico IS NULL
       OR E.id_medico IS NULL
       OR E.nu_prescricoes_estabelecimentos <> T.nu_prescricoes_mes
       OR E.nu_estabelecimentos_mes NOT BETWEEN 1 AND 32767
)
    THROW 51027, 'Total nacional por medico/mes diverge entre estabelecimentos e datas.', 1;

SELECT
    T.id_medico,
    T.competencia,
    CAST(T.nu_prescricoes_mes AS SMALLINT) AS nu_prescricoes_mes,
    CAST(T.qtd_dias_com_prescricao_mes AS TINYINT) AS qtd_dias_com_prescricao_mes,
    CAST(E.nu_estabelecimentos_mes AS SMALLINT) AS nu_estabelecimentos_mes
INTO temp_CGUSC.fp.build_crm_medico_brasil_mes
FROM #crm_medico_mes_territorio T
INNER JOIN #crm_estabelecimentos_medico_mes E
    ON E.id_medico = T.id_medico
   AND E.competencia = T.competencia
WHERE T.nivel = 'brasil';

DROP TABLE #crm_estabelecimentos_medico_mes;

-- Medico x territorio (municipio, regiao de saude, UF) x mes, com dias
-- distintos em cada nivel. Base do ranking com filtro geografico; o nivel
-- Brasil fica em build_crm_medico_brasil_mes.
IF EXISTS (
    SELECT 1
    FROM #crm_medico_mes_territorio
    WHERE nivel <> 'brasil'
      AND nu_prescricoes_mes NOT BETWEEN 1 AND 32767
)
    THROW 51026, 'Prescricoes por medico/territorio/mes fora do limite de SMALLINT.', 1;

SELECT
    CAST(nivel AS VARCHAR(16)) AS nivel,
    CAST(id_geografico AS VARCHAR(20)) AS id_geografico,
    CAST(id_medico AS VARCHAR(13)) AS id_medico,
    competencia,
    CAST(nu_prescricoes_mes AS SMALLINT) AS nu_prescricoes_mes,
    CAST(qtd_dias_com_prescricao_mes AS TINYINT) AS qtd_dias_com_prescricao_mes
INTO temp_CGUSC.fp.build_crm_medico_territorio_mes
FROM #crm_medico_mes_territorio
WHERE nivel IN ('municipio', 'regiao_saude', 'uf');

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMedicoTerritorioMes_Key
    ON temp_CGUSC.fp.build_crm_medico_territorio_mes(competencia, nivel, id_geografico, id_medico);

PRINT '   temp_CGUSC.fp.build_crm_medico_territorio_mes concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

-- ---------------------------------------------------------------------------
-- Medico x ano (Brasil e territorios): somas anuais para o ranking. Mes de alta
-- intensidade = taxa_dia do mes acima do P95 nacional do mes (mesma regra do
-- mapa). Periodos com anos inteiros leem estas tabelas; meses soltos, as mensais.
-- ---------------------------------------------------------------------------
PRINT '>> Gerando tabelas anuais (medico x ano)...';
SET @t1 = GETDATE();

DROP TABLE IF EXISTS #crm_medico_ano;

SELECT
    T.nivel,
    T.id_geografico,
    CAST(T.id_medico AS VARCHAR(13)) AS id_medico,
    T.competencia / 100 AS ano,
    SUM(T.nu_prescricoes_mes) AS nu_prescricoes,
    SUM(T.qtd_dias_com_prescricao_mes) AS qtd_dias_com_prescricao,
    COUNT(*) AS qtd_meses_ativos,
    SUM(CASE WHEN T.taxa_dia > L.p95_taxa_dia THEN 1 ELSE 0 END) AS qtd_meses_alta_intensidade
INTO #crm_medico_ano
FROM #crm_medico_mes_territorio T
INNER JOIN #crm_limiar_mes L
    ON L.competencia = T.competencia
GROUP BY T.nivel, T.id_geografico, T.id_medico, T.competencia / 100;

IF EXISTS (
    SELECT 1
    FROM #crm_medico_ano
    WHERE qtd_meses_ativos NOT BETWEEN 1 AND 12
       OR qtd_meses_alta_intensidade > qtd_meses_ativos
       OR qtd_dias_com_prescricao NOT BETWEEN qtd_meses_ativos AND 366
       OR nu_prescricoes < qtd_dias_com_prescricao
)
    THROW 51028, 'Somas anuais por medico com valores invalidos.', 1;

-- Cada linha mensal entra em exatamente uma linha anual (sem perda por falta de P95).
IF (SELECT SUM(CAST(qtd_meses_ativos AS BIGINT)) FROM #crm_medico_ano)
   <> (SELECT COUNT_BIG(*) FROM #crm_medico_mes_territorio)
    THROW 51029, 'Somas anuais por medico nao cobrem todas as linhas mensais.', 1;

CREATE TABLE temp_CGUSC.fp.build_crm_medico_brasil_ano (
    id_medico VARCHAR(13) NOT NULL,
    ano SMALLINT NOT NULL,
    nu_prescricoes INT NOT NULL,
    qtd_dias_com_prescricao SMALLINT NOT NULL,
    qtd_meses_ativos TINYINT NOT NULL,
    qtd_meses_alta_intensidade TINYINT NOT NULL
);

INSERT INTO temp_CGUSC.fp.build_crm_medico_brasil_ano WITH (TABLOCK)
SELECT
    id_medico,
    CAST(ano AS SMALLINT),
    nu_prescricoes,
    CAST(qtd_dias_com_prescricao AS SMALLINT),
    CAST(qtd_meses_ativos AS TINYINT),
    CAST(qtd_meses_alta_intensidade AS TINYINT)
FROM #crm_medico_ano
WHERE nivel = 'brasil';

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMedicoBrasilAno_Key
    ON temp_CGUSC.fp.build_crm_medico_brasil_ano(ano, id_medico);

CREATE TABLE temp_CGUSC.fp.build_crm_medico_territorio_ano (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    id_medico VARCHAR(13) NOT NULL,
    ano SMALLINT NOT NULL,
    nu_prescricoes INT NOT NULL,
    qtd_dias_com_prescricao SMALLINT NOT NULL,
    qtd_meses_ativos TINYINT NOT NULL,
    qtd_meses_alta_intensidade TINYINT NOT NULL
);

INSERT INTO temp_CGUSC.fp.build_crm_medico_territorio_ano WITH (TABLOCK)
SELECT
    CAST(nivel AS VARCHAR(16)),
    CAST(id_geografico AS VARCHAR(20)),
    id_medico,
    CAST(ano AS SMALLINT),
    nu_prescricoes,
    CAST(qtd_dias_com_prescricao AS SMALLINT),
    CAST(qtd_meses_ativos AS TINYINT),
    CAST(qtd_meses_alta_intensidade AS TINYINT)
FROM #crm_medico_ano
WHERE nivel IN ('municipio', 'regiao_saude', 'uf');

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMedicoTerritorioAno_Key
    ON temp_CGUSC.fp.build_crm_medico_territorio_ano(ano, nivel, id_geografico, id_medico);

DROP TABLE #crm_medico_ano;

PRINT '   Tabelas anuais concluidas em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

-- ---------------------------------------------------------------------------
-- Dimensao de medicos (codigo inteiro 0..N-1) e farmacia x medico x ano.
-- Base do indice de bitmaps dos filtros de farmacia; um ano por vez para nao
-- pesar no tempdb.
-- ---------------------------------------------------------------------------
PRINT '>> Gerando dimensao de medicos e farmacia x medico x ano...';
SET @t1 = GETDATE();

CREATE TABLE temp_CGUSC.fp.build_crm_medico_dim (
    id_medico_num INT NOT NULL,
    id_medico VARCHAR(13) NOT NULL,
    CONSTRAINT PK_CrmMedicoDim PRIMARY KEY CLUSTERED (id_medico_num),
    CONSTRAINT UQ_CrmMedicoDim_IdMedico UNIQUE (id_medico)
);

INSERT INTO temp_CGUSC.fp.build_crm_medico_dim WITH (TABLOCK) (id_medico_num, id_medico)
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY M.id_medico) AS INT) - 1,
    CAST(M.id_medico AS VARCHAR(13))
FROM (
    SELECT DISTINCT id_medico
    FROM temp_CGUSC.fp.build_crm_medico_estabelecimento_mes
) M;

CREATE TABLE temp_CGUSC.fp.build_crm_farmacia_medico_ano (
    ano SMALLINT NOT NULL,
    id_medico_num INT NOT NULL,
    id_cnpj INT NOT NULL,
    nu_prescricoes INT NOT NULL,
    CONSTRAINT PK_CrmFarmaciaMedicoAno PRIMARY KEY CLUSTERED (ano, id_medico_num, id_cnpj)
);

DECLARE @ano_fato INT = YEAR(@DataInicio);
WHILE @ano_fato <= YEAR(@DataFim)
BEGIN
    INSERT INTO temp_CGUSC.fp.build_crm_farmacia_medico_ano WITH (TABLOCK) (
        ano, id_medico_num, id_cnpj, nu_prescricoes
    )
    SELECT
        CAST(@ano_fato AS SMALLINT),
        D.id_medico_num,
        E.id_cnpj,
        CAST(SUM(CAST(E.nu_prescricoes_mes AS INT)) AS INT)
    FROM temp_CGUSC.fp.build_crm_medico_estabelecimento_mes E
    INNER JOIN temp_CGUSC.fp.build_crm_medico_dim D
        ON D.id_medico = E.id_medico
    WHERE E.competencia BETWEEN @ano_fato * 100 + 1 AND @ano_fato * 100 + 12
    GROUP BY D.id_medico_num, E.id_cnpj;

    SET @ano_fato = @ano_fato + 1;
END;

-- Mesmo total de prescricoes por ano que a tabela por farmacia (nada perdido
-- no join com a dimensao).
IF EXISTS (
    SELECT 1
    FROM (
        SELECT competencia / 100 AS ano, SUM(CAST(nu_prescricoes_mes AS BIGINT)) AS nu_prescricoes
        FROM temp_CGUSC.fp.build_crm_medico_estabelecimento_mes
        GROUP BY competencia / 100
    ) E
    FULL JOIN (
        SELECT CAST(ano AS INT) AS ano, SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes
        FROM temp_CGUSC.fp.build_crm_farmacia_medico_ano
        GROUP BY ano
    ) F
        ON F.ano = E.ano
    WHERE E.ano IS NULL
       OR F.ano IS NULL
       OR E.nu_prescricoes <> F.nu_prescricoes
)
    THROW 51030, 'Farmacia x medico x ano diverge da tabela por farmacia.', 1;

PRINT '   Dimensao e farmacia x medico x ano concluidas em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

DROP TABLE #crm_medico_mes_territorio;
DROP TABLE #crm_limiar_mes;
DROP TABLE #crm_competencias;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmMedicoBrasilMes_Key
    ON temp_CGUSC.fp.build_crm_medico_brasil_mes(competencia, id_medico);

PRINT '   temp_CGUSC.fp.build_crm_medico_brasil_mes concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

UPDATE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
SET status = 'OK',
    dt_atualizacao = GETDATE(),
    observacao = 'Pre-global finalizado com sucesso.'
WHERE id_pipeline = 1;

-- ============================================================================
-- RESULTADOS
-- ============================================================================
PRINT '==========================================================';
PRINT '   TEMPO TOTAL: ' + CONVERT(VARCHAR(20), GETDATE() - @t0, 114);
PRINT '==========================================================';

EXEC sp_executesql
    N'SELECT
          id_pipeline,
          pipeline_nome,
          pipeline_versao,
          dt_data_inicio,
          dt_data_fim,
          nu_registros,
          status,
          dt_criacao,
          dt_atualizacao,
          observacao
      FROM temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata;';

SELECT
    uf_farmacia,
    pipeline_versao,
    dt_data_inicio,
    dt_data_fim,
    status,
    etapa,
    nu_registros_fonte,
    nu_cnpjs_fonte,
    dt_atualizacao
FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
ORDER BY uf_farmacia;

SELECT
    COUNT(*) AS qtd_medicos_cfm
FROM temp_CGUSC.fp.build_dados_medico;

SELECT
    COUNT(*) AS qtd_medico_competencia,
    COUNT(DISTINCT id_medico) AS qtd_medicos,
    MIN(competencia) AS primeira_competencia,
    MAX(competencia) AS ultima_competencia,
    SUM(CAST(nu_prescricoes_mes AS BIGINT)) AS total_prescricoes
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes;

SELECT TOP 30
    id_medico,
    competencia,
    nu_prescricoes_mes,
    nu_estabelecimentos_mes
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes
ORDER BY nu_prescricoes_mes DESC;

END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    DECLARE @mensagem_erro NVARCHAR(4000);

    SET @mensagem_erro = CONCAT(
        'Erro ', ERROR_NUMBER(),
        ' | Severidade ', ERROR_SEVERITY(),
        ' | Estado ', ERROR_STATE(),
        ' | Linha ', ERROR_LINE(),
        ' | ', ERROR_MESSAGE()
    );

    IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata') IS NOT NULL
    BEGIN
        UPDATE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
        SET status = 'ERRO',
            dt_atualizacao = GETDATE(),
            observacao = LEFT(@mensagem_erro, 400)
        WHERE id_pipeline = 1;
    END;

    PRINT '   ERRO no pre-global CRM.';
    PRINT '   ' + @mensagem_erro;

    THROW;
END CATCH;
