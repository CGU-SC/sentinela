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
IF OBJECT_ID('fp.build_crm_prescricoes_medico_municipio_mes', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_medico_municipio_mes nao encontrada.', 16, 1);
    RETURN;
END;
IF COL_LENGTH('fp.build_crm_prescricoes_medico_municipio_mes', 'id_medico') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_medico_municipio_mes', 'competencia') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_medico_municipio_mes', 'id_ibge7') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_medico_municipio_mes', 'nu_prescricoes_mes') IS NULL
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_medico_municipio_mes sem o schema obrigatorio.',
        16,
        1
    );
    RETURN;
END;
IF EXISTS (
    SELECT 1
    FROM sys.columns C
    INNER JOIN sys.types T
        ON T.user_type_id = C.user_type_id
    WHERE C.object_id = OBJECT_ID('fp.build_crm_prescricoes_medico_municipio_mes', 'U')
      AND C.name = 'nu_prescricoes_mes'
      AND T.name <> 'smallint'
)
BEGIN
    RAISERROR(
        'A coluna nu_prescricoes_mes do modulo medico/municipio/mes deve ser SMALLINT.',
        16,
        1
    );
    RETURN;
END;
IF NOT EXISTS (SELECT 1 FROM fp.build_crm_prescricoes_medico_municipio_mes)
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_medico_municipio_mes esta vazia.', 16, 1);
    RETURN;
END;
IF EXISTS (
    SELECT id_medico, competencia, id_ibge7
    FROM fp.build_crm_prescricoes_medico_municipio_mes
    GROUP BY id_medico, competencia, id_ibge7
    HAVING COUNT_BIG(*) > 1
)
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_medico_municipio_mes possui chaves duplicadas.',
        16,
        1
    );
    RETURN;
END;
IF EXISTS (
    SELECT 1
    FROM fp.build_crm_prescricoes_medico_municipio_mes
    WHERE NULLIF(LTRIM(RTRIM(CAST(id_medico AS VARCHAR(100)))), '') IS NULL
       OR competencia < 190001
       OR competencia > 999912
       OR competencia % 100 NOT BETWEEN 1 AND 12
       OR id_ibge7 IS NULL
       OR id_ibge7 <= 0
       OR nu_prescricoes_mes IS NULL
       OR nu_prescricoes_mes < 0
       OR nu_prescricoes_mes > 32767
)
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_medico_municipio_mes possui valores invalidos.',
        16,
        1
    );
    RETURN;
END;
IF OBJECT_ID('fp.build_crm_prescricoes_gerencial', 'U') IS NULL
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_gerencial nao encontrada.', 16, 1);
    RETURN;
END;
IF COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'nivel') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'id_geografico') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'competencia') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'nu_prescricoes_total') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'qtd_crms_ativos') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'qtd_crms_anomalos') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'percentual_crms_anomalos') IS NULL
   OR COL_LENGTH('fp.build_crm_prescricoes_gerencial', 'media_prescricoes_dia') IS NULL
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_gerencial sem o schema mensal obrigatorio.',
        16,
        1
    );
    RETURN;
END;
IF NOT EXISTS (SELECT 1 FROM fp.build_crm_prescricoes_gerencial)
BEGIN
    RAISERROR('Tabela fp.build_crm_prescricoes_gerencial esta vazia.', 16, 1);
    RETURN;
END;
IF EXISTS (
    SELECT
        nivel,
        id_geografico,
        competencia
    FROM fp.build_crm_prescricoes_gerencial
    GROUP BY
        nivel,
        id_geografico,
        competencia
    HAVING COUNT_BIG(*) > 1
)
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_gerencial possui chaves duplicadas.',
        16,
        1
    );
    RETURN;
END;
IF EXISTS (
    SELECT 1
    FROM fp.build_crm_prescricoes_gerencial
    WHERE nivel NOT IN ('municipio', 'uf', 'regiao_saude')
       OR NULLIF(LTRIM(RTRIM(id_geografico)), '') IS NULL
       OR competencia < 190001
       OR competencia > 999912
       OR competencia % 100 NOT BETWEEN 1 AND 12
       OR nu_prescricoes_total < 0
       OR qtd_crms_ativos < 0
       OR qtd_crms_anomalos < 0
       OR qtd_crms_anomalos > qtd_crms_ativos
       OR percentual_crms_anomalos < 0
       OR percentual_crms_anomalos > 100
       OR media_prescricoes_dia < 0
       OR (
           qtd_crms_ativos = 0
           AND (
               nu_prescricoes_total <> 0
               OR qtd_crms_anomalos <> 0
               OR percentual_crms_anomalos IS NOT NULL
               OR media_prescricoes_dia IS NOT NULL
           )
       )
       OR (
           qtd_crms_ativos > 0
           AND (
               percentual_crms_anomalos IS NULL
               OR media_prescricoes_dia IS NULL
           )
       )
)
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_gerencial possui valores invalidos ou incoerentes.',
        16,
        1
    );
    RETURN;
END;
IF (SELECT COUNT(DISTINCT nivel) FROM fp.build_crm_prescricoes_gerencial) <> 3
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_gerencial nao possui os tres niveis geograficos.',
        16,
        1
    );
    RETURN;
END;

DECLARE @qtd_competencias_gerencial INT = (
    SELECT COUNT(DISTINCT competencia)
    FROM fp.build_crm_prescricoes_gerencial
);

IF EXISTS (
    SELECT
        nivel,
        id_geografico
    FROM fp.build_crm_prescricoes_gerencial
    GROUP BY
        nivel,
        id_geografico
    HAVING COUNT_BIG(*) <> @qtd_competencias_gerencial
)
BEGIN
    RAISERROR(
        'Tabela fp.build_crm_prescricoes_gerencial possui localidades com competencias ausentes.',
        16,
        1
    );
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

    IF OBJECT_ID('fp.app_crm_prescricoes_medico_municipio_mes', 'U') IS NOT NULL DROP TABLE fp.app_crm_prescricoes_medico_municipio_mes;
    EXEC sp_rename 'fp.build_crm_prescricoes_medico_municipio_mes', 'app_crm_prescricoes_medico_municipio_mes';

    IF OBJECT_ID('fp.app_crm_prescricoes_gerencial', 'U') IS NOT NULL DROP TABLE fp.app_crm_prescricoes_gerencial;
    EXEC sp_rename 'fp.build_crm_prescricoes_gerencial', 'app_crm_prescricoes_gerencial';

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
