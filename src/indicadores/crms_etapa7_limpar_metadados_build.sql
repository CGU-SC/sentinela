-- ============================================================================
-- LIMPEZA CRM: metadados e controles build_*
-- ============================================================================
-- Deve ser executado depois do crms_etapa6_build_crm_para_app.sql.
--
-- Remove apenas tabelas de controle, log e metadata das etapas CRM.
-- Nao remove tabelas app_*.
-- Nao remove, por padrao, bases intermediarias de dados usadas no build.
-- ============================================================================

USE [temp_CGUSC];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @limpar_intermediarias BIT = 0;

PRINT '>> [LIMPEZA CRM] Validando promocao para app_*...';

IF OBJECT_ID('fp.app_crm_concentracao_unico_alertas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_concentracao_unico_alertas nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_dados_medico', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_dados_medico nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_concentracao_multiplo_alertas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_concentracao_multiplo_alertas nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_perfil_diario', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_perfil_diario nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_perfil_horario', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_perfil_horario nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_mediana_autorizacoes_horaria', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_mediana_autorizacoes_horaria nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_mediana_autorizacoes_horaria_movel', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_mediana_autorizacoes_horaria_movel nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_volume_horario_anomalo_alertas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_volume_horario_anomalo_alertas nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_raiox_tx', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_raiox_tx nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_alertas_crm_geografico', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_alertas_crm_geografico nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_alertas_crm_registro', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_alertas_crm_registro nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_alertas_crm', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_alertas_crm nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_export', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_export nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_timeline_dia', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_timeline_dia nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_timeline_hora', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_timeline_hora nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.app_crm_timeline_eventos', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.app_crm_timeline_eventos nao encontrada. Execute a etapa 6 antes da limpeza.', 16, 1);
    RETURN;
END;

PRINT '>> [LIMPEZA CRM] Tabelas de metadata/controle/log encontradas antes da limpeza:';

SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS rows_estimada
FROM sys.tables t
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
LEFT JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
WHERE s.name = 'fp'
  AND t.name IN (
      'build_crm_pipeline_pre_global_metadata',
      'build_crm_pipeline_uf_controle',
      'build_crm_concentracao_unico_uf_metadata',
      'build_crm_concentracao_unico_etapa_log',
      'build_crm_concentracao_unico_lote_controle',
      'build_crm_concentracao_unico_lote_log',
      'build_crm_concentracao_multiplo_metadata',
      'build_crm_concentracao_multiplo_etapa_log',
      'build_crm_concentracao_multiplo_controle',
      'build_crm_concentracao_multiplo_lote_log',
      'build_crm_detalhado_lote_metadata',
      'build_crm_detalhado_lote_controle',
      'build_crm_detalhado_lote_log',
      'build_crm_detalhado_lote_etapa_log',
      'build_crm_detalhado_pos_global_metadata',
      'build_crm_detalhado_pos_global_slim_metadata',
      'build_crm_detalhado_pos_global_etapa_log'
  )
GROUP BY s.name, t.name
ORDER BY t.name;

BEGIN TRY
    BEGIN TRAN;

    DROP TABLE IF EXISTS fp.build_crm_pipeline_pre_global_metadata;
    DROP TABLE IF EXISTS fp.build_crm_detalhado_pre_global_metadata; -- nome anterior
    DROP TABLE IF EXISTS fp.build_crm_pipeline_uf_controle;

    DROP TABLE IF EXISTS fp.build_crm_concentracao_unico_uf_metadata;
    DROP TABLE IF EXISTS fp.build_crm_concentracao_unico_etapa_log;
    DROP TABLE IF EXISTS fp.build_crm_concentracao_unico_lote_controle;
    DROP TABLE IF EXISTS fp.build_crm_concentracao_unico_lote_log;

    DROP TABLE IF EXISTS fp.build_crm_concentracao_multiplo_metadata;
    DROP TABLE IF EXISTS fp.build_crm_concentracao_multiplo_etapa_log;
    DROP TABLE IF EXISTS fp.build_crm_concentracao_multiplo_controle;
    DROP TABLE IF EXISTS fp.build_crm_concentracao_multiplo_lote_log;

    DROP TABLE IF EXISTS fp.build_crm_detalhado_lote_metadata;
    DROP TABLE IF EXISTS fp.build_crm_detalhado_lote_controle;
    DROP TABLE IF EXISTS fp.build_crm_detalhado_lote_log;
    DROP TABLE IF EXISTS fp.build_crm_detalhado_lote_etapa_log;

    DROP TABLE IF EXISTS fp.build_crm_detalhado_pos_global_metadata;
    DROP TABLE IF EXISTS fp.build_crm_detalhado_pos_global_slim_metadata;
    DROP TABLE IF EXISTS fp.build_crm_detalhado_pos_global_etapa_log;

    IF @limpar_intermediarias = 1
    BEGIN
        DROP TABLE IF EXISTS fp.build_dados_medico;
        DROP TABLE IF EXISTS fp.build_crm_prescricoes_todos_estabelecimentos;
        DROP TABLE IF EXISTS fp.build_crm_medico_brasil_mes;
        DROP TABLE IF EXISTS fp.build_dados_crm_detalhado;
    END;

    COMMIT TRAN;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRAN;
    THROW;
END CATCH;

PRINT '>> [LIMPEZA CRM] Tabelas build_* remanescentes:';

SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS rows_estimada
FROM sys.tables t
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
LEFT JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
WHERE s.name = 'fp'
  AND t.name LIKE 'build[_]crm%'
GROUP BY s.name, t.name
ORDER BY t.name;

PRINT '>> [LIMPEZA CRM] Concluida.';
