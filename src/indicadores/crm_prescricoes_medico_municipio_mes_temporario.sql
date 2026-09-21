/*
    Modulo temporario: prescricoes por medico, municipio e mes.

    Objetivo:
      Criar uma tabela gerencial compacta para rankings por Brasil, UF,
      Regiao de Saude ou municipio, sem carregar o cache por CNPJ na API.

    Grao da tabela:
      id_medico + competencia + id_ibge7

    Fonte:
      temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes
      temp_CGUSC.fp.dados_farmacia

    Observacoes:
      - Este script substitui apenas a tabela temporaria de destino.
      - Nao cria arquivo .smod e nao altera o cache da aplicacao.
      - UF, id_regiao_saude e nome do municipio devem ser resolvidos pelo
        modulo de localidades a partir de id_ibge7.
      - dias_mes e taxa_prescricoes_dia sao calculados na consulta gerencial.
      - nu_prescricoes_mes e SMALLINT; a soma intermediaria permanece BIGINT.
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @SourceEstabelecimento sysname = N'temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes';
DECLARE @SourceFarmacia sysname = N'temp_CGUSC.fp.dados_farmacia';

/* Precondicoes estruturais: falhar explicitamente se a fonte nao estiver pronta. */
IF OBJECT_ID(@SourceEstabelecimento, N'U') IS NULL
    THROW 51000, 'Tabela fonte temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes nao encontrada.', 1;

IF OBJECT_ID(@SourceFarmacia, N'U') IS NULL
    THROW 51001, 'Tabela fonte temp_CGUSC.fp.dados_farmacia nao encontrada.', 1;

IF COL_LENGTH(@SourceEstabelecimento, N'id_cnpj') IS NULL
   OR COL_LENGTH(@SourceEstabelecimento, N'id_medico') IS NULL
   OR COL_LENGTH(@SourceEstabelecimento, N'competencia') IS NULL
   OR COL_LENGTH(@SourceEstabelecimento, N'nu_prescricoes_mes') IS NULL
    THROW 51002, 'Tabela de prescricoes por estabelecimento/mes sem as colunas obrigatorias.', 1;

IF COL_LENGTH(@SourceFarmacia, N'id') IS NULL
   OR COL_LENGTH(@SourceFarmacia, N'codibge') IS NULL
    THROW 51003, 'Tabela dados_farmacia sem as colunas obrigatorias id/codibge.', 1;

/*
    A dimensao de farmacias e menor que a fonte de prescricoes. Ela e
    materializada uma vez para evitar conversoes e validacoes repetidas no
    join principal.
*/
IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.dados_farmacia F
    WHERE F.id IS NULL
       OR F.codibge IS NULL
       OR TRY_CONVERT(int, F.codibge) IS NULL
       OR TRY_CONVERT(int, F.codibge) <= 0
)
    THROW 51004, 'dados_farmacia possui id ou codibge invalido.', 1;

IF EXISTS (
    SELECT F.id
    FROM temp_CGUSC.fp.dados_farmacia F
    GROUP BY F.id
    HAVING COUNT_BIG(*) > 1
)
    THROW 51005, 'dados_farmacia possui mais de uma linha para o mesmo estabelecimento.', 1;

DROP TABLE IF EXISTS #FarmaciaMunicipio;

SELECT
    F.id,
    CONVERT(int, F.codibge) AS id_ibge7
INTO #FarmaciaMunicipio
FROM temp_CGUSC.fp.dados_farmacia F;

CREATE UNIQUE CLUSTERED INDEX CUX_FarmaciaMunicipio_id
    ON #FarmaciaMunicipio (id);

/*
    Uma unica pre-validacao percorre a fonte grande. Nenhuma linha invalida
    ou sem correspondencia e descartada silenciosamente.
*/
DECLARE @SourceError nvarchar(2048);

SELECT TOP (1)
    @SourceError = CASE
        WHEN P.id_cnpj IS NULL
            THEN N'Fonte possui id_cnpj nulo.'
        WHEN M.id IS NULL
            THEN N'Existem prescricoes sem correspondencia em dados_farmacia.'
        WHEN P.id_medico IS NULL
          OR NULLIF(LTRIM(RTRIM(CONVERT(varchar(50), P.id_medico))), '') IS NULL
            THEN N'Fonte possui id_medico nulo ou vazio.'
        WHEN P.competencia IS NULL
          OR P.competencia < 190001
          OR P.competencia > 999912
          OR P.competencia % 100 NOT BETWEEN 1 AND 12
            THEN N'Fonte possui competencia invalida.'
        WHEN P.nu_prescricoes_mes IS NULL
          OR P.nu_prescricoes_mes < 0
            THEN N'Fonte possui nu_prescricoes_mes nulo ou negativo.'
    END
FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
LEFT JOIN #FarmaciaMunicipio M
    ON M.id = P.id_cnpj
WHERE P.id_cnpj IS NULL
   OR M.id IS NULL
   OR P.id_medico IS NULL
   OR NULLIF(LTRIM(RTRIM(CONVERT(varchar(50), P.id_medico))), '') IS NULL
   OR P.competencia IS NULL
   OR P.competencia < 190001
   OR P.competencia > 999912
   OR P.competencia % 100 NOT BETWEEN 1 AND 12
   OR P.nu_prescricoes_mes IS NULL
   OR P.nu_prescricoes_mes < 0;

IF @SourceError IS NOT NULL
    THROW 51006, @SourceError, 1;

BEGIN TRY
    BEGIN TRANSACTION;

    DROP TABLE IF EXISTS temp_CGUSC.fp.tmp_crm_prescricoes_medico_municipio_mes;
    DROP TABLE IF EXISTS #crm_prescricoes_medico_municipio_mes_agregado;

    CREATE TABLE temp_CGUSC.fp.tmp_crm_prescricoes_medico_municipio_mes (
        id_medico varchar(50) NOT NULL,
        competencia int NOT NULL,
        id_ibge7 int NOT NULL,
        nu_prescricoes_mes smallint NOT NULL,
        CONSTRAINT PK_tmp_crm_prescricoes_medico_municipio_mes
            PRIMARY KEY CLUSTERED (competencia, id_medico, id_ibge7)
    );

    DECLARE @InsertedRows bigint;

    SELECT
        P.id_medico,
        P.competencia,
        M.id_ibge7,
        SUM(CONVERT(bigint, P.nu_prescricoes_mes)) AS nu_prescricoes_mes
    INTO #crm_prescricoes_medico_municipio_mes_agregado
    FROM temp_CGUSC.fp.build_crm_prescricoes_estabelecimento_mes P
    INNER JOIN #FarmaciaMunicipio M
        ON M.id = P.id_cnpj
    GROUP BY
        P.id_medico,
        P.competencia,
        M.id_ibge7;

    IF EXISTS (
        SELECT 1
        FROM #crm_prescricoes_medico_municipio_mes_agregado
        WHERE nu_prescricoes_mes > 32767
    )
        THROW 51010, 'A tabela medico/municipio/mes ultrapassa o limite do SMALLINT (32767).', 1;

    INSERT INTO temp_CGUSC.fp.tmp_crm_prescricoes_medico_municipio_mes (
        id_medico,
        competencia,
        id_ibge7,
        nu_prescricoes_mes
    )
    SELECT
        id_medico,
        competencia,
        id_ibge7,
        CONVERT(smallint, nu_prescricoes_mes)
    FROM #crm_prescricoes_medico_municipio_mes_agregado;

    SET @InsertedRows = @@ROWCOUNT;

    IF @InsertedRows = 0
        THROW 51009, 'A tabela gerencial temporaria foi criada sem registros.', 1;

    DROP TABLE IF EXISTS #crm_prescricoes_medico_municipio_mes_agregado;

    CREATE NONCLUSTERED INDEX IX_tmp_crm_prescricoes_medico_municipio_mes_geo
        ON temp_CGUSC.fp.tmp_crm_prescricoes_medico_municipio_mes (
            id_ibge7,
            competencia,
            id_medico
        )
        INCLUDE (nu_prescricoes_mes);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;

DROP TABLE IF EXISTS #FarmaciaMunicipio;

/* Resumo para validacao manual da carga. */
SELECT
    COUNT_BIG(*) AS qtd_linhas,
    COUNT(DISTINCT id_medico) AS qtd_medicos,
    COUNT(DISTINCT id_ibge7) AS qtd_municipios,
    COUNT(DISTINCT competencia) AS qtd_competencias,
    SUM(CONVERT(bigint, nu_prescricoes_mes)) AS nu_prescricoes_total
FROM temp_CGUSC.fp.tmp_crm_prescricoes_medico_municipio_mes;

SELECT TOP (20)
    id_medico,
    competencia,
    id_ibge7,
    nu_prescricoes_mes
FROM temp_CGUSC.fp.tmp_crm_prescricoes_medico_municipio_mes
ORDER BY
    competencia DESC,
    nu_prescricoes_mes DESC,
    id_medico,
    id_ibge7;
