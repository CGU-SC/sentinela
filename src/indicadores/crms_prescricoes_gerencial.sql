-- CRM - PRESCRICOES GERENCIAIS MENSAIS
-- ============================================================================
--
-- Gera a tabela gerencial mensal para o mapa de CRMs.
--
-- Granularidade:
--   uma linha por nivel, localidade e competencia.
--
-- Niveis gerados:
--   municipio, uf e regiao_saude.
--
-- Regra de anomalia:
--   um CRM e anomalio quando sua media mensal ultrapassa 22 prescricoes/dia.
--   O limite e utilizado somente durante o processamento e nao e armazenado.
--
-- A tabela e recriada integralmente em uma unica transacao. Nao ha processamento
-- por lotes nem combinacoes de periodos de competencia.
-- ============================================================================

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @DataInicio DATE = '2015-07-01';
DECLARE @DataFim DATE = '2024-12-31';
DECLARE @LimitePrescricoesDia DECIMAL(19, 6) = 22.000000;

DECLARE @CompetenciaInicio INT = YEAR(@DataInicio) * 100 + MONTH(@DataInicio);
DECLARE @CompetenciaFim INT = YEAR(@DataFim) * 100 + MONTH(@DataFim);

IF @DataInicio IS NULL
   OR @DataFim IS NULL
   OR @DataInicio > @DataFim
BEGIN
    RAISERROR('Periodo invalido.', 16, 1);
    RETURN;
END;

IF @LimitePrescricoesDia <= 0
BEGIN
    RAISERROR('O limite de prescricoes por dia deve ser maior que zero.', 16, 1);
    RETURN;
END;

IF OBJECT_ID(
       'temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes',
       'U'
   ) IS NULL
BEGIN
    RAISERROR(
        'A tabela fonte build_crm_prescricoes_estabelecimento_mes nao existe.',
        16,
        1
    );
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia', 'U') IS NULL
BEGIN
    RAISERROR('A tabela fonte dados_farmacia nao existe.', 16, 1);
    RETURN;
END;

IF COL_LENGTH(
       'temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes',
       'id_cnpj'
   ) IS NULL
   OR COL_LENGTH(
          'temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes',
          'id_medico'
      ) IS NULL
   OR COL_LENGTH(
          'temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes',
          'competencia'
      ) IS NULL
   OR COL_LENGTH(
          'temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes',
          'nu_prescricoes_mes'
      ) IS NULL
BEGIN
    RAISERROR(
        'A tabela mensal nao possui o schema obrigatorio.',
        16,
        1
    );
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'codibge') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'uf') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id_regiao_saude') IS NULL
BEGIN
    RAISERROR(
        'A tabela dados_farmacia nao possui o schema geografico obrigatorio.',
        16,
        1
    );
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
    LEFT JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.id = P.id_cnpj
    WHERE P.competencia BETWEEN @CompetenciaInicio AND @CompetenciaFim
      AND F.id IS NULL
)
BEGIN
    RAISERROR(
        'Existem CNPJs da tabela fonte sem correspondencia em dados_farmacia.',
        16,
        1
    );
    RETURN;
END;

IF EXISTS (
    SELECT F.id
    FROM temp_CGUSC.fp.dados_farmacia F
    GROUP BY F.id
    HAVING COUNT_BIG(*) > 1
)
BEGIN
    RAISERROR(
        'Existem IDs duplicados em dados_farmacia.',
        16,
        1
    );
    RETURN;
END;

IF EXISTS (
    SELECT F.codibge
    FROM temp_CGUSC.fp.dados_farmacia F
    WHERE F.codibge IS NOT NULL
    GROUP BY F.codibge
    HAVING COUNT(DISTINCT UPPER(LTRIM(RTRIM(CAST(F.uf AS VARCHAR(20)))))) > 1
        OR COUNT(DISTINCT CAST(F.id_regiao_saude AS VARCHAR(20))) > 1
)
BEGIN
    RAISERROR(
        'Existem municipios com UF ou regiao de saude inconsistentes em dados_farmacia.',
        16,
        1
    );
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.dados_farmacia F
    WHERE F.codibge IS NULL
       OR F.uf IS NULL
       OR F.id_regiao_saude IS NULL
)
BEGIN
    RAISERROR(
        'Existem registros em dados_farmacia sem geografia obrigatoria.',
        16,
        1
    );
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
    WHERE P.competencia BETWEEN @CompetenciaInicio AND @CompetenciaFim
      AND (
          P.id_medico IS NULL
          OR P.nu_prescricoes_mes IS NULL
          OR P.nu_prescricoes_mes < 0
      )
)
BEGIN
    RAISERROR(
        'Existem registros fonte com CRM nulo ou quantidade de prescricoes nula/negativa.',
        16,
        1
    );
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
    INNER JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.id = P.id_cnpj
    WHERE P.competencia BETWEEN @CompetenciaInicio AND @CompetenciaFim
      AND (
          F.codibge IS NULL
          OR F.uf IS NULL
          OR F.id_regiao_saude IS NULL
      )
)
BEGIN
    RAISERROR(
        'Existem registros fonte sem geografia obrigatoria.',
        16,
        1
    );
    RETURN;
END;

DROP TABLE IF EXISTS #crm_competencias;
DROP TABLE IF EXISTS #crm_base_mensal;
DROP TABLE IF EXISTS #crm_nivel_mensal;
DROP TABLE IF EXISTS #crm_agregado_mensal;
DROP TABLE IF EXISTS #crm_geografias;

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

-- Agrega primeiro por CRM, municipio e competencia.
SELECT
    CAST(P.id_medico AS VARCHAR(50)) AS id_medico,
    CAST(F.codibge AS INT) AS id_ibge7,
    CAST(UPPER(LTRIM(RTRIM(F.uf))) AS VARCHAR(20)) AS uf,
    CAST(F.id_regiao_saude AS INT) AS id_regiao_saude,
    P.competencia,
    CAST(SUM(CAST(P.nu_prescricoes_mes AS BIGINT)) AS BIGINT)
        AS nu_prescricoes_mes
INTO #crm_base_mensal
FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.id = P.id_cnpj
WHERE P.competencia BETWEEN @CompetenciaInicio AND @CompetenciaFim
  AND P.nu_prescricoes_mes > 0
GROUP BY
    P.id_medico,
    F.codibge,
    F.uf,
    F.id_regiao_saude,
    P.competencia;

CREATE CLUSTERED INDEX IDX_CrmBaseMensal
    ON #crm_base_mensal (competencia, id_medico, id_ibge7);

-- Expande o mesmo CRM-mes para os tres niveis geograficos.
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
FROM #crm_base_mensal B

UNION ALL

SELECT
    'uf',
    B.uf,
    B.id_medico,
    B.competencia,
    SUM(B.nu_prescricoes_mes)
FROM #crm_base_mensal B
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
FROM #crm_base_mensal B
GROUP BY
    B.id_regiao_saude,
    B.id_medico,
    B.competencia;

CREATE CLUSTERED INDEX IDX_CrmNivelMensal
    ON #crm_nivel_mensal (
        nivel,
        competencia,
        id_geografico,
        id_medico
    );

-- Agrega os indicadores mensais por nivel e localidade.
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

-- Mantem tambem localidades sem atividade no mes, para o mapa distinguir
-- ausencia de dados de ausencia de anomalia.
CREATE TABLE #crm_geografias (
    nivel VARCHAR(16) NOT NULL,
    id_geografico VARCHAR(20) NOT NULL,
    PRIMARY KEY CLUSTERED (nivel, id_geografico)
);

INSERT INTO #crm_geografias (nivel, id_geografico)
SELECT DISTINCT
    'municipio',
    CAST(F.codibge AS VARCHAR(20))
FROM temp_CGUSC.fp.dados_farmacia F
WHERE F.codibge IS NOT NULL;

INSERT INTO #crm_geografias (nivel, id_geografico)
SELECT DISTINCT
    'uf',
    CAST(UPPER(LTRIM(RTRIM(F.uf))) AS VARCHAR(20))
FROM temp_CGUSC.fp.dados_farmacia F
WHERE F.uf IS NOT NULL;

INSERT INTO #crm_geografias (nivel, id_geografico)
SELECT DISTINCT
    'regiao_saude',
    CAST(F.id_regiao_saude AS VARCHAR(20))
FROM temp_CGUSC.fp.dados_farmacia F
WHERE F.id_regiao_saude IS NOT NULL;

BEGIN TRY
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

        CONSTRAINT PK_CrmPrescricoesGerencial
            PRIMARY KEY CLUSTERED (
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
                    CAST(C.dias_mes AS DECIMAL(19, 6))
                    * A.qtd_crms_ativos,
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
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;

SELECT
    COUNT_BIG(*) AS qtd_registros_gerados,
    COUNT(DISTINCT competencia) AS qtd_competencias,
    COUNT(DISTINCT id_geografico) AS qtd_localidades,
    MIN(competencia) AS competencia_minima,
    MAX(competencia) AS competencia_maxima
FROM temp_CGUSC.fp.build_crm_prescricoes_gerencial;

SELECT TOP (20)
    nivel,
    id_geografico,
    competencia,
    nu_prescricoes_total,
    qtd_crms_ativos,
    qtd_crms_anomalos,
    percentual_crms_anomalos,
    media_prescricoes_dia
FROM temp_CGUSC.fp.build_crm_prescricoes_gerencial
WHERE qtd_crms_anomalos > 0
ORDER BY
    percentual_crms_anomalos DESC,
    qtd_crms_anomalos DESC,
    competencia;
