SET NOCOUNT ON;
SET XACT_ABORT ON;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.app_crm_prescricoes_medico_municipio_mes
    WHERE nu_prescricoes_mes IS NULL
       OR nu_prescricoes_mes < 0
       OR nu_prescricoes_mes > 32767
)
    THROW 51100, 'Existem valores fora do limite do SMALLINT (0 a 32767).', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    ALTER TABLE temp_CGUSC.fp.app_crm_prescricoes_medico_municipio_mes
        ALTER COLUMN nu_prescricoes_mes SMALLINT NOT NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT
    MAX(nu_prescricoes_mes) AS maior_valor,
    COUNT_BIG(*) AS qtd_linhas
FROM temp_CGUSC.fp.app_crm_prescricoes_medico_municipio_mes;
