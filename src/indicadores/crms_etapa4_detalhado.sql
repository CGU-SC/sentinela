-- ============================================================================
-- GERADOR DE DADOS PARA INDICADOR DE CRMs - PROCESSAMENTO LOTEADO
-- ============================================================================
-- Script 2 do pipeline:
--   - processa todas as UFs pendentes, uma UF por ciclo;
--   - dentro de cada UF, processa CNPJs em lotes com checkpoint;
--   - gera tabelas locais/incrementais do indicador;
--   - usa tabelas pre-globais ja persistidas pelo script:
--       src/indicadores/crms_detalhado_pre_global_test.sql
--
-- Pre-requisitos:
--   1. temp_CGUSC.fp.build_dados_medico
--   2. temp_CGUSC.fp.build_crm_medico_brasil_mes
--   3. temp_CGUSC.fp.build_crm_concentracao_unico_alertas
--   4. temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas
--   5. temp_CGUSC.fp.build_crm_pipeline_uf_controle com concentracao unico/multiplo OK
--
-- O pos-global deve rodar depois deste script completar todos os CNPJs:
--   - build_alertas_crm_geografico
--   - build_alertas_crm_registro
--   - build_alertas_crm
--   - build_crm_export
--   - benchmarks
-- ============================================================================

-- Batch separado: garante colunas novas antes da compilacao da batch principal.
-- SQL Server valida colunas de tabelas persistentes em compile-time; se uma
-- tabela ja existir sem coluna nova, referencias estaticas abaixo falham com
-- Msg 207 mesmo que exista ALTER TABLE antes no texto.
IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NOT NULL
BEGIN
    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'dt_inicio') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD dt_inicio DATETIME NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'dt_fim') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD dt_fim DATETIME NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'status_concentracao_unico') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD status_concentracao_unico VARCHAR(20) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'status_concentracao_multiplo') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD status_concentracao_multiplo VARCHAR(20) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'status_crm_detalhado_loteado') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD status_crm_detalhado_loteado VARCHAR(20) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'dt_crm_detalhado_loteado') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD dt_crm_detalhado_loteado DATETIME NULL;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_log') IS NOT NULL
BEGIN
    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'dt_fim_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD dt_fim_lote DATETIME NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'segundos_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD segundos_lote INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'milissegundos_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD milissegundos_lote INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'qtd_cnpjs_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD qtd_cnpjs_lote INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'nu_dados_crm_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD nu_dados_crm_lote INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'nu_volume_alertas_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD nu_volume_alertas_lote INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'nu_raiox_tx_lote') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD nu_raiox_tx_lote INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'nu_cnpjs_processados_acumulado') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD nu_cnpjs_processados_acumulado INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'nu_cnpjs_total') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD nu_cnpjs_total INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'etapa') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD etapa VARCHAR(80) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'mensagem_erro') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD mensagem_erro NVARCHAR(4000) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'observacao') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD observacao VARCHAR(400) NULL;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log') IS NOT NULL
BEGIN
    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log', 'dt_fim_etapa') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log ADD dt_fim_etapa DATETIME NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log', 'segundos_etapa') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log ADD segundos_etapa INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log', 'milissegundos_etapa') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log ADD milissegundos_etapa INT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log', 'nu_registros') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log ADD nu_registros BIGINT NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log', 'observacao') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log ADD observacao VARCHAR(400) NULL;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_controle') IS NOT NULL
BEGIN
    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_controle', 'etapa') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle ADD etapa VARCHAR(80) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_controle', 'mensagem_erro') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle ADD mensagem_erro NVARCHAR(4000) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_controle', 'dt_erro') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle ADD dt_erro DATETIME NULL;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_metadata') IS NOT NULL
BEGIN
    IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_metadata', 'nu_registros') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_metadata ADD nu_registros BIGINT NULL;
END;
GO

SET NOCOUNT ON;

-- ============================================================================
-- PASSO 0: Reset opcional e inicializacao de tabelas persistentes
-- ============================================================================
DECLARE @reset BIT = 0;
DECLARE @pipeline_nome    VARCHAR(80) = 'crms_detalhado_loteado';
DECLARE @pipeline_versao  VARCHAR(40) = 'v3_2026_05_12';
DECLARE @DataInicio       DATE        = '2015-07-01';
DECLARE @DataFim          DATE        = '2024-12-31';
DECLARE @auto_materializar_uf BIT     = 1;
DECLARE @reset_fonte_uf       BIT     = 0;
DECLARE @uf_farmacia_alvo     CHAR(2) = NULL; -- Ex.: 'MG'. NULL pega pendente/interrompida.
DECLARE @existia_tabela_loteada BIT   = CASE WHEN
        OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_controle') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_diario') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_horario') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_volume_horario_anomalo_alertas') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NOT NULL
     OR OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') IS NOT NULL
    THEN 1 ELSE 0 END;
DECLARE @nu_registros BIGINT;
DECLARE @nu_cnpjs_fonte INT;
DECLARE @uf_farmacia CHAR(2);
DECLARE @t_etapa DATETIME;
DECLARE @dt_fim_etapa DATETIME;
DECLARE @nu_registros_etapa BIGINT;
DECLARE @id_etapa_log BIGINT;
DECLARE @nu_ufs_processadas INT = 0;

DECLARE @lote_size  INT      = 50;
DECLARE @t0         DATETIME = GETDATE();
DECLARE @t1         DATETIME;
DECLARE @t_bloco    DATETIME;

DECLARE @lote_num          INT = 0;
DECLARE @nu_processados    INT = 0;
DECLARE @nu_pendentes      INT;
DECLARE @nu_ja_processados INT;
DECLARE @nu_total          INT;
DECLARE @nu_lote           INT;
DECLARE @etapa             VARCHAR(80);
DECLARE @id_lote_log       BIGINT;
DECLARE @dt_fim_lote       DATETIME;
DECLARE @nu_dados_crm_lote INT;
DECLARE @nu_volume_alertas_lote INT;
DECLARE @nu_raiox_tx_lote  INT;

IF @auto_materializar_uf = 1
BEGIN
    IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia') IS NULL
    BEGIN
        RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao encontrada.', 16, 1);
        RETURN;
    END;

    IF COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'uf') IS NULL
    BEGIN
        RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao possui coluna uf.', 16, 1);
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

    IF OBJECT_ID('db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP') IS NULL
    BEGIN
        RAISERROR('Fonte nacional db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP nao encontrada.', 16, 1);
        RETURN;
    END;

    IF COL_LENGTH('db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP', 'qnt_autorizada') IS NULL
    BEGIN
        RAISERROR('Fonte nacional db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP sem coluna obrigatoria qnt_autorizada.', 16, 1);
        RETURN;
    END;

    IF OBJECT_ID('db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024') IS NULL
    BEGIN
        RAISERROR('Fonte nacional db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024 nao encontrada.', 16, 1);
        RETURN;
    END;

    IF COL_LENGTH('db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024', 'qnt_autorizada') IS NULL
    BEGIN
        RAISERROR('Fonte nacional db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024 sem coluna obrigatoria qnt_autorizada.', 16, 1);
        RETURN;
    END;

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
            status_crm_detalhado_loteado VARCHAR(20) NULL,
            dt_crm_detalhado_loteado DATETIME NULL,
            CONSTRAINT PK_BuildCrmPipelineUfControle PRIMARY KEY CLUSTERED (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim)
        );
    END;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'dt_inicio') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD dt_inicio DATETIME NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'dt_fim') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD dt_fim DATETIME NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'status_concentracao_unico') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD status_concentracao_unico VARCHAR(20) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'status_concentracao_multiplo') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD status_concentracao_multiplo VARCHAR(20) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'status_crm_detalhado_loteado') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD status_crm_detalhado_loteado VARCHAR(20) NULL;

    IF COL_LENGTH('temp_CGUSC.fp.build_crm_pipeline_uf_controle', 'dt_crm_detalhado_loteado') IS NULL
        ALTER TABLE temp_CGUSC.fp.build_crm_pipeline_uf_controle ADD dt_crm_detalhado_loteado DATETIME NULL;

    IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log') IS NULL
    BEGIN
        CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log (
            id_etapa_log        BIGINT IDENTITY(1,1) NOT NULL,
            uf_farmacia         CHAR(2)      NOT NULL,
            pipeline_versao     VARCHAR(40)  NOT NULL,
            dt_data_inicio      DATE         NOT NULL,
            dt_data_fim         DATE         NOT NULL,
            etapa               VARCHAR(80)  NOT NULL,
            dt_inicio_etapa     DATETIME     NOT NULL,
            dt_fim_etapa        DATETIME     NULL,
            segundos_etapa      INT          NULL,
            milissegundos_etapa INT          NULL,
            nu_registros        BIGINT       NULL,
            observacao          VARCHAR(400) NULL,
            CONSTRAINT PK_BuildCrmDetalhadoLoteEtapaLog PRIMARY KEY CLUSTERED (id_etapa_log)
        );

        CREATE INDEX IDX_CrmDetalhadoLoteEtapaLog_UfPeriodo
            ON temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
                (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa);
    END;

    IF @reset = 1
    BEGIN
        DELETE FROM temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        WHERE pipeline_versao = @pipeline_versao
          AND dt_data_inicio = @DataInicio
          AND dt_data_fim = @DataFim;
    END;

    INSERT INTO temp_CGUSC.fp.build_crm_pipeline_uf_controle
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim,
         status, etapa, dt_criacao, dt_atualizacao, status_crm_detalhado_loteado)
    SELECT DISTINCT
        CAST(F.uf AS CHAR(2)),
        @pipeline_versao,
        @DataInicio,
        @DataFim,
        'PENDENTE',
        'AGUARDANDO_MATERIALIZACAO',
        GETDATE(),
        GETDATE(),
        'PENDENTE'
    FROM temp_CGUSC.fp.dados_farmacia F
    WHERE F.uf IS NOT NULL
      AND LEN(LTRIM(RTRIM(F.uf))) = 2
      AND NOT EXISTS (
          SELECT 1
          FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle C
          WHERE C.uf_farmacia = CAST(F.uf AS CHAR(2))
            AND C.pipeline_versao = @pipeline_versao
            AND C.dt_data_inicio = @DataInicio
            AND C.dt_data_fim = @DataFim
      );

    UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
    SET status_crm_detalhado_loteado = 'PENDENTE'
    WHERE pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
      AND status_crm_detalhado_loteado IS NULL;

    IF @reset = 1
    BEGIN
        PRINT '>> Reset habilitado: removendo tabelas loteadas antes de iniciar UFs...';

        DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_detalhado_lote_metadata;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_detalhado_lote_controle;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_perfil_diario;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_perfil_horario;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_mediana_autorizacoes_horaria;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_volume_horario_anomalo_alertas;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_raiox_tx;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_dados_crm_detalhado;
        DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_detalhado_lote_log;

        UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
        SET status = 'PROCESSANDO',
            etapa = 'AGUARDANDO_CRM_DETALHADO_LOTEADO',
            status_crm_detalhado_loteado = 'PENDENTE',
            dt_crm_detalhado_loteado = NULL,
            dt_atualizacao = GETDATE(),
            mensagem_erro = NULL,
            dt_erro = NULL
        WHERE pipeline_versao = @pipeline_versao
          AND dt_data_inicio = @DataInicio
          AND dt_data_fim = @DataFim
          AND status_concentracao_unico = 'OK'
          AND status_concentracao_multiplo = 'OK';
    END;

ProximaUF:
    SET @lote_num = 0;
    SET @nu_processados = 0;
    SET @nu_pendentes = NULL;
    SET @nu_ja_processados = NULL;
    SET @nu_total = NULL;
    SET @nu_lote = NULL;
    SET @etapa = NULL;
    SET @id_lote_log = NULL;
    SET @dt_fim_lote = NULL;
    SET @nu_dados_crm_lote = NULL;
    SET @nu_volume_alertas_lote = NULL;
    SET @nu_raiox_tx_lote = NULL;
    SET @nu_registros = NULL;
    SET @nu_cnpjs_fonte = NULL;
    SET @uf_farmacia = @uf_farmacia_alvo;

    IF @uf_farmacia_alvo IS NULL
    BEGIN
        SELECT TOP 1 @uf_farmacia = uf_farmacia
        FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
        WHERE pipeline_versao = @pipeline_versao
          AND dt_data_inicio = @DataInicio
          AND dt_data_fim = @DataFim
          AND status_concentracao_unico = 'OK'
          AND status_concentracao_multiplo = 'OK'
          AND ISNULL(status_crm_detalhado_loteado, 'PENDENTE') <> 'OK'
        ORDER BY
            CASE ISNULL(status_crm_detalhado_loteado, 'PENDENTE')
                WHEN 'ERRO' THEN 1
                WHEN 'PROCESSANDO' THEN 2
                WHEN 'MATERIALIZANDO' THEN 3
                WHEN 'MATERIALIZADA' THEN 4
                WHEN 'INCOMPLETO' THEN 5
                WHEN 'PENDENTE' THEN 6
                ELSE 9
            END,
            uf_farmacia;
    END;
    ELSE IF @nu_ufs_processadas > 0
    BEGIN
        GOTO Resultados;
    END;

    IF @uf_farmacia IS NULL
    BEGIN
        PRINT '>> Todas as UFs estao OK ou nao ha UF pendente para esta versao/periodo.';
        GOTO Resultados;
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
        WHERE uf_farmacia = @uf_farmacia
          AND pipeline_versao = @pipeline_versao
          AND dt_data_inicio = @DataInicio
          AND dt_data_fim = @DataFim
          AND status_concentracao_unico = 'OK'
          AND status_concentracao_multiplo = 'OK'
    )
    BEGIN
        RAISERROR('UF alvo ainda nao possui concentracoes CRM unico e multiplo OK no build_crm_pipeline_uf_controle. Rode os motores temporais antes do loteado.', 16, 1);
        RETURN;
    END;

    IF EXISTS (
        SELECT 1
        FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
        WHERE uf_farmacia = @uf_farmacia
          AND pipeline_versao = @pipeline_versao
          AND dt_data_inicio = @DataInicio
          AND dt_data_fim = @DataFim
          AND status_crm_detalhado_loteado = 'OK'
          AND @reset_fonte_uf = 0
    )
    BEGIN
        PRINT '>> UF ' + @uf_farmacia + ' ja esta OK. Nada a processar.';
        SELECT * FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle WHERE uf_farmacia = @uf_farmacia;
        RETURN;
    END;

    DROP TABLE IF EXISTS #crm_mov_fonte_atual;
    DROP TABLE IF EXISTS #crm_mov_fonte_atual_metadata;
    DROP TABLE IF EXISTS #crm_cnpjs_fonte_atual;

    PRINT '>> [CRM DETALHADO LOTEADO] Materializando fonte temporaria da UF ' + @uf_farmacia + '...';

    UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
    SET status = 'PROCESSANDO',
            etapa = 'MATERIALIZANDO_FONTE_UF',
            dt_inicio = ISNULL(dt_inicio, GETDATE()),
            dt_fim = NULL,
            status_crm_detalhado_loteado = 'MATERIALIZANDO',
            dt_atualizacao = GETDATE(),
            mensagem_erro = NULL,
            dt_erro = NULL
    WHERE uf_farmacia = @uf_farmacia
      AND pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim;

        EXEC sp_executesql
            N'UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
              SET etapa = ''MATERIALIZANDO_FONTE_UF_SELECT_INTO'',
                  dt_atualizacao = GETDATE()
              WHERE uf_farmacia = @uf
                AND pipeline_versao = @versao
                AND dt_data_inicio = @inicio
                AND dt_data_fim = @fim;',
            N'@uf CHAR(2), @versao VARCHAR(40), @inicio DATE, @fim DATE',
            @uf = @uf_farmacia,
            @versao = @pipeline_versao,
            @inicio = @DataInicio,
            @fim = @DataFim;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_SELECT_INTO',
             @t_etapa, 'SELECT INTO #crm_mov_fonte_atual em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        SELECT
            CAST(F.uf AS CHAR(2)) AS uf_farmacia,
            CAST(F.id AS INT) AS id_cnpj,
            CAST(M.cnpj AS CHAR(14)) AS cnpj,
            CAST(M.crm AS VARCHAR(10)) AS crm,
            CAST(M.crm_uf AS VARCHAR(2)) AS crm_uf,
            CAST(M.data_hora AS DATETIME) AS data_hora,
            CAST(M.num_autorizacao AS VARCHAR(50)) AS num_autorizacao,
            CAST(M.valor_pago AS DECIMAL(18,2)) AS valor_pago,
            M.codigo_barra
        INTO #crm_mov_fonte_atual
        FROM (
            SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, valor_pago, qnt_autorizada, codigo_barra
            FROM db_FarmaciaPopular.dbo.Relatorio_movimentacaoFP
            UNION ALL
            SELECT cnpj, crm, crm_uf, data_hora, num_autorizacao, valor_pago, qnt_autorizada, codigo_barra
            FROM db_FarmaciaPopular.carga_2024.relatorio_movimentacaoFP_2021_2024
        ) M
        INNER JOIN temp_CGUSC.fp.dados_farmacia F
            ON F.cnpj = M.cnpj
        WHERE F.uf = @uf_farmacia
          AND M.crm IS NOT NULL
          AND M.crm_uf IS NOT NULL
          AND M.crm_uf <> 'BR'
          AND M.data_hora >= @DataInicio
          AND M.data_hora < DATEADD(DAY, 1, @DataFim)
          AND M.qnt_autorizada IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM temp_CGUSC.fp.medicamentos_patologia PAT
              WHERE PAT.codigo_barra = M.codigo_barra
                AND TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0)) IS NOT NULL
                AND TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0)) <> 0
                AND (M.qnt_autorizada / TRY_CAST(PAT.qnt_comprimidos_caixa AS DECIMAL(10,0))) <> 0
          );

        SET @nu_registros_etapa = @@ROWCOUNT;
        SET @nu_registros = @nu_registros_etapa;
        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            nu_registros = @nu_registros_etapa,
            observacao = 'SELECT INTO #crm_mov_fonte_atual.'
        WHERE id_etapa_log = @id_etapa_log;

        EXEC sp_executesql
            N'UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
              SET etapa = ''MATERIALIZANDO_FONTE_UF_IDX_CLUSTERED'',
                  dt_atualizacao = GETDATE()
              WHERE uf_farmacia = @uf
                AND pipeline_versao = @versao
                AND dt_data_inicio = @inicio
                AND dt_data_fim = @fim;',
            N'@uf CHAR(2), @versao VARCHAR(40), @inicio DATE, @fim DATE',
            @uf = @uf_farmacia,
            @versao = @pipeline_versao,
            @inicio = @DataInicio,
            @fim = @DataFim;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_IDX_CLUSTERED',
             @t_etapa, 'Indice clustered em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        CREATE CLUSTERED INDEX IDX_CrmMovFonteAtual_UfCnpjData
            ON #crm_mov_fonte_atual(uf_farmacia, id_cnpj, data_hora);

        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            observacao = 'Indice clustered #crm_mov_fonte_atual(uf_farmacia, id_cnpj, data_hora).'
        WHERE id_etapa_log = @id_etapa_log;

        EXEC sp_executesql
            N'UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
              SET etapa = ''MATERIALIZANDO_FONTE_UF_IDX_CNPJ_DATA'',
                  dt_atualizacao = GETDATE()
              WHERE uf_farmacia = @uf
                AND pipeline_versao = @versao
                AND dt_data_inicio = @inicio
                AND dt_data_fim = @fim;',
            N'@uf CHAR(2), @versao VARCHAR(40), @inicio DATE, @fim DATE',
            @uf = @uf_farmacia,
            @versao = @pipeline_versao,
            @inicio = @DataInicio,
            @fim = @DataFim;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_IDX_CNPJ_DATA',
             @t_etapa, 'Indice nonclustered CNPJ/data em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        CREATE NONCLUSTERED INDEX IDX_CrmMovFonteAtual_CnpjData
            ON #crm_mov_fonte_atual(cnpj, data_hora)
            INCLUDE (id_cnpj, crm, crm_uf, num_autorizacao, valor_pago, codigo_barra);

        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            observacao = 'Indice nonclustered #crm_mov_fonte_atual(cnpj, data_hora).'
        WHERE id_etapa_log = @id_etapa_log;

        EXEC sp_executesql
            N'UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
              SET etapa = ''MATERIALIZANDO_FONTE_UF_IDX_CRM_DATA'',
                  dt_atualizacao = GETDATE()
              WHERE uf_farmacia = @uf
                AND pipeline_versao = @versao
                AND dt_data_inicio = @inicio
                AND dt_data_fim = @fim;',
            N'@uf CHAR(2), @versao VARCHAR(40), @inicio DATE, @fim DATE',
            @uf = @uf_farmacia,
            @versao = @pipeline_versao,
            @inicio = @DataInicio,
            @fim = @DataFim;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_IDX_CRM_DATA',
             @t_etapa, 'Indice nonclustered CRM/data em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        CREATE NONCLUSTERED INDEX IDX_CrmMovFonteAtual_CrmData
            ON #crm_mov_fonte_atual(id_cnpj, crm, crm_uf, data_hora)
            INCLUDE (cnpj, num_autorizacao, valor_pago, codigo_barra);

        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            observacao = 'Indice nonclustered #crm_mov_fonte_atual(id_cnpj, crm, crm_uf, data_hora).'
        WHERE id_etapa_log = @id_etapa_log;

        EXEC sp_executesql
            N'UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
              SET etapa = ''MATERIALIZANDO_FONTE_UF_CONTAGEM'',
                  dt_atualizacao = GETDATE()
              WHERE uf_farmacia = @uf
                AND pipeline_versao = @versao
                AND dt_data_inicio = @inicio
                AND dt_data_fim = @fim;',
            N'@uf CHAR(2), @versao VARCHAR(40), @inicio DATE, @fim DATE',
            @uf = @uf_farmacia,
            @versao = @pipeline_versao,
            @inicio = @DataInicio,
            @fim = @DataFim;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_CONTAGEM_LINHAS',
             @t_etapa, 'Contagem de linhas ja capturada pelo SELECT INTO.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CONTAGEM_LINHAS iniciado.', 0, 1) WITH NOWAIT;

        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            nu_registros = @nu_registros,
            observacao = 'Contagem de linhas capturada pelo @@ROWCOUNT do SELECT INTO.'
        WHERE id_etapa_log = @id_etapa_log;

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CONTAGEM_LINHAS concluido.', 0, 1) WITH NOWAIT;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_CNPJS_SELECT_INTO',
             @t_etapa, 'Criacao de #crm_cnpjs_fonte_atual por dados_farmacia + EXISTS em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CNPJS_SELECT_INTO iniciado.', 0, 1) WITH NOWAIT;

        SELECT
            F.id AS id_cnpj,
            CAST(F.cnpj AS CHAR(14)) AS cnpj
        INTO #crm_cnpjs_fonte_atual
        FROM temp_CGUSC.fp.dados_farmacia F
        WHERE F.uf = @uf_farmacia
          AND EXISTS (
              SELECT 1
              FROM #crm_mov_fonte_atual M
              WHERE M.uf_farmacia = @uf_farmacia
                AND M.id_cnpj = F.id
          );

        SET @nu_registros_etapa = @@ROWCOUNT;
        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            nu_registros = @nu_registros_etapa,
            observacao = 'Criacao de #crm_cnpjs_fonte_atual por dados_farmacia + EXISTS.'
        WHERE id_etapa_log = @id_etapa_log;

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CNPJS_SELECT_INTO concluido.', 0, 1) WITH NOWAIT;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_CNPJS_IDX',
             @t_etapa, 'Indice clustered de #crm_cnpjs_fonte_atual em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CNPJS_IDX iniciado.', 0, 1) WITH NOWAIT;

        CREATE UNIQUE CLUSTERED INDEX IDX_CrmCnpjsFonteAtual
            ON #crm_cnpjs_fonte_atual(id_cnpj);

        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            observacao = 'Indice clustered #crm_cnpjs_fonte_atual(id_cnpj).'
        WHERE id_etapa_log = @id_etapa_log;

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CNPJS_IDX concluido.', 0, 1) WITH NOWAIT;

        SET @t_etapa = GETDATE();
        SET @id_etapa_log = NULL;

        INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa,
             dt_inicio_etapa, observacao)
        VALUES
            (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, 'MATERIALIZANDO_FONTE_UF_CNPJS_COUNT',
             @t_etapa, 'Contagem de CNPJs materializados em andamento.');

        SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CNPJS_COUNT iniciado.', 0, 1) WITH NOWAIT;

        SELECT @nu_cnpjs_fonte = COUNT(*)
        FROM #crm_cnpjs_fonte_atual;

        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
            nu_registros = @nu_cnpjs_fonte,
            observacao = 'Contagem de CNPJs materializados.'
        WHERE id_etapa_log = @id_etapa_log;

        RAISERROR('   MATERIALIZANDO_FONTE_UF_CNPJS_COUNT concluido.', 0, 1) WITH NOWAIT;

        CREATE TABLE #crm_mov_fonte_atual_metadata (
            id_pipeline          TINYINT      NOT NULL,
            pipeline_versao      VARCHAR(40)  NOT NULL,
            uf_farmacia          CHAR(2)      NOT NULL,
            dt_data_inicio       DATE         NOT NULL,
            dt_data_fim          DATE         NOT NULL,
            nu_registros_fonte   BIGINT       NOT NULL,
            nu_cnpjs_fonte       INT          NOT NULL,
            dt_criacao           DATETIME     NOT NULL,
            status               VARCHAR(20)  NOT NULL,
            observacao           VARCHAR(400) NULL
        );

        INSERT INTO #crm_mov_fonte_atual_metadata
            (id_pipeline, pipeline_versao, uf_farmacia, dt_data_inicio, dt_data_fim,
             nu_registros_fonte, nu_cnpjs_fonte, dt_criacao, status, observacao)
        VALUES
            (1, @pipeline_versao, @uf_farmacia, @DataInicio, @DataFim,
             @nu_registros, @nu_cnpjs_fonte, GETDATE(), 'OK',
             'Fonte materializada pelo crms_detalhado_loteado_test.sql.');

        UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
        SET status = 'PROCESSANDO',
            status_crm_detalhado_loteado = 'MATERIALIZADA',
            etapa = 'FONTE_OK',
            dt_atualizacao = GETDATE(),
            nu_registros_fonte = @nu_registros,
            nu_cnpjs_fonte = @nu_cnpjs_fonte
        WHERE uf_farmacia = @uf_farmacia
          AND pipeline_versao = @pipeline_versao
          AND dt_data_inicio = @DataInicio
          AND dt_data_fim = @DataFim;
END;

IF OBJECT_ID('tempdb..#crm_mov_fonte_atual') IS NULL
BEGIN
    RAISERROR('Tabela fonte temporaria #crm_mov_fonte_atual nao encontrada. Habilite @auto_materializar_uf ou materialize a fonte antes.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('tempdb..#crm_mov_fonte_atual_metadata') IS NULL
BEGIN
    RAISERROR('Metadata temporaria #crm_mov_fonte_atual_metadata nao encontrada. Habilite @auto_materializar_uf ou materialize a fonte antes.', 16, 1);
    RETURN;
END;

SELECT @uf_farmacia = uf_farmacia
FROM #crm_mov_fonte_atual_metadata
WHERE id_pipeline = 1
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim
  AND status = 'OK';

IF @uf_farmacia IS NULL
BEGIN
    RAISERROR('Fonte materializada incompativel: UF ausente, status diferente de OK, periodo divergente ou versao inesperada.', 16, 1);
    RETURN;
END;

SELECT @nu_registros = nu_registros_fonte
FROM #crm_mov_fonte_atual_metadata
WHERE id_pipeline = 1
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim
  AND status = 'OK';

UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
SET etapa = 'VALIDANDO_PRE_GLOBAL',
    dt_atualizacao = GETDATE()
WHERE uf_farmacia = @uf_farmacia
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_mes') IS NULL
BEGIN
    RAISERROR('Tabela pre-global temp_CGUSC.fp.build_crm_medico_brasil_mes nao encontrada. Rode crms_detalhado_pre_global_test.sql primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_dados_medico') IS NULL
BEGIN
    RAISERROR('Tabela pre-global temp_CGUSC.fp.build_dados_medico nao encontrada. Rode crms_detalhado_pre_global_test.sql primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_unico_alertas') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_concentracao_unico_alertas nao encontrada. Rode o motor temporal de CRM unico antes do loteado.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas nao encontrada. Rode o motor temporal de CRM multiplo antes do loteado.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_unico_alertas', 'id_cnpj') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_unico_alertas', 'dt_dia') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_unico_alertas', 'dt_ini_concentracao') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_unico_alertas', 'dt_fim_concentracao') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_concentracao_unico_alertas existe, mas nao possui o schema minimo esperado: id_cnpj, dt_dia, dt_ini_concentracao, dt_fim_concentracao.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas', 'id_cnpj') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas', 'dt_dia') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas', 'dt_ini_concentracao') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas', 'dt_fim_concentracao') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas existe, mas nao possui o schema minimo esperado: id_cnpj, dt_dia, dt_ini_concentracao, dt_fim_concentracao.', 16, 1);
    RETURN;
END;

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
    WHERE uf_farmacia = @uf_farmacia
      AND pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
      AND status_concentracao_unico = 'OK'
      AND status_concentracao_multiplo = 'OK'
)
BEGIN
    RAISERROR('Concentracoes CRM unico e multiplo ainda nao estao OK para a UF atual no build_crm_pipeline_uf_controle. Rode os motores temporais antes do loteado.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NOT NULL
    UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
    SET status = 'PROCESSANDO',
        etapa = 'PREPARANDO_LOTEADO',
        status_crm_detalhado_loteado = 'PROCESSANDO',
        dt_atualizacao = GETDATE(),
        mensagem_erro = NULL,
        dt_erro = NULL
    WHERE uf_farmacia = @uf_farmacia
      AND pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_metadata') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_lote_metadata (
        id_pipeline       TINYINT      NOT NULL,
        pipeline_nome     VARCHAR(80)  NOT NULL,
        pipeline_versao   VARCHAR(40)  NOT NULL,
        dt_data_inicio    DATE         NOT NULL,
        dt_data_fim       DATE         NOT NULL,
        nu_registros      BIGINT NULL,
        dt_criacao        DATETIME     NOT NULL,
        dt_atualizacao    DATETIME     NULL,
        status            VARCHAR(20)  NOT NULL,
        observacao        VARCHAR(400) NULL,
        CONSTRAINT PK_BuildCrmDetalhadoLoteMetadata PRIMARY KEY CLUSTERED (id_pipeline),
        CONSTRAINT CK_BuildCrmDetalhadoLoteMetadata_Id CHECK (id_pipeline = 1)
    );
END;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_metadata', 'nu_registros') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_metadata ADD nu_registros BIGINT NULL;

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_detalhado_lote_metadata WHERE id_pipeline = 1)
BEGIN
    IF @reset = 0 AND @existia_tabela_loteada = 1
    BEGIN
        RAISERROR('Estado loteado existente sem metadata. Para evitar mistura com dados antigos, rode uma primeira execucao limpa com @reset = 1.', 16, 1);
        RETURN;
    END;

    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_metadata
        (id_pipeline, pipeline_nome, pipeline_versao, dt_data_inicio, dt_data_fim,
         dt_criacao, dt_atualizacao, status, observacao)
    VALUES
        (1, @pipeline_nome, @pipeline_versao, @DataInicio, @DataFim,
         GETDATE(), GETDATE(), 'PROCESSANDO', 'Metadata criada pelo script loteado.');
END
ELSE IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_metadata
    WHERE id_pipeline = 1
      AND pipeline_nome = @pipeline_nome
      AND pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
)
BEGIN
    RAISERROR('Metadata existente incompativel com este script/periodo. Rode com @reset = 1 para iniciar uma base limpa.', 16, 1);
    RETURN;
END
ELSE
BEGIN
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_metadata
    SET status = 'PROCESSANDO',
        dt_atualizacao = GETDATE(),
        observacao = 'Execucao retomada/validada pelo script loteado.'
    WHERE id_pipeline = 1;
END;

EXEC sp_executesql
    N'UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_metadata
      SET nu_registros = @nu_mov
      WHERE id_pipeline = 1;',
    N'@nu_mov BIGINT',
    @nu_mov = @nu_registros;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_controle') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle (
        id_cnpj             INT          NOT NULL,
        cnpj                CHAR(14)     NOT NULL,
        dt_inicio           DATETIME     NOT NULL,
        dt_fim              DATETIME     NULL,
        status              VARCHAR(12)  NOT NULL,
        nu_dados_crm        INT          NULL,
        nu_volume_alertas   INT          NULL,
        nu_raiox_tx         INT          NULL,
        etapa               VARCHAR(80)  NULL,
        mensagem_erro       NVARCHAR(4000) NULL,
        dt_erro             DATETIME     NULL,
        CONSTRAINT PK_BuildCrmDetalhadoLoteControle PRIMARY KEY CLUSTERED (id_cnpj)
    );
END;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_controle', 'etapa') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle ADD etapa VARCHAR(80) NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_controle', 'mensagem_erro') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle ADD mensagem_erro NVARCHAR(4000) NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_controle', 'dt_erro') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_controle ADD dt_erro DATETIME NULL;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_log') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log (
        id_lote_log                    BIGINT IDENTITY(1,1) NOT NULL,
        uf_farmacia                    CHAR(2)      NOT NULL,
        pipeline_versao                VARCHAR(40)  NOT NULL,
        dt_data_inicio                 DATE         NOT NULL,
        dt_data_fim                    DATE         NOT NULL,
        lote_num                       INT          NOT NULL,
        dt_inicio_lote                 DATETIME     NOT NULL,
        dt_fim_lote                    DATETIME     NULL,
        segundos_lote                  INT          NULL,
        milissegundos_lote             INT          NULL,
        qtd_cnpjs_lote                 INT          NULL,
        nu_dados_crm_lote              INT          NULL,
        nu_volume_alertas_lote         INT          NULL,
        nu_raiox_tx_lote               INT          NULL,
        nu_cnpjs_processados_acumulado INT          NULL,
        nu_cnpjs_total                 INT          NULL,
        status                         VARCHAR(20)  NOT NULL,
        etapa                          VARCHAR(80)  NULL,
        mensagem_erro                  NVARCHAR(4000) NULL,
        observacao                     VARCHAR(400) NULL,
        CONSTRAINT PK_BuildCrmDetalhadoLoteLog PRIMARY KEY CLUSTERED (id_lote_log)
    );

    CREATE INDEX IDX_CrmDetalhadoLoteLog_UfPeriodo
        ON temp_CGUSC.fp.build_crm_detalhado_lote_log
            (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, lote_num);
END;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'mensagem_erro') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD mensagem_erro NVARCHAR(4000) NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_lote_log', 'etapa') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_lote_log ADD etapa VARCHAR(80) NULL;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_diario') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_perfil_diario (
        id_cnpj                              INT           NOT NULL,
        competencia                          INT           NOT NULL,
        dt_janela                            DATE          NOT NULL,
        nu_prescricoes_dia                   SMALLINT      NOT NULL,
        nu_crms_distintos                    SMALLINT      NOT NULL,
        mediana_diaria                       DECIMAL(7,2)  NULL,
        is_dia_com_volume_horario_anomalo    BIT           NOT NULL,
        is_anomalo_unico                     BIT           NOT NULL,
        is_crm_multiplo                      BIT           NOT NULL
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_horario') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_perfil_horario (
        id_cnpj                      INT           NOT NULL,
        dt_janela                    DATE          NOT NULL,
        hr_janela                    TINYINT       NOT NULL,
        nu_prescricoes               SMALLINT      NOT NULL,
        nu_crms_diferentes           SMALLINT      NOT NULL,
        mediana_hora                 DECIMAL(6,2)  NULL,
        is_hora_com_alerta           BIT           NOT NULL,
        is_volume_horario_anomalo    BIT           NOT NULL,
        is_crm_unico                 BIT           NOT NULL,
        is_crm_multiplo              BIT           NOT NULL
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_mediana_autorizacoes_horaria (
        id_cnpj       INT           NOT NULL,
        ano           SMALLINT      NOT NULL,
        trimestre     TINYINT       NOT NULL,
        hr_janela     TINYINT       NOT NULL,
        mediana_hora  DECIMAL(6,2)  NULL
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel (
        id_cnpj              INT           NOT NULL,
        dt_janela            DATE          NOT NULL,
        hr_janela            TINYINT       NOT NULL,
        mediana_hora_movel   DECIMAL(6,2)  NULL,
        mad_hora_movel       DECIMAL(10,4) NULL
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.build_volume_horario_anomalo_alertas') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_volume_horario_anomalo_alertas (
        id_cnpj          INT           NOT NULL,
        competencia      INT           NOT NULL,
        dt_alerta        DATE          NOT NULL,
        hr_janela        TINYINT       NOT NULL,
        nu_prescricoes   SMALLINT      NOT NULL,
        nu_crms          SMALLINT      NOT NULL,
        mediana_hora     DECIMAL(6,2)  NULL,
        multiplicador    DECIMAL(10,1) NULL
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_raiox_tx (
        id_cnpj          INT           NOT NULL,
        dt_janela        DATE          NOT NULL,
        hr_janela        TINYINT       NOT NULL,
        data_hora        DATETIME      NOT NULL,
        num_autorizacao  VARCHAR(50)   NOT NULL,
        id_medico        VARCHAR(13)   NOT NULL,
        id_gtin          INT           NOT NULL,
        valor_pago       DECIMAL(9,2)  NULL
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NOT NULL
   AND TYPE_NAME(COLUMNPROPERTY(OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx'), 'data_hora', 'SystemTypeId')) <> 'datetime'
BEGIN
    ALTER TABLE temp_CGUSC.fp.build_crm_raiox_tx ALTER COLUMN data_hora DATETIME NOT NULL;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_dados_crm_detalhado (
        nu_cnpj                         CHAR(14)      NOT NULL,
        competencia                     INT           NOT NULL,
        id_medico                       VARCHAR(13)   NOT NULL,
        nu_prescricoes_medico           SMALLINT      NOT NULL,
        vl_autorizacoes_medico          DECIMAL(18,2) NOT NULL,
        nu_prescricoes_pico_h           SMALLINT      NOT NULL,
        taxa_pico_h                     DECIMAL(7,2)  NOT NULL,
        dt_prescricao_inicial_medico    DATE          NOT NULL,
        dt_prescricao_final_medico      DATE          NOT NULL
    );
END;

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_diario') AND name = 'IDX_DailyProfile')
    CREATE CLUSTERED INDEX IDX_DailyProfile ON temp_CGUSC.fp.build_crm_perfil_diario(id_cnpj, dt_janela);

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_horario') AND name = 'IDX_PerfilHorario')
    CREATE CLUSTERED INDEX IDX_PerfilHorario ON temp_CGUSC.fp.build_crm_perfil_horario(id_cnpj, dt_janela, hr_janela);

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria') AND name = 'IDX_MedianaHoraria')
    CREATE CLUSTERED INDEX IDX_MedianaHoraria ON temp_CGUSC.fp.build_mediana_autorizacoes_horaria(id_cnpj, ano, trimestre, hr_janela);

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel') AND name = 'IDX_MedianaHorariaMovel')
    CREATE CLUSTERED INDEX IDX_MedianaHorariaMovel ON temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel(id_cnpj, dt_janela, hr_janela);

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_volume_horario_anomalo_alertas') AND name = 'IDX_AlertaSequencialCNPJ')
    CREATE CLUSTERED INDEX IDX_AlertaSequencialCNPJ ON temp_CGUSC.fp.build_volume_horario_anomalo_alertas(id_cnpj, dt_alerta, hr_janela);

-- As duas maiores tabelas ficam como heap durante a carga loteada.
-- Os clustered indexes sao criados apenas ao final para evitar custo de
-- manutencao do indice em cada INSERT incremental.


-- ============================================================================
-- PASSO 1: Processamento por lotes de CNPJ
-- ============================================================================

UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
SET etapa = 'INICIANDO_PROCESSAMENTO_LOTEADO',
    dt_atualizacao = GETDATE()
WHERE uf_farmacia = @uf_farmacia
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim;

PRINT '>> [CRM DETALHADO LOTEADO] Iniciando processamento...';
PRINT '   UF fonte: ' + @uf_farmacia;
PRINT '   Periodo: ' + CAST(@DataInicio AS VARCHAR(10)) + ' -> ' + CAST(@DataFim AS VARCHAR(10));
PRINT '   Lote: ' + CAST(@lote_size AS VARCHAR(10)) + ' CNPJs por iteracao';


-- Limpa lote interrompido para reprocessar do zero.
PRINT '>> Passo 1.0: Limpando CNPJs interrompidos...';
UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
SET etapa = 'LIMPANDO_CNPJS_INTERROMPIDOS',
    dt_atualizacao = GETDATE()
WHERE uf_farmacia = @uf_farmacia
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim;

SET @t1 = GETDATE();

DELETE T
FROM temp_CGUSC.fp.build_crm_perfil_diario T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.id_cnpj = T.id_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE T
FROM temp_CGUSC.fp.build_crm_perfil_horario T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.id_cnpj = T.id_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE T
FROM temp_CGUSC.fp.build_mediana_autorizacoes_horaria T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.id_cnpj = T.id_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE T
FROM temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.id_cnpj = T.id_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE T
FROM temp_CGUSC.fp.build_volume_horario_anomalo_alertas T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.id_cnpj = T.id_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE T
FROM temp_CGUSC.fp.build_crm_raiox_tx T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.id_cnpj = T.id_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE T
FROM temp_CGUSC.fp.build_dados_crm_detalhado T
INNER JOIN temp_CGUSC.fp.build_crm_detalhado_lote_controle C ON C.cnpj = T.nu_cnpj
WHERE C.status = 'PROCESSANDO';

DELETE FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle
WHERE status = 'PROCESSANDO';

PRINT '   Limpeza concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);


-- Fila de CNPJs pendentes.
PRINT '>> Passo 1.1: Construindo fila de CNPJs pendentes...';
UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
SET etapa = 'CONSTRUINDO_FILA_CNPJS',
    dt_atualizacao = GETDATE()
WHERE uf_farmacia = @uf_farmacia
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim;

SET @t1 = GETDATE();

DROP TABLE IF EXISTS #cnpjs_pendentes;

SELECT
    C.id_cnpj,
    C.cnpj
INTO #cnpjs_pendentes
FROM #crm_cnpjs_fonte_atual C
WHERE NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle L
    WHERE L.id_cnpj = C.id_cnpj
      AND L.status = 'OK'
);

SET @nu_pendentes      = (SELECT COUNT(*) FROM #cnpjs_pendentes);
SET @nu_ja_processados = (
    SELECT COUNT(*)
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
    WHERE C.status = 'OK'
      AND EXISTS (
          SELECT 1
          FROM #crm_cnpjs_fonte_atual F
          WHERE F.id_cnpj = C.id_cnpj
      )
);
SET @nu_total          = @nu_pendentes + @nu_ja_processados;

PRINT '   CNPJs ja processados: ' + CAST(@nu_ja_processados AS VARCHAR(20)) + ' / ' + CAST(@nu_total AS VARCHAR(20));
PRINT '   CNPJs pendentes:      ' + CAST(@nu_pendentes AS VARCHAR(20));
PRINT '   Fila concluida em:    ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

IF @nu_pendentes = 0
BEGIN
    PRINT '   Nada a processar. Base loteada ja esta completa.';
    GOTO Finalizar;
END;

PRINT '>> Preparando tabelas grandes para carga em heap...';
UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
SET etapa = 'PREPARANDO_HEAP_TABELAS_GRANDES',
    dt_atualizacao = GETDATE()
WHERE uf_farmacia = @uf_farmacia
  AND pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim;

SET @t1 = GETDATE();

IF EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') AND name = 'IDX_RaioX_Cnpj_Data')
    DROP INDEX IDX_RaioX_Cnpj_Data ON temp_CGUSC.fp.build_crm_raiox_tx;

IF EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') AND name = 'IDX_DadosDet')
    DROP INDEX IDX_DadosDet ON temp_CGUSC.fp.build_dados_crm_detalhado;

PRINT '   Preparacao concluida em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);


WHILE EXISTS (SELECT 1 FROM #cnpjs_pendentes)
BEGIN
    SET @lote_num += 1;
    SET @t1 = GETDATE();
    SET @id_lote_log = NULL;
    SET @dt_fim_lote = NULL;
    SET @nu_dados_crm_lote = NULL;
    SET @nu_volume_alertas_lote = NULL;
    SET @nu_raiox_tx_lote = NULL;

    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, lote_num,
         dt_inicio_lote, status, etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @lote_num,
         @t1, 'PROCESSANDO', 'INICIO_LOTE', 'Lote iniciado.');

    SET @id_lote_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #lote_atual;

    SELECT TOP (@lote_size)
        id_cnpj,
        cnpj
    INTO #lote_atual
    FROM #cnpjs_pendentes
    ORDER BY id_cnpj;

    SET @nu_lote = (SELECT COUNT(*) FROM #lote_atual);

    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log
    SET qtd_cnpjs_lote = @nu_lote
    WHERE id_lote_log = @id_lote_log;

    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_controle (id_cnpj, cnpj, dt_inicio, status)
    SELECT L.id_cnpj, L.cnpj, GETDATE(), 'PROCESSANDO'
    FROM #lote_atual L
    WHERE NOT EXISTS (
        SELECT 1
        FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
        WHERE C.id_cnpj = L.id_cnpj
    );

    SET @etapa = 'INICIO_LOTE';

    UPDATE C
    SET status = 'PROCESSANDO',
        dt_inicio = GETDATE(),
        dt_fim = NULL,
        etapa = @etapa,
        mensagem_erro = NULL,
        dt_erro = NULL
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
    INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    BEGIN TRY
    SET @etapa = 'IDEMPOTENCIA_LOTE';

    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log
    SET etapa = @etapa
    WHERE id_lote_log = @id_lote_log;

    UPDATE C
    SET etapa = @etapa
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
    INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    -- Garante idempotencia do lote atual.
    DELETE T FROM temp_CGUSC.fp.build_crm_perfil_diario T INNER JOIN #lote_atual L ON L.id_cnpj = T.id_cnpj;
    DELETE T FROM temp_CGUSC.fp.build_crm_perfil_horario T INNER JOIN #lote_atual L ON L.id_cnpj = T.id_cnpj;
    DELETE T FROM temp_CGUSC.fp.build_mediana_autorizacoes_horaria T INNER JOIN #lote_atual L ON L.id_cnpj = T.id_cnpj;
    DELETE T FROM temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel T INNER JOIN #lote_atual L ON L.id_cnpj = T.id_cnpj;
    DELETE T FROM temp_CGUSC.fp.build_volume_horario_anomalo_alertas T INNER JOIN #lote_atual L ON L.id_cnpj = T.id_cnpj;
    DELETE T FROM temp_CGUSC.fp.build_crm_raiox_tx T INNER JOIN #lote_atual L ON L.id_cnpj = T.id_cnpj;
    DELETE T FROM temp_CGUSC.fp.build_dados_crm_detalhado T INNER JOIN #lote_atual L ON L.cnpj = T.nu_cnpj;

    PRINT '>> Lote ' + RIGHT('0000' + CAST(@lote_num AS VARCHAR(10)), 4) +
          ' | CNPJs no lote: ' + CAST(@nu_lote AS VARCHAR(10));


    -- ========================================================================
    -- 2.A: Base horaria mestra do lote
    -- ========================================================================
    SET @etapa = '2.A_BASE_HORARIA_MESTRA';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();
    DROP TABLE IF EXISTS #base_horaria_mestra;

    SELECT
        L.cnpj AS nu_cnpj,
        CAST(CAST(M.crm AS VARCHAR(10)) + '/' + M.crm_uf AS VARCHAR(13)) AS id_medico,
        YEAR(M.data_hora) * 100 + MONTH(M.data_hora) AS competencia,
        CAST(M.data_hora AS DATE) AS dt_dia,
        CAST(DATEPART(HOUR, M.data_hora) AS TINYINT) AS hr_janela,
        CAST(COUNT(DISTINCT M.num_autorizacao) AS SMALLINT) AS nu_prescricoes_hora,
        CAST(SUM(M.valor_pago) AS DECIMAL(18,2)) AS vl_autorizacoes_hora,
        CAST(MIN(M.data_hora) AS SMALLDATETIME) AS dt_ini_hora,
        CAST(MAX(M.data_hora) AS SMALLDATETIME) AS dt_fim_hora,
        CAST(DATEDIFF(MINUTE, MIN(M.data_hora), MAX(M.data_hora)) AS TINYINT) AS nu_minutos_hora
    INTO #base_horaria_mestra
    FROM #crm_mov_fonte_atual M
    INNER JOIN temp_CGUSC.fp.medicamentos_patologia PAT ON PAT.codigo_barra = M.codigo_barra
    INNER JOIN #lote_atual L ON L.cnpj = M.cnpj
    WHERE M.crm_uf IS NOT NULL
      AND M.crm IS NOT NULL
      AND M.crm_uf <> 'BR'
      AND M.data_hora >= @DataInicio
      AND M.data_hora < DATEADD(DAY, 1, @DataFim)
    GROUP BY
        L.cnpj,
        M.crm,
        M.crm_uf,
        YEAR(M.data_hora),
        MONTH(M.data_hora),
        CAST(M.data_hora AS DATE),
        DATEPART(HOUR, M.data_hora);

    CREATE CLUSTERED INDEX IDX_Mestra ON #base_horaria_mestra(nu_cnpj, id_medico, competencia);
    CREATE NONCLUSTERED INDEX IDX_Mestra_DiaHora
        ON #base_horaria_mestra(nu_cnpj, dt_dia, hr_janela)
        INCLUDE (id_medico, competencia, nu_prescricoes_hora);

    PRINT '      2.A base_horaria_mestra: ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.B: Derivacoes mensais/horarias/estabelecimento
    -- ========================================================================
    SET @etapa = '2.B_DERIVACOES_BASE';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    DROP TABLE IF EXISTS #base_agregada_crm_cnpj;
    SELECT
        CONCAT(nu_cnpj, '|', id_medico, '|', CAST(competencia AS VARCHAR(6))) AS chave,
        id_medico,
        nu_cnpj,
        competencia,
        CAST(SUM(nu_prescricoes_hora) AS SMALLINT) AS nu_prescricoes_medico,
        CAST(SUM(vl_autorizacoes_hora) AS DECIMAL(18,2)) AS vl_autorizacoes_medico,
        CAST(MIN(dt_ini_hora) AS DATE) AS dt_prescricao_inicial_medico,
        CAST(MAX(dt_fim_hora) AS DATE) AS dt_prescricao_final_medico
    INTO #base_agregada_crm_cnpj
    FROM #base_horaria_mestra
    GROUP BY nu_cnpj, id_medico, competencia;

    CREATE CLUSTERED INDEX IDX_BaseAgreg_Key ON #base_agregada_crm_cnpj(nu_cnpj, id_medico, competencia);

    DROP TABLE IF EXISTS #base_horaria_crm;
    SELECT * INTO #base_horaria_crm FROM #base_horaria_mestra;
    CREATE CLUSTERED INDEX IDX_BaseHora_Mestra ON #base_horaria_crm(nu_cnpj, id_medico, dt_dia, hr_janela);

    DROP TABLE IF EXISTS #tb_info_estabelecimento;
    SELECT
        nu_cnpj AS cnpj,
        competencia,
        CAST(SUM(nu_prescricoes_hora) AS INT) AS nu_autorizacoes_estabelecimento,
        CAST(SUM(vl_autorizacoes_hora) AS DECIMAL(18,2)) AS vl_autorizacoes_estabelecimento,
        MIN(dt_ini_hora) AS dt_venda_inicial_estabelecimento,
        MAX(dt_fim_hora) AS dt_venda_final_estabelecimento
    INTO #tb_info_estabelecimento
    FROM #base_horaria_mestra
    GROUP BY nu_cnpj, competencia;

    CREATE CLUSTERED INDEX IDX_InfoEst ON #tb_info_estabelecimento(cnpj, competencia);

    DROP TABLE IF EXISTS #whitelist_crms_relevantes;
    SELECT nu_cnpj, id_medico
    INTO #whitelist_crms_relevantes
    FROM #base_agregada_crm_cnpj
    GROUP BY nu_cnpj, id_medico
    HAVING SUM(nu_prescricoes_medico) >= 5;

    CREATE CLUSTERED INDEX IDX_Whitelist ON #whitelist_crms_relevantes(nu_cnpj, id_medico);

    PRINT '      2.B derivacoes base:       ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.C: Anomalias horarias e medianas
    -- ========================================================================
    SET @etapa = '2.C_ANOMALIAS_HORARIAS';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    SET @etapa = '2.C.1_BASE_HORARIA_SELECT';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'SELECT INTO #base_horaria em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #base_horaria;
    SELECT
        nu_cnpj AS cnpj,
        competencia,
        dt_dia AS dt_janela,
        hr_janela,
        CAST(SUM(nu_prescricoes_hora) AS SMALLINT) AS nu_prescricoes_hora,
        CAST(COUNT(DISTINCT id_medico) AS SMALLINT) AS nu_crms_distintos_hora
    INTO #base_horaria
    FROM #base_horaria_mestra
    GROUP BY nu_cnpj, competencia, dt_dia, hr_janela;

    SET @nu_registros_etapa = @@ROWCOUNT;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'SELECT INTO #base_horaria.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.2_BASE_HORARIA_INDEXES';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Indices de #base_horaria em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    CREATE CLUSTERED INDEX IDX_BH_Surto ON #base_horaria(cnpj, dt_janela, hr_janela);
    CREATE NONCLUSTERED INDEX IDX_BH_Movel ON #base_horaria(cnpj, hr_janela, dt_janela) INCLUDE (nu_prescricoes_hora);

    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        observacao = 'Indices IDX_BH_Surto e IDX_BH_Movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.3_MEDIANA_TRIMESTRAL';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'PERCENTILE_CONT trimestral por CNPJ/hora em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #mediana_hora;
    SELECT DISTINCT
        cnpj,
        competencia,
        hr_janela,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nu_prescricoes_hora)
            OVER (PARTITION BY cnpj, (competencia / 100), ((competencia % 100 - 1) / 3), hr_janela) AS mediana_hora
    INTO #mediana_hora
    FROM #base_horaria;

    SET @nu_registros_etapa = @@ROWCOUNT;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'SELECT INTO #mediana_hora.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.4_DATAS_HORAS_MOVEL';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Criacao de grade dia ativo x 24 horas em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #horas_janela;
    CREATE TABLE #horas_janela (
        hr_janela TINYINT NOT NULL PRIMARY KEY
    );

    INSERT INTO #horas_janela (hr_janela)
    VALUES (0), (1), (2), (3), (4), (5), (6), (7),
           (8), (9), (10), (11), (12), (13), (14), (15),
           (16), (17), (18), (19), (20), (21), (22), (23);

    DROP TABLE IF EXISTS #datas_horas_movel;
    SELECT
        D.cnpj,
        D.competencia,
        D.dt_janela,
        H.hr_janela
    INTO #datas_horas_movel
    FROM (
        SELECT DISTINCT cnpj, competencia, dt_janela
        FROM #base_horaria
    ) D
    CROSS JOIN #horas_janela H;

    CREATE CLUSTERED INDEX IDX_DatasHorasMovel
        ON #datas_horas_movel(cnpj, dt_janela, hr_janela);

    SET @nu_registros_etapa = (SELECT COUNT_BIG(*) FROM #datas_horas_movel);
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #datas_horas_movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.5_DIAS_ATIVOS_MOVEL';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Criacao de #dias_ativos_movel em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #dias_ativos_movel;
    SELECT
        cnpj,
        dt_janela
    INTO #dias_ativos_movel
    FROM #base_horaria
    GROUP BY cnpj, dt_janela;

    CREATE CLUSTERED INDEX IDX_DiasAtivosMovel
        ON #dias_ativos_movel(cnpj, dt_janela);

    SET @nu_registros_etapa = @@ROWCOUNT;
    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #dias_ativos_movel;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #dias_ativos_movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.6A_HORAS_CANDIDATAS';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Selecao de horas candidatas a volume horario anomalo em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #horas_volume_candidatas;
    SELECT
        cnpj,
        competencia,
        dt_janela,
        hr_janela,
        nu_prescricoes_hora
    INTO #horas_volume_candidatas
    FROM #base_horaria
    WHERE nu_prescricoes_hora >= 10;

    CREATE CLUSTERED INDEX IDX_HorasVolumeCandidatas
        ON #horas_volume_candidatas(cnpj, dt_janela, hr_janela);

    SET @nu_registros_etapa = @@ROWCOUNT;
    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #horas_volume_candidatas;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #horas_volume_candidatas.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.6B_BASELINE_MOVEL_SELECT';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'SELECT INTO #baseline_horaria_movel para horas candidatas em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #baseline_horaria_movel;
    SELECT
        H.cnpj,
        H.competencia,
        H.dt_janela,
        H.hr_janela,
        CAST(ISNULL(B.nu_prescricoes_hora, 0) AS SMALLINT) AS nu_prescricoes_hora
    INTO #baseline_horaria_movel
    FROM #horas_volume_candidatas H
    INNER JOIN #dias_ativos_movel D
        ON  D.cnpj = H.cnpj
        AND D.dt_janela >= DATEADD(MONTH, -3, H.dt_janela)
        AND D.dt_janela < H.dt_janela
    LEFT JOIN #base_horaria B
        ON  B.cnpj = D.cnpj
        AND B.dt_janela = D.dt_janela
        AND B.hr_janela = H.hr_janela;

    SET @nu_registros_etapa = @@ROWCOUNT;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'SELECT INTO #baseline_horaria_movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.6C_BASELINE_MOVEL_INDEX';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Indice de #baseline_horaria_movel em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    CREATE CLUSTERED INDEX IDX_BaselineMovel
        ON #baseline_horaria_movel(cnpj, dt_janela, hr_janela, nu_prescricoes_hora);

    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        observacao = 'Indice IDX_BaselineMovel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.6D_BASELINE_MOVEL_COUNT';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Contagem de #baseline_horaria_movel em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #baseline_horaria_movel;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'COUNT_BIG de #baseline_horaria_movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.7_MESES_ATIVOS_BASELINE';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Contagem de meses ativos do baseline em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #meses_ativos_baseline;
    SELECT
        H.cnpj,
        H.dt_janela,
        COUNT(DISTINCT MA.competencia) AS qtd_meses_ativos_baseline
    INTO #meses_ativos_baseline
    FROM (
        SELECT DISTINCT cnpj, dt_janela
        FROM #horas_volume_candidatas
    ) H
    INNER JOIN #dias_ativos_movel D
        ON  D.cnpj = H.cnpj
        AND D.dt_janela >= DATEADD(MONTH, -3, H.dt_janela)
        AND D.dt_janela < H.dt_janela
    CROSS APPLY (
        SELECT CAST(YEAR(D.dt_janela) * 100 + MONTH(D.dt_janela) AS INT) AS competencia
    ) MA
    GROUP BY H.cnpj, H.dt_janela;

    CREATE CLUSTERED INDEX IDX_MesesAtivosBaseline
        ON #meses_ativos_baseline(cnpj, dt_janela);

    SET @nu_registros_etapa = @@ROWCOUNT;
    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #meses_ativos_baseline;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #meses_ativos_baseline.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.8_MEDIANA_MOVEL_CALC';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'PERCENTILE_CONT da mediana movel em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #mediana_hora_movel_calc;
    SELECT DISTINCT
        B.cnpj,
        B.competencia,
        B.dt_janela,
        B.hr_janela,
        MB.qtd_meses_ativos_baseline,
        CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY B.nu_prescricoes_hora)
            OVER (PARTITION BY B.cnpj, B.dt_janela, B.hr_janela) AS DECIMAL(6,2)) AS mediana_hora_movel
    INTO #mediana_hora_movel_calc
    FROM #baseline_horaria_movel B
    INNER JOIN #meses_ativos_baseline MB
        ON  MB.cnpj = B.cnpj
        AND MB.dt_janela = B.dt_janela;

    CREATE CLUSTERED INDEX IDX_MedianaMovelCalc
        ON #mediana_hora_movel_calc(cnpj, dt_janela, hr_janela);

    SET @nu_registros_etapa = @@ROWCOUNT;
    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #mediana_hora_movel_calc;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #mediana_hora_movel_calc.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.9_MEDIANA_MOVEL_FINAL';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Filtro de mediana movel com baseline minimo em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #mediana_hora_movel;
    SELECT
        cnpj,
        competencia,
        dt_janela,
        hr_janela,
        mediana_hora_movel
    INTO #mediana_hora_movel
    FROM #mediana_hora_movel_calc
    WHERE qtd_meses_ativos_baseline >= 2;

    CREATE CLUSTERED INDEX IDX_MedianaMovel ON #mediana_hora_movel(cnpj, dt_janela, hr_janela);

    SET @nu_registros_etapa = @@ROWCOUNT;
    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #mediana_hora_movel;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #mediana_hora_movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.10_MAD_MOVEL';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'PERCENTILE_CONT do MAD movel em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #mad_hora_movel;
    SELECT DISTINCT
        B.cnpj,
        B.competencia,
        B.dt_janela,
        B.hr_janela,
        CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(B.nu_prescricoes_hora - M.mediana_hora_movel))
            OVER (PARTITION BY B.cnpj, B.dt_janela, B.hr_janela) AS DECIMAL(10,4)) AS mad_hora_movel
    INTO #mad_hora_movel
    FROM #baseline_horaria_movel B
    INNER JOIN #mediana_hora_movel M
        ON  M.cnpj = B.cnpj
        AND M.dt_janela = B.dt_janela
        AND M.hr_janela = B.hr_janela;

    CREATE CLUSTERED INDEX IDX_MadMovel ON #mad_hora_movel(cnpj, dt_janela, hr_janela);

    SET @nu_registros_etapa = @@ROWCOUNT;
    SELECT @nu_registros_etapa = COUNT_BIG(*) FROM #mad_hora_movel;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'Criacao e indice de #mad_hora_movel.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.11_ANOMALIAS_SELECT';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Classificacao de anomalias horarias em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    DROP TABLE IF EXISTS #anomalias_horarias;
    SELECT
        H.*,
        MT.mediana_hora AS mediana_hora,
        MAD.mad_hora_movel AS mad_hora,
        CASE
            WHEN H.nu_prescricoes_hora >= 10
             AND M.mediana_hora_movel IS NOT NULL
             AND MAD.mad_hora_movel > 0
             AND (0.6745 * (H.nu_prescricoes_hora - M.mediana_hora_movel) / MAD.mad_hora_movel) > 4.5
            THEN 1
            WHEN H.nu_prescricoes_hora >= 10
             AND M.mediana_hora_movel IS NOT NULL
             AND MAD.mad_hora_movel = 0
             AND H.nu_prescricoes_hora > M.mediana_hora_movel
            THEN 1
            ELSE 0
        END AS is_anomalo_hora
    INTO #anomalias_horarias
    FROM #base_horaria H
    LEFT JOIN #mediana_hora MT
        ON  MT.cnpj = H.cnpj
        AND MT.competencia = H.competencia
        AND MT.hr_janela = H.hr_janela
    LEFT JOIN #mediana_hora_movel M
        ON  M.cnpj = H.cnpj
        AND M.dt_janela = H.dt_janela
        AND M.hr_janela = H.hr_janela
    LEFT JOIN #mad_hora_movel MAD
        ON  MAD.cnpj = H.cnpj
        AND MAD.dt_janela = H.dt_janela
        AND MAD.hr_janela = H.hr_janela;

    SET @nu_registros_etapa = @@ROWCOUNT;
    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        nu_registros = @nu_registros_etapa,
        observacao = 'SELECT INTO #anomalias_horarias.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C.12_ANOMALIAS_INDEX';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;
    SET @t_etapa = GETDATE();
    SET @id_etapa_log = NULL;
    INSERT INTO temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
        (uf_farmacia, pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, observacao)
    VALUES
        (@uf_farmacia, @pipeline_versao, @DataInicio, @DataFim, @etapa, @t_etapa, 'Indice de #anomalias_horarias em andamento.');
    SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

    CREATE CLUSTERED INDEX IDX_AnomaliaH ON #anomalias_horarias(cnpj, dt_janela, hr_janela);

    SET @dt_fim_etapa = GETDATE();
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    SET dt_fim_etapa = @dt_fim_etapa,
        segundos_etapa = DATEDIFF(SECOND, @t_etapa, @dt_fim_etapa),
        milissegundos_etapa = DATEDIFF(MILLISECOND, @t_etapa, @dt_fim_etapa),
        observacao = 'Indice IDX_AnomaliaH.'
    WHERE id_etapa_log = @id_etapa_log;

    SET @etapa = '2.C_ANOMALIAS_HORARIAS';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    PRINT '      2.C anomalias horarias:    ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.D: Pior hora por CRM/mes, surtos e totais diarios
    -- ========================================================================
    SET @etapa = '2.D_SURTOS_PIORES_HORAS';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    DROP TABLE IF EXISTS #pior_dia_crm;
    ;WITH calc_taxa AS (
        SELECT
            nu_cnpj,
            id_medico,
            competencia,
            dt_dia,
            hr_janela,
            nu_prescricoes_hora,
            dt_ini_hora,
            dt_fim_hora,
            nu_minutos_hora,
            CASE
                WHEN nu_minutos_hora = 0 THEN CAST(nu_prescricoes_hora AS FLOAT) * 60.0
                ELSE CAST(nu_prescricoes_hora AS DECIMAL(10,2)) / (CAST(NULLIF(nu_minutos_hora, 0) AS DECIMAL(10,2)) / 60.0)
            END AS taxa_hora
        FROM #base_horaria_crm
        WHERE nu_prescricoes_hora >= 5
    ),
    ranked AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY nu_cnpj, id_medico, competencia
                ORDER BY
                    CASE
                        WHEN nu_prescricoes_hora >= 5  AND nu_minutos_hora <= 5 THEN 1
                        WHEN nu_prescricoes_hora >= 5  AND taxa_hora >= 12 THEN 2
                        WHEN nu_prescricoes_hora >= 10 AND (taxa_hora >= 7 OR nu_minutos_hora <= 60) THEN 3
                        ELSE 99
                    END ASC,
                    taxa_hora DESC,
                    nu_prescricoes_hora DESC
            ) AS rn
        FROM calc_taxa
    )
    SELECT
        nu_cnpj,
        id_medico,
        competencia,
        dt_dia,
        CAST(nu_prescricoes_hora AS SMALLINT) AS nu_prescricoes_pico_h,
        dt_ini_hora AS dt_ini_dia,
        dt_fim_hora AS dt_fim_dia,
        nu_minutos_hora AS nu_minutos_dia,
        CAST(taxa_hora AS DECIMAL(7,2)) AS taxa_dia
    INTO #pior_dia_crm
    FROM ranked
    WHERE rn = 1;

    CREATE CLUSTERED INDEX IDX_PiorDia ON #pior_dia_crm(nu_cnpj, id_medico, competencia);

    DROP TABLE IF EXISTS #crms_em_surto_raw;
    SELECT DISTINCT
        M.nu_cnpj,
        M.id_medico,
        M.competencia
    INTO #crms_em_surto_raw
    FROM #base_horaria_mestra M
    INNER JOIN #anomalias_horarias A
        ON  A.cnpj = M.nu_cnpj
        AND A.dt_janela = M.dt_dia
        AND A.hr_janela = M.hr_janela
    WHERE A.is_anomalo_hora = 1;

    DROP TABLE IF EXISTS #totais_diarios;
    SELECT
        cnpj,
        competencia,
        dt_janela,
        CAST(SUM(nu_prescricoes_hora) AS SMALLINT) AS nu_prescricoes_dia,
        CAST(MAX(is_anomalo_hora) AS BIT) AS dia_tem_anomalia_hora
    INTO #totais_diarios
    FROM #anomalias_horarias
    GROUP BY cnpj, competencia, dt_janela;

    DROP TABLE IF EXISTS #mediana_diaria;
    SELECT DISTINCT
        cnpj,
        competencia,
        CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nu_prescricoes_dia)
            OVER (PARTITION BY cnpj, (competencia / 100), ((competencia % 100 - 1) / 3)) AS DECIMAL(7,2)) AS mediana_diaria
    INTO #mediana_diaria
    FROM #totais_diarios;

    CREATE CLUSTERED INDEX IDX_MedianaDia ON #mediana_diaria(cnpj, competencia);

    PRINT '      2.D surtos e piores horas: ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.E: Tabelas de perfil e alertas locais
    -- ========================================================================
    SET @etapa = '2.E_PERFIS_ALERTAS';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    ;WITH crms_distintos_dia AS (
        SELECT
            nu_cnpj AS cnpj,
            dt_dia AS dt_janela,
            CAST(COUNT(DISTINCT id_medico) AS SMALLINT) AS nu_crms_distintos
        FROM #base_horaria_mestra
        GROUP BY nu_cnpj, dt_dia
    ),
    anomalias_unico_dia AS (
        SELECT DISTINCT U.id_cnpj, U.dt_dia AS dt_alerta
        FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U
        INNER JOIN #lote_atual L ON L.id_cnpj = U.id_cnpj
    ),
    anomalias_multiplo_dia AS (
        SELECT DISTINCT MU.id_cnpj, MU.dt_dia AS dt_alerta
        FROM temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas MU
        INNER JOIN #lote_atual L ON L.id_cnpj = MU.id_cnpj
    )
    INSERT INTO temp_CGUSC.fp.build_crm_perfil_diario
        (id_cnpj, competencia, dt_janela, nu_prescricoes_dia, nu_crms_distintos, mediana_diaria,
         is_dia_com_volume_horario_anomalo, is_anomalo_unico, is_crm_multiplo)
    SELECT
        F.id,
        T.competencia,
        T.dt_janela,
        T.nu_prescricoes_dia,
        ISNULL(C.nu_crms_distintos, CAST(0 AS SMALLINT)),
        M.mediana_diaria,
        CAST(T.dia_tem_anomalia_hora AS BIT),
        CAST(CASE WHEN U.dt_alerta IS NOT NULL THEN 1 ELSE 0 END AS BIT),
        CAST(CASE WHEN MU.dt_alerta IS NOT NULL THEN 1 ELSE 0 END AS BIT)
    FROM #totais_diarios T
    INNER JOIN #lote_atual L ON L.cnpj = T.cnpj
    INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = L.id_cnpj
    INNER JOIN #mediana_diaria M ON M.cnpj = T.cnpj AND M.competencia = T.competencia
    LEFT JOIN crms_distintos_dia C ON C.cnpj = T.cnpj AND C.dt_janela = T.dt_janela
    LEFT JOIN anomalias_unico_dia U ON U.id_cnpj = F.id AND U.dt_alerta = T.dt_janela
    LEFT JOIN anomalias_multiplo_dia MU ON MU.id_cnpj = F.id AND MU.dt_alerta = T.dt_janela;

    INSERT INTO temp_CGUSC.fp.build_crm_perfil_horario
        (id_cnpj, dt_janela, hr_janela, nu_prescricoes, nu_crms_diferentes, mediana_hora,
         is_hora_com_alerta, is_volume_horario_anomalo, is_crm_unico, is_crm_multiplo)
    SELECT
        F.id,
        H.dt_janela,
        H.hr_janela,
        H.nu_prescricoes_hora,
        H.nu_crms_distintos_hora,
        H.mediana_hora,
        CAST(CASE
            WHEN H.is_anomalo_hora = 1 THEN 1
            WHEN U.has_unico IS NOT NULL THEN 1
            WHEN MU.has_multiplo IS NOT NULL THEN 1
            ELSE 0
        END AS BIT) AS is_hora_com_alerta,
        CAST(CASE WHEN H.is_anomalo_hora = 1 THEN 1 ELSE 0 END AS BIT),
        CAST(CASE WHEN U.has_unico IS NOT NULL THEN 1 ELSE 0 END AS BIT),
        CAST(CASE WHEN MU.has_multiplo IS NOT NULL THEN 1 ELSE 0 END AS BIT)
    FROM #anomalias_horarias H
    INNER JOIN #lote_atual L ON L.cnpj = H.cnpj
    INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = L.id_cnpj
    INNER JOIN temp_CGUSC.fp.build_crm_perfil_diario D
        ON  D.id_cnpj = F.id
        AND D.dt_janela = H.dt_janela
    OUTER APPLY (
        SELECT TOP 1 1 AS has_unico
        FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U
        WHERE U.id_cnpj = F.id
          AND U.dt_dia = H.dt_janela
          AND H.hr_janela BETWEEN DATEPART(HOUR, U.dt_ini_concentracao) AND DATEPART(HOUR, U.dt_fim_concentracao)
    ) U
    OUTER APPLY (
        SELECT TOP 1 1 AS has_multiplo
        FROM temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas MU
        WHERE MU.id_cnpj = F.id
          AND MU.dt_dia = H.dt_janela
          AND H.hr_janela BETWEEN DATEPART(HOUR, MU.dt_ini_concentracao) AND DATEPART(HOUR, MU.dt_fim_concentracao)
    ) MU
    WHERE D.is_dia_com_volume_horario_anomalo = 1
       OR D.is_anomalo_unico = 1
       OR D.is_crm_multiplo = 1;

    INSERT INTO temp_CGUSC.fp.build_mediana_autorizacoes_horaria
        (id_cnpj, ano, trimestre, hr_janela, mediana_hora)
    SELECT DISTINCT
        F.id,
        CAST(M.competencia / 100 AS SMALLINT),
        CAST((M.competencia % 100 - 1) / 3 AS TINYINT),
        M.hr_janela,
        CAST(M.mediana_hora AS DECIMAL(6,2))
    FROM #mediana_hora M
    INNER JOIN #lote_atual L ON L.cnpj = M.cnpj
    INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = L.id_cnpj;

    INSERT INTO temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel
        (id_cnpj, dt_janela, hr_janela, mediana_hora_movel, mad_hora_movel)
    SELECT
        F.id,
        M.dt_janela,
        M.hr_janela,
        M.mediana_hora_movel,
        MAD.mad_hora_movel
    FROM #mediana_hora_movel M
    INNER JOIN #mad_hora_movel MAD
        ON  MAD.cnpj = M.cnpj
        AND MAD.dt_janela = M.dt_janela
        AND MAD.hr_janela = M.hr_janela
    INNER JOIN #lote_atual L ON L.cnpj = M.cnpj
    INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = L.id_cnpj;

    INSERT INTO temp_CGUSC.fp.build_volume_horario_anomalo_alertas
        (id_cnpj, competencia, dt_alerta, hr_janela, nu_prescricoes, nu_crms, mediana_hora, multiplicador)
    SELECT
        F.id,
        H.competencia,
        H.dt_janela,
        H.hr_janela,
        H.nu_prescricoes_hora,
        H.nu_crms_distintos_hora,
        H.mediana_hora,
        CAST(CAST(H.nu_prescricoes_hora AS DECIMAL(10,2)) / NULLIF(H.mediana_hora, 0) AS DECIMAL(10,1))
    FROM #anomalias_horarias H
    INNER JOIN #lote_atual L ON L.cnpj = H.cnpj
    INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = L.id_cnpj
    WHERE H.is_anomalo_hora = 1;

    PRINT '      2.E perfis e alertas:      ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.F: Raio-X transacional dos dias suspeitos
    -- ========================================================================
    SET @etapa = '2.F_CRM_RAIOX_TX';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    ;WITH DiasSuspeitos AS (
        SELECT V.id_cnpj, V.dt_alerta
        FROM temp_CGUSC.fp.build_volume_horario_anomalo_alertas V
        INNER JOIN #lote_atual L ON L.id_cnpj = V.id_cnpj
        UNION
        SELECT U.id_cnpj, U.dt_dia AS dt_alerta
        FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U
        INNER JOIN #lote_atual L ON L.id_cnpj = U.id_cnpj
        UNION
        SELECT MU.id_cnpj, MU.dt_dia AS dt_alerta
        FROM temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas MU
        INNER JOIN #lote_atual L ON L.id_cnpj = MU.id_cnpj
    )
    INSERT INTO temp_CGUSC.fp.build_crm_raiox_tx
        (id_cnpj, dt_janela, hr_janela, data_hora, num_autorizacao, id_medico, id_gtin, valor_pago)
    SELECT
        D.id_cnpj,
        CAST(M.data_hora AS DATE),
        CAST(DATEPART(HOUR, M.data_hora) AS TINYINT),
        CAST(M.data_hora AS DATETIME),
        M.num_autorizacao,
        CAST(CAST(M.crm AS VARCHAR(10)) + '/' + M.crm_uf AS VARCHAR(13)),
        PAT.id,
        CAST(M.valor_pago AS DECIMAL(9,2))
    FROM DiasSuspeitos D
    INNER JOIN #lote_atual L ON L.id_cnpj = D.id_cnpj
    INNER JOIN #crm_mov_fonte_atual M
        ON  M.cnpj = L.cnpj
        AND M.data_hora >= D.dt_alerta
        AND M.data_hora < DATEADD(DAY, 1, D.dt_alerta)
    INNER JOIN temp_CGUSC.fp.medicamentos_patologia PAT ON PAT.codigo_barra = M.codigo_barra
    WHERE M.crm_uf IS NOT NULL
      AND M.crm IS NOT NULL
      AND M.crm_uf <> 'BR'
      AND M.data_hora >= @DataInicio
      AND M.data_hora < DATEADD(DAY, 1, @DataFim);

    PRINT '      2.F build_crm_raiox_tx:          ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.G: Base de alertas e build_dados_crm_detalhado
    -- ========================================================================
    SET @etapa = '2.G_DADOS_CRM_DETALHADO';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    DROP TABLE IF EXISTS #lista_alertas_temp;
    SELECT
        A.nu_cnpj,
        A.id_medico,
        A.competencia,
        A.nu_prescricoes_medico,
        A.vl_autorizacoes_medico,
        A.dt_prescricao_inicial_medico,
        A.dt_prescricao_final_medico,
        DATEDIFF(DAY, A.dt_prescricao_inicial_medico, A.dt_prescricao_final_medico) + 1 AS nu_dias,
        ISNULL(P.nu_prescricoes_pico_h, 0) AS nu_prescricoes_pico_h,
        ISNULL(P.nu_minutos_dia, 0) AS nu_minutos_pico_h,
        ISNULL(P.taxa_dia, 0) AS taxa_pico_h,
        C.nu_autorizacoes_estabelecimento,
        C.dt_venda_inicial_estabelecimento,
        C.dt_venda_final_estabelecimento,
        TRY_CAST(A.nu_prescricoes_medico AS DECIMAL(10,2)) /
            NULLIF(TRY_CAST(C.nu_autorizacoes_estabelecimento AS DECIMAL(10,2)), 0) AS percentual
    INTO #lista_alertas_temp
    FROM #base_agregada_crm_cnpj A
    INNER JOIN #tb_info_estabelecimento C
        ON  C.cnpj = A.nu_cnpj
        AND C.competencia = A.competencia
    LEFT JOIN #pior_dia_crm P
        ON  P.nu_cnpj = A.nu_cnpj
        AND P.id_medico = A.id_medico
        AND P.competencia = A.competencia
    WHERE EXISTS (
            SELECT 1
            FROM #whitelist_crms_relevantes W
            WHERE W.nu_cnpj = A.nu_cnpj
              AND W.id_medico = A.id_medico
        )
       OR EXISTS (
            SELECT 1
            FROM #crms_em_surto_raw SR
            WHERE SR.nu_cnpj = A.nu_cnpj
              AND SR.id_medico = A.id_medico
              AND SR.competencia = A.competencia
        );

    INSERT INTO temp_CGUSC.fp.build_dados_crm_detalhado
        (nu_cnpj, competencia, id_medico, nu_prescricoes_medico, vl_autorizacoes_medico,
         nu_prescricoes_pico_h, taxa_pico_h, dt_prescricao_inicial_medico, dt_prescricao_final_medico)
    SELECT
        A.nu_cnpj,
        A.competencia,
        A.id_medico,
        A.nu_prescricoes_medico,
        A.vl_autorizacoes_medico,
        A.nu_prescricoes_pico_h,
        A.taxa_pico_h,
        A.dt_prescricao_inicial_medico,
        A.dt_prescricao_final_medico
    FROM #lista_alertas_temp A
    INNER JOIN temp_CGUSC.fp.build_crm_medico_brasil_mes P
        ON  P.id_medico = A.id_medico
        AND P.competencia = A.competencia;

    PRINT '      2.G build_dados_crm_detalhado:   ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);


    -- ========================================================================
    -- 2.H: Fecha checkpoint do lote
    -- ========================================================================
    SET @etapa = '2.H_CHECKPOINT';
    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log SET etapa = @etapa WHERE id_lote_log = @id_lote_log;
    UPDATE C SET etapa = @etapa FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @t_bloco = GETDATE();

    UPDATE C
    SET status = 'OK',
        dt_fim = GETDATE(),
        etapa = 'OK',
        mensagem_erro = NULL,
        dt_erro = NULL,
        nu_dados_crm = ISNULL((
            SELECT COUNT(*)
            FROM temp_CGUSC.fp.build_dados_crm_detalhado D
            WHERE D.nu_cnpj = C.cnpj
        ), 0),
        nu_volume_alertas = ISNULL((
            SELECT COUNT(*)
            FROM temp_CGUSC.fp.build_volume_horario_anomalo_alertas V
            WHERE V.id_cnpj = C.id_cnpj
        ), 0),
        nu_raiox_tx = ISNULL((
            SELECT COUNT(*)
            FROM temp_CGUSC.fp.build_crm_raiox_tx R
            WHERE R.id_cnpj = C.id_cnpj
        ), 0)
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
    INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    DELETE P
    FROM #cnpjs_pendentes P
    INNER JOIN #lote_atual L ON L.id_cnpj = P.id_cnpj;

    SET @nu_processados += @nu_lote;

    SELECT
        @nu_dados_crm_lote = SUM(ISNULL(C.nu_dados_crm, 0)),
        @nu_volume_alertas_lote = SUM(ISNULL(C.nu_volume_alertas, 0)),
        @nu_raiox_tx_lote = SUM(ISNULL(C.nu_raiox_tx, 0))
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
    INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

    SET @dt_fim_lote = GETDATE();

    UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log
    SET dt_fim_lote = @dt_fim_lote,
        segundos_lote = DATEDIFF(SECOND, @t1, @dt_fim_lote),
        milissegundos_lote = DATEDIFF(MILLISECOND, @t1, @dt_fim_lote),
        qtd_cnpjs_lote = @nu_lote,
        nu_dados_crm_lote = @nu_dados_crm_lote,
        nu_volume_alertas_lote = @nu_volume_alertas_lote,
        nu_raiox_tx_lote = @nu_raiox_tx_lote,
        nu_cnpjs_processados_acumulado = @nu_ja_processados + @nu_processados,
        nu_cnpjs_total = @nu_total,
        status = 'OK',
        etapa = 'OK',
        observacao = 'Lote finalizado.'
    WHERE id_lote_log = @id_lote_log;

    PRINT '      2.H checkpoint:            ' + CONVERT(VARCHAR(20), GETDATE() - @t_bloco, 114);

    PRINT '   Lote ' + RIGHT('0000' + CAST(@lote_num AS VARCHAR(10)), 4) +
          ' | ' + CAST(@nu_ja_processados + @nu_processados AS VARCHAR(20)) + '/' + CAST(@nu_total AS VARCHAR(20)) + ' CNPJs' +
          ' | ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);
    END TRY
    BEGIN CATCH
        DECLARE @mensagem_erro NVARCHAR(4000);

        SET @mensagem_erro = CONCAT(
            'Erro ', ERROR_NUMBER(),
            ' | Severidade ', ERROR_SEVERITY(),
            ' | Estado ', ERROR_STATE(),
            ' | Linha ', ERROR_LINE(),
            ' | ', ERROR_MESSAGE()
        );

        UPDATE C
        SET status = 'ERRO',
            dt_fim = GETDATE(),
            etapa = @etapa,
            mensagem_erro = @mensagem_erro,
            dt_erro = GETDATE()
        FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
        INNER JOIN #lote_atual L ON L.id_cnpj = C.id_cnpj;

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_metadata
        SET status = 'ERRO',
            dt_atualizacao = GETDATE(),
            observacao = LEFT(@mensagem_erro, 400)
        WHERE id_pipeline = 1;

        SET @dt_fim_lote = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_log
        SET dt_fim_lote = @dt_fim_lote,
            segundos_lote = DATEDIFF(SECOND, @t1, @dt_fim_lote),
            milissegundos_lote = DATEDIFF(MILLISECOND, @t1, @dt_fim_lote),
            qtd_cnpjs_lote = @nu_lote,
            nu_cnpjs_processados_acumulado = @nu_ja_processados + @nu_processados,
            nu_cnpjs_total = @nu_total,
            status = 'ERRO',
            etapa = @etapa,
            mensagem_erro = @mensagem_erro,
            observacao = LEFT(@mensagem_erro, 400)
        WHERE id_lote_log = @id_lote_log;

        IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NOT NULL
            UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
            SET status = 'ERRO',
                status_crm_detalhado_loteado = 'ERRO',
                etapa = @etapa,
                dt_atualizacao = GETDATE(),
                mensagem_erro = @mensagem_erro,
                dt_erro = GETDATE()
            WHERE uf_farmacia = @uf_farmacia
              AND pipeline_versao = @pipeline_versao
              AND dt_data_inicio = @DataInicio
              AND dt_data_fim = @DataFim;

        PRINT '   ERRO no lote ' + RIGHT('0000' + CAST(@lote_num AS VARCHAR(10)), 4) +
              ' | Etapa: ' + ISNULL(@etapa, 'N/I');
        PRINT '   ' + @mensagem_erro;

        THROW;
    END CATCH;
END;


-- ============================================================================
-- PASSO 2: Finalizacao da UF atual
-- ============================================================================
Finalizar:
UPDATE temp_CGUSC.fp.build_crm_detalhado_lote_metadata
SET status = CASE
        WHEN EXISTS (
            SELECT 1
            FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
            INNER JOIN #crm_cnpjs_fonte_atual F ON F.id_cnpj = C.id_cnpj
            WHERE C.status <> 'OK'
        ) THEN 'INCOMPLETO'
        ELSE 'OK'
    END,
    dt_atualizacao = GETDATE(),
    observacao = 'Execucao finalizada pelo script loteado.'
WHERE id_pipeline = 1;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NOT NULL
    UPDATE temp_CGUSC.fp.build_crm_pipeline_uf_controle
    SET status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
                INNER JOIN #crm_cnpjs_fonte_atual F ON F.id_cnpj = C.id_cnpj
                WHERE C.status <> 'OK'
            ) THEN 'PROCESSANDO'
            ELSE 'OK'
        END,
        etapa = CASE
            WHEN EXISTS (
                SELECT 1
                FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
                INNER JOIN #crm_cnpjs_fonte_atual F ON F.id_cnpj = C.id_cnpj
                WHERE C.status <> 'OK'
            ) THEN 'LOTEADO_INCOMPLETO'
            ELSE 'UF_OK'
        END,
        status_crm_detalhado_loteado = CASE
            WHEN EXISTS (
                SELECT 1
                FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
                INNER JOIN #crm_cnpjs_fonte_atual F ON F.id_cnpj = C.id_cnpj
                WHERE C.status <> 'OK'
            ) THEN 'INCOMPLETO'
            ELSE 'OK'
        END,
        dt_crm_detalhado_loteado = CASE
            WHEN EXISTS (
                SELECT 1
                FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
                INNER JOIN #crm_cnpjs_fonte_atual F ON F.id_cnpj = C.id_cnpj
                WHERE C.status <> 'OK'
            ) THEN dt_crm_detalhado_loteado
            ELSE GETDATE()
        END,
        dt_fim = CASE
            WHEN EXISTS (
                SELECT 1
                FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
                INNER JOIN #crm_cnpjs_fonte_atual F ON F.id_cnpj = C.id_cnpj
                WHERE C.status <> 'OK'
            ) THEN dt_fim
            ELSE GETDATE()
        END,
        dt_atualizacao = GETDATE()
    WHERE uf_farmacia = @uf_farmacia
      AND pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim;

SET @nu_ufs_processadas += 1;

DROP TABLE IF EXISTS #crm_mov_fonte_atual;
DROP TABLE IF EXISTS #crm_mov_fonte_atual_metadata;
DROP TABLE IF EXISTS #crm_cnpjs_fonte_atual;
DROP TABLE IF EXISTS #cnpjs_pendentes;
DROP TABLE IF EXISTS #lote_atual;

IF @uf_farmacia_alvo IS NULL
BEGIN
    GOTO ProximaUF;
END;


-- ============================================================================
-- RESULTADOS
-- ============================================================================
Resultados:
PRINT '>> Criando indices finais das tabelas grandes...';
SET @t1 = GETDATE();

IF OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') AND name = 'IDX_RaioX_Cnpj_Data')
    CREATE CLUSTERED INDEX IDX_RaioX_Cnpj_Data
        ON temp_CGUSC.fp.build_crm_raiox_tx(id_cnpj, dt_janela);

IF OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM temp_CGUSC.sys.indexes WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') AND name = 'IDX_DadosDet')
    CREATE CLUSTERED INDEX IDX_DadosDet
        ON temp_CGUSC.fp.build_dados_crm_detalhado(nu_cnpj, id_medico, competencia);

PRINT '   Indices finais concluidos em: ' + CONVERT(VARCHAR(20), GETDATE() - @t1, 114);

PRINT '==========================================================';
PRINT '   TEMPO TOTAL: ' + CONVERT(VARCHAR(20), GETDATE() - @t0, 114);
PRINT '   UFs processadas: ' + CAST(@nu_ufs_processadas AS VARCHAR(10));
PRINT '==========================================================';

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_metadata') IS NOT NULL
BEGIN
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
          FROM temp_CGUSC.fp.build_crm_detalhado_lote_metadata;';
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NOT NULL
    SELECT *
    FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
    ORDER BY uf_farmacia;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log') IS NOT NULL
BEGIN
    SELECT TOP 30
        uf_farmacia,
        etapa,
        dt_inicio_etapa,
        dt_fim_etapa,
        segundos_etapa,
        milissegundos_etapa,
        nu_registros,
        observacao
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_etapa_log
    WHERE pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
    ORDER BY id_etapa_log DESC;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_log') IS NOT NULL
BEGIN
    SELECT TOP 30
        uf_farmacia,
        lote_num,
        dt_inicio_lote,
        dt_fim_lote,
        segundos_lote,
        milissegundos_lote,
        qtd_cnpjs_lote,
        nu_dados_crm_lote,
        nu_volume_alertas_lote,
        nu_raiox_tx_lote,
        nu_cnpjs_processados_acumulado,
        nu_cnpjs_total,
        status,
        etapa,
        mensagem_erro
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_log
    WHERE pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
    ORDER BY id_lote_log DESC;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_controle') IS NOT NULL
BEGIN
    SELECT
        status,
        COUNT(*) AS qtd_cnpjs,
        SUM(ISNULL(nu_dados_crm, 0)) AS total_dados_crm,
        SUM(ISNULL(nu_volume_alertas, 0)) AS total_volume_alertas,
        SUM(ISNULL(nu_raiox_tx, 0)) AS total_raiox_tx,
        MIN(dt_inicio) AS primeiro_inicio,
        MAX(dt_fim) AS ultimo_fim
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle
    GROUP BY status;

    SELECT
        id_cnpj,
        cnpj,
        status,
        etapa,
        mensagem_erro,
        dt_inicio,
        dt_fim,
        dt_erro
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle C
    WHERE C.status <> 'OK'
    ORDER BY dt_inicio DESC, id_cnpj;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') IS NOT NULL
   AND OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_diario') IS NOT NULL
   AND OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_horario') IS NOT NULL
   AND OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel') IS NOT NULL
   AND OBJECT_ID('temp_CGUSC.fp.build_volume_horario_anomalo_alertas') IS NOT NULL
   AND OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NOT NULL
BEGIN
    SELECT
        (SELECT COUNT(*) FROM temp_CGUSC.fp.build_dados_crm_detalhado) AS qtd_dados_crm_detalhado,
        (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_perfil_diario) AS qtd_perfil_diario,
        (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_perfil_horario) AS qtd_perfil_horario,
        (SELECT COUNT(*) FROM temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel) AS qtd_mediana_horaria_movel,
        (SELECT COUNT(*) FROM temp_CGUSC.fp.build_volume_horario_anomalo_alertas) AS qtd_volume_alertas,
        (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_raiox_tx) AS qtd_raiox_tx;
END;
