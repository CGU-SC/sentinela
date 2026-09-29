-- ============================================================================
-- PROMOCAO CRM: build_* -> app_*
-- ============================================================================
-- Renomeia as tabelas geradas pelos scripts CRM para os nomes estaveis da app.
-- Nao copia dados e nao cria backup app_*_old.
--
-- REGRA: uma app_* so e substituida se existir a build_* correspondente (ja
-- validada). Sem build_*, a app_* fica intacta. Assim da para rodar o script
-- inteiro depois de refazer so parte das etapas: promove apenas o que foi
-- gerado agora.
--
-- GRUPO "CRM MEDICO" (saidas da etapa 1 / 1b, dependentes entre si): as 11
-- tabelas sao promovidas juntas, ou nenhuma. Se so parte tiver build_*, o
-- script para (evita misturar execucoes diferentes). O grupo so e promovido
-- se a metadata da etapa 1 estiver com status OK (etapa 1 concluida ou
-- crms_etapa1b_finalizar.sql executado).
--
-- Demais tabelas (etapas 2 a 5 e indicadores): cada uma e promovida sozinha,
-- se tiver build_*.
--
-- Tudo numa transacao: se qualquer troca falhar, nenhuma app_* e alterada.
-- Tabelas descontinuadas nao sao apagadas: aparecem no resumo final.
-- ============================================================================

USE [temp_CGUSC];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @tabelas TABLE (
    ordem INT IDENTITY(1, 1) NOT NULL,
    nome SYSNAME NOT NULL,
    grupo VARCHAR(20) NOT NULL
);
INSERT INTO @tabelas (nome, grupo) VALUES
    ('dados_medico', 'crm_medico'),
    ('crm_medico_estabelecimento_mes', 'crm_medico'),
    ('crm_medico_brasil_mes', 'crm_medico'),
    ('crm_medico_territorio_mes', 'crm_medico'),
    ('crm_medico_brasil_ano', 'crm_medico'),
    ('crm_medico_territorio_ano', 'crm_medico'),
    ('crm_medico_dim', 'crm_medico'),
    ('crm_farmacia_medico_ano', 'crm_medico'),
    ('crm_mapa_municipio_regiao_periodo', 'crm_medico'),
    ('crm_mapa_uf_periodo', 'crm_medico'),
    ('crm_limiar_p95_mes', 'crm_medico'),
    ('crm_concentracao_unico_alertas', 'independente'),
    ('crm_concentracao_multiplo_alertas', 'independente'),
    ('crm_perfil_diario', 'independente'),
    ('crm_perfil_horario', 'independente'),
    ('mediana_autorizacoes_horaria', 'independente'),
    ('mediana_autorizacoes_horaria_movel', 'independente'),
    ('volume_horario_anomalo_alertas', 'independente'),
    ('crm_raiox_tx', 'independente'),
    ('alertas_crm_geografico', 'independente'),
    ('alertas_crm_registro', 'independente'),
    ('alertas_crm', 'independente'),
    ('crm_export', 'independente'),
    ('crm_prescricoes_brasil_semestre', 'independente'),
    ('crm_timeline_dia', 'independente'),
    ('crm_timeline_hora', 'independente'),
    ('crm_timeline_eventos', 'independente'),
    ('indicador_crm_bench_uf', 'independente'),
    ('indicador_crm_bench_regiao', 'independente'),
    ('indicador_crm_bench_br', 'independente'),
    ('indicador_crm_hhi', 'independente');

DECLARE @descontinuadas TABLE (nome SYSNAME NOT NULL);
INSERT INTO @descontinuadas (nome) VALUES
    ('crm_prescricoes_medico_municipio_mes'),
    ('crm_contagem_medicos_uf_brasil_periodo'),
    ('crm_contagem_medicos_municipio_regiao_periodo');

DECLARE @resumo TABLE (
    ordem INT NOT NULL,
    tabela SYSNAME NOT NULL,
    situacao VARCHAR(60) NOT NULL
);

DECLARE @qtd_grupo INT = (SELECT COUNT(*) FROM @tabelas WHERE grupo = 'crm_medico');
DECLARE @qtd_grupo_com_build INT = (
    SELECT COUNT(*)
    FROM @tabelas
    WHERE grupo = 'crm_medico'
      AND OBJECT_ID('fp.build_' + nome, 'U') IS NOT NULL
);
DECLARE @faltando NVARCHAR(2000);

-- ============================================================================
-- Grupo CRM medico: tudo ou nada, e so com a etapa 1 concluida
-- ============================================================================
IF @qtd_grupo_com_build BETWEEN 1 AND @qtd_grupo - 1
BEGIN
    SELECT @faltando = STRING_AGG(CAST('build_' + nome AS NVARCHAR(200)), ', ')
    FROM @tabelas
    WHERE grupo = 'crm_medico'
      AND OBJECT_ID('fp.build_' + nome, 'U') IS NULL;
    SET @faltando = LEFT(N'Grupo CRM medico incompleto (as 11 tabelas da etapa 1 sao promovidas juntas). Faltam: ' + @faltando, 2000);
    THROW 51055, @faltando, 1;
END;

IF @qtd_grupo_com_build = @qtd_grupo
BEGIN
    -- Dois IFs: com a tabela ausente, o SELECT nem pode ser compilado.
    IF OBJECT_ID('fp.build_crm_pipeline_pre_global_metadata', 'U') IS NULL
        THROW 51056, 'Grupo CRM medico: metadata da etapa 1 (build_crm_pipeline_pre_global_metadata) ausente. Conclua a etapa 1 (ou rode crms_etapa1b_finalizar.sql) antes de promover.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM fp.build_crm_pipeline_pre_global_metadata
        WHERE id_pipeline = 1 AND status = 'OK'
    )
        THROW 51056, 'Grupo CRM medico: metadata da etapa 1 sem status OK. Conclua a etapa 1 (ou rode crms_etapa1b_finalizar.sql) antes de promover.', 1;

    PRINT '>> [PROMOCAO CRM] Grupo CRM medico: validando as 11 tabelas build_*...';

    IF COL_LENGTH('fp.build_crm_medico_estabelecimento_mes', 'id_cnpj') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_estabelecimento_mes', 'id_medico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_estabelecimento_mes', 'competencia') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_estabelecimento_mes', 'nu_prescricoes_mes') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_estabelecimento_mes', 'qtd_dias_com_prescricao_mes') IS NULL
        THROW 51021, 'Tabela CRM estabelecimento/medico/mes sem os cinco campos obrigatorios.', 1;

    IF EXISTS (
        SELECT 1
        FROM sys.columns C
        INNER JOIN sys.types T ON T.user_type_id = C.user_type_id
        WHERE C.object_id = OBJECT_ID('fp.build_crm_medico_estabelecimento_mes', 'U')
          AND (
              (C.name IN ('id_cnpj', 'competencia') AND T.name <> 'int')
              OR (C.name = 'id_medico' AND T.name <> 'varchar')
              OR (C.name = 'nu_prescricoes_mes' AND T.name <> 'smallint')
              OR (C.name = 'qtd_dias_com_prescricao_mes' AND T.name <> 'tinyint')
          )
    )
        THROW 51022, 'Tipos invalidos na tabela CRM estabelecimento/medico/mes.', 1;

    IF NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_estabelecimento_mes)
        THROW 51023, 'Tabela CRM estabelecimento/medico/mes vazia.', 1;

    IF EXISTS (
        SELECT 1
        FROM fp.build_crm_medico_estabelecimento_mes P
        CROSS APPLY (VALUES (
            TRY_CONVERT(DATE, CONVERT(VARCHAR(6), P.competencia) + '01', 112)
        )) Mes(competencia_data)
        WHERE P.id_cnpj IS NULL
           OR NULLIF(LTRIM(RTRIM(P.id_medico)), '') IS NULL
           OR Mes.competencia_data IS NULL
           OR P.nu_prescricoes_mes IS NULL
           OR P.nu_prescricoes_mes < 1
           OR P.qtd_dias_com_prescricao_mes IS NULL
           OR P.qtd_dias_com_prescricao_mes < 1
           OR P.qtd_dias_com_prescricao_mes > DAY(EOMONTH(Mes.competencia_data))
           OR P.qtd_dias_com_prescricao_mes > P.nu_prescricoes_mes
    )
        THROW 51024, 'Valores invalidos na tabela CRM estabelecimento/medico/mes.', 1;
    IF COL_LENGTH('fp.build_crm_medico_brasil_mes', 'id_medico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_mes', 'competencia') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_mes', 'nu_prescricoes_mes') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_mes', 'qtd_dias_com_prescricao_mes') IS NULL
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_medico_brasil_mes sem o schema obrigatorio.',
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
        WHERE C.object_id = OBJECT_ID('fp.build_crm_medico_brasil_mes', 'U')
          AND C.name = 'nu_prescricoes_mes'
          AND T.name <> 'smallint'
    )
    BEGIN
        RAISERROR(
            'A coluna nu_prescricoes_mes do modulo medico/Brasil/mes deve ser SMALLINT.',
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
        WHERE C.object_id = OBJECT_ID('fp.build_crm_medico_brasil_mes', 'U')
          AND C.name = 'qtd_dias_com_prescricao_mes'
          AND T.name <> 'tinyint'
    )
    BEGIN
        RAISERROR(
            'A coluna qtd_dias_com_prescricao_mes do modulo medico/Brasil/mes deve ser TINYINT.',
            16,
            1
        );
        RETURN;
    END;
    IF NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_brasil_mes)
    BEGIN
        RAISERROR('Tabela fp.build_crm_medico_brasil_mes esta vazia.', 16, 1);
        RETURN;
    END;
    IF EXISTS (
        SELECT id_medico, competencia
        FROM fp.build_crm_medico_brasil_mes
        GROUP BY id_medico, competencia
        HAVING COUNT_BIG(*) > 1
    )
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_medico_brasil_mes possui chaves duplicadas.',
            16,
            1
        );
        RETURN;
    END;
    IF EXISTS (
        SELECT 1
        FROM fp.build_crm_medico_brasil_mes
        WHERE NULLIF(LTRIM(RTRIM(CAST(id_medico AS VARCHAR(100)))), '') IS NULL
           OR competencia < 190001
           OR competencia > 999912
           OR competencia % 100 NOT BETWEEN 1 AND 12
           OR nu_prescricoes_mes IS NULL
           OR nu_prescricoes_mes < 1
           OR nu_prescricoes_mes > 32767
           OR qtd_dias_com_prescricao_mes IS NULL
           OR qtd_dias_com_prescricao_mes < 1
           OR qtd_dias_com_prescricao_mes > DAY(EOMONTH(TRY_CONVERT(DATE, CONVERT(VARCHAR(6), competencia) + '01', 112)))
           OR qtd_dias_com_prescricao_mes > nu_prescricoes_mes
           OR TRY_CONVERT(DATE, CONVERT(VARCHAR(6), competencia) + '01', 112) IS NULL
    )
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_medico_brasil_mes possui valores invalidos.',
            16,
            1
        );
        RETURN;
    END;
    IF COL_LENGTH('fp.build_crm_medico_territorio_mes', 'nivel') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_mes', 'id_geografico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_mes', 'id_medico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_mes', 'competencia') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_mes', 'nu_prescricoes_mes') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_mes', 'qtd_dias_com_prescricao_mes') IS NULL
        THROW 51039, 'Tabela CRM medico/territorio/mes sem os seis campos obrigatorios.', 1;
    IF EXISTS (
        SELECT 1
        FROM sys.columns C
        INNER JOIN sys.types T ON T.user_type_id = C.user_type_id
        WHERE C.object_id = OBJECT_ID('fp.build_crm_medico_territorio_mes', 'U')
          AND (
              (C.name = 'nu_prescricoes_mes' AND T.name <> 'smallint')
              OR (C.name = 'qtd_dias_com_prescricao_mes' AND T.name <> 'tinyint')
          )
    )
        THROW 51040, 'Tipos invalidos na tabela CRM medico/territorio/mes.', 1;
    IF NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_territorio_mes)
        THROW 51041, 'Tabela CRM medico/territorio/mes vazia.', 1;
    IF EXISTS (
        SELECT nivel, id_geografico, id_medico, competencia
        FROM fp.build_crm_medico_territorio_mes
        GROUP BY nivel, id_geografico, id_medico, competencia
        HAVING COUNT_BIG(*) > 1
    )
        THROW 51042, 'Tabela CRM medico/territorio/mes possui chaves duplicadas.', 1;
    IF EXISTS (
        SELECT 1
        FROM fp.build_crm_medico_territorio_mes P
        CROSS APPLY (VALUES (
            TRY_CONVERT(DATE, CONVERT(VARCHAR(6), P.competencia) + '01', 112)
        )) Mes(competencia_data)
        WHERE P.nivel NOT IN ('municipio', 'regiao_saude', 'uf')
           OR NULLIF(LTRIM(RTRIM(P.id_geografico)), '') IS NULL
           OR NULLIF(LTRIM(RTRIM(P.id_medico)), '') IS NULL
           OR Mes.competencia_data IS NULL
           OR P.nu_prescricoes_mes IS NULL
           OR P.nu_prescricoes_mes < 1
           OR P.qtd_dias_com_prescricao_mes IS NULL
           OR P.qtd_dias_com_prescricao_mes < 1
           OR P.qtd_dias_com_prescricao_mes > DAY(EOMONTH(Mes.competencia_data))
           OR P.qtd_dias_com_prescricao_mes > P.nu_prescricoes_mes
    )
        THROW 51043, 'Valores invalidos na tabela CRM medico/territorio/mes.', 1;
    IF (SELECT COUNT(DISTINCT nivel) FROM fp.build_crm_medico_territorio_mes) <> 3
        THROW 51044, 'Tabela CRM medico/territorio/mes sem os tres niveis (municipio, regiao de saude, UF).', 1;
    IF COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'nivel') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'id_geografico') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'competencia_inicio') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'competencia_fim') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'qtd_medicos_ativos') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'qtd_medicos_alta_intensidade') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'qtd_medicos_anomalos') IS NOT NULL
       OR COL_LENGTH('fp.build_crm_mapa_municipio_regiao_periodo', 'qtd_medicos_elegiveis') IS NOT NULL
    BEGIN
        RAISERROR(
            'Tabela de contagens por municipio/regiao sem o schema obrigatorio (ativos e alta intensidade; sem anomalos e elegiveis).',
            16,
            1
        );
        RETURN;
    END;
    IF NOT EXISTS (SELECT 1 FROM fp.build_crm_mapa_municipio_regiao_periodo)
    BEGIN
        RAISERROR('Tabela de contagens por municipio/regiao esta vazia.', 16, 1);
        RETURN;
    END;
    IF EXISTS (
        SELECT
            nivel,
            id_geografico,
            competencia_inicio,
            competencia_fim
        FROM fp.build_crm_mapa_municipio_regiao_periodo
        GROUP BY
            nivel,
            id_geografico,
            competencia_inicio,
            competencia_fim
        HAVING COUNT_BIG(*) > 1
    )
    BEGIN
        RAISERROR(
            'Tabela de contagens por municipio/regiao possui chaves duplicadas.',
            16,
            1
        );
        RETURN;
    END;
    IF EXISTS (
        SELECT 1
        FROM fp.build_crm_mapa_municipio_regiao_periodo
        WHERE nivel NOT IN ('municipio', 'regiao_saude')
           OR NULLIF(LTRIM(RTRIM(id_geografico)), '') IS NULL
           OR competencia_inicio < 190001
           OR competencia_inicio > 999912
           OR competencia_inicio % 100 NOT BETWEEN 1 AND 12
           OR competencia_fim < 190001
           OR competencia_fim > 999912
           OR competencia_fim % 100 NOT BETWEEN 1 AND 12
           OR competencia_inicio > competencia_fim
           OR qtd_medicos_ativos < 0
           OR qtd_medicos_alta_intensidade < 0
           OR qtd_medicos_alta_intensidade > qtd_medicos_ativos
    )
    BEGIN
        RAISERROR(
            'Tabela de contagens por municipio/regiao possui valores invalidos.',
            16,
            1
        );
        RETURN;
    END;
    IF (SELECT COUNT(DISTINCT nivel) FROM fp.build_crm_mapa_municipio_regiao_periodo) <> 2
    BEGIN
        RAISERROR(
            'Tabela de contagens por municipio/regiao nao possui os dois niveis.',
            16,
            1
        );
        RETURN;
    END;

    DECLARE @primeiro_mes_municipio_regiao INT = (
        SELECT MIN(competencia_inicio)
        FROM fp.build_crm_mapa_municipio_regiao_periodo
    );
    DECLARE @ultimo_mes_municipio_regiao INT = (
        SELECT MAX(competencia_fim)
        FROM fp.build_crm_mapa_municipio_regiao_periodo
    );
    DECLARE @qtd_meses_municipio_regiao BIGINT = DATEDIFF(
        MONTH,
        DATEFROMPARTS(@primeiro_mes_municipio_regiao / 100, @primeiro_mes_municipio_regiao % 100, 1),
        DATEFROMPARTS(@ultimo_mes_municipio_regiao / 100, @ultimo_mes_municipio_regiao % 100, 1)
    ) + 1;
    DECLARE @qtd_periodos_municipio_regiao BIGINT =
        @qtd_meses_municipio_regiao * (@qtd_meses_municipio_regiao + 1) / 2;

    IF EXISTS (
        SELECT nivel, id_geografico
        FROM fp.build_crm_mapa_municipio_regiao_periodo
        GROUP BY nivel, id_geografico
        HAVING COUNT_BIG(*) <> @qtd_periodos_municipio_regiao
    )
        THROW 51034, 'Contagens por municipio/regiao sem todos os periodos por territorio.', 1;

    IF COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'nivel') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'id_geografico') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'competencia_inicio') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'competencia_fim') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'qtd_medicos_ativos') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'qtd_medicos_alta_intensidade') IS NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'qtd_medicos_anomalos') IS NOT NULL
       OR COL_LENGTH('fp.build_crm_mapa_uf_periodo', 'qtd_medicos_elegiveis') IS NOT NULL
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_mapa_uf_periodo sem o schema obrigatorio.',
            16,
            1
        );
        RETURN;
    END;
    IF NOT EXISTS (SELECT 1 FROM fp.build_crm_mapa_uf_periodo)
    BEGIN
        RAISERROR('Tabela fp.build_crm_mapa_uf_periodo esta vazia.', 16, 1);
        RETURN;
    END;
    IF EXISTS (
        SELECT
            nivel,
            id_geografico,
            competencia_inicio,
            competencia_fim
        FROM fp.build_crm_mapa_uf_periodo
        GROUP BY
            nivel,
            id_geografico,
            competencia_inicio,
            competencia_fim
        HAVING COUNT_BIG(*) > 1
    )
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_mapa_uf_periodo possui chaves duplicadas.',
            16,
            1
        );
        RETURN;
    END;
    IF EXISTS (
        SELECT 1
        FROM fp.build_crm_mapa_uf_periodo
        WHERE nivel NOT IN ('uf', 'brasil')
           OR (nivel = 'brasil' AND id_geografico <> 'BR')
           OR (nivel = 'uf' AND (id_geografico = 'BR' OR LEN(LTRIM(RTRIM(id_geografico))) <> 2))
           OR competencia_inicio < 190001
           OR competencia_inicio > 999912
           OR competencia_inicio % 100 NOT BETWEEN 1 AND 12
           OR competencia_fim < 190001
           OR competencia_fim > 999912
           OR competencia_fim % 100 NOT BETWEEN 1 AND 12
           OR competencia_inicio > competencia_fim
           OR qtd_medicos_ativos < 0
           OR qtd_medicos_alta_intensidade < 0
           OR qtd_medicos_alta_intensidade > qtd_medicos_ativos
    )
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_mapa_uf_periodo possui valores invalidos.',
            16,
            1
        );
        RETURN;
    END;

    IF (SELECT COUNT(DISTINCT id_geografico) FROM fp.build_crm_mapa_uf_periodo WHERE nivel = 'uf') <> 27
       OR (SELECT COUNT(DISTINCT id_geografico) FROM fp.build_crm_mapa_uf_periodo WHERE nivel = 'brasil') <> 1
    BEGIN
        RAISERROR('Mapa Brasil exige 27 UFs e um escopo BR.', 16, 1);
        RETURN;
    END;

    DECLARE @competencia_min_uf_periodo INT = (
        SELECT MIN(competencia_inicio)
        FROM fp.build_crm_mapa_uf_periodo
    );
    DECLARE @competencia_max_uf_periodo INT = (
        SELECT MAX(competencia_fim)
        FROM fp.build_crm_mapa_uf_periodo
    );
    IF @primeiro_mes_municipio_regiao <> @competencia_min_uf_periodo
       OR @ultimo_mes_municipio_regiao <> @competencia_max_uf_periodo
        THROW 51035, 'Periodos de municipio/regiao divergem dos periodos UF/Brasil.', 1;
    DECLARE @qtd_meses_uf_periodo BIGINT = DATEDIFF(
        MONTH,
        DATEFROMPARTS(@competencia_min_uf_periodo / 100, @competencia_min_uf_periodo % 100, 1),
        DATEFROMPARTS(@competencia_max_uf_periodo / 100, @competencia_max_uf_periodo % 100, 1)
    ) + 1;
    DECLARE @qtd_periodos_uf_esperada BIGINT =
        @qtd_meses_uf_periodo * (@qtd_meses_uf_periodo + 1) / 2;

    IF EXISTS (
        SELECT nivel, id_geografico
        FROM fp.build_crm_mapa_uf_periodo
        GROUP BY nivel, id_geografico
        HAVING COUNT_BIG(*) <> @qtd_periodos_uf_esperada
    )
    BEGIN
        RAISERROR(
            'Tabela fp.build_crm_mapa_uf_periodo nao possui todos os intervalos para cada territorio.',
            16,
            1
        );
        RETURN;
    END;

    IF COL_LENGTH('fp.build_crm_limiar_p95_mes', 'competencia') IS NULL
       OR COL_LENGTH('fp.build_crm_limiar_p95_mes', 'qtd_medicos_ativos') IS NULL
       OR COL_LENGTH('fp.build_crm_limiar_p95_mes', 'p95_taxa_dia') IS NULL
        THROW 51036, 'Tabela de limiar de alta intensidade sem o schema obrigatorio.', 1;
    IF EXISTS (
        SELECT 1
        FROM fp.build_crm_limiar_p95_mes
        WHERE qtd_medicos_ativos < 1
           OR p95_taxa_dia IS NULL
           OR p95_taxa_dia < 1
    )
        THROW 51037, 'Tabela de limiar de alta intensidade possui valores invalidos.', 1;
    -- Um limiar por mes da grade do mapa, sem lacunas.
    IF (SELECT COUNT_BIG(*) FROM fp.build_crm_limiar_p95_mes) <> @qtd_meses_uf_periodo
       OR (SELECT MIN(competencia) FROM fp.build_crm_limiar_p95_mes) <> @competencia_min_uf_periodo
       OR (SELECT MAX(competencia) FROM fp.build_crm_limiar_p95_mes) <> @competencia_max_uf_periodo
        THROW 51038, 'Tabela de limiar de alta intensidade nao cobre todos os meses do mapa.', 1;

    -- ---------------------------------------------------------------------------
    -- Tabelas anuais do ranking (medico x ano): schema, valores e totais iguais aos
    -- das tabelas mensais correspondentes.
    -- ---------------------------------------------------------------------------
    IF COL_LENGTH('fp.build_crm_medico_brasil_ano', 'id_medico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_ano', 'ano') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_ano', 'nu_prescricoes') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_ano', 'qtd_dias_com_prescricao') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_ano', 'qtd_meses_ativos') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_brasil_ano', 'qtd_meses_alta_intensidade') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'nivel') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'id_geografico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'id_medico') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'ano') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'nu_prescricoes') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'qtd_dias_com_prescricao') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'qtd_meses_ativos') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_territorio_ano', 'qtd_meses_alta_intensidade') IS NULL
        THROW 51045, 'Tabelas CRM medico/ano sem os campos obrigatorios.', 1;
    IF EXISTS (
        SELECT 1
        FROM sys.columns C
        INNER JOIN sys.types T ON T.user_type_id = C.user_type_id
        WHERE C.object_id IN (
                  OBJECT_ID('fp.build_crm_medico_brasil_ano', 'U'),
                  OBJECT_ID('fp.build_crm_medico_territorio_ano', 'U')
              )
          AND (
              (C.name = 'ano' AND T.name <> 'smallint')
              OR (C.name = 'nu_prescricoes' AND T.name <> 'int')
              OR (C.name = 'qtd_dias_com_prescricao' AND T.name <> 'smallint')
              OR (C.name = 'qtd_meses_ativos' AND T.name <> 'tinyint')
              OR (C.name = 'qtd_meses_alta_intensidade' AND T.name <> 'tinyint')
          )
    )
        THROW 51046, 'Tipos invalidos nas tabelas CRM medico/ano.', 1;
    IF NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_brasil_ano)
       OR NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_territorio_ano)
        THROW 51047, 'Tabela CRM medico/ano vazia.', 1;
    IF EXISTS (
        SELECT id_medico, ano
        FROM fp.build_crm_medico_brasil_ano
        GROUP BY id_medico, ano
        HAVING COUNT_BIG(*) > 1
    )
       OR EXISTS (
        SELECT nivel, id_geografico, id_medico, ano
        FROM fp.build_crm_medico_territorio_ano
        GROUP BY nivel, id_geografico, id_medico, ano
        HAVING COUNT_BIG(*) > 1
    )
        THROW 51048, 'Tabela CRM medico/ano possui chaves duplicadas.', 1;
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT CAST('brasil' AS VARCHAR(16)) AS nivel, CAST('BR' AS VARCHAR(20)) AS id_geografico,
                   id_medico, ano, nu_prescricoes, qtd_dias_com_prescricao,
                   qtd_meses_ativos, qtd_meses_alta_intensidade
            FROM fp.build_crm_medico_brasil_ano
            UNION ALL
            SELECT nivel, id_geografico, id_medico, ano, nu_prescricoes, qtd_dias_com_prescricao,
                   qtd_meses_ativos, qtd_meses_alta_intensidade
            FROM fp.build_crm_medico_territorio_ano
        ) A
        WHERE A.nivel NOT IN ('brasil', 'municipio', 'regiao_saude', 'uf')
           OR NULLIF(LTRIM(RTRIM(A.id_geografico)), '') IS NULL
           OR NULLIF(LTRIM(RTRIM(A.id_medico)), '') IS NULL
           OR A.ano NOT BETWEEN 1900 AND 9999
           OR A.qtd_meses_ativos NOT BETWEEN 1 AND 12
           OR A.qtd_meses_alta_intensidade > A.qtd_meses_ativos
           OR A.qtd_dias_com_prescricao NOT BETWEEN A.qtd_meses_ativos AND 366
           OR A.nu_prescricoes < A.qtd_dias_com_prescricao
    )
        THROW 51049, 'Valores invalidos nas tabelas CRM medico/ano.', 1;

    -- Mesmos anos e mesmos totais das mensais em cada nivel: prescricoes, dias com
    -- prescricao e meses ativos (= linhas mensais). Evita anual de outra execucao.
    DROP TABLE IF EXISTS #crm_totais_mes;
    DROP TABLE IF EXISTS #crm_totais_ano;

    SELECT
        CAST('brasil' AS VARCHAR(16)) AS nivel,
        competencia / 100 AS ano,
        SUM(CAST(nu_prescricoes_mes AS BIGINT)) AS nu_prescricoes,
        SUM(CAST(qtd_dias_com_prescricao_mes AS BIGINT)) AS qtd_dias,
        COUNT_BIG(*) AS qtd_meses
    INTO #crm_totais_mes
    FROM fp.build_crm_medico_brasil_mes
    GROUP BY competencia / 100;

    INSERT INTO #crm_totais_mes (nivel, ano, nu_prescricoes, qtd_dias, qtd_meses)
    SELECT nivel, competencia / 100,
           SUM(CAST(nu_prescricoes_mes AS BIGINT)),
           SUM(CAST(qtd_dias_com_prescricao_mes AS BIGINT)),
           COUNT_BIG(*)
    FROM fp.build_crm_medico_territorio_mes
    GROUP BY nivel, competencia / 100;

    SELECT
        CAST('brasil' AS VARCHAR(16)) AS nivel,
        CAST(ano AS INT) AS ano,
        SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes,
        SUM(CAST(qtd_dias_com_prescricao AS BIGINT)) AS qtd_dias,
        SUM(CAST(qtd_meses_ativos AS BIGINT)) AS qtd_meses
    INTO #crm_totais_ano
    FROM fp.build_crm_medico_brasil_ano
    GROUP BY ano;

    INSERT INTO #crm_totais_ano (nivel, ano, nu_prescricoes, qtd_dias, qtd_meses)
    SELECT nivel, ano,
           SUM(CAST(nu_prescricoes AS BIGINT)),
           SUM(CAST(qtd_dias_com_prescricao AS BIGINT)),
           SUM(CAST(qtd_meses_ativos AS BIGINT))
    FROM fp.build_crm_medico_territorio_ano
    GROUP BY nivel, ano;

    IF EXISTS (
        SELECT 1
        FROM #crm_totais_mes M
        FULL JOIN #crm_totais_ano A
            ON A.nivel = M.nivel
           AND A.ano = M.ano
        WHERE M.ano IS NULL
           OR A.ano IS NULL
           OR M.nu_prescricoes <> A.nu_prescricoes
           OR M.qtd_dias <> A.qtd_dias
           OR M.qtd_meses <> A.qtd_meses
    )
        THROW 51050, 'Tabelas CRM medico/ano divergem das mensais em anos ou totais.', 1;

    DROP TABLE #crm_totais_mes;
    DROP TABLE #crm_totais_ano;

    -- ---------------------------------------------------------------------------
    -- Dimensao de medicos e farmacia x medico x ano (indice de bitmaps dos filtros
    -- de farmacia): codigos 0..N-1 sem lacunas, todo medico com codigo, chaves
    -- unicas e mesmo total anual de prescricoes do Brasil.
    -- ---------------------------------------------------------------------------
    IF COL_LENGTH('fp.build_crm_medico_dim', 'id_medico_num') IS NULL
       OR COL_LENGTH('fp.build_crm_medico_dim', 'id_medico') IS NULL
       OR COL_LENGTH('fp.build_crm_farmacia_medico_ano', 'ano') IS NULL
       OR COL_LENGTH('fp.build_crm_farmacia_medico_ano', 'id_medico_num') IS NULL
       OR COL_LENGTH('fp.build_crm_farmacia_medico_ano', 'id_cnpj') IS NULL
       OR COL_LENGTH('fp.build_crm_farmacia_medico_ano', 'nu_prescricoes') IS NULL
        THROW 51051, 'Dimensao de medicos ou farmacia x medico x ano sem os campos obrigatorios.', 1;
    IF (SELECT COUNT_BIG(*) FROM fp.build_crm_medico_dim)
           <> (SELECT ISNULL(MAX(CAST(id_medico_num AS BIGINT)), -1) + 1 FROM fp.build_crm_medico_dim)
       OR (SELECT MIN(id_medico_num) FROM fp.build_crm_medico_dim) <> 0
       OR EXISTS (
            SELECT id_medico FROM fp.build_crm_medico_dim GROUP BY id_medico HAVING COUNT_BIG(*) > 1
       )
        THROW 51052, 'Dimensao de medicos com codigos repetidos ou lacunas.', 1;
    IF EXISTS (
        SELECT 1
        FROM (SELECT DISTINCT id_medico FROM fp.build_crm_medico_brasil_ano) B
        WHERE NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_dim D WHERE D.id_medico = B.id_medico)
    )
       OR EXISTS (
        SELECT 1
        FROM fp.build_crm_farmacia_medico_ano F
        WHERE F.nu_prescricoes < 1
           OR NOT EXISTS (SELECT 1 FROM fp.build_crm_medico_dim D WHERE D.id_medico_num = F.id_medico_num)
    )
        THROW 51053, 'Farmacia x medico x ano ou ranking com medico fora da dimensao, ou prescricoes invalidas.', 1;
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT CAST(ano AS INT) AS ano, SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes
            FROM fp.build_crm_medico_brasil_ano
            GROUP BY ano
        ) B
        FULL JOIN (
            SELECT CAST(ano AS INT) AS ano, SUM(CAST(nu_prescricoes AS BIGINT)) AS nu_prescricoes
            FROM fp.build_crm_farmacia_medico_ano
            GROUP BY ano
        ) F
            ON F.ano = B.ano
        WHERE B.ano IS NULL
           OR F.ano IS NULL
           OR B.nu_prescricoes <> F.nu_prescricoes
    )
        THROW 51054, 'Farmacia x medico x ano diverge do total anual de prescricoes do Brasil.', 1;
END
ELSE
    PRINT '>> [PROMOCAO CRM] Grupo CRM medico sem build_*: app_* mantidas.';

-- ============================================================================
-- Promocao: so onde existe build_*
-- ============================================================================
PRINT '>> [PROMOCAO CRM] Renomeando tabelas...';

DECLARE @ordem INT = 0;
DECLARE @nome SYSNAME;
DECLARE @antigo NVARCHAR(300);
DECLARE @novo SYSNAME;
DECLARE @sql NVARCHAR(600);

BEGIN TRY
    BEGIN TRAN;

    WHILE 1 = 1
    BEGIN
        SELECT TOP (1) @ordem = ordem, @nome = nome
        FROM @tabelas
        WHERE ordem > @ordem
        ORDER BY ordem;
        IF @@ROWCOUNT = 0 BREAK;

        IF OBJECT_ID('fp.build_' + @nome, 'U') IS NULL
        BEGIN
            INSERT INTO @resumo (ordem, tabela, situacao)
            VALUES (@ordem, 'app_' + @nome,
                    IIF(OBJECT_ID('fp.app_' + @nome, 'U') IS NULL,
                        'sem build e sem app', 'mantida (sem build)'));
            CONTINUE;
        END;

        IF OBJECT_ID('fp.app_' + @nome, 'U') IS NOT NULL
        BEGIN
            SET @sql = N'DROP TABLE fp.' + QUOTENAME(N'app_' + @nome) + N';';
            EXEC sys.sp_executesql @sql;
        END;

        SET @antigo = N'fp.build_' + @nome;
        SET @novo = N'app_' + @nome;
        EXEC sys.sp_rename @antigo, @novo;

        INSERT INTO @resumo (ordem, tabela, situacao)
        VALUES (@ordem, @novo, 'promovida');
    END;

    COMMIT TRAN;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRAN;
    PRINT '   ERRO na promocao: nenhuma app_* foi alterada.';
    THROW;
END CATCH;

INSERT INTO @resumo (ordem, tabela, situacao)
SELECT 1000, 'app_' + nome, 'descontinuada (nao apagada; pode apagar)'
FROM @descontinuadas
WHERE OBJECT_ID('fp.app_' + nome, 'U') IS NOT NULL;

PRINT '>> [PROMOCAO CRM] Concluida.';

SELECT tabela, situacao FROM @resumo ORDER BY ordem, tabela;
