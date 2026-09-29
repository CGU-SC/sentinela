-- ============================================================================
-- POS-PROCESSAMENTO GLOBAL PARA INDICADOR DE CRMs
-- ============================================================================
-- Script 3 do pipeline:
--   - valida que o loteado terminou com sucesso;
--   - consolida alertas globais;
--   - gera tabela final de exportacao;
--   - gera benchmarks e matriz HHI.
--
-- Pre-requisitos:
--   1. temp_CGUSC.fp.build_crm_detalhado_lote_metadata com status OK
--   2. temp_CGUSC.fp.build_crm_pipeline_uf_controle com UFs OK no loteado
--   3. temp_CGUSC.fp.build_dados_medico
--   4. temp_CGUSC.fp.build_crm_medico_brasil_mes
--   5. temp_CGUSC.fp.build_dados_crm_detalhado
--   6. temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas
--   7. temp_CGUSC.fp.build_crm_raiox_tx
--
-- Saidas persistentes:
--   - temp_CGUSC.fp.build_alertas_crm_geografico
--   - temp_CGUSC.fp.build_alertas_crm_registro
--   - temp_CGUSC.fp.build_alertas_crm
--   - temp_CGUSC.fp.build_crm_export
--   - temp_CGUSC.fp.build_crm_timeline_dia
--   - temp_CGUSC.fp.build_crm_timeline_hora
--   - temp_CGUSC.fp.build_crm_timeline_eventos
--   - temp_CGUSC.fp.build_indicador_crm_bench_uf
--   - temp_CGUSC.fp.build_indicador_crm_bench_regiao
--   - temp_CGUSC.fp.build_indicador_crm_bench_br
--   - temp_CGUSC.fp.build_indicador_crm_hhi
-- ============================================================================

-- Batch separado: valida o estado do pipeline antes de remover qualquer saida
-- pos-global ja existente. Assim, uma execucao acidental antes do loteado
-- terminar nao apaga resultados bons de uma rodada anterior.
SET NOCOUNT ON;

DECLARE @PrecheckDataInicio DATE = '2015-07-01';
DECLARE @PrecheckDataFim    DATE = '2024-12-31';
DECLARE @PrecheckVersao     VARCHAR(40) = 'v3_2026_05_12';
DECLARE @PrecheckOk         BIT;

IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao encontrada.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'cnpj') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'municipio') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'uf') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'codibge') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id_regiao_saude') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia existe, mas nao possui o schema minimo esperado: id, cnpj, municipio, uf, codibge, id_regiao_saude.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.sus.tb_ibge') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.sus.tb_ibge nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.fnCalcular_Distancia_KM') IS NULL
BEGIN
    RAISERROR('Funcao temp_CGUSC.fp.fnCalcular_Distancia_KM nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_metadata') IS NULL
BEGIN
    RAISERROR('Metadata loteada temp_CGUSC.fp.build_crm_detalhado_lote_metadata nao encontrada. Rode crms_detalhado_loteado_test.sql primeiro.', 16, 1);
    RETURN;
END;

SET @PrecheckOk = 0;
SELECT @PrecheckOk = CASE WHEN EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_detalhado_lote_metadata
    WHERE id_pipeline = 1
      AND pipeline_nome = 'crms_detalhado_loteado'
      AND pipeline_versao = @PrecheckVersao
      AND dt_data_inicio = @PrecheckDataInicio
      AND dt_data_fim = @PrecheckDataFim
      AND status = 'OK'
) THEN 1 ELSE 0 END;

IF @PrecheckOk = 0
BEGIN
    RAISERROR('Loteado incompativel ou nao finalizado com OK para esta versao/periodo.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_pipeline_uf_controle nao encontrada.', 16, 1);
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
    WHERE pipeline_versao = @PrecheckVersao
      AND dt_data_inicio = @PrecheckDataInicio
      AND dt_data_fim = @PrecheckDataFim
      AND (
             ISNULL(status_concentracao_unico, '') <> 'OK'
          OR ISNULL(status_concentracao_multiplo, '') <> 'OK'
          OR ISNULL(status_crm_detalhado_loteado, '') <> 'OK'
      )
)
BEGIN
    RAISERROR('Ainda ha UF sem concentracoes e/ou loteado OK no build_crm_pipeline_uf_controle para esta versao/periodo.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_controle') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_detalhado_lote_controle nao encontrada.', 16, 1);
    RETURN;
END;

IF EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle WHERE status <> 'OK')
BEGIN
    RAISERROR('Ainda ha CNPJ sem status OK em temp_CGUSC.fp.build_crm_detalhado_lote_controle.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_dados_medico') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_mes') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_unico_alertas') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_diario') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_horario') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_volume_horario_anomalo_alertas') IS NULL
    OR OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NULL
BEGIN
    RAISERROR('Uma ou mais tabelas de entrada do pos-global nao existem. Rode pre-global, concentracoes e loteado antes.', 16, 1);
    RETURN;
END;

PRINT '>> Garantindo indices auxiliares para o pos-global...';

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.sys.indexes
    WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx')
      AND name = 'IDX_BuildRaioX_Cnpj_DataHora'
)
    CREATE NONCLUSTERED INDEX IDX_BuildRaioX_Cnpj_DataHora
        ON temp_CGUSC.fp.build_crm_raiox_tx(id_cnpj, data_hora)
        INCLUDE (id_medico);

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.sys.indexes
    WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas')
      AND name = 'IDX_BuildMultiploAlertas_Janela'
)
    CREATE NONCLUSTERED INDEX IDX_BuildMultiploAlertas_Janela
        ON temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas(id_cnpj, dt_ini_concentracao, dt_fim_concentracao)
        INCLUDE (dt_dia);

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.sys.indexes
    WHERE object_id = OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado')
      AND name = 'IDX_BuildDadosCrmDetalhado_MedComp'
)
    CREATE NONCLUSTERED INDEX IDX_BuildDadosCrmDetalhado_MedComp
        ON temp_CGUSC.fp.build_dados_crm_detalhado(id_medico, competencia, nu_cnpj);

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log (
        id_etapa_log        BIGINT IDENTITY(1,1) NOT NULL,
        pipeline_versao     VARCHAR(40)  NOT NULL,
        dt_data_inicio      DATE         NOT NULL,
        dt_data_fim         DATE         NOT NULL,
        etapa               VARCHAR(80)  NOT NULL,
        dt_inicio_etapa     DATETIME     NOT NULL,
        dt_fim_etapa        DATETIME     NULL,
        segundos_etapa      INT          NULL,
        milissegundos_etapa INT          NULL,
        nu_registros        BIGINT       NULL,
        status              VARCHAR(20)  NOT NULL,
        observacao          VARCHAR(400) NULL,
        mensagem_erro       NVARCHAR(4000) NULL,
        CONSTRAINT PK_BuildCrmDetalhadoPosGlobalEtapaLog PRIMARY KEY CLUSTERED (id_etapa_log)
    );

    CREATE INDEX IDX_CrmDetalhadoPosGlobalEtapaLog_Periodo
        ON temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
            (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa);
END;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'dt_fim_etapa') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD dt_fim_etapa DATETIME NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'segundos_etapa') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD segundos_etapa INT NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'milissegundos_etapa') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD milissegundos_etapa INT NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'nu_registros') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD nu_registros BIGINT NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'status') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD status VARCHAR(20) NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'observacao') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD observacao VARCHAR(400) NULL;

IF COL_LENGTH('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log', 'mensagem_erro') IS NULL
    ALTER TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log ADD mensagem_erro NVARCHAR(4000) NULL;

-- Batch separado: remove saidas pos-globais antigas antes da compilacao da
-- batch principal. Isso evita Msg 207 quando uma tabela antiga existe com
-- schema diferente, mas sera recriada abaixo.
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_alertas_crm_geografico;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_alertas_crm_registro;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_alertas_crm;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_export;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_prescricoes_brasil_semestre;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_timeline_dia;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_timeline_hora;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_timeline_eventos;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_bench_uf;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_bench_regiao;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_bench_br;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_hhi;
GO

SET NOCOUNT ON;

DECLARE @DataInicio DATE = '2015-07-01';
DECLARE @DataFim    DATE = '2024-12-31';
DECLARE @t0         DATETIME = GETDATE();
DECLARE @t1         DATETIME;
DECLARE @pipeline_nome        VARCHAR(80) = 'crms_detalhado_pos_global';
DECLARE @pipeline_versao      VARCHAR(40) = 'v3_2026_05_12';
DECLARE @loteado_nome         VARCHAR(80) = 'crms_detalhado_loteado';
DECLARE @metadata_ok          BIT;
DECLARE @etapa               VARCHAR(80);
DECLARE @id_etapa_log        BIGINT;
DECLARE @dt_fim_etapa        DATETIME;
DECLARE @nu_registros_etapa  BIGINT;

PRINT '>> [POS-GLOBAL CRM] Iniciando pos-processamento global...';
PRINT '   Periodo: ' + CAST(@DataInicio AS VARCHAR(10)) + ' -> ' + CAST(@DataFim AS VARCHAR(10));

-- ============================================================================
-- PASSO 0: Validacoes de pre-requisitos e estado do pipeline
-- ============================================================================
IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia nao encontrada.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'cnpj') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'municipio') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'uf') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'codibge') IS NULL
    OR COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id_regiao_saude') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.dados_farmacia existe, mas nao possui o schema minimo esperado: id, cnpj, municipio, uf, codibge, id_regiao_saude.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.sus.tb_ibge') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.sus.tb_ibge nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.fnCalcular_Distancia_KM') IS NULL
BEGIN
    RAISERROR('Funcao temp_CGUSC.fp.fnCalcular_Distancia_KM nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_metadata') IS NULL
BEGIN
    RAISERROR('Metadata loteada temp_CGUSC.fp.build_crm_detalhado_lote_metadata nao encontrada. Rode crms_detalhado_loteado_test.sql primeiro.', 16, 1);
    RETURN;
END;

SET @metadata_ok = 0;
EXEC sp_executesql
    N'SELECT @ok = CASE WHEN EXISTS (
          SELECT 1
          FROM temp_CGUSC.fp.build_crm_detalhado_lote_metadata
          WHERE id_pipeline = 1
            AND pipeline_nome = @nome
            AND pipeline_versao = @versao
            AND dt_data_inicio = @inicio
            AND dt_data_fim = @fim
            AND status = ''OK''
      ) THEN 1 ELSE 0 END;',
    N'@nome VARCHAR(80), @versao VARCHAR(40), @inicio DATE, @fim DATE, @ok BIT OUTPUT',
    @nome = @loteado_nome,
    @versao = @pipeline_versao,
    @inicio = @DataInicio,
    @fim = @DataFim,
    @ok = @metadata_ok OUTPUT;

IF @metadata_ok = 0
BEGIN
    RAISERROR('Loteado incompativel ou nao finalizado com OK para esta versao/periodo.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_pipeline_uf_controle') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_pipeline_uf_controle nao encontrada.', 16, 1);
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.build_crm_pipeline_uf_controle
    WHERE pipeline_versao = @pipeline_versao
      AND dt_data_inicio = @DataInicio
      AND dt_data_fim = @DataFim
      AND (
             ISNULL(status_concentracao_unico, '') <> 'OK'
          OR ISNULL(status_concentracao_multiplo, '') <> 'OK'
          OR ISNULL(status_crm_detalhado_loteado, '') <> 'OK'
      )
)
BEGIN
    RAISERROR('Ainda ha UF sem concentracoes e/ou loteado OK no build_crm_pipeline_uf_controle para esta versao/periodo.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_lote_controle') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_detalhado_lote_controle nao encontrada.', 16, 1);
    RETURN;
END;

IF EXISTS (SELECT 1 FROM temp_CGUSC.fp.build_crm_detalhado_lote_controle WHERE status <> 'OK')
BEGIN
    RAISERROR('Ainda ha CNPJ sem status OK em temp_CGUSC.fp.build_crm_detalhado_lote_controle.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_dados_medico') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_dados_medico nao encontrada. Rode o pre-global primeiro.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.build_dados_medico', 'dt_primeira_inscricao_uf') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_dados_medico sem coluna obrigatoria dt_primeira_inscricao_uf. Rode crms_etapa1_pre_global.sql novamente.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_medico_brasil_mes') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_medico_brasil_mes nao encontrada. Rode o pre-global primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_dados_crm_detalhado') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_dados_crm_detalhado nao encontrada. Rode o loteado primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_unico_alertas') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_concentracao_unico_alertas nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas nao encontrada.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_diario') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_perfil_diario nao encontrada. Rode o loteado primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_perfil_horario') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_perfil_horario nao encontrada. Rode o loteado primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel nao encontrada. Rode o loteado primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_volume_horario_anomalo_alertas') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_volume_horario_anomalo_alertas nao encontrada. Rode o loteado primeiro.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('temp_CGUSC.fp.build_crm_raiox_tx') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.build_crm_raiox_tx nao encontrada. Rode o loteado primeiro.', 16, 1);
    RETURN;
END;

DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_alertas_crm_geografico;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_alertas_crm_registro;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_alertas_crm;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_export;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_timeline_dia;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_timeline_hora;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_crm_timeline_eventos;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_bench_uf;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_bench_regiao;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_bench_br;
DROP TABLE IF EXISTS temp_CGUSC.fp.build_indicador_crm_hhi;

CREATE TABLE temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata (
    id_pipeline       TINYINT      NOT NULL,
    pipeline_nome     VARCHAR(80)  NOT NULL,
    pipeline_versao   VARCHAR(40)  NOT NULL,
    dt_data_inicio    DATE         NOT NULL,
    dt_data_fim       DATE         NOT NULL,
    nu_alertas_crm    BIGINT       NULL,
    nu_crm_export     BIGINT       NULL,
    nu_timeline_dia   BIGINT       NULL,
    nu_timeline_hora  BIGINT       NULL,
    nu_timeline_eventos BIGINT     NULL,
    nu_bench_uf       BIGINT       NULL,
    nu_bench_regiao   BIGINT       NULL,
    nu_bench_br       BIGINT       NULL,
    nu_hhi            BIGINT       NULL,
    dt_criacao        DATETIME     NOT NULL,
    dt_atualizacao    DATETIME     NULL,
    status            VARCHAR(20)  NOT NULL,
    observacao        VARCHAR(400) NULL,
    CONSTRAINT PK_BuildCrmDetalhadoPosGlobalMetadata PRIMARY KEY CLUSTERED (id_pipeline),
    CONSTRAINT CK_BuildCrmDetalhadoPosGlobalMetadata_Id CHECK (id_pipeline = 1)
);

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata
    (id_pipeline, pipeline_nome, pipeline_versao, dt_data_inicio, dt_data_fim,
     dt_criacao, dt_atualizacao, status, observacao)
VALUES
    (1, @pipeline_nome, @pipeline_versao, @DataInicio, @DataFim,
     GETDATE(), GETDATE(), 'PROCESSANDO', 'Pos-global em processamento.');

DELETE FROM temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
WHERE pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim;

BEGIN TRY

-- ============================================================================
-- PASSO 1: Motor geografico
-- ============================================================================
PRINT '>> Passo 1: Criando temp_CGUSC.fp.build_alertas_crm_geografico...';
SET @etapa = '1_ALERTAS_CRM_GEOGRAFICO';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_alertas_crm_geografico.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

DROP TABLE IF EXISTS #base_com_geo;

SELECT
    D.nu_cnpj,
    D.id_medico,
    D.competencia,
    D.nu_prescricoes_medico,
    D.vl_autorizacoes_medico,
    D.dt_prescricao_inicial_medico,
    D.dt_prescricao_final_medico,
    G.latitude,
    G.longitude,
    F.municipio AS no_municipio,
    F.uf AS sg_uf
INTO #base_com_geo
FROM temp_CGUSC.fp.build_dados_crm_detalhado D
LEFT JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.cnpj = D.nu_cnpj
LEFT JOIN temp_CGUSC.sus.tb_ibge G
    ON G.id_ibge7 = F.codibge
WHERE D.nu_prescricoes_medico >= 30
  AND G.latitude IS NOT NULL
  AND G.longitude IS NOT NULL;

CREATE CLUSTERED INDEX IDX_GeoBase
    ON #base_com_geo(id_medico, competencia);

;WITH PairedWithDistance AS (
    SELECT
        T1.competencia,
        T1.id_medico,
        T1.nu_cnpj AS cnpj_a,
        T1.dt_prescricao_inicial_medico AS dt_ini_a,
        T1.dt_prescricao_final_medico AS dt_fim_a,
        T1.no_municipio AS no_municipio_a,
        T1.sg_uf AS sg_uf_a,
        T1.nu_prescricoes_medico AS nu_prescricoes_a,
        T1.vl_autorizacoes_medico AS vl_autorizacoes_a,
        T2.nu_cnpj AS cnpj_b,
        T2.dt_prescricao_inicial_medico AS dt_ini_b,
        T2.dt_prescricao_final_medico AS dt_fim_b,
        T2.no_municipio AS no_municipio_b,
        T2.sg_uf AS sg_uf_b,
        T2.nu_prescricoes_medico AS nu_prescricoes_b,
        T2.vl_autorizacoes_medico AS vl_autorizacoes_b,
        CASE
            WHEN ABS(T1.latitude - T2.latitude) > 2.0
              OR ABS(T1.longitude - T2.longitude) > 2.0
            THEN temp_CGUSC.fp.fnCalcular_Distancia_KM(T1.latitude, T1.longitude, T2.latitude, T2.longitude)
            ELSE 0
        END AS distancia_km
    FROM #base_com_geo T1
    INNER JOIN #base_com_geo T2
        ON  T2.id_medico = T1.id_medico
        AND T1.nu_cnpj < T2.nu_cnpj
        AND T1.competencia = T2.competencia
),
ParesFiltrados AS (
    SELECT *
    FROM PairedWithDistance
    WHERE distancia_km > 400
),
ParesPriorizados AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY id_medico, competencia
            ORDER BY (nu_prescricoes_a + nu_prescricoes_b) DESC, distancia_km DESC
        ) AS rn
    FROM ParesFiltrados
),
TotaisPorMedico AS (
    SELECT id_medico, competencia, COUNT(*) AS total_pares
    FROM ParesPriorizados
    GROUP BY id_medico, competencia
)
SELECT
    P.id_medico,
    P.competencia,
    P.cnpj_a,
    P.no_municipio_a,
    CAST(P.sg_uf_a AS VARCHAR(2)) AS sg_uf_a,
    P.dt_ini_a,
    P.dt_fim_a,
    P.nu_prescricoes_a,
    CAST(P.vl_autorizacoes_a AS DECIMAL(18,2)) AS vl_autorizacoes_a,
    P.cnpj_b,
    P.no_municipio_b,
    CAST(P.sg_uf_b AS VARCHAR(2)) AS sg_uf_b,
    P.dt_ini_b,
    P.dt_fim_b,
    P.nu_prescricoes_b,
    CAST(P.vl_autorizacoes_b AS DECIMAL(18,2)) AS vl_autorizacoes_b,
    CAST(P.vl_autorizacoes_a + P.vl_autorizacoes_b AS DECIMAL(18,2)) AS vl_autorizacoes_total,
    CAST(P.distancia_km AS DECIMAL(10,2)) AS distancia_km,
    T.total_pares
INTO temp_CGUSC.fp.build_alertas_crm_geografico
FROM ParesPriorizados P
INNER JOIN TotaisPorMedico T
    ON  T.id_medico = P.id_medico
    AND T.competencia = P.competencia
WHERE P.rn = 1;

CREATE CLUSTERED INDEX IDX_GeoAlerta
    ON temp_CGUSC.fp.build_alertas_crm_geografico(id_medico, competencia);

CREATE NONCLUSTERED INDEX IDX_BuildGeoAlerta_CnpjA
    ON temp_CGUSC.fp.build_alertas_crm_geografico(cnpj_a, id_medico, competencia);

CREATE NONCLUSTERED INDEX IDX_BuildGeoAlerta_CnpjB
    ON temp_CGUSC.fp.build_alertas_crm_geografico(cnpj_b, id_medico, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm_geografico;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_alertas_crm_geografico criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_alertas_crm_geografico concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 2: Motor de registro CFM
-- ============================================================================
PRINT '>> Passo 2: Criando temp_CGUSC.fp.build_alertas_crm_registro...';
SET @etapa = '2_ALERTAS_CRM_REGISTRO';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_alertas_crm_registro.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

SELECT
    A.nu_cnpj AS cnpj,
    A.id_medico,
    A.competencia,
    CONVERT(VARCHAR(20), MIN(A.dt_prescricao_inicial_medico), 103) AS dt_primeira_presc,
    CAST(NULL AS VARCHAR(20)) AS dt_registro_crm,
    CAST('INEXISTENTE' AS VARCHAR(20)) AS tipo_anomalia,
    SUM(A.nu_prescricoes_medico) AS nu_prescricoes,
    SUM(A.vl_autorizacoes_medico) AS vl_prescricoes
INTO temp_CGUSC.fp.build_alertas_crm_registro
FROM temp_CGUSC.fp.build_dados_crm_detalhado A
LEFT JOIN temp_CGUSC.fp.build_dados_medico M
    ON M.id_medico = A.id_medico
WHERE M.id_medico IS NULL
GROUP BY A.nu_cnpj, A.id_medico, A.competencia;

INSERT INTO temp_CGUSC.fp.build_alertas_crm_registro
    (cnpj, id_medico, competencia,
     dt_primeira_presc, dt_registro_crm, tipo_anomalia,
     nu_prescricoes, vl_prescricoes)
SELECT
    A.nu_cnpj AS cnpj,
    A.id_medico,
    A.competencia,
    CONVERT(VARCHAR(20), MIN(A.dt_prescricao_inicial_medico), 103) AS dt_primeira_presc,
    CONVERT(VARCHAR(20), M.dt_primeira_inscricao_uf, 103) AS dt_registro_crm,
    'IRREGULAR' AS tipo_anomalia,
    SUM(A.nu_prescricoes_medico) AS nu_prescricoes,
    SUM(A.vl_autorizacoes_medico) AS vl_prescricoes
FROM temp_CGUSC.fp.build_dados_crm_detalhado A
INNER JOIN temp_CGUSC.fp.build_dados_medico M
    ON M.id_medico = A.id_medico
WHERE M.dt_primeira_inscricao_uf > A.dt_prescricao_inicial_medico
GROUP BY A.nu_cnpj, A.id_medico, A.competencia, M.dt_primeira_inscricao_uf;

CREATE CLUSTERED INDEX IDX_Registro
    ON temp_CGUSC.fp.build_alertas_crm_registro(cnpj, id_medico, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm_registro;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_alertas_crm_registro criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_alertas_crm_registro concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 3: Consolidador de flags
-- ============================================================================
PRINT '>> Passo 3: Criando temp_CGUSC.fp.build_alertas_crm...';
SET @etapa = '3_ALERTAS_CRM';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_alertas_crm.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

DROP TABLE IF EXISTS #multiplo_temporal;
DROP TABLE IF EXISTS #multiplo_janelas;
DROP TABLE IF EXISTS #multiplo_limites;
DROP TABLE IF EXISTS #raiox_multiplo;
DROP TABLE IF EXISTS #base_alertas;
DROP TABLE IF EXISTS #conc_agg;
DROP TABLE IF EXISTS #geo_cnpj;
DROP TABLE IF EXISTS #registro;

PRINT '   3.A Materializando janelas de CRM multiplo...';
SELECT
    MU.id_cnpj,
    YEAR(MU.dt_dia) * 100 + MONTH(MU.dt_dia) AS competencia,
    MU.dt_ini_concentracao,
    MU.dt_fim_concentracao
INTO #multiplo_janelas
FROM temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas MU;

CREATE CLUSTERED INDEX IDX_MultiploJanelas_Key
    ON #multiplo_janelas(id_cnpj, dt_ini_concentracao, dt_fim_concentracao);

PRINT '   3.B Calculando limites por CNPJ...';
SELECT
    id_cnpj,
    MIN(dt_ini_concentracao) AS dt_ini_min,
    MAX(dt_fim_concentracao) AS dt_fim_max
INTO #multiplo_limites
FROM #multiplo_janelas
GROUP BY id_cnpj;

CREATE CLUSTERED INDEX IDX_MultiploLimites_Key
    ON #multiplo_limites(id_cnpj);

PRINT '   3.C Filtrando transacoes Raio-X multiplo...';
SELECT
    R.id_cnpj,
    R.id_medico,
    R.data_hora
INTO #raiox_multiplo
FROM temp_CGUSC.fp.build_crm_raiox_tx R
INNER JOIN #multiplo_limites L
    ON  L.id_cnpj = R.id_cnpj
    AND R.data_hora BETWEEN L.dt_ini_min AND L.dt_fim_max;

CREATE CLUSTERED INDEX IDX_RaioXMultiplo_Key
    ON #raiox_multiplo(id_cnpj, data_hora, id_medico);

PRINT '   3.D Cruzando janelas multiplo com transacoes...';
SELECT
    F.cnpj AS nu_cnpj,
    R.id_medico,
    J.competencia
INTO #multiplo_temporal
FROM #multiplo_janelas J
INNER JOIN #raiox_multiplo R
    ON  R.id_cnpj = J.id_cnpj
    AND R.data_hora BETWEEN J.dt_ini_concentracao AND J.dt_fim_concentracao
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.id = J.id_cnpj
GROUP BY F.cnpj, R.id_medico, J.competencia
OPTION (RECOMPILE);

CREATE CLUSTERED INDEX IDX_MultiploTemporal_Key
    ON #multiplo_temporal(nu_cnpj, id_medico, competencia);

PRINT '   3.E Consolidando concentracao unico...';
SELECT
    F.cnpj AS nu_cnpj,
    U.id_medico,
    YEAR(U.dt_dia) * 100 + MONTH(U.dt_dia) AS competencia,
    COUNT(*) AS qtd_dias
INTO #conc_agg
FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.id = U.id_cnpj
GROUP BY F.cnpj, U.id_medico, YEAR(U.dt_dia) * 100 + MONTH(U.dt_dia);

CREATE CLUSTERED INDEX IDX_ConcAgg_Key
    ON #conc_agg(nu_cnpj, id_medico, competencia);

PRINT '   3.F Consolidando geografico...';
SELECT DISTINCT T.nu_cnpj, T.id_medico, T.competencia
INTO #geo_cnpj
FROM (
    SELECT G3.cnpj_a AS nu_cnpj, G3.id_medico, G3.competencia
    FROM temp_CGUSC.fp.build_alertas_crm_geografico G3
    UNION ALL
    SELECT G4.cnpj_b AS nu_cnpj, G4.id_medico, G4.competencia
    FROM temp_CGUSC.fp.build_alertas_crm_geografico G4
) T;

CREATE CLUSTERED INDEX IDX_GeoCnpj_Key
    ON #geo_cnpj(nu_cnpj, id_medico, competencia);

PRINT '   3.G Consolidando registro...';
SELECT DISTINCT R2.cnpj AS nu_cnpj, R2.id_medico, R2.competencia
INTO #registro
FROM temp_CGUSC.fp.build_alertas_crm_registro R2;

CREATE CLUSTERED INDEX IDX_RegistroTemp_Key
    ON #registro(nu_cnpj, id_medico, competencia);

PRINT '   3.H Montando base final de alertas...';
SELECT DISTINCT
    F.cnpj AS nu_cnpj,
    U.id_medico,
    YEAR(U.dt_dia) * 100 + MONTH(U.dt_dia) AS competencia
INTO #base_alertas
FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.id = U.id_cnpj
UNION
SELECT nu_cnpj, id_medico, competencia FROM #geo_cnpj
UNION
SELECT nu_cnpj, id_medico, competencia FROM #registro
UNION
SELECT nu_cnpj, id_medico, competencia FROM #multiplo_temporal;

CREATE CLUSTERED INDEX IDX_BaseAlertas_Key
    ON #base_alertas(nu_cnpj, id_medico, competencia);

PRINT '   3.I Criando build_alertas_crm...';
SELECT
    B.nu_cnpj,
    B.id_medico,
    B.competencia,
    CAST(CASE WHEN CA.id_medico IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_concentracao,
    CAST(CASE WHEN GC.id_medico IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_geografico,
    CAST(CASE WHEN RE.id_medico IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_registro,
    CAST(CASE WHEN SR.id_medico IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS alerta_concentracao_multiplos_crms,
    ISNULL(CA.qtd_dias, 0) AS qtd_dias_concentracao
INTO temp_CGUSC.fp.build_alertas_crm
FROM #base_alertas B
LEFT JOIN #conc_agg CA
    ON  CA.nu_cnpj = B.nu_cnpj
    AND CA.id_medico = B.id_medico
    AND CA.competencia = B.competencia
LEFT JOIN #multiplo_temporal SR
    ON  SR.nu_cnpj = B.nu_cnpj
    AND SR.id_medico = B.id_medico
    AND SR.competencia = B.competencia
LEFT JOIN #geo_cnpj GC
    ON  GC.nu_cnpj = B.nu_cnpj
    AND GC.id_medico = B.id_medico
    AND GC.competencia = B.competencia
LEFT JOIN #registro RE
    ON  RE.nu_cnpj = B.nu_cnpj
    AND RE.id_medico = B.id_medico
    AND RE.competencia = B.competencia
OPTION (RECOMPILE);

CREATE CLUSTERED INDEX IDX_Alertas_Key
    ON temp_CGUSC.fp.build_alertas_crm(nu_cnpj, id_medico, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_alertas_crm criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_alertas_crm concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 4: Tabela final de exportacao
-- ============================================================================
PRINT '>> Passo 4: Criando temp_CGUSC.fp.build_crm_export...';
SET @etapa = '4_CRM_EXPORT';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_crm_export.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

SELECT
    A.id_medico,
    FAR.id AS id_cnpj,
    A.competencia,
    A.nu_prescricoes_medico AS nu_prescricoes_mes,
    A.vl_autorizacoes_medico AS vl_total_prescricoes,
    A.nu_prescricoes_pico_h,
    A.taxa_pico_h,
    P.nu_prescricoes_mes AS nu_prescricoes_total_brasil,
    P.nu_estabelecimentos_mes AS nu_estabelecimentos,
    CAST(CASE WHEN CONC.nu_cnpj IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_concentracao_mesmo_crm,
    CAST(CASE WHEN G.id_medico IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_distancia_geografica,
    A.dt_prescricao_inicial_medico AS dt_primeira_prescricao,
    M.dt_primeira_inscricao_uf AS dt_inscricao_crm,
    CAST(CASE WHEN REG_INV.cnpj IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_crm_invalido,
    CAST(CASE WHEN REG_IRR.cnpj IS NOT NULL THEN 1 ELSE 0 END AS BIT) AS flag_prescricao_antes_registro,
    ISNULL(AL.alerta_concentracao_multiplos_crms, CAST(0 AS BIT)) AS alerta_concentracao_multiplos_crms
INTO temp_CGUSC.fp.build_crm_export
FROM temp_CGUSC.fp.build_dados_crm_detalhado A
LEFT JOIN temp_CGUSC.fp.build_dados_medico M
    ON M.id_medico = A.id_medico
LEFT JOIN temp_CGUSC.fp.dados_farmacia FAR
    ON FAR.cnpj = A.nu_cnpj
LEFT JOIN temp_CGUSC.fp.build_alertas_crm AL
    ON  AL.nu_cnpj = A.nu_cnpj
    AND AL.id_medico = A.id_medico
    AND AL.competencia = A.competencia
LEFT JOIN temp_CGUSC.fp.build_crm_medico_brasil_mes P
    ON  P.id_medico = A.id_medico
    AND P.competencia = A.competencia
LEFT JOIN (
    SELECT DISTINCT
        F.cnpj AS nu_cnpj,
        C.id_medico,
        YEAR(C.dt_dia) * 100 + MONTH(C.dt_dia) AS competencia
    FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas C
    INNER JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.id = C.id_cnpj
) CONC
    ON  CONC.nu_cnpj = A.nu_cnpj
    AND CONC.id_medico = A.id_medico
    AND CONC.competencia = A.competencia
LEFT JOIN temp_CGUSC.fp.build_alertas_crm_geografico G
    ON  G.id_medico = A.id_medico
    AND G.competencia = A.competencia
    AND (G.cnpj_a = A.nu_cnpj OR G.cnpj_b = A.nu_cnpj)
LEFT JOIN temp_CGUSC.fp.build_alertas_crm_registro REG_INV
    ON  REG_INV.cnpj = A.nu_cnpj
    AND REG_INV.id_medico = A.id_medico
    AND REG_INV.competencia = A.competencia
    AND REG_INV.tipo_anomalia = 'INEXISTENTE'
LEFT JOIN temp_CGUSC.fp.build_alertas_crm_registro REG_IRR
    ON  REG_IRR.cnpj = A.nu_cnpj
    AND REG_IRR.id_medico = A.id_medico
    AND REG_IRR.competencia = A.competencia
    AND REG_IRR.tipo_anomalia = 'IRREGULAR';

CREATE CLUSTERED INDEX IDX_CrmExport_Key
    ON temp_CGUSC.fp.build_crm_export(id_cnpj, id_medico, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_crm_export;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_crm_export criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_crm_export concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 4.A.1: Resumo nacional semestral de prescricoes por CRM
-- ============================================================================
PRINT '>> Passo 4.A.1: Criando temp_CGUSC.fp.build_crm_prescricoes_brasil_semestre...';
SET @etapa = '4A1_CRM_BRASIL_SEMESTRE';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1,
     'PROCESSANDO', 'Criando build_crm_prescricoes_brasil_semestre.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

SELECT
    P.id_medico,
    CAST((P.competencia / 100) * 10 + CASE WHEN P.competencia % 100 BETWEEN 1 AND 6 THEN 1 ELSE 2 END AS INT) AS chave_semestre,
    CAST(SUM(CAST(P.nu_prescricoes_mes AS BIGINT)) AS INT) AS nu_prescricoes_total_brasil,
    CAST(SUM(DAY(EOMONTH(DATEFROMPARTS(P.competencia / 100, P.competencia % 100, 1)))) AS SMALLINT) AS dias_ativos_brasil
INTO temp_CGUSC.fp.build_crm_prescricoes_brasil_semestre
FROM temp_CGUSC.fp.build_crm_medico_brasil_mes P
GROUP BY
    P.id_medico,
    P.competencia / 100,
    CASE WHEN P.competencia % 100 BETWEEN 1 AND 6 THEN 1 ELSE 2 END;

CREATE UNIQUE CLUSTERED INDEX IDX_CrmBrasilSemestre_Key
    ON temp_CGUSC.fp.build_crm_prescricoes_brasil_semestre(id_medico, chave_semestre);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_crm_prescricoes_brasil_semestre;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_crm_prescricoes_brasil_semestre criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_crm_prescricoes_brasil_semestre concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 4.B: Contrato enxuto da timeline CRM para o app
-- ============================================================================
PRINT '>> Passo 4.B: Criando temp_CGUSC.fp.build_crm_timeline_*...';
SET @etapa = '4B_CRM_TIMELINE_APP';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1,
     'PROCESSANDO', 'Criando build_crm_timeline_dia, build_crm_timeline_hora e build_crm_timeline_eventos.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

DROP TABLE IF EXISTS #timeline_unico_scores;
SELECT
    U.id_cnpj,
    CAST(U.dt_dia AS DATE) AS dt_janela,
    CAST(U.id_medico AS VARCHAR(13)) AS id_medico,
    CAST(U.taxa_hora_pior_ritmo AS DECIMAL(7,2)) AS score_crm_unico_hora,
    CAST(U.nu_autorizacoes_pior_ritmo AS SMALLINT) AS score_crm_unico_qtd,
    CAST(U.janela_pior_ritmo_minutos AS SMALLINT) AS score_crm_unico_minutos,
    ROW_NUMBER() OVER (
        PARTITION BY U.id_cnpj, U.dt_dia
        ORDER BY
            U.id_severidade DESC,
            U.taxa_hora_pior_ritmo DESC,
            U.nu_autorizacoes_pior_ritmo DESC,
            U.id_medico
    ) AS rn
INTO #timeline_unico_scores
FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U;

CREATE CLUSTERED INDEX IDX_TimelineUnicoScores
    ON #timeline_unico_scores(id_cnpj, dt_janela, rn);

DROP TABLE IF EXISTS #timeline_multiplo_scores;
SELECT
    MU.id_cnpj,
    CAST(MU.dt_dia AS DATE) AS dt_janela,
    CAST(MU.taxa_hora_pior_ritmo AS DECIMAL(7,2)) AS score_crm_multiplo_hora,
    CAST(MU.nu_autorizacoes_pior_ritmo AS SMALLINT) AS score_crm_multiplo_qtd,
    CAST(MU.janela_pior_ritmo_minutos AS SMALLINT) AS score_crm_multiplo_minutos,
    CAST(MU.nu_crms_distintos AS SMALLINT) AS score_crm_multiplo_crms,
    ROW_NUMBER() OVER (
        PARTITION BY MU.id_cnpj, MU.dt_dia
        ORDER BY
            MU.id_severidade DESC,
            MU.taxa_hora_pior_ritmo DESC,
            MU.nu_autorizacoes_pior_ritmo DESC,
            MU.nu_crms_distintos DESC
    ) AS rn
INTO #timeline_multiplo_scores
FROM temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas MU;

CREATE CLUSTERED INDEX IDX_TimelineMultiploScores
    ON #timeline_multiplo_scores(id_cnpj, dt_janela, rn);

SELECT
    CAST(D.id_cnpj AS INT) AS id_cnpj,
    CAST(D.dt_janela AS DATE) AS dt_janela,
    CAST(D.competencia AS INT) AS competencia,
    CAST(D.nu_prescricoes_dia AS SMALLINT) AS nu_prescricoes_dia,
    CAST(D.nu_crms_distintos AS SMALLINT) AS nu_crms_distintos,
    CAST(D.mediana_diaria AS DECIMAL(7,2)) AS mediana_diaria,
    CAST(D.is_dia_com_volume_horario_anomalo AS BIT) AS is_dia_com_volume_horario_anomalo,
    CAST(D.is_anomalo_unico AS BIT) AS is_anomalo_unico,
    CAST(D.is_crm_multiplo AS BIT) AS is_crm_multiplo,
    U.score_crm_unico_hora,
    U.score_crm_unico_qtd,
    U.score_crm_unico_minutos,
    U.id_medico AS score_crm_unico_medico,
    MU.score_crm_multiplo_hora,
    MU.score_crm_multiplo_qtd,
    MU.score_crm_multiplo_minutos,
    MU.score_crm_multiplo_crms
INTO temp_CGUSC.fp.build_crm_timeline_dia
FROM temp_CGUSC.fp.build_crm_perfil_diario D
LEFT JOIN #timeline_unico_scores U
    ON  U.id_cnpj = D.id_cnpj
    AND U.dt_janela = D.dt_janela
    AND U.rn = 1
LEFT JOIN #timeline_multiplo_scores MU
    ON  MU.id_cnpj = D.id_cnpj
    AND MU.dt_janela = D.dt_janela
    AND MU.rn = 1;

CREATE CLUSTERED INDEX IDX_CrmTimelineDia
    ON temp_CGUSC.fp.build_crm_timeline_dia(id_cnpj, dt_janela);

SELECT
    CAST(H.id_cnpj AS INT) AS id_cnpj,
    CAST(H.dt_janela AS DATE) AS dt_janela,
    CAST(H.hr_janela AS TINYINT) AS hr_janela,
    CAST(H.nu_prescricoes AS SMALLINT) AS nu_prescricoes,
    CAST(H.nu_crms_diferentes AS SMALLINT) AS nu_crms_diferentes,
    CAST(H.mediana_hora AS DECIMAL(6,2)) AS mediana_hora,
    CAST(M.mad_hora_movel AS DECIMAL(10,4)) AS mad_hora,
    CAST(H.is_hora_com_alerta AS BIT) AS is_hora_com_alerta,
    CAST(H.is_volume_horario_anomalo AS BIT) AS is_volume_horario_anomalo,
    CAST(H.is_crm_unico AS BIT) AS is_crm_unico,
    CAST(H.is_crm_multiplo AS BIT) AS is_crm_multiplo
INTO temp_CGUSC.fp.build_crm_timeline_hora
FROM temp_CGUSC.fp.build_crm_perfil_horario H
LEFT JOIN temp_CGUSC.fp.build_mediana_autorizacoes_horaria_movel M
    ON  M.id_cnpj = H.id_cnpj
    AND M.dt_janela = H.dt_janela
    AND M.hr_janela = H.hr_janela;

CREATE CLUSTERED INDEX IDX_CrmTimelineHora
    ON temp_CGUSC.fp.build_crm_timeline_hora(id_cnpj, dt_janela, hr_janela);

SELECT
    CAST(E.id_cnpj AS INT) AS id_cnpj,
    CAST(E.dt_janela AS DATE) AS dt_janela,
    CAST(E.tipo AS VARCHAR(8)) AS tipo,
    CAST(E.hora_inicio AS CHAR(5)) AS hora_inicio,
    CAST(E.hora_fim AS CHAR(5)) AS hora_fim,
    CAST(E.minuto_inicio AS SMALLINT) AS minuto_inicio,
    CAST(E.minuto_fim AS SMALLINT) AS minuto_fim,
    CAST(E.severidade AS VARCHAR(7)) AS severidade,
    CAST(E.id_medico AS VARCHAR(13)) AS id_medico,
    CAST(E.nu_crms_distintos AS SMALLINT) AS nu_crms_distintos
INTO temp_CGUSC.fp.build_crm_timeline_eventos
FROM (
    SELECT
        U.id_cnpj,
        U.dt_dia AS dt_janela,
        CAST('UNICO' AS VARCHAR(8)) AS tipo,
        CONVERT(CHAR(5), U.dt_ini_concentracao, 108) AS hora_inicio,
        CONVERT(CHAR(5), U.dt_fim_concentracao, 108) AS hora_fim,
        DATEDIFF(MINUTE, CAST(U.dt_dia AS DATETIME), U.dt_ini_concentracao) AS minuto_inicio,
        DATEDIFF(MINUTE, CAST(U.dt_dia AS DATETIME), U.dt_fim_concentracao) AS minuto_fim,
        CASE U.id_severidade
            WHEN 4 THEN 'EXTREMO'
            WHEN 3 THEN 'CRITICO'
            WHEN 2 THEN 'GRAVE'
            WHEN 1 THEN 'ALTO'
            ELSE 'ALERTA'
        END AS severidade,
        U.id_medico,
        CAST(NULL AS SMALLINT) AS nu_crms_distintos
    FROM temp_CGUSC.fp.build_crm_concentracao_unico_alertas U

    UNION ALL

    SELECT
        MU.id_cnpj,
        MU.dt_dia AS dt_janela,
        CAST('MULTIPLO' AS VARCHAR(8)) AS tipo,
        CONVERT(CHAR(5), MU.dt_ini_concentracao, 108) AS hora_inicio,
        CONVERT(CHAR(5), MU.dt_fim_concentracao, 108) AS hora_fim,
        DATEDIFF(MINUTE, CAST(MU.dt_dia AS DATETIME), MU.dt_ini_concentracao) AS minuto_inicio,
        DATEDIFF(MINUTE, CAST(MU.dt_dia AS DATETIME), MU.dt_fim_concentracao) AS minuto_fim,
        CASE MU.id_severidade
            WHEN 4 THEN 'EXTREMO'
            WHEN 3 THEN 'CRITICO'
            WHEN 2 THEN 'GRAVE'
            WHEN 1 THEN 'ALTO'
            ELSE 'ALERTA'
        END AS severidade,
        CAST(NULL AS VARCHAR(13)) AS id_medico,
        MU.nu_crms_distintos
    FROM temp_CGUSC.fp.build_crm_concentracao_multiplo_alertas MU

    UNION ALL

    SELECT
        V.id_cnpj,
        V.dt_alerta AS dt_janela,
        CAST('VOLUME' AS VARCHAR(8)) AS tipo,
        RIGHT('0' + CAST(V.hr_janela AS VARCHAR(2)), 2) + ':00' AS hora_inicio,
        CASE
            WHEN V.hr_janela = 23 THEN '24:00'
            ELSE RIGHT('0' + CAST(V.hr_janela + 1 AS VARCHAR(2)), 2) + ':00'
        END AS hora_fim,
        V.hr_janela * 60 AS minuto_inicio,
        (V.hr_janela + 1) * 60 AS minuto_fim,
        'CRITICO' AS severidade,
        CAST(NULL AS VARCHAR(13)) AS id_medico,
        V.nu_crms AS nu_crms_distintos
    FROM temp_CGUSC.fp.build_volume_horario_anomalo_alertas V
) E;

CREATE CLUSTERED INDEX IDX_CrmTimelineEventos
    ON temp_CGUSC.fp.build_crm_timeline_eventos(id_cnpj, dt_janela, minuto_inicio);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa =
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_dia)
  + (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_hora)
  + (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_eventos);

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_crm_timeline_* criadas.'
WHERE id_etapa_log = @id_etapa_log;

SET @id_etapa_log = NULL;

PRINT '   build_crm_timeline_* concluidas em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 5: Base temporaria para benchmarks
-- ============================================================================
PRINT '>> Passo 5: Criando #indicador_crm...';
SET @etapa = '5_INDICADOR_CRM_BASE';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando base temporaria #indicador_crm.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

DROP TABLE IF EXISTS #indicador_crm;

;WITH
Totais AS (
    SELECT
        nu_cnpj AS cnpj,
        competencia,
        SUM(nu_prescricoes_medico) AS total_prescricoes,
        SUM(vl_autorizacoes_medico) AS total_valor,
        COUNT(DISTINCT id_medico) AS total_prescritores
    FROM temp_CGUSC.fp.build_dados_crm_detalhado
    GROUP BY nu_cnpj, competencia
),
Top5 AS (
    SELECT
        cnpj,
        competencia,
        MAX(CASE WHEN rk = 1 THEN id_medico END) AS id_top1,
        SUM(CASE WHEN rk = 1 THEN vl_total_prescricoes ELSE 0 END) AS vl_top1,
        SUM(CASE WHEN rk <= 5 THEN vl_total_prescricoes ELSE 0 END) AS vl_top5
    FROM (
        SELECT
            nu_cnpj AS cnpj,
            competencia,
            id_medico,
            vl_autorizacoes_medico AS vl_total_prescricoes,
            ROW_NUMBER() OVER (
                PARTITION BY nu_cnpj, competencia
                ORDER BY vl_autorizacoes_medico DESC
            ) AS rk
        FROM temp_CGUSC.fp.build_dados_crm_detalhado
    ) R
    WHERE rk <= 5
    GROUP BY cnpj, competencia
),
Anomalias AS (
    SELECT
        A.nu_cnpj AS cnpj,
        A.competencia,
        COUNT(CASE WHEN REG_INV.cnpj IS NOT NULL THEN 1 END) AS qtd_crm_invalido,
        COUNT(CASE WHEN REG_IRR.cnpj IS NOT NULL THEN 1 END) AS qtd_antes_registro
    FROM temp_CGUSC.fp.build_dados_crm_detalhado A
    LEFT JOIN temp_CGUSC.fp.build_alertas_crm_registro REG_INV
        ON  REG_INV.cnpj = A.nu_cnpj
        AND REG_INV.id_medico = A.id_medico
        AND REG_INV.competencia = A.competencia
        AND REG_INV.tipo_anomalia = 'INEXISTENTE'
    LEFT JOIN temp_CGUSC.fp.build_alertas_crm_registro REG_IRR
        ON  REG_IRR.cnpj = A.nu_cnpj
        AND REG_IRR.id_medico = A.id_medico
        AND REG_IRR.competencia = A.competencia
        AND REG_IRR.tipo_anomalia = 'IRREGULAR'
    GROUP BY A.nu_cnpj, A.competencia
),
HHI AS (
    SELECT
        E.nu_cnpj AS cnpj,
        E.competencia,
        SUM(POWER(
            CAST(E.vl_autorizacoes_medico AS DECIMAL(18,4)) /
            NULLIF(CAST(T.total_valor AS DECIMAL(18,4)), 0) * 100.0
        , 2)) AS indice_hhi
    FROM temp_CGUSC.fp.build_dados_crm_detalhado E
    INNER JOIN Totais T
        ON T.cnpj = E.nu_cnpj
       AND T.competencia = E.competencia
    GROUP BY E.nu_cnpj, E.competencia
),
Turistas AS (
    SELECT
        nu_cnpj AS cnpj,
        competencia,
        COUNT(DISTINCT id_medico) AS qtd_turistas
    FROM temp_CGUSC.fp.build_alertas_crm
    WHERE flag_geografico = 1
    GROUP BY nu_cnpj, competencia
)
SELECT
    I.cnpj,
    I.competencia,
    I.total_prescricoes AS qtd_prescricoes_mes,
    I.total_valor AS vl_total_prescricoes,
    I.total_prescritores AS qtd_prescritores,
    T.id_top1,
    ISNULL(T.vl_top1, 0) AS vl_top1,
    ISNULL(T.vl_top5, 0) AS vl_top5,
    ISNULL(H.indice_hhi, 0) AS indice_hhi,
    ISNULL(AN.qtd_crm_invalido, 0) AS qtd_crm_invalido,
    ISNULL(AN.qtd_antes_registro, 0) AS qtd_crm_antes_registro,
    ISNULL(TU.qtd_turistas, 0) AS qtd_prescritores_turistas
INTO #indicador_crm
FROM Totais I
LEFT JOIN Top5 T
    ON T.cnpj = I.cnpj
   AND T.competencia = I.competencia
LEFT JOIN HHI H
    ON H.cnpj = I.cnpj
   AND H.competencia = I.competencia
LEFT JOIN Anomalias AN
    ON AN.cnpj = I.cnpj
   AND AN.competencia = I.competencia
LEFT JOIN Turistas TU
    ON TU.cnpj = I.cnpj
   AND TU.competencia = I.competencia;

CREATE CLUSTERED INDEX IDX_IndCrm
    ON #indicador_crm(cnpj, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM #indicador_crm;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = '#indicador_crm criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   #indicador_crm concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 6: Benchmarks UF, regiao de saude e Brasil
-- ============================================================================
PRINT '>> Passo 6.A: Criando temp_CGUSC.fp.build_indicador_crm_bench_uf...';
SET @etapa = '6.A_BENCH_UF';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_indicador_crm_bench_uf.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

;WITH CTE AS (
    SELECT
        I.competencia,
        F.uf,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.indice_hhi, 0))
            OVER (PARTITION BY F.uf, I.competencia) AS mediana_hhi_uf,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.vl_top1 / NULLIF(I.vl_total_prescricoes, 0) * 100, 0))
            OVER (PARTITION BY F.uf, I.competencia) AS mediana_concentracao_top1_uf,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.vl_top5 / NULLIF(I.vl_total_prescricoes, 0) * 100, 0))
            OVER (PARTITION BY F.uf, I.competencia) AS mediana_concentracao_top5_uf,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(CAST(
            CASE
                WHEN I.qtd_prescritores > 0
                THEN I.qtd_crm_invalido * 100.0 / I.qtd_prescritores
                ELSE 0
            END AS DECIMAL(18,4)), 0))
            OVER (PARTITION BY F.uf, I.competencia) AS mediana_pct_crm_invalido_uf,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.qtd_prescritores_turistas, 0))
            OVER (PARTITION BY F.uf, I.competencia) AS mediana_turistas_uf
    FROM #indicador_crm I
    INNER JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.cnpj = I.cnpj
)
SELECT *
INTO temp_CGUSC.fp.build_indicador_crm_bench_uf
FROM CTE;

CREATE CLUSTERED INDEX IDX_BenchUF
    ON temp_CGUSC.fp.build_indicador_crm_bench_uf(uf, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_uf;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_indicador_crm_bench_uf criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_indicador_crm_bench_uf concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);

PRINT '>> Passo 6.B: Criando temp_CGUSC.fp.build_indicador_crm_bench_regiao...';
SET @etapa = '6.B_BENCH_REGIAO';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_indicador_crm_bench_regiao.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

;WITH CTE AS (
    SELECT DISTINCT
        F.id_regiao_saude,
        I.competencia,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.indice_hhi, 0))
            OVER (PARTITION BY F.id_regiao_saude, I.competencia) AS mediana_hhi_reg,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.vl_top1 / NULLIF(I.vl_total_prescricoes, 0) * 100, 0))
            OVER (PARTITION BY F.id_regiao_saude, I.competencia) AS mediana_concentracao_reg,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.vl_top5 / NULLIF(I.vl_total_prescricoes, 0) * 100, 0))
            OVER (PARTITION BY F.id_regiao_saude, I.competencia) AS mediana_concentracao_top5_reg,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(CAST(
            CASE
                WHEN I.qtd_prescritores > 0
                THEN I.qtd_crm_invalido * 100.0 / I.qtd_prescritores
                ELSE 0
            END AS DECIMAL(18,4)), 0))
            OVER (PARTITION BY F.id_regiao_saude, I.competencia) AS mediana_crm_invalido_reg,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.qtd_prescritores_turistas, 0))
            OVER (PARTITION BY F.id_regiao_saude, I.competencia) AS mediana_turistas_reg
    FROM temp_CGUSC.fp.dados_farmacia F
    LEFT JOIN #indicador_crm I
        ON I.cnpj = F.cnpj
    WHERE F.id_regiao_saude IS NOT NULL
      AND I.competencia IS NOT NULL
)
SELECT *
INTO temp_CGUSC.fp.build_indicador_crm_bench_regiao
FROM CTE;

CREATE CLUSTERED INDEX IDX_BenchReg
    ON temp_CGUSC.fp.build_indicador_crm_bench_regiao(id_regiao_saude, competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_regiao;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_indicador_crm_bench_regiao criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_indicador_crm_bench_regiao concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);

PRINT '>> Passo 6.C: Criando temp_CGUSC.fp.build_indicador_crm_bench_br...';
SET @etapa = '6.C_BENCH_BR';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_indicador_crm_bench_br.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

;WITH CTE AS (
    SELECT DISTINCT
        I.competencia,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.vl_top1 / NULLIF(I.vl_total_prescricoes, 0) * 100, 0))
            OVER (PARTITION BY I.competencia) AS mediana_concentracao_br,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.vl_top5 / NULLIF(I.vl_total_prescricoes, 0) * 100, 0))
            OVER (PARTITION BY I.competencia) AS mediana_concentracao_top5_br,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.indice_hhi, 0))
            OVER (PARTITION BY I.competencia) AS mediana_hhi_br,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(CAST(
            CASE
                WHEN I.qtd_prescritores > 0
                THEN I.qtd_crm_invalido * 100.0 / I.qtd_prescritores
                ELSE 0
            END AS DECIMAL(18,4)), 0))
            OVER (PARTITION BY I.competencia) AS mediana_pct_crm_invalido_br,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ISNULL(I.qtd_prescritores_turistas, 0))
            OVER (PARTITION BY I.competencia) AS mediana_turistas_br
    FROM #indicador_crm I
)
SELECT *
INTO temp_CGUSC.fp.build_indicador_crm_bench_br
FROM CTE;

CREATE CLUSTERED INDEX IDX_BenchBR
    ON temp_CGUSC.fp.build_indicador_crm_bench_br(competencia);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_br;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_indicador_crm_bench_br criada.'
WHERE id_etapa_log = @id_etapa_log;

PRINT '   build_indicador_crm_bench_br concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- PASSO 7: Matriz HHI
-- ============================================================================
PRINT '>> Passo 7: Criando temp_CGUSC.fp.build_indicador_crm_hhi...';
SET @etapa = '7_INDICADOR_CRM_HHI';
SET @t1 = GETDATE();
SET @id_etapa_log = NULL;

INSERT INTO temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
    (pipeline_versao, dt_data_inicio, dt_data_fim, etapa, dt_inicio_etapa, status, observacao)
VALUES
    (@pipeline_versao, @DataInicio, @DataFim, @etapa, @t1, 'PROCESSANDO', 'Criando build_indicador_crm_hhi.');

SET @id_etapa_log = CONVERT(BIGINT, SCOPE_IDENTITY());

;WITH HHI_por_cnpj AS (
    SELECT
        I.cnpj,
        AVG(I.indice_hhi) AS indice_hhi,
        F.id_regiao_saude,
        CAST(F.uf AS VARCHAR(2)) AS uf
    FROM #indicador_crm I
    INNER JOIN temp_CGUSC.fp.dados_farmacia F
        ON F.cnpj = I.cnpj
    GROUP BY I.cnpj, F.id_regiao_saude, F.uf
),
Bench AS (
    SELECT
        uf,
        AVG(mediana_hhi_uf) AS mediana_hhi_uf
    FROM temp_CGUSC.fp.build_indicador_crm_bench_uf
    GROUP BY uf
),
BenchReg AS (
    SELECT
        id_regiao_saude,
        AVG(mediana_hhi_reg) AS mediana_hhi_reg
    FROM temp_CGUSC.fp.build_indicador_crm_bench_regiao
    GROUP BY id_regiao_saude
),
BenchBR AS (
    SELECT AVG(mediana_hhi_br) AS mediana_hhi_br
    FROM temp_CGUSC.fp.build_indicador_crm_bench_br
)
SELECT
    H.cnpj,
    CAST(H.indice_hhi AS DECIMAL(18,4)) AS indice_hhi,
    ISNULL(CAST(BU.mediana_hhi_uf AS DECIMAL(18,4)), 0) AS estado_mediana,
    ISNULL(CAST(BR.mediana_hhi_br AS DECIMAL(18,4)), 0) AS pais_mediana,
    ISNULL(CAST(BR2.mediana_hhi_reg AS DECIMAL(18,4)), 0) AS regiao_saude_mediana,
    CAST(CASE
        WHEN BU.mediana_hhi_uf > 0
        THEN (H.indice_hhi + 0.01) / (BU.mediana_hhi_uf + 0.01)
        ELSE 0
    END AS DECIMAL(18,4)) AS risco_relativo_uf_mediana,
    CAST(CASE
        WHEN BR.mediana_hhi_br > 0
        THEN (H.indice_hhi + 0.01) / (BR.mediana_hhi_br + 0.01)
        ELSE 0
    END AS DECIMAL(18,4)) AS risco_relativo_br_mediana,
    CAST(CASE
        WHEN BR2.mediana_hhi_reg > 0
        THEN (H.indice_hhi + 0.01) / (BR2.mediana_hhi_reg + 0.01)
        ELSE 0
    END AS DECIMAL(18,4)) AS risco_relativo_reg_mediana
INTO temp_CGUSC.fp.build_indicador_crm_hhi
FROM HHI_por_cnpj H
LEFT JOIN Bench BU
    ON BU.uf = H.uf
LEFT JOIN BenchReg BR2
    ON BR2.id_regiao_saude = H.id_regiao_saude
CROSS JOIN BenchBR BR;

CREATE CLUSTERED INDEX IDX_CrmHHI
    ON temp_CGUSC.fp.build_indicador_crm_hhi(cnpj);

SET @dt_fim_etapa = GETDATE();
SELECT @nu_registros_etapa = COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_hhi;

UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
SET dt_fim_etapa = @dt_fim_etapa,
    segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
    milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
    nu_registros = @nu_registros_etapa,
    status = 'OK',
    observacao = 'build_indicador_crm_hhi criada.'
WHERE id_etapa_log = @id_etapa_log;

SET @id_etapa_log = NULL;

PRINT '   build_indicador_crm_hhi concluida em: ' + CONVERT(VARCHAR(20), @dt_fim_etapa - @t1, 114);


-- ============================================================================
-- FINALIZACAO E RESULTADOS
-- ============================================================================
UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata
SET nu_alertas_crm = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm),
    nu_crm_export = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_export),
    nu_timeline_dia = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_dia),
    nu_timeline_hora = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_hora),
    nu_timeline_eventos = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_eventos),
    nu_bench_uf = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_uf),
    nu_bench_regiao = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_regiao),
    nu_bench_br = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_br),
    nu_hhi = (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_hhi),
    status = 'OK',
    dt_atualizacao = GETDATE(),
    observacao = 'Pos-global finalizado com sucesso.'
WHERE id_pipeline = 1;

PRINT '==========================================================';
PRINT '   TEMPO TOTAL: ' + CONVERT(VARCHAR(20), GETDATE() - @t0, 114);
PRINT '==========================================================';

SELECT
    id_pipeline,
    pipeline_nome,
    pipeline_versao,
    dt_data_inicio,
    dt_data_fim,
    nu_alertas_crm,
    nu_crm_export,
    nu_timeline_dia,
    nu_timeline_hora,
    nu_timeline_eventos,
    nu_bench_uf,
    nu_bench_regiao,
    nu_bench_br,
    nu_hhi,
    status,
    dt_criacao,
    dt_atualizacao,
    observacao
FROM temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata;

SELECT TOP 30
    etapa,
    dt_inicio_etapa,
    dt_fim_etapa,
    segundos_etapa,
    milissegundos_etapa,
    nu_registros,
    status,
    observacao,
    mensagem_erro
FROM temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
WHERE pipeline_versao = @pipeline_versao
  AND dt_data_inicio = @DataInicio
  AND dt_data_fim = @DataFim
ORDER BY id_etapa_log DESC;

SELECT
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm_geografico) AS qtd_alertas_crm_geografico,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm_registro) AS qtd_alertas_crm_registro,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_alertas_crm) AS qtd_alertas_crm,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_export) AS qtd_crm_export,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_dia) AS qtd_crm_timeline_dia,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_hora) AS qtd_crm_timeline_hora,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_crm_timeline_eventos) AS qtd_crm_timeline_eventos,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_uf) AS qtd_bench_uf,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_regiao) AS qtd_bench_regiao,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_bench_br) AS qtd_bench_br,
    (SELECT COUNT(*) FROM temp_CGUSC.fp.build_indicador_crm_hhi) AS qtd_hhi;

SELECT TOP 30
    id_medico,
    id_cnpj,
    competencia,
    nu_prescricoes_mes,
    vl_total_prescricoes,
    flag_concentracao_mesmo_crm,
    flag_distancia_geografica,
    flag_crm_invalido,
    flag_prescricao_antes_registro,
    alerta_concentracao_multiplos_crms
FROM temp_CGUSC.fp.build_crm_export
ORDER BY nu_prescricoes_mes DESC;

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

    IF OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata') IS NOT NULL
    BEGIN
        UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_metadata
        SET status = 'ERRO',
            dt_atualizacao = GETDATE(),
            observacao = LEFT(@mensagem_erro, 400)
        WHERE id_pipeline = 1;
    END;

    IF @id_etapa_log IS NOT NULL
       AND OBJECT_ID('temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log') IS NOT NULL
    BEGIN
        SET @dt_fim_etapa = GETDATE();

        UPDATE temp_CGUSC.fp.build_crm_detalhado_pos_global_etapa_log
        SET dt_fim_etapa = @dt_fim_etapa,
            segundos_etapa = DATEDIFF(SECOND, @t1, @dt_fim_etapa),
            milissegundos_etapa = DATEDIFF(MILLISECOND, @t1, @dt_fim_etapa),
            status = 'ERRO',
            observacao = LEFT(@mensagem_erro, 400),
            mensagem_erro = @mensagem_erro
        WHERE id_etapa_log = @id_etapa_log;
    END;

    PRINT '   ERRO no pos-global CRM.';
    PRINT '   ' + @mensagem_erro;

    THROW;
END CATCH;
