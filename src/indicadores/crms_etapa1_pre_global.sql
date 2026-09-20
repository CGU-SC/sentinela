-- ============================================================================
-- PRE-PROCESSAMENTO GLOBAL PARA INDICADOR DE CRMs
-- ============================================================================
-- Este script prepara tabelas globais reutilizaveis pelo fluxo loteado do
-- crms_detalhado_test.sql.
--
-- Saidas persistentes:
--   0. temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata
--      Metadados de versao, periodo e status consumidos pelo script loteado.
--
--   1. temp_CGUSC.fp.build_dados_medico
--      Mapa CFM normalizado por id_medico.
--
--   2. temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes
--      Relacao completa por (id_cnpj, id_medico, competencia), com o total
--      mensal de prescricoes do medico no estabelecimento.
--
--   3. temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos
--      Totais nacionais por (id_medico, competencia), equivalentes ao antigo
--      #prescricoes_todos_estabelecimentos.
--
--   4. temp_CGUSC.fp.build_crm_prescricoes_gerencial
--      Indicadores mensais por nivel geografico, destinados ao mapa gerencial
--      de prescricoes por dia.
--
-- Observacao:
--   build_alertas_crm_geografico e benchmarks dependem de build_dados_crm_detalhado
--   completo, entao ficam para o script pos-global.
-- ============================================================================

SET NOCOUNT ON;

DECLARE @DataInicio DATE = '2015-07-01';
DECLARE @DataFim    DATE = '2024-12-31';
DECLARE @LimitePrescricoesDia DECIMAL(19, 6) = 22.000000;
DECLARE @t0         DATETIME = GETDATE();
DECLARE @t1         DATETIME;
DECLARE @pipeline_nome   VARCHAR(80) = 'crms_detalhado_pre_global';
DECLARE @pipeline_versao VARCHAR(40) = 'v5_2026_09_19';
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

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata;

CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata (
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
    CONSTRAINT PK_BuildCrmDetalhadoPreGlobalMetadata PRIMARY KEY CLUSTERED (id_pipeline),
    CONSTRAINT CK_BuildCrmDetalhadoPreGlobalMetadata_Id CHECK (id_pipeline = 1)
);

EXEC sp_executesql
    N'INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata
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
--   1. conta autorizacoes por (cnpj, medico, competencia);
--   2. soma esses totais para (medico, competencia e municipio);
--   3. expande os dados para UF e regiao de saude;
--   4. materializa os indicadores mensais do mapa.
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

SELECT
    CAST(M.cnpj AS CHAR(14)) AS nu_cnpj,
    CAST(CAST(M.crm AS VARCHAR(10)) + '/' + M.crm_uf AS VARCHAR(13)) AS id_medico,
    YEAR(M.data_hora) * 100 + MONTH(M.data_hora) AS competencia,
    COUNT(DISTINCT M.num_autorizacao) AS nu_prescricoes_medico
INTO #base_crm_cnpj
FROM (
    SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, valor_pago, qnt_autorizada, codigo_barra
    FROM db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP
    UNION ALL
    SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, valor_pago, qnt_autorizada, codigo_barra
    FROM db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024
) M
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
GROUP BY
    M.cnpj,
    M.crm,
    M.crm_uf,
    YEAR(M.data_hora),
    MONTH(M.data_hora);

CREATE CLUSTERED INDEX IDX_BaseCrmCnpj
    ON #base_crm_cnpj(nu_cnpj, id_medico, competencia);

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

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos;

SELECT
    CAST(F.id AS INT) AS id_cnpj,
    B.id_medico,
    B.competencia,
    CAST(B.nu_prescricoes_medico AS SMALLINT) AS nu_prescricoes_mes
INTO temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes
FROM #base_crm_cnpj B
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.cnpj = B.nu_cnpj;

CREATE CLUSTERED INDEX IDX_CrmPrescEstabMes_Key
    ON temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes(id_cnpj, id_medico, competencia);

CREATE NONCLUSTERED INDEX IDX_CrmPrescEstabMes_Medico
    ON temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes(id_medico, competencia, id_cnpj);

DROP TABLE IF EXISTS #crm_prescricoes_medico_municipio_mes;
DROP TABLE IF EXISTS #crm_competencias;
DROP TABLE IF EXISTS #crm_nivel_mensal;
DROP TABLE IF EXISTS #crm_agregado_mensal;
DROP TABLE IF EXISTS #crm_geografias;

SELECT
    P.id_medico,
    P.competencia,
    CAST(F.codibge AS INT) AS id_ibge7,
    CAST(UPPER(LTRIM(RTRIM(F.uf))) AS VARCHAR(20)) AS uf,
    CAST(F.id_regiao_saude AS INT) AS id_regiao_saude,
    CAST(SUM(CAST(P.nu_prescricoes_mes AS BIGINT)) AS BIGINT)
        AS nu_prescricoes_mes
INTO #crm_prescricoes_medico_municipio_mes
FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.id = P.id_cnpj
GROUP BY
    P.id_medico,
    P.competencia,
    F.codibge,
    F.uf,
    F.id_regiao_saude;

CREATE CLUSTERED INDEX IDX_CrmPrescGerencialBase
    ON #crm_prescricoes_medico_municipio_mes (competencia, id_medico, id_ibge7);

CREATE TABLE #crm_competencias (
    competencia INT NOT NULL,
    competencia_data DATE NOT NULL,
    dias_mes TINYINT NOT NULL,
    PRIMARY KEY CLUSTERED (competencia)
);

;WITH Meses AS (
    SELECT DATEFROMPARTS(YEAR(@DataInicio), MONTH(@DataInicio), 1)
        AS competencia_data

    UNION ALL

    SELECT DATEADD(MONTH, 1, competencia_data)
    FROM Meses
    WHERE competencia_data <
        DATEFROMPARTS(YEAR(@DataFim), MONTH(@DataFim), 1)
)
INSERT INTO #crm_competencias (
    competencia,
    competencia_data,
    dias_mes
)
SELECT
    YEAR(competencia_data) * 100 + MONTH(competencia_data),
    competencia_data,
    DAY(EOMONTH(competencia_data))
FROM Meses
OPTION (MAXRECURSION 0);

CREATE TABLE #crm_nivel_mensal (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    id_medico VARCHAR(50) NOT NULL,
    competencia INT NOT NULL,
    nu_prescricoes_mes BIGINT NOT NULL
);

INSERT INTO #crm_nivel_mensal (
    nivel,
    id_geografico,
    id_medico,
    competencia,
    nu_prescricoes_mes
)
SELECT
    'municipio',
    CAST(B.id_ibge7 AS VARCHAR(20)),
    B.id_medico,
    B.competencia,
    B.nu_prescricoes_mes
FROM #crm_prescricoes_medico_municipio_mes B

UNION ALL

SELECT
    'uf',
    B.uf,
    B.id_medico,
    B.competencia,
    SUM(B.nu_prescricoes_mes)
FROM #crm_prescricoes_medico_municipio_mes B
GROUP BY
    B.uf,
    B.id_medico,
    B.competencia

UNION ALL

SELECT
    'regiao_saude',
    CAST(B.id_regiao_saude AS VARCHAR(20)),
    B.id_medico,
    B.competencia,
    SUM(B.nu_prescricoes_mes)
FROM #crm_prescricoes_medico_municipio_mes B
GROUP BY
    B.id_regiao_saude,
    B.id_medico,
    B.competencia;

CREATE CLUSTERED INDEX IDX_CrmPrescNivelMensal
    ON #crm_nivel_mensal (nivel, competencia, id_geografico, id_medico);

SELECT
    N.nivel,
    N.id_geografico,
    N.competencia,
    CAST(SUM(N.nu_prescricoes_mes) AS BIGINT) AS nu_prescricoes_total,
    COUNT_BIG(*) AS qtd_crms_ativos,
    SUM(
        CASE
            WHEN N.nu_prescricoes_mes /
                NULLIF(CAST(C.dias_mes AS DECIMAL(19, 6)), 0)
                > @LimitePrescricoesDia
            THEN CAST(1 AS BIGINT)
            ELSE CAST(0 AS BIGINT)
        END
    ) AS qtd_crms_anomalos
INTO #crm_agregado_mensal
FROM #crm_nivel_mensal N
INNER JOIN #crm_competencias C
    ON C.competencia = N.competencia
GROUP BY
    N.nivel,
    N.id_geografico,
    N.competencia;

CREATE CLUSTERED INDEX IDX_CrmAgregadoMensal
    ON #crm_agregado_mensal (nivel, id_geografico, competencia);

CREATE TABLE #crm_geografias (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    PRIMARY KEY CLUSTERED (nivel, id_geografico)
);

INSERT INTO #crm_geografias (nivel, id_geografico)
SELECT DISTINCT 'municipio', CAST(F.codibge AS VARCHAR(20))
FROM temp_CGUSC.fp.dados_farmacia F;

INSERT INTO #crm_geografias (nivel, id_geografico)
SELECT DISTINCT 'uf', CAST(UPPER(LTRIM(RTRIM(F.uf))) AS VARCHAR(20))
FROM temp_CGUSC.fp.dados_farmacia F;

INSERT INTO #crm_geografias (nivel, id_geografico)
SELECT DISTINCT 'regiao_saude', CAST(F.id_regiao_saude AS VARCHAR(20))
FROM temp_CGUSC.fp.dados_farmacia F;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_gerencial;

CREATE TABLE temp_CGUSC.fp.build_crm_prescricoes_gerencial (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    competencia INT NOT NULL,
    nu_prescricoes_total BIGINT NOT NULL,
    qtd_crms_ativos INT NOT NULL,
    qtd_crms_anomalos INT NOT NULL,
    percentual_crms_anomalos DECIMAL(19, 6) NULL,
    media_prescricoes_dia DECIMAL(19, 6) NULL,
    CONSTRAINT PK_CrmPrescricoesGerencial PRIMARY KEY CLUSTERED (
        nivel,
        id_geografico,
        competencia
    )
);

INSERT INTO temp_CGUSC.fp.build_crm_prescricoes_gerencial (
    nivel,
    id_geografico,
    competencia,
    nu_prescricoes_total,
    qtd_crms_ativos,
    qtd_crms_anomalos,
    percentual_crms_anomalos,
    media_prescricoes_dia
)
SELECT
    G.nivel,
    G.id_geografico,
    C.competencia,
    COALESCE(A.nu_prescricoes_total, 0),
    COALESCE(CAST(A.qtd_crms_ativos AS INT), 0),
    COALESCE(CAST(A.qtd_crms_anomalos AS INT), 0),
    CASE
        WHEN COALESCE(A.qtd_crms_ativos, 0) = 0 THEN NULL
        ELSE CAST(
            100.0 * A.qtd_crms_anomalos /
            NULLIF(A.qtd_crms_ativos, 0)
            AS DECIMAL(19, 6)
        )
    END,
    CASE
        WHEN COALESCE(A.qtd_crms_ativos, 0) = 0 THEN NULL
        ELSE CAST(
            A.nu_prescricoes_total /
            NULLIF(
                CAST(C.dias_mes AS DECIMAL(19, 6)) * A.qtd_crms_ativos,
                0
            )
            AS DECIMAL(19, 6)
        )
    END
FROM #crm_geografias G
CROSS JOIN #crm_competencias C
LEFT JOIN #crm_agregado_mensal A
    ON A.nivel = G.nivel
   AND A.id_geografico = G.id_geografico
   AND A.competencia = C.competencia;

COMMIT TRANSACTION;

PRINT '   temp_CGUSC.fp.build_crm_prescricoes_gerencial mensal concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

SELECT
    id_medico,
    competencia,
    CAST(SUM(nu_prescricoes_mes) AS SMALLINT) AS nu_prescricoes_medico_em_todos_estabelecimentos,
    CAST(COUNT(DISTINCT id_cnpj) AS SMALLINT) AS nu_estabelecimentos_com_registro_mesmo_crm
INTO temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos
FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes
GROUP BY id_medico, competencia;

CREATE CLUSTERED INDEX IDX_CrmPrescTodos_Key
    ON temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos(id_medico, competencia);

PRINT '   temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

UPDATE temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata
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
      FROM temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata;';

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
    SUM(nu_prescricoes_medico_em_todos_estabelecimentos) AS total_prescricoes
FROM temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos;

SELECT TOP 30
    id_medico,
    competencia,
    nu_prescricoes_medico_em_todos_estabelecimentos,
    nu_estabelecimentos_com_registro_mesmo_crm
FROM temp_CGUSC.fp.build_crm_prescricoes_todos_estabelecimentos
ORDER BY nu_prescricoes_medico_em_todos_estabelecimentos DESC;

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

    IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata') IS NOT NULL
    BEGIN
        UPDATE temp_CGUSC.fp.build_crm_detalhado_pre_global_metadata
        SET status = 'ERRO',
            dt_atualizacao = GETDATE(),
            observacao = LEFT(@mensagem_erro, 400)
        WHERE id_pipeline = 1;
    END;

    PRINT '   ERRO no pre-global CRM.';
    PRINT '   ' + @mensagem_erro;

    THROW;
END CATCH;
