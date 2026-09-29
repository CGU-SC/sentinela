-- ============================================================================
-- TEMPORARIO - RETOMADA DO PRE-GLOBAL CRM, ANO A ANO (LOOP AUTOMATICO)
-- ============================================================================
-- Gera as tabelas finais da etapa 1 que nao chegaram a ser gravadas:
--   * temp_CGUSC.fp.build_crm_medico_brasil_mes
--   * temp_CGUSC.fp.build_crm_medico_territorio_mes
--   * temp_CGUSC.fp.build_crm_medico_brasil_ano      (somas por medico x ano)
--   * temp_CGUSC.fp.build_crm_medico_territorio_ano  (somas por territorio x medico x ano)
--   * temp_CGUSC.fp.build_crm_medico_dim              (id_medico -> id_medico_num)
--   * temp_CGUSC.fp.build_crm_farmacia_medico_ano     (prescricoes por farmacia x medico x ano)
-- As tabelas anuais aceleram o ranking de medicos: anos inteiros do periodo
-- sao lidos delas e os meses soltos continuam nas mensais. A dimensao e a
-- farmacia x medico x ano alimentam o indice de bitmaps dos filtros de farmacia
-- da tela de analises (montado na sincronizacao).
--
-- COMO USAR
--   1. Ajuste @AnoInicial e @AnoFinal abaixo (padrao: 2015 a 2024) e execute.
--      O script processa um ano de cada vez, em sequencia.
--   2. Depois que terminar, execute crms_etapa1b_finalizar.sql.
--
-- CADA ANO E INDEPENDENTE
--   Todo o processamento intermediario fica em #temporarias (tempdb) e contem
--   apenas o ano da vez; elas sao apagadas ao fim de cada ano, entao o tempdb
--   nao acumula entre anos. No temp_CGUSC so e gravado o resultado final do
--   ano, numa unica transacao: se der erro, nada do ano fica gravado pela metade.
--
-- SE DER ERRO OU FOR INTERROMPIDO
--   Os anos ja concluidos continuam gravados. Basta executar o script de novo,
--   sem mudar nada: anos ja gravados sao pulados e ele segue do ano que falhou.
--   As mensagens de progresso aparecem na hora (aba Messages do SSMS).
--
-- Se precisar refazer um ano ja gravado:
--   DELETE FROM temp_CGUSC.fp.build_crm_medico_brasil_mes
--   WHERE competencia BETWEEN <ano>01 AND <ano>12;
--   DELETE FROM temp_CGUSC.fp.build_crm_medico_territorio_mes
--   WHERE competencia BETWEEN <ano>01 AND <ano>12;
--   DELETE FROM temp_CGUSC.fp.build_crm_medico_brasil_ano WHERE ano = <ano>;
--   DELETE FROM temp_CGUSC.fp.build_crm_medico_territorio_ano WHERE ano = <ano>;
--   DELETE FROM temp_CGUSC.fp.build_crm_farmacia_medico_ano WHERE ano = <ano>;
--   (a dimensao de medicos nao e apagada: os codigos ja dados continuam validos)
--
-- Excluir este arquivo e crms_etapa1b_finalizar.sql quando a etapa 1 voltar a
-- ser executada inteira.
-- ============================================================================

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @AnoInicial INT = 2015;   -- <<< primeiro ano a processar
DECLARE @AnoFinal   INT = 2024;   -- <<< ultimo ano a processar

-- Devem ser iguais aos da execucao interrompida (conferidos na metadata).
DECLARE @DataInicio DATE = '2015-07-01';
DECLARE @DataFim    DATE = '2024-12-31';

DECLARE @Ano INT = NULL;
DECLARE @tInicio DATETIME = GETDATE();
DECLARE @t0 DATETIME;
DECLARE @t1 DATETIME;
DECLARE @IniAno DATE;
DECLARE @FimAno DATE;
DECLARE @CompIni INT;
DECLARE @CompFim INT;
DECLARE @tabelas_com_ano INT;
DECLARE @proximo_id_medico INT;
DECLARE @Msg NVARCHAR(2000);
DECLARE @resumo TABLE (ano INT NOT NULL, situacao VARCHAR(30) NOT NULL, tempo VARCHAR(20) NULL);

BEGIN TRY

SET @Msg = '>> [RETOMADA PRE-GLOBAL CRM] Anos ' + CAST(@AnoInicial AS VARCHAR(4)) + ' a '
    + CAST(@AnoFinal AS VARCHAR(4)) + ' - conferindo pre-requisitos...';
RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

IF @AnoInicial > @AnoFinal
   OR @AnoInicial < YEAR(@DataInicio)
   OR @AnoFinal > YEAR(@DataFim)
    THROW 51105, 'Anos fora do periodo da etapa 1 (ou @AnoInicial maior que @AnoFinal).', 1;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_dados_medico') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_estabelecimento_mes') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_limiar_p95_mes') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_mapa_municipio_regiao_periodo') IS NULL
   OR OBJECT_ID('temp_CGUSC.fp.build_crm_mapa_uf_periodo') IS NULL
    THROW 51100, 'Retomada impossivel: falta alguma saida anterior da etapa 1 (com nome build_). Execute a etapa 1 inteira.', 1;

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
    WHERE id_pipeline = 1
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
)
    THROW 51101, 'Periodo da retomada diferente do periodo da execucao interrompida (metadata).', 1;

-- Tabelas finais: criadas vazias na primeira execucao e preenchidas ano a ano.
IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_mes') IS NULL
    CREATE TABLE temp_CGUSC.fp.build_crm_medico_brasil_mes (
        id_medico VARCHAR(13) NOT NULL,
        competencia INT NOT NULL,
        nu_prescricoes_mes SMALLINT NOT NULL,
        qtd_dias_com_prescricao_mes TINYINT NOT NULL,
        nu_estabelecimentos_mes SMALLINT NOT NULL,
        CONSTRAINT PK_CrmMedicoBrasilMes
            PRIMARY KEY CLUSTERED (competencia, id_medico)
    );

IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_territorio_mes') IS NULL
    CREATE TABLE temp_CGUSC.fp.build_crm_medico_territorio_mes (
        nivel VARCHAR(16) NOT NULL,
        id_geografico VARCHAR(20) NOT NULL,
        id_medico VARCHAR(13) NOT NULL,
        competencia INT NOT NULL,
        nu_prescricoes_mes SMALLINT NOT NULL,
        qtd_dias_com_prescricao_mes TINYINT NOT NULL,
        CONSTRAINT PK_CrmMedicoTerritorioMes
            PRIMARY KEY CLUSTERED (competencia, nivel, id_geografico, id_medico)
    );

IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_ano') IS NULL
    CREATE TABLE temp_CGUSC.fp.build_crm_medico_brasil_ano (
        id_medico VARCHAR(13) NOT NULL,
        ano SMALLINT NOT NULL,
        nu_prescricoes INT NOT NULL,
        qtd_dias_com_prescricao SMALLINT NOT NULL,
        qtd_meses_ativos TINYINT NOT NULL,
        qtd_meses_alta_intensidade TINYINT NOT NULL,
        CONSTRAINT PK_CrmMedicoBrasilAno
            PRIMARY KEY CLUSTERED (ano, id_medico)
    );

IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_territorio_ano') IS NULL
    CREATE TABLE temp_CGUSC.fp.build_crm_medico_territorio_ano (
        nivel VARCHAR(16) NOT NULL,
        id_geografico VARCHAR(20) NOT NULL,
        id_medico VARCHAR(13) NOT NULL,
        ano SMALLINT NOT NULL,
        nu_prescricoes INT NOT NULL,
        qtd_dias_com_prescricao SMALLINT NOT NULL,
        qtd_meses_ativos TINYINT NOT NULL,
        qtd_meses_alta_intensidade TINYINT NOT NULL,
        CONSTRAINT PK_CrmMedicoTerritorioAno
            PRIMARY KEY CLUSTERED (ano, nivel, id_geografico, id_medico)
    );

-- Dimensao de medicos: codigo inteiro denso (0, 1, 2, ...) para o indice de
-- bitmaps. Cresce a cada ano com os medicos ainda sem codigo.
IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_dim') IS NULL
    CREATE TABLE temp_CGUSC.fp.build_crm_medico_dim (
        id_medico_num INT NOT NULL,
        id_medico VARCHAR(13) NOT NULL,
        CONSTRAINT PK_CrmMedicoDim PRIMARY KEY CLUSTERED (id_medico_num),
        CONSTRAINT UQ_CrmMedicoDim_IdMedico UNIQUE (id_medico)
    );

IF OBJECT_ID('temp_CGUSC.fp.build_crm_farmacia_medico_ano') IS NULL
    CREATE TABLE temp_CGUSC.fp.build_crm_farmacia_medico_ano (
        ano SMALLINT NOT NULL,
        id_medico_num INT NOT NULL,
        id_cnpj INT NOT NULL,
        nu_prescricoes INT NOT NULL,
        CONSTRAINT PK_CrmFarmaciaMedicoAno
            PRIMARY KEY CLUSTERED (ano, id_medico_num, id_cnpj)
    );

-- Uma tabela ja existente precisa ter o schema desta retomada (evita misturar
-- com sobras de execucoes antigas).
IF COL_LENGTH('temp_CGUSC.fp.build_crm_medico_brasil_mes', 'nu_estabelecimentos_mes') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.build_crm_medico_brasil_mes', 'qtd_dias_com_prescricao_mes') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.build_crm_medico_territorio_mes', 'nivel') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.build_crm_medico_territorio_mes', 'qtd_dias_com_prescricao_mes') IS NULL
   OR NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.sys.key_constraints
        WHERE name = 'PK_CrmMedicoBrasilMes'
          AND parent_object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_mes'))
   OR NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.sys.key_constraints
        WHERE name = 'PK_CrmMedicoTerritorioMes'
          AND parent_object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_medico_territorio_mes'))
   OR COL_LENGTH('temp_CGUSC.fp.build_crm_medico_brasil_ano', 'qtd_meses_alta_intensidade') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.build_crm_medico_territorio_ano', 'qtd_meses_alta_intensidade') IS NULL
   OR NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.sys.key_constraints
        WHERE name = 'PK_CrmMedicoBrasilAno'
          AND parent_object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_ano'))
   OR NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.sys.key_constraints
        WHERE name = 'PK_CrmMedicoTerritorioAno'
          AND parent_object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_medico_territorio_ano'))
   OR NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.sys.key_constraints
        WHERE name = 'PK_CrmMedicoDim'
          AND parent_object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_medico_dim'))
   OR NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.sys.key_constraints
        WHERE name = 'PK_CrmFarmaciaMedicoAno'
          AND parent_object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_farmacia_medico_ano'))
    THROW 51106, 'Tabelas build_crm_medico_* / build_crm_farmacia_medico_ano existem com estrutura antiga. Apague todas (DROP TABLE) e comece de novo pelo primeiro ano.', 1;

-- ============================================================================
-- LOOP: um ano por vez
-- ============================================================================
SET @Ano = @AnoInicial - 1;

WHILE @Ano < @AnoFinal
BEGIN
    SET @Ano = @Ano + 1;
    SET @t0 = GETDATE();

    SET @Msg = '>> [RETOMADA PRE-GLOBAL CRM] Ano ' + CAST(@Ano AS VARCHAR(4)) + ' - conferindo...';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

    SET @IniAno = CASE WHEN DATEFROMPARTS(@Ano, 1, 1) < @DataInicio
                       THEN @DataInicio ELSE DATEFROMPARTS(@Ano, 1, 1) END;
    SET @FimAno = CASE WHEN DATEFROMPARTS(@Ano, 12, 31) > @DataFim
                       THEN @DataFim ELSE DATEFROMPARTS(@Ano, 12, 31) END;
    SET @CompIni = YEAR(@IniAno) * 100 + MONTH(@IniAno);
    SET @CompFim = YEAR(@FimAno) * 100 + MONTH(@FimAno);

    IF NOT EXISTS (
        SELECT 1
        FROM temp_CGUSC.fp.build_crm_medico_estabelecimento_mes
        WHERE competencia BETWEEN @CompIni AND @CompFim
    )
        THROW 51102, 'build_crm_medico_estabelecimento_mes nao tem dados deste ano.', 1;

    -- Ano ja gravado nas 5 tabelas: pula. Gravado so em parte: para (so acontece
    -- com sobra de versao antiga do script; apague o ano antes, ver cabecalho).
    SET @tabelas_com_ano =
          IIF(EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_medico_brasil_mes
                      WHERE competencia BETWEEN @CompIni AND @CompFim), 1, 0)
        + IIF(EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_medico_territorio_mes
                      WHERE competencia BETWEEN @CompIni AND @CompFim), 1, 0)
        + IIF(EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_medico_brasil_ano WHERE ano = @Ano), 1, 0)
        + IIF(EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_medico_territorio_ano WHERE ano = @Ano), 1, 0)
        + IIF(EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_farmacia_medico_ano WHERE ano = @Ano), 1, 0);

    IF @tabelas_com_ano BETWEEN 1 AND 4
    BEGIN
        SET @Msg = CONCAT('Ano ', @Ano, ' gravado so em ', @tabelas_com_ano,
            ' das 5 tabelas finais (sobra de execucao antiga). Apague o ano (instrucoes no cabecalho) e rode de novo.');
        THROW 51107, @Msg, 1;
    END;

    IF @tabelas_com_ano = 5
    BEGIN
        SET @Msg = '   Ano ' + CAST(@Ano AS VARCHAR(4)) + ' ja gravado: pulando.';
        RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
        INSERT INTO @resumo (ano, situacao, tempo) VALUES (@Ano, 'ja gravado (pulado)', NULL);
        CONTINUE;
    END;


    UPDATE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
    SET status = 'PROCESSANDO',
        dt_atualizacao = GETDATE(),
        observacao = 'Retomada por ano: processando ' + CAST(@Ano AS VARCHAR(4)) + '.'
    WHERE id_pipeline = 1;

    -- ============================================================================
    -- 1. Prescricoes por CNPJ, medico e DATA no ano (mesmas regras da etapa 1)
    -- ============================================================================
    SET @Msg = '>> Lendo a movimentacao do ano ate o nivel de dia...';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @t1 = GETDATE();

    DROP TABLE IF EXISTS #base_crm_cnpj_autorizacoes_dia;
    DROP TABLE IF EXISTS #base_crm_cnpj_dia;

    SELECT DISTINCT
        CAST(M.cnpj AS CHAR(14)) AS nu_cnpj,
        CAST(CAST(M.crm AS VARCHAR(10)) + '/' + M.crm_uf AS VARCHAR(13)) AS id_medico,
        YEAR(M.data_hora) * 100 + MONTH(M.data_hora) AS competencia,
        CAST(M.data_hora AS DATE) AS dt_prescricao,
        M.num_autorizacao
    INTO #base_crm_cnpj_autorizacoes_dia
    FROM (
        SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, qnt_autorizada, codigo_barra
        FROM db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP
        UNION ALL
        SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, qnt_autorizada, codigo_barra
        FROM db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024
    ) M
    WHERE M.crm_uf IS NOT NULL
      AND M.crm IS NOT NULL
      AND M.crm_uf <> 'BR'
      AND M.data_hora >= @IniAno
      AND M.data_hora < DATEADD(DAY, 1, @FimAno)
      AND M.num_autorizacao IS NOT NULL
      AND M.qnt_autorizada IS NOT NULL
      AND EXISTS (
          SELECT 1
          FROM temp_CGUSC.fp.medicamentos_patologia PAT
          WHERE PAT.codigo_barra = M.codigo_barra
            AND TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0)) IS NOT NULL
            AND TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0)) <> 0
            AND (M.qnt_autorizada / TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0))) <> 0
      );

    CREATE CLUSTERED INDEX IDX_RetomadaAutorizacoesDia
        ON #base_crm_cnpj_autorizacoes_dia
           (nu_cnpj, id_medico, competencia, num_autorizacao, dt_prescricao);

    IF EXISTS (
        SELECT 1
        FROM #base_crm_cnpj_autorizacoes_dia
        GROUP BY nu_cnpj, id_medico, competencia, num_autorizacao
        HAVING COUNT_BIG(*) > 1
    )
        THROW 51011, 'Prescricoes diarias divergem do total mensal: autorizacao em datas diferentes ou fonte inconsistente.', 1;

    SELECT
        nu_cnpj,
        id_medico,
        competencia,
        dt_prescricao,
        COUNT_BIG(*) AS nu_prescricoes_medico
    INTO #base_crm_cnpj_dia
    FROM #base_crm_cnpj_autorizacoes_dia
    GROUP BY nu_cnpj, id_medico, competencia, dt_prescricao;

    DROP TABLE #base_crm_cnpj_autorizacoes_dia;

    CREATE CLUSTERED INDEX IDX_RetomadaCnpjDia
        ON #base_crm_cnpj_dia(nu_cnpj, id_medico, competencia, dt_prescricao);

    SET @Msg = '   Movimentacao do ano concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

    -- ============================================================================
    -- 2. Conferencia contra build_crm_medico_estabelecimento_mes (so este ano)
    -- ============================================================================
    SET @Msg = '>> Conferindo com build_crm_medico_estabelecimento_mes...';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @t1 = GETDATE();

    DROP TABLE IF EXISTS #retomada_cnpj_mes;
    DROP TABLE IF EXISTS #estabelecimento_mes_ano;

    SELECT
        CAST(F.id AS INT) AS id_cnpj,
        D.id_medico,
        D.competencia,
        SUM(D.nu_prescricoes_medico) AS nu_prescricoes_mes,
        COUNT_BIG(*) AS qtd_dias_com_prescricao_mes
    INTO #retomada_cnpj_mes
    FROM #base_crm_cnpj_dia D
    INNER JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.cnpj = D.nu_cnpj
    GROUP BY CAST(F.id AS INT), D.id_medico, D.competencia;

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaCnpjMes
        ON #retomada_cnpj_mes(id_cnpj, id_medico, competencia);

    SELECT
        E.id_cnpj,
        E.id_medico,
        E.competencia,
        E.nu_prescricoes_mes,
        E.qtd_dias_com_prescricao_mes
    INTO #estabelecimento_mes_ano
    FROM temp_CGUSC.fp.build_crm_medico_estabelecimento_mes E
    WHERE E.competencia BETWEEN @CompIni AND @CompFim;

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaEstabelecimentoMesAno
        ON #estabelecimento_mes_ano(id_cnpj, id_medico, competencia);

    IF EXISTS (
        SELECT 1
        FROM #retomada_cnpj_mes R
        FULL JOIN #estabelecimento_mes_ano E
            ON E.id_cnpj = R.id_cnpj
           AND E.id_medico = R.id_medico
           AND E.competencia = R.competencia
        WHERE R.id_cnpj IS NULL
           OR E.id_cnpj IS NULL
           OR R.nu_prescricoes_mes <> E.nu_prescricoes_mes
           OR R.qtd_dias_com_prescricao_mes <> E.qtd_dias_com_prescricao_mes
    )
        THROW 51104, 'A releitura do ano diverge de build_crm_medico_estabelecimento_mes. Execute a etapa 1 inteira.', 1;

    DROP TABLE #estabelecimento_mes_ano;

    -- Estabelecimentos e total por medico/mes. A releitura acabou de ser conferida
    -- linha a linha contra build_crm_medico_estabelecimento_mes, entao pode ser
    -- usada no lugar dela.
    DROP TABLE IF EXISTS #crm_estabelecimentos_medico_mes;

    SELECT
        id_medico,
        competencia,
        COUNT_BIG(*) AS nu_estabelecimentos_mes,
        SUM(CAST(nu_prescricoes_mes AS BIGINT)) AS nu_prescricoes_estabelecimentos
    INTO #crm_estabelecimentos_medico_mes
    FROM #retomada_cnpj_mes
    GROUP BY id_medico, competencia;

    -- Farmacia x medico no ano (base do indice de bitmaps dos filtros de farmacia).
    DROP TABLE IF EXISTS #crm_farmacia_medico_ano;

    SELECT
        id_cnpj,
        id_medico,
        SUM(nu_prescricoes_mes) AS nu_prescricoes
    INTO #crm_farmacia_medico_ano
    FROM #retomada_cnpj_mes
    GROUP BY id_cnpj, id_medico;

    DROP TABLE #retomada_cnpj_mes;

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaEstabelecimentosMedicoMes
        ON #crm_estabelecimentos_medico_mes(id_medico, competencia);

    SET @Msg = '   Conferencia concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

    -- ============================================================================
    -- 3. Medico x data em municipio -> regiao / UF -> Brasil
    -- ============================================================================
    SET @Msg = '>> Agregando por territorio...';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @t1 = GETDATE();

    DROP TABLE IF EXISTS #crm_municipio_geo;
    DROP TABLE IF EXISTS #crm_dia_municipio;
    DROP TABLE IF EXISTS #crm_dia_regiao;
    DROP TABLE IF EXISTS #crm_dia_uf;
    DROP TABLE IF EXISTS #crm_dia_brasil;
    DROP TABLE IF EXISTS #crm_medico_mes_territorio;

    SELECT DISTINCT
        CAST(F.codibge AS VARCHAR(20)) AS id_municipio,
        CAST(F.id_regiao_saude AS VARCHAR(20)) AS id_regiao_saude,
        CAST(UPPER(LTRIM(RTRIM(F.uf))) AS VARCHAR(2)) AS uf
    INTO #crm_municipio_geo
    FROM temp_CGUSC.fp.dados_farmacia F;

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaMunicipioGeo
        ON #crm_municipio_geo(id_municipio);

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

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaDiaMunicipio
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

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaDiaUf
        ON #crm_dia_uf(id_medico, competencia, dt_prescricao, uf);

    SELECT
        U.id_medico,
        U.competencia,
        U.dt_prescricao,
        SUM(U.nu_prescricoes_dia) AS nu_prescricoes_dia
    INTO #crm_dia_brasil
    FROM #crm_dia_uf U
    GROUP BY U.id_medico, U.competencia, U.dt_prescricao;

    CREATE TABLE #crm_medico_mes_territorio (
        nivel VARCHAR(16) NOT NULL,
        id_geografico VARCHAR(20) NOT NULL,
        id_medico VARCHAR(13) NOT NULL,
        competencia INT NOT NULL,
        nu_prescricoes_mes INT NOT NULL,
        qtd_dias_com_prescricao_mes INT NOT NULL
    );

    INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
    SELECT 'municipio', id_municipio, id_medico, competencia, SUM(nu_prescricoes_dia), COUNT(*)
    FROM #crm_dia_municipio
    GROUP BY id_municipio, id_medico, competencia;

    DROP TABLE #crm_dia_municipio;

    INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
    SELECT 'regiao_saude', id_regiao_saude, id_medico, competencia, SUM(nu_prescricoes_dia), COUNT(*)
    FROM #crm_dia_regiao
    GROUP BY id_regiao_saude, id_medico, competencia;

    DROP TABLE #crm_dia_regiao;

    INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
    SELECT 'uf', uf, id_medico, competencia, SUM(nu_prescricoes_dia), COUNT(*)
    FROM #crm_dia_uf
    GROUP BY uf, id_medico, competencia;

    DROP TABLE #crm_dia_uf;

    INSERT INTO #crm_medico_mes_territorio WITH (TABLOCK)
    SELECT 'brasil', 'BR', id_medico, competencia, SUM(nu_prescricoes_dia), COUNT(*)
    FROM #crm_dia_brasil
    GROUP BY id_medico, competencia;

    DROP TABLE #crm_dia_brasil;
    DROP TABLE #crm_municipio_geo;

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaMedicoMesTerritorio
        ON #crm_medico_mes_territorio(nivel, id_geografico, id_medico, competencia);

    IF EXISTS (
        SELECT 1
        FROM #crm_medico_mes_territorio
        WHERE qtd_dias_com_prescricao_mes NOT BETWEEN 1 AND
            DAY(EOMONTH(DATEFROMPARTS(competencia / 100, competencia % 100, 1)))
           OR nu_prescricoes_mes < qtd_dias_com_prescricao_mes
    )
        THROW 51013, 'Dias com prescricao invalidos no agregado mensal por territorio.', 1;

    IF EXISTS (
        SELECT 1
        FROM #crm_medico_mes_territorio
        WHERE nu_prescricoes_mes NOT BETWEEN 1 AND 32767
    )
        THROW 51025, 'Prescricoes por medico/territorio/mes fora do limite de SMALLINT.', 1;

    -- O nivel Brasil (id_medico, competencia) e a tabela de estabelecimentos
    -- (id_medico, competencia) tem a mesma chave e o mesmo indice: merge simples.
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT id_medico, competencia, nu_prescricoes_mes
            FROM #crm_medico_mes_territorio
            WHERE nivel = 'brasil'
              AND id_geografico = 'BR'
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

    SET @Msg = '   Agregacao por territorio concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

    -- ============================================================================
    -- 4. Somas do ano por medico (Brasil e territorios)
    -- ============================================================================
    -- Mes de alta intensidade: taxa do mes (prescricoes / dias com prescricao,
    -- DECIMAL(19,6)) acima do P95 nacional do mes, a mesma regra do mapa e do
    -- ranking. O P95 vem de build_crm_limiar_p95_mes, ja gravado pela etapa 1.
    SET @Msg = '>> Somando o ano por medico (tabelas anuais)...';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @t1 = GETDATE();

    DROP TABLE IF EXISTS #crm_limiar_ano;
    DROP TABLE IF EXISTS #crm_medico_ano;

    SELECT competencia, p95_taxa_dia
    INTO #crm_limiar_ano
    FROM temp_CGUSC.fp.build_crm_limiar_p95_mes
    WHERE competencia BETWEEN @CompIni AND @CompFim;

    CREATE UNIQUE CLUSTERED INDEX IDX_RetomadaLimiarAno ON #crm_limiar_ano(competencia);

    IF EXISTS (
        SELECT 1
        FROM (SELECT DISTINCT competencia FROM #crm_medico_mes_territorio) T
        LEFT JOIN #crm_limiar_ano L ON L.competencia = T.competencia
        WHERE L.competencia IS NULL
    )
        THROW 51110, 'Existe mes do ano sem P95 em build_crm_limiar_p95_mes.', 1;

    SELECT
        T.nivel,
        T.id_geografico,
        T.id_medico,
        SUM(T.nu_prescricoes_mes) AS nu_prescricoes,
        SUM(T.qtd_dias_com_prescricao_mes) AS qtd_dias_com_prescricao,
        COUNT(*) AS qtd_meses_ativos,
        SUM(CASE
                WHEN CAST(CAST(T.nu_prescricoes_mes AS DECIMAL(19, 6)) / T.qtd_dias_com_prescricao_mes AS DECIMAL(19, 6))
                     > L.p95_taxa_dia
                THEN 1 ELSE 0
            END) AS qtd_meses_alta_intensidade
    INTO #crm_medico_ano
    FROM #crm_medico_mes_territorio T
    INNER JOIN #crm_limiar_ano L
        ON L.competencia = T.competencia
    GROUP BY T.nivel, T.id_geografico, T.id_medico;

    DROP TABLE #crm_limiar_ano;

    IF EXISTS (
        SELECT 1
        FROM #crm_medico_ano
        WHERE qtd_meses_ativos NOT BETWEEN 1 AND 12
           OR qtd_meses_alta_intensidade > qtd_meses_ativos
           OR qtd_dias_com_prescricao NOT BETWEEN qtd_meses_ativos AND 366
           OR nu_prescricoes < qtd_dias_com_prescricao
    )
        THROW 51111, 'Somas anuais por medico com valores invalidos.', 1;

    SET @Msg = '   Somas anuais concluidas em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

    -- ============================================================================
    -- 5. Grava o ano nas tabelas finais mensais e anuais (tudo ou nada)
    -- ============================================================================
    SET @Msg = '>> Gravando o ano em build_crm_medico_brasil_mes/territorio_mes e brasil_ano/territorio_ano...';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @t1 = GETDATE();

    BEGIN TRANSACTION;

    INSERT INTO temp_CGUSC.fp.build_crm_medico_brasil_mes WITH (TABLOCK) (
        id_medico,
        competencia,
        nu_prescricoes_mes,
        qtd_dias_com_prescricao_mes,
        nu_estabelecimentos_mes
    )
    SELECT
        T.id_medico,
        T.competencia,
        CAST(T.nu_prescricoes_mes AS SMALLINT),
        CAST(T.qtd_dias_com_prescricao_mes AS TINYINT),
        CAST(E.nu_estabelecimentos_mes AS SMALLINT)
    FROM #crm_medico_mes_territorio T
    INNER JOIN #crm_estabelecimentos_medico_mes E
        ON E.id_medico = T.id_medico
       AND E.competencia = T.competencia
    WHERE T.nivel = 'brasil'
      AND T.id_geografico = 'BR';

    INSERT INTO temp_CGUSC.fp.build_crm_medico_territorio_mes WITH (TABLOCK) (
        nivel,
        id_geografico,
        id_medico,
        competencia,
        nu_prescricoes_mes,
        qtd_dias_com_prescricao_mes
    )
    SELECT
        nivel,
        id_geografico,
        id_medico,
        competencia,
        CAST(nu_prescricoes_mes AS SMALLINT),
        CAST(qtd_dias_com_prescricao_mes AS TINYINT)
    FROM #crm_medico_mes_territorio
    WHERE nivel IN ('municipio', 'regiao_saude', 'uf');

    INSERT INTO temp_CGUSC.fp.build_crm_medico_brasil_ano WITH (TABLOCK) (
        id_medico,
        ano,
        nu_prescricoes,
        qtd_dias_com_prescricao,
        qtd_meses_ativos,
        qtd_meses_alta_intensidade
    )
    SELECT
        id_medico,
        CAST(@Ano AS SMALLINT),
        nu_prescricoes,
        CAST(qtd_dias_com_prescricao AS SMALLINT),
        CAST(qtd_meses_ativos AS TINYINT),
        CAST(qtd_meses_alta_intensidade AS TINYINT)
    FROM #crm_medico_ano
    WHERE nivel = 'brasil'
      AND id_geografico = 'BR';

    INSERT INTO temp_CGUSC.fp.build_crm_medico_territorio_ano WITH (TABLOCK) (
        nivel,
        id_geografico,
        id_medico,
        ano,
        nu_prescricoes,
        qtd_dias_com_prescricao,
        qtd_meses_ativos,
        qtd_meses_alta_intensidade
    )
    SELECT
        nivel,
        id_geografico,
        id_medico,
        CAST(@Ano AS SMALLINT),
        nu_prescricoes,
        CAST(qtd_dias_com_prescricao AS SMALLINT),
        CAST(qtd_meses_ativos AS TINYINT),
        CAST(qtd_meses_alta_intensidade AS TINYINT)
    FROM #crm_medico_ano
    WHERE nivel IN ('municipio', 'regiao_saude', 'uf');

    -- Medicos ainda sem codigo recebem os proximos inteiros (sem lacunas).
    SET @proximo_id_medico = (
        SELECT ISNULL(MAX(id_medico_num), -1) + 1
        FROM temp_CGUSC.fp.build_crm_medico_dim WITH (UPDLOCK, HOLDLOCK)
    );

    INSERT INTO temp_CGUSC.fp.build_crm_medico_dim (id_medico_num, id_medico)
    SELECT
        @proximo_id_medico + CAST(ROW_NUMBER() OVER (ORDER BY N.id_medico) AS INT) - 1,
        N.id_medico
    FROM (SELECT DISTINCT id_medico FROM #crm_farmacia_medico_ano) N
    WHERE NOT EXISTS (
        SELECT 1 FROM temp_CGUSC.fp.build_crm_medico_dim D WHERE D.id_medico = N.id_medico
    );

    INSERT INTO temp_CGUSC.fp.build_crm_farmacia_medico_ano WITH (TABLOCK) (
        ano,
        id_medico_num,
        id_cnpj,
        nu_prescricoes
    )
    SELECT
        CAST(@Ano AS SMALLINT),
        D.id_medico_num,
        F.id_cnpj,
        CAST(F.nu_prescricoes AS INT)
    FROM #crm_farmacia_medico_ano F
    INNER JOIN temp_CGUSC.fp.build_crm_medico_dim D
        ON D.id_medico = F.id_medico;

    UPDATE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
    SET status = 'PROCESSANDO',
        dt_atualizacao = GETDATE(),
        observacao = 'Retomada por ano: ' + CAST(@Ano AS VARCHAR(4)) + ' gravado.'
    WHERE id_pipeline = 1;

    COMMIT TRANSACTION;

    DROP TABLE #crm_medico_mes_territorio;
    DROP TABLE #crm_estabelecimentos_medico_mes;
    DROP TABLE #crm_medico_ano;
    DROP TABLE #crm_farmacia_medico_ano;

    SET @Msg = '   Gravacao concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @Msg = '==========================================================';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @Msg = '   ANO ' + CAST(@Ano AS VARCHAR(4)) + ' CONCLUIDO EM: ' + CONVERT(VARCHAR(20), GETDATE() - @t0, 114);
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @Msg = '==========================================================';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

    INSERT INTO @resumo (ano, situacao, tempo)
    VALUES (@Ano, 'processado', CONVERT(VARCHAR(20), GETDATE() - @t0, 114));
END;  -- WHILE

SET @Msg = '==========================================================';
RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
SET @Msg = '   TODOS OS ANOS CONCLUIDOS. TEMPO TOTAL: ' + CONVERT(VARCHAR(20), GETDATE() - @tInicio, 114);
RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
SET @Msg = '   Proximo passo: crms_etapa1b_finalizar.sql';
RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
SET @Msg = '==========================================================';
RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;

SELECT ano, situacao, tempo FROM @resumo ORDER BY ano;

-- Anos ja gravados.
SELECT
    B.competencia / 100 AS ano,
    COUNT(DISTINCT B.competencia) AS meses,
    COUNT_BIG(*) AS linhas_brasil_mes
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes B
GROUP BY B.competencia / 100
ORDER BY ano;


END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    DECLARE @mensagem_erro NVARCHAR(4000) = CONCAT(
        'Erro ', ERROR_NUMBER(),
        ' | Linha ', ERROR_LINE(),
        ' | ', ERROR_MESSAGE()
    );

    IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata') IS NOT NULL
        UPDATE temp_CGUSC.fp.build_crm_pipeline_pre_global_metadata
        SET status = 'ERRO',
            dt_atualizacao = GETDATE(),
            observacao = LEFT('Retomada ano ' + ISNULL(CAST(@Ano AS VARCHAR(4)), '(pre-requisitos)') + ': ' + @mensagem_erro, 400)
        WHERE id_pipeline = 1;

    SET @Msg = '   ERRO na retomada do pre-global CRM (ano ' + ISNULL(CAST(@Ano AS VARCHAR(4)), 'nenhum: pre-requisitos') + ').'
        + ' Anos anteriores continuam gravados; rode o script de novo para seguir deste ano.';
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    SET @Msg = '   ' + @mensagem_erro;
    RAISERROR('%s', 0, 1, @Msg) WITH NOWAIT;
    THROW;
END CATCH;
