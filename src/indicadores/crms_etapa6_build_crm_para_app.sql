-- ============================================================================
-- PROMOCAO CRM: build_* -> app_*
-- ============================================================================
-- Renomeia as tabelas geradas pelos scripts CRM para os nomes estaveis da app.
--
-- Nao copia dados.
-- Nao cria backup app_*_old.
-- Se uma app_* ja existir, ela e removida antes do rename.
-- ============================================================================

USE [temp_CGUSC];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

PRINT '>> [PROMOCAO CRM] Validando tabelas obrigatorias...';

IF OBJECT_ID('fp.build_crm_concentracao_unico_alertas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_concentracao_unico_alertas nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_dados_medico', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_dados_medico nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_concentracao_multiplo_alertas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_concentracao_multiplo_alertas nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_perfil_diario', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_perfil_diario nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_perfil_horario', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_perfil_horario nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_mediana_autorizacoes_horaria', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_mediana_autorizacoes_horaria nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_mediana_autorizacoes_horaria_movel', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_mediana_autorizacoes_horaria_movel nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_volume_horario_anomalo_alertas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_volume_horario_anomalo_alertas nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_raiox_tx', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_raiox_tx nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_alertas_crm_geografico', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_alertas_crm_geografico nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_alertas_crm_registro', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_alertas_crm_registro nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_alertas_crm', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_alertas_crm nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_export', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_export nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_prescricoes_brasil_semestre', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_brasil_semestre nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_prescricoes_estabelecimento_mes', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_estabelecimento_mes nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_prescricoes_gerencial_mes', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_gerencial_mes nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_timeline_dia', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_timeline_dia nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_timeline_hora', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_timeline_hora nao encontrada.', 16, 1);
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_timeline_eventos', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_timeline_eventos nao encontrada.', 16, 1);
    RETURN;
END;

PRINT '>> [PROMOCAO CRM] Renomeando tabelas...';

BEGIN TRY
    BEGIN TRAN;

    IF OBJECT_ID('fp.app_dados_medico', 'U') IS NOT NULL DROP TABLE fp.app_dados_medico;
    EXEC sp_rename 'fp.build_dados_medico', 'app_dados_medico';

    IF OBJECT_ID('fp.app_crm_concentracao_unico_alertas', 'U') IS NOT NULL DROP TABLE fp.app_crm_concentracao_unico_alertas;
    EXEC sp_rename 'fp.build_crm_concentracao_unico_alertas', 'app_crm_concentracao_unico_alertas';

    IF OBJECT_ID('fp.app_crm_concentracao_multiplo_alertas', 'U') IS NOT NULL DROP TABLE fp.app_crm_concentracao_multiplo_alertas;
    EXEC sp_rename 'fp.build_crm_concentracao_multiplo_alertas', 'app_crm_concentracao_multiplo_alertas';

    IF OBJECT_ID('fp.app_crm_perfil_diario', 'U') IS NOT NULL DROP TABLE fp.app_crm_perfil_diario;
    EXEC sp_rename 'fp.build_crm_perfil_diario', 'app_crm_perfil_diario';

    IF OBJECT_ID('fp.app_crm_perfil_horario', 'U') IS NOT NULL DROP TABLE fp.app_crm_perfil_horario;
    EXEC sp_rename 'fp.build_crm_perfil_horario', 'app_crm_perfil_horario';

    IF OBJECT_ID('fp.app_mediana_autorizacoes_horaria', 'U') IS NOT NULL DROP TABLE fp.app_mediana_autorizacoes_horaria;
    EXEC sp_rename 'fp.build_mediana_autorizacoes_horaria', 'app_mediana_autorizacoes_horaria';

    IF OBJECT_ID('fp.app_mediana_autorizacoes_horaria_movel', 'U') IS NOT NULL DROP TABLE fp.app_mediana_autorizacoes_horaria_movel;
    EXEC sp_rename 'fp.build_mediana_autorizacoes_horaria_movel', 'app_mediana_autorizacoes_horaria_movel';

    IF OBJECT_ID('fp.app_volume_horario_anomalo_alertas', 'U') IS NOT NULL DROP TABLE fp.app_volume_horario_anomalo_alertas;
    EXEC sp_rename 'fp.build_volume_horario_anomalo_alertas', 'app_volume_horario_anomalo_alertas';

    IF OBJECT_ID('fp.app_crm_raiox_tx', 'U') IS NOT NULL DROP TABLE fp.app_crm_raiox_tx;
    EXEC sp_rename 'fp.build_crm_raiox_tx', 'app_crm_raiox_tx';

    IF OBJECT_ID('fp.app_alertas_crm_geografico', 'U') IS NOT NULL DROP TABLE fp.app_alertas_crm_geografico;
    EXEC sp_rename 'fp.build_alertas_crm_geografico', 'app_alertas_crm_geografico';

    IF OBJECT_ID('fp.app_alertas_crm_registro', 'U') IS NOT NULL DROP TABLE fp.app_alertas_crm_registro;
    EXEC sp_rename 'fp.build_alertas_crm_registro', 'app_alertas_crm_registro';

    IF OBJECT_ID('fp.app_alertas_crm', 'U') IS NOT NULL DROP TABLE fp.app_alertas_crm;
    EXEC sp_rename 'fp.build_alertas_crm', 'app_alertas_crm';

    IF OBJECT_ID('fp.app_crm_export', 'U') IS NOT NULL DROP TABLE fp.app_crm_export;
    EXEC sp_rename 'fp.build_crm_export', 'app_crm_export';

    IF OBJECT_ID('fp.app_crm_prescricoes_brasil_semestre', 'U') IS NOT NULL DROP TABLE fp.app_crm_prescricoes_brasil_semestre;
    EXEC sp_rename 'fp.build_crm_prescricoes_brasil_semestre', 'app_crm_prescricoes_brasil_semestre';

    IF OBJECT_ID('fp.app_crm_prescricoes_estabelecimento_mes', 'U') IS NOT NULL DROP TABLE fp.app_crm_prescricoes_estabelecimento_mes;
    EXEC sp_rename 'fp.build_crm_prescricoes_estabelecimento_mes', 'app_crm_prescricoes_estabelecimento_mes';

    IF OBJECT_ID('fp.app_crm_prescricoes_gerencial_mes', 'U') IS NOT NULL DROP TABLE fp.app_crm_prescricoes_gerencial_mes;
    EXEC sp_rename 'fp.build_crm_prescricoes_gerencial_mes', 'app_crm_prescricoes_gerencial_mes';

    IF OBJECT_ID('fp.app_crm_timeline_dia', 'U') IS NOT NULL DROP TABLE fp.app_crm_timeline_dia;
    EXEC sp_rename 'fp.build_crm_timeline_dia', 'app_crm_timeline_dia';

    IF OBJECT_ID('fp.app_crm_timeline_hora', 'U') IS NOT NULL DROP TABLE fp.app_crm_timeline_hora;
    EXEC sp_rename 'fp.build_crm_timeline_hora', 'app_crm_timeline_hora';

    IF OBJECT_ID('fp.app_crm_timeline_eventos', 'U') IS NOT NULL DROP TABLE fp.app_crm_timeline_eventos;
    EXEC sp_rename 'fp.build_crm_timeline_eventos', 'app_crm_timeline_eventos';

    IF OBJECT_ID('fp.build_indicador_crm_bench_uf', 'U') IS NOT NULL
    BEGIN
        IF OBJECT_ID('fp.app_indicador_crm_bench_uf', 'U') IS NOT NULL DROP TABLE fp.app_indicador_crm_bench_uf;
        EXEC sp_rename 'fp.build_indicador_crm_bench_uf', 'app_indicador_crm_bench_uf';
    END;

    IF OBJECT_ID('fp.build_indicador_crm_bench_regiao', 'U') IS NOT NULL
    BEGIN
        IF OBJECT_ID('fp.app_indicador_crm_bench_regiao', 'U') IS NOT NULL DROP TABLE fp.app_indicador_crm_bench_regiao;
        EXEC sp_rename 'fp.build_indicador_crm_bench_regiao', 'app_indicador_crm_bench_regiao';
    END;

    IF OBJECT_ID('fp.build_indicador_crm_bench_br', 'U') IS NOT NULL
    BEGIN
        IF OBJECT_ID('fp.app_indicador_crm_bench_br', 'U') IS NOT NULL DROP TABLE fp.app_indicador_crm_bench_br;
        EXEC sp_rename 'fp.build_indicador_crm_bench_br', 'app_indicador_crm_bench_br';
    END;

    IF OBJECT_ID('fp.build_indicador_crm_hhi', 'U') IS NOT NULL
    BEGIN
        IF OBJECT_ID('fp.app_indicador_crm_hhi', 'U') IS NOT NULL DROP TABLE fp.app_indicador_crm_hhi;
        EXEC sp_rename 'fp.build_indicador_crm_hhi', 'app_indicador_crm_hhi';
    END;

    COMMIT TRAN;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRAN;
    THROW;
END CATCH;

PRINT '>> [PROMOCAO CRM] Concluida.';
