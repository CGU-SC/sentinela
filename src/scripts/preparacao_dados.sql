--**************************************************************************************************************************************
-- Configuracao e versao minima do sistema
--**************************************************************************************************************************************

IF OBJECT_ID('temp_CGUSC.fp.config_sistema', 'U') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.config_sistema (
        id INT IDENTITY(1,1) NOT NULL,
        chave VARCHAR(50) NOT NULL,
        valor VARCHAR(MAX) NOT NULL,
        descricao VARCHAR(255) NULL,
        dt_atualizacao DATETIME NOT NULL
            CONSTRAINT DF_config_sistema_dt_atualizacao DEFAULT GETDATE(),
        CONSTRAINT PK_config_sistema PRIMARY KEY CLUSTERED (id),
        CONSTRAINT UQ_config_sistema_chave UNIQUE (chave)
    );
END;

IF COL_LENGTH('temp_CGUSC.fp.config_sistema', 'id') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.config_sistema', 'chave') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.config_sistema', 'valor') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.config_sistema', 'descricao') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.config_sistema', 'dt_atualizacao') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.config_sistema sem colunas obrigatorias.', 16, 1);
    RETURN;
END;

IF NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.config_sistema
    WHERE chave = 'versao_minima_obrigatoria'
)
BEGIN
    INSERT INTO temp_CGUSC.fp.config_sistema (chave, valor, descricao)
    VALUES (
        'versao_minima_obrigatoria',
        '3.1.0',
        'Define a versao minima do executavel permitida para rodar.'
    );
END
ELSE
BEGIN
    UPDATE temp_CGUSC.fp.config_sistema
    SET valor = '3.1.0',
        descricao = 'Define a versao minima do executavel permitida para rodar.',
        dt_atualizacao = GETDATE()
    WHERE chave = 'versao_minima_obrigatoria';
END;


--**************************************************************************************************************************************
-- Criar lista de CNPJs que serao analisados
--**************************************************************************************************************************************

DROP TABLE IF EXISTS temp_CGUSC.fp.lista_cnpjs
SELECT DISTINCT A.cnpj
INTO temp_CGUSC.fp.lista_cnpjs
FROM db_farmaciaPopular.dbo.relatorio_movimentacao_2015_2024 A
WHERE A.data_hora >= '2015-07-01'
  AND A.data_hora < '2024-12-11'
GROUP BY A.cnpj;

-- Cria índice clusterizado para performance máxima nos JOINs subsequentes
CREATE CLUSTERED INDEX IX_lista_cnpjs_cnpj 
ON temp_CGUSC.fp.lista_cnpjs (cnpj);

-- Chave estavel de GTIN: preserva o mesmo id para cada codigo_barra mesmo apos
-- recriar temp_CGUSC.fp.medicamentos_patologia.
IF OBJECT_ID('temp_CGUSC.fp.medicamentos_patologia_chave') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.medicamentos_patologia_chave (
        id           INT IDENTITY(1,1) NOT NULL,
        codigo_barra VARCHAR(14)       NOT NULL,
        dt_criacao   DATETIME          NOT NULL
            CONSTRAINT DF_MedicamentosPatologiaChave_DtCriacao DEFAULT GETDATE(),
        CONSTRAINT PK_MedicamentosPatologiaChave PRIMARY KEY CLUSTERED (id),
        CONSTRAINT UQ_MedicamentosPatologiaChave_CodigoBarra UNIQUE (codigo_barra)
    );
END;

INSERT INTO temp_CGUSC.fp.medicamentos_patologia_chave (codigo_barra)
SELECT DISTINCT CAST(M.codigo_barra AS VARCHAR(14)) AS codigo_barra
FROM temp_CGUSC.fp.medicamentos_patologia AS M
WHERE M.codigo_barra IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM temp_CGUSC.fp.medicamentos_patologia_chave AS K
      WHERE K.codigo_barra = CAST(M.codigo_barra AS VARCHAR(14))
  );




--**************************************************************************************************************************************
-- Particionamento dos CNPJs para processamento em pequenos lotes
--**************************************************************************************************************************************

-- Verifica se a tabela de lotes existe e a remove, se necessario
DROP TABLE IF EXISTS temp_CGUSC.fp.classificacao_blocos;

-- Cria uma tabela temporária com CNPJs classificados em 50 grupos
SELECT 
    cnpj,
    NTILE(50) OVER (ORDER BY cnpj) AS classif
INTO temp_CGUSC.fp.classificacao_blocos
FROM temp_CGUSC.fp.lista_cnpjs;

-- Cria índice no campo classif para otimizar JOINs
CREATE NONCLUSTERED INDEX IX_classificacao_blocos_classif
ON temp_CGUSC.fp.classificacao_blocos (classif)
INCLUDE (cnpj);





--***************************************************************************************************************
--Criar Tabela com CNPJ da Farmácia e a data da primeira venda
--***************************************************************************************************************



-- Verifica se a tabela temporária existe e a remove, se necessário
IF OBJECT_ID('temp_CGUSC.fp.farmacia_inicio_venda', 'U') IS NOT NULL
    DROP TABLE temp_CGUSC.fp.farmacia_inicio_venda;

-- Cria uma tabela temporária com o CNPJ e a data inicial de vendas
SELECT 
    A.cnpj,
    MIN(A.data_hora) AS datavendainicial
INTO temp_CGUSC.fp.farmacia_inicio_venda
FROM db_farmaciaPopular.dbo.relatorio_movimentacao_2015_2024 A
INNER JOIN temp_CGUSC.fp.lista_cnpjs B 
    ON B.cnpj = A.cnpj
WHERE A.data_hora >= '2015-07-01'
  AND A.data_hora < '2024-12-11'
GROUP BY A.cnpj;


-- definir os estoques iniciais com critério da soma das duas últimas aquisições anteriores a primeira venda na base de --producao



DROP TABLE IF EXISTS TEMP_CGUSC.fp.farmacia_inicio_venda_gtin
select a.cnpj, a.codigo_barra, min(data_hora) as data_inicio_venda
into TEMP_CGUSC.fp.farmacia_inicio_venda_gtin
FROM db_farmaciaPopular.dbo.relatorio_movimentacao_2015_2024 A
inner join temp_CGUSC.fp.medicamentos_patologia B on B.codigo_barra = A.codigo_barra
inner join temp_CGUSC.fp.lista_cnpjs C on C.cnpj = A.cnpj
WHERE 
a.data_hora >= '2015-07-01' and a.data_hora < '2024-12-11'
group by A.cnpj,A.codigo_barra


CREATE NONCLUSTERED INDEX indiceCodigoBarra ON TEMP_CGUSC.fp.farmacia_inicio_venda_gtin(codigo_barra)
CREATE NONCLUSTERED INDEX indicecnpj ON TEMP_CGUSC.fp.farmacia_inicio_venda_gtin(cnpj)
CREATE NONCLUSTERED INDEX indiceDataHora ON TEMP_CGUSC.fp.farmacia_inicio_venda_gtin(data_inicio_venda)



drop table if exists #datas_estoques_inicio_contagem
select A.cnpj as cnpj_estabelecimento,A.codigo_barra,
DATEADD(m,-6,data_inicio_venda) as 'data_estoque_inicial',
DATEADD(d,-1,data_inicio_venda) as 'data_estoque_final'
into #datas_estoques_inicio_contagem
from temp_CGUSC.fp.farmacia_inicio_venda_gtin A 


drop table if exists #notas_estoque_inicialFP
select A.destinatarioNFE as cnpj_estabelecimento,codigoBarra as codigo_barra, A.numeroNFE, A.dataEmissaoNFE, A.quantidade
into #notas_estoque_inicialFP
from db_farmaciapopular_nf.dbo.aquisicoesFazenda_2015_2025 A
inner join #datas_estoques_inicio_contagem B on B.cnpj_estabelecimento = A.destinatarioNFE and B.codigo_barra = A.codigoBarra
where A.dataEmissaoNFE>=B.data_estoque_inicial and A.dataEmissaoNFE<=B.data_estoque_final and A.tipooperacao = 1


CREATE NONCLUSTERED INDEX index1 ON #notas_estoque_inicialFP(cnpj_estabelecimento)
CREATE NONCLUSTERED INDEX index2 ON #notas_estoque_inicialFP(codigo_barra)
CREATE NONCLUSTERED INDEX index3 ON #notas_estoque_inicialFP(dataEmissaoNFE)


drop table if exists #notas_estoque_inicialFP_temp2
select cnpj_estabelecimento,codigo_barra,numeroNFE,dataEmissaoNFE, quantidade,
    ROW_NUMBER() OVER (
        PARTITION BY codigo_barra,cnpj_estabelecimento
        ORDER BY dataEmissaoNFE desc, numeroNFE desc
    ) row_num
into #notas_estoque_inicialFP_temp2
from #notas_estoque_inicialFP


CREATE NONCLUSTERED INDEX index1 ON #notas_estoque_inicialFP_temp2(cnpj_estabelecimento)
CREATE NONCLUSTERED INDEX index2 ON #notas_estoque_inicialFP_temp2(codigo_barra)
CREATE NONCLUSTERED INDEX index3 ON #notas_estoque_inicialFP_temp2(dataEmissaoNFE)



drop table if exists temp_CGUSC.fp.estoque_inicial
select cnpj_estabelecimento,a.codigo_barra,sum(quantidade) as estoque_inicial, b.data_inicio_venda as 'data_estoque_inicial' 
into temp_CGUSC.fp.estoque_inicial
from #notas_estoque_inicialFP_temp2 A
inner join temp_CGUSC.fp.farmacia_inicio_venda_gtin B on B.cnpj = A.cnpj_estabelecimento and B.codigo_barra = A.codigo_barra
where row_num < 3 
group by a.cnpj_estabelecimento,a.codigo_barra,b.data_inicio_venda
order by a.codigo_barra asc

CREATE NONCLUSTERED INDEX index1 ON temp_CGUSC.fp.estoque_inicial(cnpj_estabelecimento)
CREATE NONCLUSTERED INDEX index2 ON temp_CGUSC.fp.estoque_inicial(codigo_barra)


-- Salvar as notas de fiscais de aquisição consideradas na Estimativa do Estoque Inicial

drop table if exists temp_CGUSC.fp.estoque_inicial_notas
select A.cnpj_estabelecimento,A.quantidade as qnt, A.codigo_barra, A.dataEmissaoNFE, A.numeroNFE, b.estoque_inicial
into temp_CGUSC.fp.estoque_inicial_notas
from #notas_estoque_inicialFP_temp2 A
inner join temp_CGUSC.fp.estoque_inicial b on b.cnpj_estabelecimento = A.cnpj_estabelecimento and b.codigo_barra = A.codigo_barra
where row_num < 3 

CREATE NONCLUSTERED INDEX index1 ON temp_CGUSC.fp.estoque_inicial_notas(cnpj_estabelecimento)
CREATE NONCLUSTERED INDEX index2 ON temp_CGUSC.fp.estoque_inicial_notas(codigo_barra)
   
















--***************************************************************************************************************
--Criar lista de Contatos das Farmácias Analisadas. Informação utilizada na geração dos relatórios.
--***************************************************************************************************************

-- Verifica se a tabela temporária existe e a remove, se necessário
IF OBJECT_ID('temp_CGUSC.dbo.ContatoFarmacia', 'U') IS NOT NULL
    DROP TABLE temp_CGUSC.dbo.ContatoFarmacia;

-- Seleciona os dados de contato das farmácias e insere na tabela temporária
SELECT 
    B.cnpj, -- CNPJ da lista de entrada
    COALESCE(A.nu_ddd, '#') AS nu_ddd, -- DDD, substituindo nulos por '#'
    COALESCE(A.nu_telefone, '#') AS nu_telefone, -- Telefone, substituindo nulos por '#'
    COALESCE(A.ds_email, '#') AS ds_email -- E-mail, substituindo nulos por '#'
INTO temp_CGUSC.dbo.ContatoFarmacia -- Insere o resultado na tabela temporária
FROM temp_CGUSC.fp.lista_cnpjs B -- Tabela com a lista de CNPJs a serem consultados
LEFT JOIN (
    -- Subconsulta para combinar dados das duas tabelas de farmácia e evitar duplicatas
    SELECT 
        NU_CNPJ, 
        NU_DDD, 
        NU_TELEFONE, 
        DS_EMAIL,
        -- Atribui um número de linha para cada registro por CNPJ, ordenando por prioridade da fonte
        ROW_NUMBER() OVER (PARTITION BY NU_CNPJ ORDER BY 
            CASE WHEN fonte = 'carga_2024' THEN 1 ELSE 2 END) AS rn
    FROM (
        -- Combina os dados das duas tabelas de farmácia
        SELECT 
            NU_CNPJ, 
            NU_DDD, 
            NU_TELEFONE, 
            DS_EMAIL, 
            'carga_2024' AS fonte -- Identifica a origem como carga_2024
        FROM db_farmaciaPopular.carga_2024.tb_farmacia
        WHERE NU_CNPJ IS NOT NULL -- Filtra apenas registros com CNPJ válido
        UNION ALL
        SELECT 
            NU_CNPJ, 
            NU_DDD, 
            NU_TELEFONE, 
            DS_EMAIL, 
            'dbo' AS fonte -- Identifica a origem como dbo
        FROM db_farmaciaPopular.dbo.tb_farmacia
        WHERE NU_CNPJ IS NOT NULL -- Filtra apenas registros com CNPJ válido
    ) combined -- Nome da subconsulta que combina os dados
) A 
    ON B.cnpj = A.NU_CNPJ -- Junta com a lista de CNPJs usando LEFT JOIN
WHERE A.rn = 1 OR A.rn IS NULL; -- Seleciona apenas o primeiro registro por CNPJ ou nulos (sem correspondência)




--**************************************************************************************************************************************
-- criar tabelas [processamentosFP], dadosProcessamentosFP e movimentacaoMensalCodigoBarraFP
--**************************************************************************************************************************************





-- Verifica e remove a tabela temporária movimentacaoMensalCodigoBarraFP, se existir
IF OBJECT_ID('temp_cgusc.fp.movimentacao_mensal_gtin', 'U') IS NOT NULL
    DROP TABLE temp_cgusc.fp.movimentacao_mensal_gtin;

-- Verifica e remove a tabela temporária processamentosFP, se existir
IF OBJECT_ID('temp_cgusc.fp.processamentosFP', 'U') IS NOT NULL
    DROP TABLE temp_cgusc.fp.processamentosFP;
    
IF OBJECT_ID('fp.memoria_calculo_consolidada', 'U') IS NOT NULL
    DROP TABLE fp.memoria_calculo_consolidada;




CREATE TABLE fp.memoria_calculo_consolidada (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_processamento BIGINT NOT NULL, -- Link com a tabela processamentosFP
    cnpj VARCHAR(14) NOT NULL,
    
    -- O "Coração" da Auditoria: Todo o cálculo do Python em formato JSON estruturado (Payload v2)
    memoria_calculo_payload VARBINARY(MAX),
    schema_version TINYINT NOT NULL DEFAULT 1,
    
    data_carga DATETIME DEFAULT GETDATE()
);

-- Índice para recuperação rápida por CNPJ (ex: para refazer um Excel específico)
CREATE NONCLUSTERED INDEX IDX_Memoria_CNPJ ON fp.memoria_calculo_consolidada(cnpj);



-- Cria a tabela temporária processamento para armazenar dados de auditoria das farmácias
	drop table if exists temp_cgusc.fp.processamento
	CREATE TABLE temp_cgusc.fp.processamento(
	[id] [int] PRIMARY KEY IDENTITY(1,1) NOT NULL,
	[cnpj] [varchar](14) NOT NULL,
	razao_social [varchar](200) NULL,
	nome_fantasia [varchar](200) NULL,
	municipio [varchar](100) NULL,
	uf [char](2) NULL,
	[periodo_inicial] [date] NOT NULL,
	[periodo_final] [date] NOT NULL,
	[data_processamento] [datetime2] NOT NULL,
	situacao [tinyint] not null,
    status_detalhado VARCHAR(500),  
    tempo_processamento_segundos DECIMAL(10,2), 
    total_registros_processados INT,  
    total_medicamentos INT
	);

	CREATE INDEX ix_processamento_cnpj ON temp_cgusc.fp.processamento(cnpj);
	CREATE INDEX ix_processamento_data ON temp_cgusc.fp.processamento(data_processamento);


-- Cria a tabela temporária movimentacaoMensalCodigoBarraFP para movimentações mensais por código de barra
	drop table if exists temp_cgusc.fp.movimentacao_mensal_gtin
	CREATE TABLE temp_cgusc.fp.movimentacao_mensal_gtin(
	[id] INT Identity(1,1) Primary Key,
	[id_processamento] INT NULL,
	[id_gtin] INT NOT NULL,
	[periodo] [date] NULL,
	[qnt_caixas_vendidas] [smallint] NULL,
	[qnt_caixas_sem_comprovacao] [smallint] NULL,
	[num_autorizacoes] [smallint] NULL,
	[valor_vendas] [DECIMAL](9, 2) NULL,
	[valor_sem_comprovacao] [DECIMAL](9, 2) NULL,
	constraint fk2_id_processamento_movimentacao_codigo_barra foreign key (id_processamento) references temp_cgusc.[fp].[processamento](id),
	constraint fk_movMensalGtin_id_gtin foreign key (id_gtin) references temp_cgusc.[fp].[medicamentos_patologia_chave](id)
	);

	-- Índices para performance de consulta por GTIN e Auditoria
	CREATE INDEX ix_movMensalGtin_proc ON temp_cgusc.fp.movimentacao_mensal_gtin(id_processamento);
	CREATE INDEX ix_movMensalGtin_periodo ON temp_cgusc.fp.movimentacao_mensal_gtin(periodo);
	CREATE INDEX ix_movMensalGtin_gtin ON temp_cgusc.fp.movimentacao_mensal_gtin(id_gtin);









   
      

   
   



   
      






























	--------------------------------------------------------------
-- MÓDULO: Farmácia Popular
-- OBJETIVO: Criação das tabelas de dados de farmácias e sócios
-- BASE: db_CNPJ / db_FarmaciaPopular
--------------------------------------------------------------


--------------------------------------------------------------
-- ETAPA 1: Dados cadastrais das farmácias (1ª passagem)
--------------------------------------------------------------

DROP TABLE IF EXISTS #tempCnaesSecundarios;

IF EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.lista_cnpjs LST
    INNER JOIN db_CNPJ.dbo.CNAESecundaria CS
        ON CS.CNPJ = LST.cnpj
    WHERE TRY_CAST(CS.idSubClasseCNAE AS INT) IS NULL
)
BEGIN
    THROW 50005, 'Existem CNAEs secundarios invalidos para farmacias do programa.', 1;
END;

SELECT DISTINCT
    CAST(CS.CNPJ AS CHAR(14)) AS cnpj,
    TRY_CAST(CS.idSubClasseCNAE AS INT) AS id_cnae_secundario,
    CAST(
        temp_CGUSC.dbo.InitCapEachWord(SC.DescSubClasseCNAE)
        AS VARCHAR(255)
    ) AS cnae_secundario
INTO #tempCnaesSecundarios
FROM temp_CGUSC.fp.lista_cnpjs LST
INNER JOIN db_CNPJ.dbo.CNAESecundaria CS
    ON CS.CNPJ = LST.cnpj
LEFT JOIN db_CNPJ.dbo.SubClasseCNAE SC
    ON SC.idSubClasseCNAE = CS.idSubClasseCNAE
;

DECLARE @qtd_cnaes_secundarios_sem_descricao BIGINT;
DECLARE @aviso_cnaes_secundarios VARCHAR(2048);

SELECT
    @qtd_cnaes_secundarios_sem_descricao = COUNT_BIG(*)
FROM #tempCnaesSecundarios
WHERE NULLIF(LTRIM(RTRIM(cnae_secundario)), '') IS NULL;

IF @qtd_cnaes_secundarios_sem_descricao > 0
BEGIN
    SET @aviso_cnaes_secundarios =
        'AVISO: '
        + CAST(@qtd_cnaes_secundarios_sem_descricao AS VARCHAR(20))
        + ' vinculos de CNAE secundario serao preservados sem descricao, '
        + 'pois o codigo nao foi encontrado na tabela db_CNPJ.dbo.SubClasseCNAE.';

    RAISERROR(@aviso_cnaes_secundarios, 10, 1) WITH NOWAIT;
END;

CREATE UNIQUE CLUSTERED INDEX ix_tempCnaesSecundarios
    ON #tempCnaesSecundarios(cnpj, id_cnae_secundario);

DROP TABLE IF EXISTS #cnpjs_cnae_farmacia_secundario;

SELECT DISTINCT
    cnpj
INTO #cnpjs_cnae_farmacia_secundario
FROM #tempCnaesSecundarios
WHERE id_cnae_secundario IN (4771701, 4771702);

CREATE UNIQUE CLUSTERED INDEX ix_cnpjs_cnae_farmacia_secundario
    ON #cnpjs_cnae_farmacia_secundario(cnpj);

DROP TABLE IF EXISTS #tempDadosFarmacias;

SELECT
    CAST(c.cnpj AS CHAR(14))                                   AS cnpj,
    CAST(c.indMatriz AS CHAR(1))                               AS indMatriz,
    CAST(temp_CGUSC.dbo.InitCapEachWord(LEFT(c.RazaoSocial, 100)) AS VARCHAR(100)) AS razaoSocial,
    CAST(temp_CGUSC.dbo.InitCapEachWord(LEFT(c.NomeFantasia, 100)) AS VARCHAR(100)) AS nomeFantasia,
    CAST(c.CodPorteEmpresa AS TINYINT)                         AS CodPorteEmpresa,
    temp_CGUSC.dbo.InitCapEachWord(c.TipoLogradouro)           AS tipoLogradouro,
    temp_CGUSC.dbo.InitCapEachWord(c.Logradouro)               AS logradouro,
    c.Numero                                                   AS numero,
    temp_CGUSC.dbo.InitCapEachWord(c.Complemento)              AS complemento,
    temp_CGUSC.dbo.InitCapEachWord(c.Bairro)                   AS bairro,
    CAST(c.cep AS CHAR(8))                                     AS cep,
    CAST(ibge.id_ibge7 AS CHAR(7))                             AS codibge,
    CAST(ibge.no_municipio    AS VARCHAR(100))                 AS municipio,
    ibge.sg_uf                                                 AS uf,
    CAST(ibge.nu_populacao    AS INT)                          AS populacao2019,
    CAST(ibge.no_regiao_saude AS VARCHAR(100))                 AS no_regiao_saude,
    CAST(ibge.id_regiao_saude AS VARCHAR(20))                  AS id_regiao_saude,
    c.IndPossuiSocio                                           AS indPossuiSocio,
    CAST(c.SituacaoCadastral AS TINYINT)                       AS situacaoCadastral,
    temp_CGUSC.dbo.InitCapEachWord(sit.ds_situacao_cnpj)       AS descricaoSituacaoCadastral,
    CAST(c.DataSituacaoCadastral AS DATE)                      AS DataSituacaoCadastral,
    CAST(c.DataAbertura AS DATE)                               AS data_abertura,
    CAST(c.CodNaturezaJuridica AS SMALLINT)                    AS CodNaturezaJuridica,
    temp_CGUSC.dbo.InitCapEachWord(nat.DescNaturezaJuridica)   AS natureza_juridica,
    c.CpfResponsavel,
    temp_CGUSC.dbo.InitCapEachWord(c.NomeResponsavel)          AS nome_responsavel,
    c.QualificacaoResponsavel,
    temp_CGUSC.dbo.InitCapEachWord(qua.DescricaoQualificacao)  AS descricaoQualificacaoResponsavel,
    c.CnaeFiscal                                               AS id_cnae_principal,
    temp_CGUSC.dbo.InitCapEachWord(cnae_p.DescSubClasseCNAE)   AS cnae_principal,
    CASE
        WHEN TRY_CAST(c.CnaeFiscal AS INT) IN (4771701, 4771702)
          OR cnae_farmacia_secundario.cnpj IS NOT NULL
        THEN CAST(0 AS TINYINT)
        ELSE CAST(1 AS TINYINT)
    END                                                        AS is_cnae_farmacia_ausente,
    c.Telefone1                                                AS telefone_1,
    c.Telefone2                                                AS telefone_2,
    LOWER(c.CorreioEletronico)                                 AS correio_eletronico,
    GETDATE()                                                  AS data_processamento
INTO #tempDadosFarmacias
FROM temp_CGUSC.fp.lista_cnpjs                     AS lst
INNER JOIN db_CNPJ.dbo.cnpj                            AS c    ON c.cnpj               = lst.cnpj
LEFT JOIN  db_CNPJ.dbo.naturezaJuridica                  AS nat  ON nat.idNaturezaJuridica  = c.CodNaturezaJuridica
LEFT JOIN  db_CNPJ.dbo.dime_situacao_cadastral_cnpj      AS sit  ON sit.cd_situacao_cnpj   = c.SituacaoCadastral
LEFT JOIN  db_CNPJ.dbo.qualificacao                      AS qua  ON qua.idQualificacao      = c.QualificacaoResponsavel
LEFT JOIN  db_CNPJ.dbo.Municipio                         AS mun  ON mun.SkMunicipio         = c.CodMunicipio
LEFT JOIN  temp_CGUSC.fp.dados_ibge                      AS ibge ON ibge.id_ibge7           = mun.CodIbge
LEFT JOIN  db_CNPJ.dbo.SubClasseCNAE                     AS cnae_p ON cnae_p.idSubClasseCNAE = c.CnaeFiscal
LEFT JOIN  #cnpjs_cnae_farmacia_secundario AS cnae_farmacia_secundario
    ON cnae_farmacia_secundario.cnpj = lst.cnpj;

-- Índice em #tempDadosFarmacias
-- Chave principal de acesso: CNPJ
CREATE INDEX ix_tempFarmacias_cnpj
    ON #tempDadosFarmacias (cnpj);


--------------------------------------------------------------
-- ETAPA 1.1: Enriquecimento — Dados Geográficos e Porte
--------------------------------------------------------------

DROP TABLE IF EXISTS #tempDadosFarmacias2;

SELECT
    f.cnpj,
    f.indMatriz,
    f.razaoSocial,
    f.nomeFantasia,
    f.CodPorteEmpresa,
    f.tipoLogradouro,
    f.logradouro,
    f.numero,
    f.complemento,
    f.bairro,
    RIGHT('00000000' + CONVERT(VARCHAR(8), LTRIM(RTRIM(f.cep))), 8) AS cep,
    f.codibge,
    f.municipio,
    f.uf,
    f.populacao2019,
    f.no_regiao_saude,
    f.id_regiao_saude,
    f.indPossuiSocio,
    f.situacaoCadastral,
    f.descricaoSituacaoCadastral                                     AS situacaoReceita,
    f.data_abertura,
    f.DataSituacaoCadastral                                          AS dataSituacaoCadastral,
    f.CodNaturezaJuridica                                            AS codNaturezaJuridica,
    f.natureza_juridica,
    f.CpfResponsavel                                                 AS cpfResponsavel,
    f.nome_responsavel,
    f.QualificacaoResponsavel                                        AS qualificacaoResponsavel,
    f.descricaoQualificacaoResponsavel,
    f.id_cnae_principal,
    f.cnae_principal,
    f.is_cnae_farmacia_ausente,
    f.telefone_1,
    f.telefone_2,
    f.correio_eletronico,
    f.data_processamento,
    CASE f.CodPorteEmpresa
        WHEN '01' THEN 'Microempresa (ME)'
        WHEN '03' THEN 'Empresa de Pequeno Porte (EPP)'
        WHEN '05' THEN 'Demais'
        ELSE 'Não Informado'
    END AS ds_porte_empresa
INTO #tempDadosFarmacias2
FROM #tempDadosFarmacias AS f;

-- Chave estavel de farmacia: preserva o mesmo id para cada CNPJ mesmo apos
-- recriar temp_CGUSC.fp.dados_farmacia.
IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia_chave') IS NULL
BEGIN
    CREATE TABLE temp_CGUSC.fp.dados_farmacia_chave (
        id         INT IDENTITY(1,1) NOT NULL,
        cnpj       CHAR(14)          NOT NULL,
        dt_criacao DATETIME          NOT NULL
            CONSTRAINT DF_DadosFarmaciaChave_DtCriacao DEFAULT GETDATE(),
        CONSTRAINT PK_DadosFarmaciaChave PRIMARY KEY CLUSTERED (id),
        CONSTRAINT UQ_DadosFarmaciaChave_Cnpj UNIQUE (cnpj)
    );
END;

IF OBJECT_ID('temp_CGUSC.fp.dados_farmacia') IS NOT NULL
   AND COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'id') IS NOT NULL
   AND COL_LENGTH('temp_CGUSC.fp.dados_farmacia', 'cnpj') IS NOT NULL
BEGIN
    SET IDENTITY_INSERT temp_CGUSC.fp.dados_farmacia_chave ON;

    INSERT INTO temp_CGUSC.fp.dados_farmacia_chave (id, cnpj)
    SELECT DISTINCT CAST(f.id AS INT) AS id, CAST(f.cnpj AS CHAR(14)) AS cnpj
    FROM temp_CGUSC.fp.dados_farmacia AS f
    WHERE f.id IS NOT NULL
      AND f.cnpj IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM temp_CGUSC.fp.dados_farmacia_chave AS k
          WHERE k.cnpj = CAST(f.cnpj AS CHAR(14))
      )
      AND NOT EXISTS (
          SELECT 1
          FROM temp_CGUSC.fp.dados_farmacia_chave AS k
          WHERE k.id = CAST(f.id AS INT)
      );

    SET IDENTITY_INSERT temp_CGUSC.fp.dados_farmacia_chave OFF;
END;

INSERT INTO temp_CGUSC.fp.dados_farmacia_chave (cnpj)
SELECT DISTINCT CAST(f.cnpj AS CHAR(14)) AS cnpj
FROM #tempDadosFarmacias2 AS f
WHERE NOT EXISTS (
    SELECT 1
    FROM temp_CGUSC.fp.dados_farmacia_chave AS k
    WHERE k.cnpj = CAST(f.cnpj AS CHAR(14))
);

-- Colunas de controle e georreferenciamento
ALTER TABLE #tempDadosFarmacias2 ADD id        INT;
ALTER TABLE #tempDadosFarmacias2 ADD latitude  DECIMAL(9, 6);
ALTER TABLE #tempDadosFarmacias2 ADD longitude DECIMAL(9, 6);

UPDATE f
SET id = k.id
FROM #tempDadosFarmacias2 AS f
INNER JOIN temp_CGUSC.fp.dados_farmacia_chave AS k
    ON k.cnpj = CAST(f.cnpj AS CHAR(14));

IF EXISTS (SELECT 1 FROM #tempDadosFarmacias2 WHERE id IS NULL)
BEGIN
    RAISERROR('Falha ao mapear id estavel para um ou mais CNPJs em dados_farmacia_chave.', 16, 1);
    RETURN;
END;

ALTER TABLE #tempDadosFarmacias2
    ALTER COLUMN id INT NOT NULL;

ALTER TABLE #tempDadosFarmacias2
    ADD PRIMARY KEY (id);

-- Índice em #tempDadosFarmacias2
-- CNPJ é a chave de negócio usada em todos os JOINs posteriores
CREATE INDEX ix_tempFarmacias2_cnpj
    ON #tempDadosFarmacias2 (cnpj);


--------------------------------------------------------------
-- ETAPA 4: Datas de movimentação por farmácia
--------------------------------------------------------------

DROP TABLE IF EXISTS #tempDatasMovimentacao;

SELECT
    mov.cnpj,
    MIN(mov.data_hora) AS dataInicialDadosMovimentacao,
    MAX(mov.data_hora) AS dataFinalDadosMovimentacao
INTO #tempDatasMovimentacao
FROM db_FarmaciaPopular.dbo.relatorio_movimentacao_2015_2024 AS mov
GROUP BY mov.cnpj;

-- Índice em #tempDatasMovimentacao
-- CNPJ é a única chave de JOIN desta tabela
CREATE INDEX ix_tempDatasMovimentacao_cnpj
    ON #tempDatasMovimentacao (cnpj);


--------------------------------------------------------------
-- ETAPA 5: Tabela final consolidada
--------------------------------------------------------------

DROP TABLE IF EXISTS temp_CGUSC.fp.dados_farmacia_cnaes_secundarios;
DROP TABLE IF EXISTS temp_CGUSC.fp.dados_farmacia;

SELECT
    f.*,
    mov.dataInicialDadosMovimentacao,
    mov.dataFinalDadosMovimentacao,
    cs.VlrCapitalSocial AS capital_social
INTO temp_CGUSC.fp.dados_farmacia
FROM #tempDadosFarmacias2                  AS f
LEFT JOIN #tempDatasMovimentacao           AS mov ON mov.cnpj = f.cnpj
LEFT JOIN db_CNPJ_CapitalSocial.dbo.CNPJ_CapitalSocial AS cs  ON cs.NumCNPJ = f.cnpj;

-- O id ja vem de temp_CGUSC.fp.dados_farmacia_chave; aqui apenas garantimos
-- a PK e os indices da tabela final.
ALTER TABLE temp_CGUSC.fp.dados_farmacia
    ADD PRIMARY KEY (id);



-- Índices na tabela final
-- O ID já é Clustered por ser Primary Key.

-- Chave de negócio: CNPJ
CREATE NONCLUSTERED INDEX ix_dadosFarmacia_cnpj
    ON temp_CGUSC.fp.dados_farmacia (cnpj);

-- Filtros geográficos frequentes: UF e município
CREATE INDEX ix_dadosFarmacia_uf_municipio
    ON temp_CGUSC.fp.dados_farmacia (uf, municipio);

-- Filtro municipal por codigo IBGE
CREATE INDEX ix_dadosFarmacia_codibge
    ON temp_CGUSC.fp.dados_farmacia (codibge)
    INCLUDE (id, cnpj);

-- Georreferenciamento: suporte a queries espaciais aproximadas
CREATE INDEX ix_dadosFarmacia_geo
    ON temp_CGUSC.fp.dados_farmacia (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

SELECT
    F.id AS id_cnpj,
    C.id_cnae_secundario,
    C.cnae_secundario,
    CAST(GETDATE() AS SMALLDATETIME) AS data_processamento
INTO temp_CGUSC.fp.dados_farmacia_cnaes_secundarios
FROM #tempCnaesSecundarios C
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.cnpj = C.cnpj;

IF (
    SELECT COUNT_BIG(*)
    FROM temp_CGUSC.fp.dados_farmacia_cnaes_secundarios
) <> (
    SELECT COUNT_BIG(*)
    FROM #tempCnaesSecundarios
)
BEGIN
    THROW 50007, 'Nem todos os CNAEs secundarios foram associados a dados_farmacia.', 1;
END;

ALTER TABLE temp_CGUSC.fp.dados_farmacia_cnaes_secundarios
    ALTER COLUMN id_cnpj INT NOT NULL;

ALTER TABLE temp_CGUSC.fp.dados_farmacia_cnaes_secundarios
    ALTER COLUMN id_cnae_secundario INT NOT NULL;

ALTER TABLE temp_CGUSC.fp.dados_farmacia_cnaes_secundarios
    ADD CONSTRAINT PK_dados_farmacia_cnaes_secundarios
        PRIMARY KEY CLUSTERED (id_cnpj, id_cnae_secundario);

ALTER TABLE temp_CGUSC.fp.dados_farmacia_cnaes_secundarios
    ADD CONSTRAINT FK_dados_farmacia_cnaes_secundarios_farmacia
        FOREIGN KEY (id_cnpj)
        REFERENCES temp_CGUSC.fp.dados_farmacia(id);




---------------------------------------------------------------------------------------------------------------
-- Gerar Lista de CNPJs e Endereços.
-- Arquivo deve ser salvo em XLS para ser lido no script python Coordenadas.py, a fim de se obter as coordenadas de cada 
-- estabelecimento
----------------------------------------------------------------------------------------------------------------


SELECT A.cnpj
	,isnull(A.logradouro, '') + ', ' + try_cast(isnull(A.numero, '') AS VARCHAR(50)) + ', ' + isnull(A.bairro, '') + ', ' + isnull(A.municipio, '') + ', ' + isnull(A.uf, '') AS endereco
FROM temp_CGUSC.fp.dados_farmacia A

----------------------------------------------------------------------------------------------------------------------




----------------------------------------------------------------------------------------------------------------------
-- Após fazer a carga das coordenadas de cada CNPJ na tabela temp_CGUSC.dbo.coordenadas, atualizar a tabela dadosFarmaciasFP.
-- com os dados de latitude e longitude
----------------------------------------------------------------------------------------------------------------------
UPDATE farmacias -- Alias para a tabela de destino
SET
    farmacias.latitude = coords.latitude,
    farmacias.longitude = coords.longitude
FROM
    temp_CGUSC.fp.dados_farmacia AS farmacias -- Tabela que será atualizada (destino)
INNER JOIN
    temp_CGUSC.dbo.coordenadas AS coords -- Tabela com os dados de origem
ON
    farmacias.CNPJ = coords.CNPJ; -- Condição de junção (chave)






























---------------------------------------------------------------------------------------------------------------
-- Gerar Tabela com pagamentos realizados para as farmácias.
----------------------------------------------------------------------------------------------------------------


USE db_dw_portal_siafi;
GO

-- =========================================================================
-- PASSO 1: Isolar e Indexar a Classificação Orçamentária Única
-- =========================================================================
IF OBJECT_ID('tempdb..#Orcamento_Blindado') IS NOT NULL DROP TABLE #Orcamento_Blindado;

SELECT 
    fob.skordembancaria,
    CONVERT(VARCHAR(4), prog.codacao) AS Codigo_Acao,
    CONVERT(VARCHAR(12), 
        CASE 
            WHEN prog.codacao = '20YR' THEN 'gratuidade'
            WHEN prog.codacao = '20YS' THEN 'co-pagamento'
            ELSE NULL 
        END
    ) AS Programa_Acao
INTO #Orcamento_Blindado
FROM dbo.fatordembancaria fob
INNER JOIN dbo.dimempenho emp ON fob.skempenho = emp.skempenho
INNER JOIN dbo.dimptres pt ON emp.codptres = pt.codptres 
INNER JOIN dbo.dimfuncionalprogramaticaresumida prog 
    ON pt.codfuncao = prog.codfuncao 
    AND pt.codsubfuncao = prog.codsubfuncao
    AND pt.codprograma = prog.codprograma 
    AND pt.codacao = prog.codacao
    AND pt.numano = prog.numano
WHERE prog.codacao IN ('20YR', '20YS')
GROUP BY 
    fob.skordembancaria,
    prog.codacao; 

CREATE CLUSTERED INDEX IX_OB_Orcamento ON #Orcamento_Blindado (skordembancaria);


-- =========================================================================
-- PASSO 3: Processar e Salvar os Dados na Tabela Física Final
-- =========================================================================
-- Se a tabela já existir de rodadas anteriores, removemos para evitar erro de tabela duplicada
IF OBJECT_ID('temp_CGUSC.fp.pagamentos_consolidados_farmacia_popular') IS NOT NULL 
    DROP TABLE temp_CGUSC.fp.pagamentos_consolidados_farmacia_popular;

SELECT 
    -- Transforma '20161229' no tipo profissional DATE (2016-12-29)
    CONVERT(DATE, CAST(flc.skdattransacao AS VARCHAR(8)), 112) AS data_pagamento,
    df.id AS id_farmacia, -- <-- Alterado: Salvando o ID (INT) ao invés do CNPJ (CHAR) para economizar espaço
    orc.Codigo_Acao AS codigo_acao,
    orc.Programa_Acao AS programa_acao,
    ob.coddocumento AS numero_ordem_bancaria,
    CONVERT(DECIMAL(11,2), SUM(flc.vallancamento)) AS valor_pago
    
INTO temp_CGUSC.fp.pagamentos_consolidados_farmacia_popular -- <-- Cria e joga o resultado direto aqui!

FROM dbo.fatlistacredores flc
INNER JOIN dbo.dimfavorecido fav ON flc.skfavorecido = fav.skfavorecido
INNER JOIN dbo.dimordembancaria ob ON flc.skordembancaria = ob.skordembancaria
INNER JOIN dbo.dimunidadegestora ug ON flc.skug = ug.skug
LEFT JOIN #Orcamento_Blindado orc ON flc.skordembancaria = orc.skordembancaria 
INNER JOIN temp_CGUSC.fp.dados_farmacia df ON fav.codfavorecido = df.cnpj -- <-- Alterado para a nova tabela
WHERE ug.codug = '257001'

GROUP BY 
    flc.skdattransacao,
    df.id, -- <-- Agrupando pelo ID agora
    ob.coddocumento,
    orc.Codigo_Acao,
    orc.Programa_Acao;


-- =========================================================================
-- PASSO 4: Limpeza de Memória e Validação Inicial
-- =========================================================================
DROP TABLE #Orcamento_Blindado;




























--------------------------------------------------------------
-- ETAPA 2: Dicionário de CPFs
--------------------------------------------------------------

USE [temp_CGUSC];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

DROP TABLE IF EXISTS #cpfs_vivos;
GO
SELECT DISTINCT cpf_cnpj_socio AS cpf INTO #cpfs_vivos 
FROM (
    SELECT cpfResponsavel AS cpf_cnpj_socio FROM temp_CGUSC.fp.dados_farmacia WHERE cpfResponsavel IS NOT NULL
    UNION
    SELECT soc.cpfcnpjSocio FROM temp_CGUSC.fp.lista_cnpjs lst
    INNER JOIN db_CNPJ.dbo.socios soc ON soc.cnpj = lst.cnpj WHERE soc.indSocio = 'PF'
) AS u;
GO
CREATE CLUSTERED INDEX ix_cpfs_vivos ON #cpfs_vivos(cpf);
GO

IF OBJECT_ID('temp_CGUSC.fp.esocial_cnpj_trabalhador_ano', 'U') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.esocial_cnpj_trabalhador_ano nao encontrada para marcar socios do eSocial.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('temp_CGUSC.fp.esocial_cnpj_trabalhador_ano', 'id_cnpj') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.esocial_cnpj_trabalhador_ano', 'cpf_trabalhador') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.esocial_cnpj_trabalhador_ano', 'cbo') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.esocial_cnpj_trabalhador_ano', 'dt_rescisao') IS NULL
BEGIN
    RAISERROR('Tabela temp_CGUSC.fp.esocial_cnpj_trabalhador_ano sem colunas obrigatorias id_cnpj/cpf_trabalhador/cbo/dt_rescisao.', 16, 1);
    RETURN;
END;

DROP TABLE IF EXISTS #cbo_esocial_permitido;
GO
SELECT
    V.cbo,
    V.motivo
INTO #cbo_esocial_permitido
FROM (VALUES
    (411005, 'Auxiliar de escritorio'),
    (411010, 'Assistente administrativo'),
    (411030, 'Auxiliar de pessoal'),
    (412205, 'Continuo'),
    (413110, 'Auxiliar de contabilidade'),
    (414110, 'Armazenista'),
    (414125, 'Estoquista'),
    (421105, 'Atendente comercial'),
    (421110, 'Bilheteiro de transportes coletivos'),
    (421125, 'Operador de caixa'),
    (421205, 'Recebedor de apostas'),
    (511110, 'Comissario de trem'),
    (512105, 'Empregado domestico'),
    (513435, 'Atendente de lanchonete'),
    (514320, 'Faxineiro'),
    (519110, 'Motofretista'),
    (521110, 'Vendedor de comercio varejista'),
    (521130, 'Atendente de farmacia balconista'),
    (521140, 'Atendente de lojas e mercados'),
    (784205, 'Alimentador de linha de producao')
) AS V(cbo, motivo);
GO
CREATE UNIQUE CLUSTERED INDEX ix_cbo_esocial_permitido
ON #cbo_esocial_permitido(cbo);
GO

DROP TABLE IF EXISTS #esocial_vinculo_trabalhista;
GO
SELECT DISTINCT
    CAST(E.cpf_trabalhador AS CHAR(11)) AS cpf,
    CAST(F.cnpj AS VARCHAR(14)) AS cnpj_esocial
INTO #esocial_vinculo_trabalhista
FROM temp_CGUSC.fp.esocial_cnpj_trabalhador_ano E
INNER JOIN temp_CGUSC.fp.dados_farmacia F
    ON F.id = E.id_cnpj
CROSS APPLY (
    SELECT TRY_CONVERT(INT, E.cbo) AS cbo_int
) CBO
WHERE E.cpf_trabalhador IS NOT NULL
  AND E.dt_rescisao IS NULL
  AND CBO.cbo_int IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM #cbo_esocial_permitido X
      WHERE X.cbo = CBO.cbo_int
  );
GO
CREATE CLUSTERED INDEX ix_esocial_vinculo_trabalhista
ON #esocial_vinculo_trabalhista(cpf, cnpj_esocial);
GO

IF OBJECT_ID('db_seguro_defeso.dbo.Pescador_Requerimentos', 'U') IS NULL
BEGIN
    RAISERROR('Tabela db_seguro_defeso.dbo.Pescador_Requerimentos nao encontrada para marcar socios no Seguro Defeso.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('db_seguro_defeso.dbo.Pescador_Requerimentos', 'NumeroRequerimento') IS NULL
   OR COL_LENGTH('db_seguro_defeso.dbo.Pescador_Requerimentos', 'CPFRequerente') IS NULL
   OR COL_LENGTH('db_seguro_defeso.dbo.Pescador_Requerimentos', 'StatusRequerimento') IS NULL
   OR COL_LENGTH('db_seguro_defeso.dbo.Pescador_Requerimentos', 'SituacaoRequerimento') IS NULL
   OR COL_LENGTH('db_seguro_defeso.dbo.Pescador_Requerimentos', 'QtdParcelasPagas') IS NULL
   OR COL_LENGTH('db_seguro_defeso.dbo.Pescador_Requerimentos', 'ValorParcelasPagas') IS NULL
BEGIN
    RAISERROR('Tabela db_seguro_defeso.dbo.Pescador_Requerimentos sem colunas obrigatorias para marcar socios no Seguro Defeso.', 16, 1);
    RETURN;
END;

IF OBJECT_ID('db_seguro_defeso.dbo.Pescador_Parcelas', 'U') IS NULL
BEGIN
    RAISERROR('Tabela db_seguro_defeso.dbo.Pescador_Parcelas nao encontrada para marcar socios no Seguro Defeso.', 16, 1);
    RETURN;
END;

IF COL_LENGTH('db_seguro_defeso.dbo.Pescador_Parcelas', 'NumeroRequerimento') IS NULL
   OR COL_LENGTH('db_seguro_defeso.dbo.Pescador_Parcelas', 'SituacaoAtualParcela') IS NULL
BEGIN
    RAISERROR('Tabela db_seguro_defeso.dbo.Pescador_Parcelas sem colunas obrigatorias NumeroRequerimento/SituacaoAtualParcela.', 16, 1);
    RETURN;
END;

DROP TABLE IF EXISTS #seguro_defeso_requerimentos_base;
GO
SELECT
    R.NumeroRequerimento,
    CAST(R.CPFRequerente AS CHAR(11)) AS cpf,
    R.QtdParcelasPagas,
    R.ValorParcelasPagas
INTO #seguro_defeso_requerimentos_base
FROM db_seguro_defeso.dbo.Pescador_Requerimentos R
INNER JOIN #cpfs_vivos C
    ON C.cpf = R.CPFRequerente
WHERE R.CPFRequerente IS NOT NULL
  AND R.StatusRequerimento IN ('Habilitado', 'Notificado')
  AND R.SituacaoRequerimento IN ('Beneficiario', 'Segurado');
GO
CREATE CLUSTERED INDEX ix_seguro_defeso_requerimentos_base
ON #seguro_defeso_requerimentos_base(NumeroRequerimento, cpf);
GO
CREATE INDEX ix_seguro_defeso_requerimentos_base_cpf
ON #seguro_defeso_requerimentos_base(cpf);
GO

DROP TABLE IF EXISTS #seguro_defeso_cpfs;
GO
SELECT DISTINCT cpf
INTO #seguro_defeso_cpfs
FROM (
    SELECT B.cpf
    FROM #seguro_defeso_requerimentos_base B
    WHERE ISNULL(B.QtdParcelasPagas, 0) > 0
       OR ISNULL(B.ValorParcelasPagas, 0) > 0

    UNION

    SELECT B.cpf
    FROM #seguro_defeso_requerimentos_base B
    INNER JOIN db_seguro_defeso.dbo.Pescador_Parcelas P
        ON P.NumeroRequerimento = B.NumeroRequerimento
    WHERE P.SituacaoAtualParcela IN (
        'Parcela Paga',
        'Parcela Paga por Compensação',
        'Parcela Emitida',
        'Parcela Reemitida'
    )
) S;
GO
CREATE UNIQUE CLUSTERED INDEX ix_seguro_defeso_cpfs
ON #seguro_defeso_cpfs(cpf);
GO

GO
DROP TABLE IF EXISTS #temp_metadata_cpfs;
GO
CREATE TABLE #temp_metadata_cpfs (
    CPF CHAR(11) NOT NULL,
    nome VARCHAR(100) NULL,
    dataNascimento DATE NULL,
    is_cadunico TINYINT NOT NULL
);
GO
CREATE UNIQUE CLUSTERED INDEX ix_temp_metadata_cpfs
ON #temp_metadata_cpfs(CPF);
GO

DROP TABLE IF EXISTS #cpfs_metadata_lote;
GO
SELECT cpf
INTO #cpfs_metadata_lote
FROM #cpfs_vivos;
GO
CREATE CLUSTERED INDEX ix_cpfs_metadata_lote ON #cpfs_metadata_lote(cpf);
GO

DROP TABLE IF EXISTS #cpf_data_lote;
GO
SELECT
    C.CPF,
    MAX(CAST(C.dataNascimento AS DATE)) AS dataNascimento
INTO #cpf_data_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = L.cpf
WHERE C.CPF IS NOT NULL
GROUP BY C.CPF;
GO
CREATE CLUSTERED INDEX ix_cpf_data_lote ON #cpf_data_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadastro_lote;
GO
SELECT
    D.CPF,
    CAST(temp_CGUSC.dbo.InitCapEachWord(LEFT(MAX(CAST(C.nome AS VARCHAR(100))), 100)) AS VARCHAR(100)) AS nome,
    D.dataNascimento
INTO #cpf_cadastro_lote
FROM #cpf_data_lote D
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = D.CPF
   AND (
          CAST(C.dataNascimento AS DATE) = D.dataNascimento
       OR (C.dataNascimento IS NULL AND D.dataNascimento IS NULL)
   )
GROUP BY
    D.CPF,
    D.dataNascimento;
GO
CREATE CLUSTERED INDEX ix_cpf_cadastro_lote ON #cpf_cadastro_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadunico_lote;
GO
SELECT DISTINCT
    L.cpf AS CPF
INTO #cpf_cadunico_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CadUnico.dbo.tb_00_consolid CAD
    ON CAD.CPF_CAD_UNICO = L.cpf
WHERE CAD.CPF_CAD_UNICO IS NOT NULL;
GO
CREATE CLUSTERED INDEX ix_cpf_cadunico_lote ON #cpf_cadunico_lote(CPF);
GO

INSERT INTO #temp_metadata_cpfs (CPF, nome, dataNascimento, is_cadunico)
SELECT
    B.CPF,
    B.nome,
    B.dataNascimento,
    CASE WHEN CAD.CPF IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico
FROM #cpf_cadastro_lote B
LEFT JOIN #cpf_cadunico_lote CAD
    ON CAD.CPF = B.CPF;
GO

DROP TABLE IF EXISTS #dados_socios_esocial;
GO
SELECT DISTINCT
    CAST(soc.cpfcnpjSocio AS VARCHAR(14)) AS cpf_cnpj_socio,
    CAST(soc.cnpj AS VARCHAR(14)) AS cnpj
INTO #dados_socios_esocial
FROM temp_CGUSC.fp.lista_cnpjs lst
INNER JOIN db_CNPJ.dbo.socios soc
    ON soc.cnpj = lst.cnpj
INNER JOIN #esocial_vinculo_trabalhista ESO
    ON ESO.cpf = soc.cpfcnpjSocio
   AND ESO.cnpj_esocial <> soc.cnpj
WHERE soc.indSocio = 'PF'
  AND COALESCE(soc.dataExclusaoSociedade,
               TRY_CONVERT(DATE, NULLIF(soc.datfim, '00'), 112)) IS NULL;
GO
CREATE UNIQUE CLUSTERED INDEX ix_dados_socios_esocial
ON #dados_socios_esocial(cpf_cnpj_socio, cnpj);
GO

DROP TABLE IF EXISTS #dados_socios_seguro_defeso;
GO
SELECT DISTINCT
    CAST(soc.cpfcnpjSocio AS VARCHAR(14)) AS cpf_cnpj_socio,
    CAST(soc.cnpj AS VARCHAR(14)) AS cnpj
INTO #dados_socios_seguro_defeso
FROM temp_CGUSC.fp.lista_cnpjs lst
INNER JOIN db_CNPJ.dbo.socios soc
    ON soc.cnpj = lst.cnpj
INNER JOIN #seguro_defeso_cpfs DEF
    ON DEF.cpf = soc.cpfcnpjSocio
WHERE soc.indSocio = 'PF'
  AND COALESCE(soc.dataExclusaoSociedade,
               TRY_CONVERT(DATE, NULLIF(soc.datfim, '00'), 112)) IS NULL;
GO
CREATE UNIQUE CLUSTERED INDEX ix_dados_socios_seguro_defeso
ON #dados_socios_seguro_defeso(cpf_cnpj_socio, cnpj);
GO


--------------------------------------------------------------
-- ETAPA 3: Sócios formais das farmácias (N1)
--------------------------------------------------------------

GO
DROP TABLE IF EXISTS temp_CGUSC.fp.dados_socios_novo;
GO

SELECT DISTINCT
    soc.cpfcnpjSocio                                          AS cpf_cnpj_socio,
    soc.cnpj,
    CAST(soc.indSocio AS CHAR(2))                             AS indicador_socio,
    temp_CGUSC.dbo.InitCapEachWord(LEFT(soc.nomeSocio, 100))  AS nome_socio,
    CAST(temp_CGUSC.dbo.InitCapEachWord(ibge.no_municipio) AS VARCHAR(60)) AS municipio,
    CAST(ibge.sg_uf AS CHAR(2))                               AS uf,
    CAST(soc.dataEntradaSociedade AS DATE)                    AS data_entrada_sociedade,
    COALESCE(
        CAST(soc.dataExclusaoSociedade AS DATE),
        TRY_CONVERT(DATE, NULLIF(soc.datfim, '00'), 112)
    )                                                         AS data_exclusao_sociedade,
    CAST(soc.percentualQualificacao / 100.0 AS DECIMAL(5,2))  AS percentual_qualificacao,
    CAST(temp_CGUSC.dbo.InitCapEachWord(soc.descQualificacaoSocio) AS VARCHAR(60)) AS descricao_qualificacao,
    NULLIF(CAST(soc.CpfRepresentante AS CHAR(11)), '00000000000') AS cpf_representante,
    NULLIF(TRY_CAST(soc.IdQualificacaoRepresentante AS TINYINT), 0) AS id_qualificacao_representante,
    cobi_rep.nome                                             AS nome_representante,
    CAST(temp_CGUSC.dbo.InitCapEachWord(qua_rep.DescricaoQualificacao) AS VARCHAR(60)) AS descricao_qualificacao_representante,
    CAST(cobi.dataNascimento AS DATE)                         AS data_nascimento_socio,
    CAST(cobi_rep.dataNascimento AS DATE)                     AS data_nascimento_representante,
    CAST(GETDATE() AS SMALLDATETIME)                          AS data_processamento,
    CASE WHEN cobi.is_cadunico = 1 THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico,
    CASE WHEN ESO.cpf_cnpj_socio IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_esocial,
    CASE WHEN DEF.cpf_cnpj_socio IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_seguro_defeso,
    CASE WHEN obt.cpf IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_falecido
INTO temp_CGUSC.fp.dados_socios_novo
FROM temp_CGUSC.fp.lista_cnpjs lst
INNER JOIN db_CNPJ.dbo.socios soc ON soc.cnpj = lst.cnpj
INNER JOIN db_CNPJ.dbo.CNPJ cnpj ON cnpj.cnpj = soc.cnpj
LEFT JOIN db_CNPJ.dbo.Municipio mun ON mun.SkMunicipio = soc.CodMunicipio
LEFT JOIN temp_CGUSC.fp.dados_ibge ibge ON ibge.id_ibge7 = mun.CodIbge
LEFT JOIN #temp_metadata_cpfs cobi ON cobi.CPF = soc.cpfcnpjSocio AND soc.indSocio = 'PF'
LEFT JOIN #temp_metadata_cpfs cobi_rep ON cobi_rep.CPF = soc.CpfRepresentante AND soc.CpfRepresentante <> '00000000000'
LEFT JOIN db_CNPJ.dbo.Qualificacao AS qua_rep ON qua_rep.IdQualificacao = TRY_CAST(soc.IdQualificacaoRepresentante AS INT)
LEFT JOIN #dados_socios_esocial ESO
    ON ESO.cpf_cnpj_socio = soc.cpfcnpjSocio
   AND ESO.cnpj = soc.cnpj
LEFT JOIN #dados_socios_seguro_defeso DEF
    ON DEF.cpf_cnpj_socio = soc.cpfcnpjSocio
   AND DEF.cnpj = soc.cnpj
LEFT JOIN temp_CGUSC.fp.obito_unificada obt ON obt.cpf = soc.cpfcnpjSocio;
GO


--------------------------------------------------------------
-- ETAPA 3.1: Incluir Responsáveis de Empresas Individuais/MEI
-- (farmácias do programa sem QSA na tabela socios)
--------------------------------------------------------------

-- Tabela auxiliar: CNPJs que já têm ao menos um sócio formal
GO
DROP TABLE IF EXISTS #cnpjs_com_socios;
GO
SELECT DISTINCT cnpj INTO #cnpjs_com_socios FROM temp_CGUSC.fp.dados_socios_novo;
GO
CREATE CLUSTERED INDEX ix_cnpjs_com_socios ON #cnpjs_com_socios (cnpj);
GO

DROP TABLE IF EXISTS #responsaveis_individuais_esocial;
GO
SELECT DISTINCT
    CAST(f.cpfResponsavel AS VARCHAR(14)) AS cpf_cnpj_socio,
    CAST(f.cnpj AS VARCHAR(14)) AS cnpj
INTO #responsaveis_individuais_esocial
FROM temp_CGUSC.fp.dados_farmacia f
LEFT JOIN #cnpjs_com_socios s
    ON s.cnpj = f.cnpj
INNER JOIN #esocial_vinculo_trabalhista ESO
    ON ESO.cpf = f.cpfResponsavel
   AND ESO.cnpj_esocial <> f.cnpj
WHERE s.cnpj IS NULL
  AND f.cpfResponsavel IS NOT NULL;
GO
CREATE UNIQUE CLUSTERED INDEX ix_responsaveis_individuais_esocial
ON #responsaveis_individuais_esocial(cpf_cnpj_socio, cnpj);
GO

DROP TABLE IF EXISTS #responsaveis_individuais_seguro_defeso;
GO
SELECT DISTINCT
    CAST(f.cpfResponsavel AS VARCHAR(14)) AS cpf_cnpj_socio,
    CAST(f.cnpj AS VARCHAR(14)) AS cnpj
INTO #responsaveis_individuais_seguro_defeso
FROM temp_CGUSC.fp.dados_farmacia f
LEFT JOIN #cnpjs_com_socios s
    ON s.cnpj = f.cnpj
INNER JOIN #seguro_defeso_cpfs DEF
    ON DEF.cpf = f.cpfResponsavel
WHERE s.cnpj IS NULL
  AND f.cpfResponsavel IS NOT NULL;
GO
CREATE UNIQUE CLUSTERED INDEX ix_responsaveis_individuais_seguro_defeso
ON #responsaveis_individuais_seguro_defeso(cpf_cnpj_socio, cnpj);
GO

INSERT INTO temp_CGUSC.fp.dados_socios_novo (
    cpf_cnpj_socio, cnpj, indicador_socio, nome_socio, municipio, uf,
    data_entrada_sociedade, percentual_qualificacao, descricao_qualificacao,
    data_nascimento_socio, data_processamento, is_cadunico, is_esocial,
    is_seguro_defeso, is_falecido
)
SELECT 
    f.cpfResponsavel,
    f.cnpj,
    'PF'                                   AS indicador_socio,
    f.nome_responsavel,
    f.municipio,
    f.uf,
    f.dataSituacaoCadastral                AS data_entrada_sociedade,
    100.00                                 AS percentual_qualificacao,
    f.descricaoQualificacaoResponsavel,
    CAST(cobi.dataNascimento AS DATE)      AS data_nascimento_socio,
    CAST(GETDATE() AS SMALLDATETIME)       AS data_processamento,
    CASE WHEN cobi.is_cadunico = 1 THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico,
    CASE WHEN ESO.cpf_cnpj_socio IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_esocial,
    CASE WHEN DEF.cpf_cnpj_socio IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_seguro_defeso,
    CASE WHEN obt.cpf IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_falecido
FROM temp_CGUSC.fp.dados_farmacia f
LEFT JOIN #cnpjs_com_socios s ON s.cnpj = f.cnpj
LEFT JOIN #temp_metadata_cpfs cobi ON cobi.CPF = f.cpfResponsavel
LEFT JOIN #responsaveis_individuais_esocial ESO
    ON ESO.cpf_cnpj_socio = f.cpfResponsavel
   AND ESO.cnpj = f.cnpj
LEFT JOIN #responsaveis_individuais_seguro_defeso DEF
    ON DEF.cpf_cnpj_socio = f.cpfResponsavel
   AND DEF.cnpj = f.cnpj
LEFT JOIN temp_CGUSC.fp.obito_unificada obt ON obt.cpf = f.cpfResponsavel
WHERE s.cnpj IS NULL
  AND f.cpfResponsavel IS NOT NULL;
GO

CREATE CLUSTERED INDEX cx_sociosFP_cpf_cnpj_socio ON temp_CGUSC.fp.dados_socios_novo (cpf_cnpj_socio, cnpj);
GO
CREATE INDEX ix_sociosFP_cnpj ON temp_CGUSC.fp.dados_socios_novo (cnpj);
GO

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.fp.dados_socios_novo)
BEGIN
    THROW 50010, 'A nova tabela fp.dados_socios ficou vazia. A publicacao foi cancelada.', 1;
END;

IF COL_LENGTH('temp_CGUSC.fp.dados_socios_novo', 'is_esocial') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.dados_socios_novo', 'is_seguro_defeso') IS NULL
BEGIN
    THROW 50011, 'A nova tabela fp.dados_socios nao possui as colunas obrigatorias de alertas.', 1;
END;
GO

BEGIN TRY
    BEGIN TRANSACTION;
    DROP TABLE IF EXISTS temp_CGUSC.fp.dados_socios;
    EXEC sys.sp_rename
        N'fp.dados_socios_novo',
        N'dados_socios',
        N'OBJECT';
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

--------------------------------------------------------------
-- ETAPA 4: Expans�o N�vel 2
-- Para cada CPF do N1, mapeia:
--   (a) empresas formais (QSA): via db_CNPJ.dbo.socios
--   (b) farm�cias individuais (EI/MEI do programa): via fp.dados_farmacia
--------------------------------------------------------------

-- Lista de CPFs eleg�veis para expans�o (apenas PF do N1)
GO
DROP TABLE IF EXISTS #cpfs_n1;
GO
SELECT DISTINCT cpf_cnpj_socio
INTO #cpfs_n1
FROM temp_CGUSC.fp.dados_socios
WHERE cpf_cnpj_socio IS NOT NULL
  AND cpf_cnpj_socio <> '99999999999999';
GO
CREATE CLUSTERED INDEX ix_cpfs_n1 ON #cpfs_n1 (cpf_cnpj_socio);
GO

-- (a) V�nculos formais: empresas onde o CPF aparece no QSA
GO
DROP TABLE IF EXISTS #n2_formal;
GO
SELECT
    s.cpfcnpjSocio                                           AS cpf_cnpj_socio,
    CAST(s.cnpj AS VARCHAR(14))                              AS cnpj_empresa,
    CAST(s.indSocio AS CHAR(2))                              AS indicador_socio,
    CAST(LEFT(s.descQualificacaoSocio, 60) AS VARCHAR(60))   AS descricao_qualificacao,
    NULLIF(CAST(s.CpfRepresentante AS CHAR(11)), '00000000000') AS cpf_representante,
    CAST(s.dataEntradaSociedade AS DATE)                     AS data_entrada_sociedade,
    COALESCE(
        CAST(s.dataExclusaoSociedade AS DATE),
        TRY_CONVERT(DATE, NULLIF(s.datfim, '00'), 112)
    )                                                        AS data_exclusao_sociedade
INTO #n2_formal
FROM #cpfs_n1 e
INNER JOIN db_CNPJ.dbo.socios s ON s.cpfcnpjSocio = e.cpf_cnpj_socio;
GO
CREATE CLUSTERED INDEX ix_n2_formal ON #n2_formal (cpf_cnpj_socio, cnpj_empresa);
GO

-- (b) V�nculos individuais: farm�cias EI/MEI do programa onde o CPF � respons�vel
--     (empresas sem QSA na tabela socios)
GO
DROP TABLE IF EXISTS #n2_individual;
GO
SELECT
    f.cpfResponsavel                                         AS cpf_cnpj_socio,
    CAST(f.cnpj AS VARCHAR(14))                              AS cnpj_empresa,
    CAST('PF' AS CHAR(2))                                    AS indicador_socio,
    CAST('TITULAR PESSOA FISICA' AS VARCHAR(60))             AS descricao_qualificacao,
    CAST(NULL AS CHAR(11))                                   AS cpf_representante,
    CAST(f.dataSituacaoCadastral AS DATE)                    AS data_entrada_sociedade,
    CAST(NULL AS DATE)                                       AS data_exclusao_sociedade
INTO #n2_individual
FROM #cpfs_n1 e
INNER JOIN temp_CGUSC.fp.dados_farmacia f ON f.cpfResponsavel = e.cpf_cnpj_socio
WHERE NOT EXISTS (SELECT 1 FROM db_CNPJ.dbo.socios s WHERE s.cnpj = f.cnpj);
GO
CREATE CLUSTERED INDEX ix_n2_individual ON #n2_individual (cpf_cnpj_socio, cnpj_empresa);
GO

-- Consolida��o deduplicada N2 (formal + individual)
GO
DROP TABLE IF EXISTS #teia_fonte_nivel2_raw;
GO
SELECT
    raw.cpf_cnpj_socio,
    raw.cnpj_empresa,
    raw.indicador_socio,
    raw.descricao_qualificacao,
    raw.cpf_representante,
    cobi_rep.nome                                            AS nome_representante,
    raw.data_entrada_sociedade,
    raw.data_exclusao_sociedade
INTO #teia_fonte_nivel2_raw
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY cpf_cnpj_socio, cnpj_empresa
        ORDER BY
            CASE WHEN data_exclusao_sociedade IS NULL THEN 0 ELSE 1 END,
            data_entrada_sociedade DESC
    ) AS rn
    FROM (
        SELECT cpf_cnpj_socio, cnpj_empresa, indicador_socio, descricao_qualificacao, cpf_representante, data_entrada_sociedade, data_exclusao_sociedade FROM #n2_formal
        UNION ALL
        SELECT cpf_cnpj_socio, cnpj_empresa, indicador_socio, descricao_qualificacao, cpf_representante, data_entrada_sociedade, data_exclusao_sociedade FROM #n2_individual
    ) u
) raw
LEFT JOIN #temp_metadata_cpfs cobi_rep ON cobi_rep.CPF = raw.cpf_representante
WHERE raw.rn = 1;
GO
CREATE CLUSTERED INDEX ix_t2_raw ON #teia_fonte_nivel2_raw (cpf_cnpj_socio, cnpj_empresa);
GO
CREATE INDEX ix_t2_raw_cnpj ON #teia_fonte_nivel2_raw (cnpj_empresa);
GO

-- Enriquecer dicion�rio com representantes do N2
DROP TABLE IF EXISTS #cpfs_metadata_lote;
GO
SELECT DISTINCT
    raw.cpf_representante AS cpf
INTO #cpfs_metadata_lote
FROM #teia_fonte_nivel2_raw raw
WHERE raw.cpf_representante IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM #temp_metadata_cpfs M
      WHERE M.CPF = raw.cpf_representante
  );
GO
CREATE CLUSTERED INDEX ix_cpfs_metadata_lote ON #cpfs_metadata_lote(cpf);
GO

DROP TABLE IF EXISTS #cpf_data_lote;
GO
SELECT
    C.CPF,
    MAX(CAST(C.dataNascimento AS DATE)) AS dataNascimento
INTO #cpf_data_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = L.cpf
WHERE C.CPF IS NOT NULL
GROUP BY C.CPF;
GO
CREATE CLUSTERED INDEX ix_cpf_data_lote ON #cpf_data_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadastro_lote;
GO
SELECT
    D.CPF,
    CAST(temp_CGUSC.dbo.InitCapEachWord(LEFT(MAX(CAST(C.nome AS VARCHAR(100))), 100)) AS VARCHAR(100)) AS nome,
    D.dataNascimento
INTO #cpf_cadastro_lote
FROM #cpf_data_lote D
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = D.CPF
   AND (
          CAST(C.dataNascimento AS DATE) = D.dataNascimento
       OR (C.dataNascimento IS NULL AND D.dataNascimento IS NULL)
   )
GROUP BY
    D.CPF,
    D.dataNascimento;
GO
CREATE CLUSTERED INDEX ix_cpf_cadastro_lote ON #cpf_cadastro_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadunico_lote;
GO
SELECT DISTINCT
    L.cpf AS CPF
INTO #cpf_cadunico_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CadUnico.dbo.tb_00_consolid CAD
    ON CAD.CPF_CAD_UNICO = L.cpf
WHERE CAD.CPF_CAD_UNICO IS NOT NULL;
GO
CREATE CLUSTERED INDEX ix_cpf_cadunico_lote ON #cpf_cadunico_lote(CPF);
GO

INSERT INTO #temp_metadata_cpfs (CPF, nome, dataNascimento, is_cadunico)
SELECT
    B.CPF,
    B.nome,
    B.dataNascimento,
    CASE WHEN CAD.CPF IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico
FROM #cpf_cadastro_lote B
LEFT JOIN #cpf_cadunico_lote CAD
    ON CAD.CPF = B.CPF;
GO

-- Dicion�rio de metadados das empresas do N2
GO
DROP TABLE IF EXISTS #universo_cnpjs;
GO
SELECT DISTINCT cnpj_empresa INTO #universo_cnpjs FROM #teia_fonte_nivel2_raw;
GO
CREATE CLUSTERED INDEX ix_universo_cnpjs ON #universo_cnpjs (cnpj_empresa);
GO

GO
DROP TABLE IF EXISTS #metadata_empresas;
GO
SELECT DISTINCT
    u.cnpj_empresa,
    CAST(LEFT(c.RazaoSocial, 100) AS VARCHAR(100))           AS razao_social,
    CAST(LEFT(c.NomeFantasia, 100) AS VARCHAR(100))          AS nome_fantasia,
    TRY_CAST(c.CnaeFiscal AS INT)                            AS id_cnae_principal,
    CAST(sit.ds_situacao_cnpj AS VARCHAR(60))                AS situacao_rf,
    CAST(ibge.no_municipio AS VARCHAR(60))                   AS municipio,
    CAST(ibge.sg_uf AS CHAR(2))                              AS uf
INTO #metadata_empresas
FROM #universo_cnpjs u
INNER JOIN db_CNPJ.dbo.CNPJ c ON c.cnpj = u.cnpj_empresa
LEFT JOIN db_CNPJ.dbo.dime_situacao_cadastral_cnpj sit ON sit.cd_situacao_cnpj = c.SituacaoCadastral
LEFT JOIN db_CNPJ.dbo.Municipio mun ON mun.SkMunicipio = c.CodMunicipio
LEFT JOIN temp_CGUSC.fp.dados_ibge ibge ON ibge.id_ibge7 = mun.CodIbge;
GO
CREATE CLUSTERED INDEX ix_meta_cnpj ON #metadata_empresas (cnpj_empresa);
GO

-- Teia N�vel 2 Final
GO
DROP TABLE IF EXISTS temp_CGUSC.fp.teia_fonte_nivel2_novo;
GO
SELECT DISTINCT
    raw.cpf_cnpj_socio,
    raw.cnpj_empresa,
    m.razao_social,
    m.nome_fantasia,
    m.id_cnae_principal,
    raw.indicador_socio,
    raw.descricao_qualificacao,
    raw.cpf_representante,
    raw.nome_representante,
    raw.data_entrada_sociedade,
    raw.data_exclusao_sociedade,
    m.situacao_rf,
    m.municipio,
    m.uf,
    CASE WHEN lst.cnpj IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_farmacia_fp,
    CASE WHEN cobi.is_cadunico = 1 THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico,
    CASE WHEN obt.cpf IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_falecido
INTO temp_CGUSC.fp.teia_fonte_nivel2_novo
FROM #teia_fonte_nivel2_raw raw
INNER JOIN #metadata_empresas m ON m.cnpj_empresa = raw.cnpj_empresa
LEFT JOIN temp_CGUSC.fp.lista_cnpjs lst ON lst.cnpj = raw.cnpj_empresa
LEFT JOIN #temp_metadata_cpfs cobi ON cobi.CPF = raw.cpf_cnpj_socio
LEFT JOIN temp_CGUSC.fp.obito_unificada obt ON obt.cpf = raw.cpf_cnpj_socio;
GO
CREATE CLUSTERED INDEX cx_t2_final ON temp_CGUSC.fp.teia_fonte_nivel2_novo (cpf_cnpj_socio, cnpj_empresa);
GO

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.fp.teia_fonte_nivel2_novo)
BEGIN
    THROW 50012, 'A nova tabela fp.teia_fonte_nivel2 ficou vazia. A publicacao foi cancelada.', 1;
END;
GO

BEGIN TRY
    BEGIN TRANSACTION;
    DROP TABLE IF EXISTS temp_CGUSC.fp.teia_fonte_nivel2;
    EXEC sys.sp_rename
        N'fp.teia_fonte_nivel2_novo',
        N'teia_fonte_nivel2',
        N'OBJECT';
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO


--------------------------------------------------------------
-- ETAPA 5: Expans�o N�vel 3
-- S�cios/titulares das empresas que apareceram no N2
-- Inclui EI/MEI via fp.dados_farmacia
--------------------------------------------------------------

-- Enriquecer dicion�rio com CPFs do N3
GO
DROP TABLE IF EXISTS #novos_cpfs_n3;
GO

SELECT DISTINCT cpf
INTO #novos_cpfs_n3
FROM (
    SELECT DISTINCT s.cpfcnpjSocio AS cpf
    FROM (SELECT DISTINCT cnpj_empresa FROM temp_CGUSC.fp.teia_fonte_nivel2) n2
    INNER JOIN db_CNPJ.dbo.socios s ON s.cnpj = n2.cnpj_empresa
    WHERE s.indSocio = 'PF' AND s.cpfcnpjSocio <> '99999999999999'
    UNION
    SELECT DISTINCT s.CpfRepresentante
    FROM (SELECT DISTINCT cnpj_empresa FROM temp_CGUSC.fp.teia_fonte_nivel2) n2
    INNER JOIN db_CNPJ.dbo.socios s ON s.cnpj = n2.cnpj_empresa
    WHERE s.CpfRepresentante <> '00000000000' AND s.CpfRepresentante IS NOT NULL
    UNION
    SELECT DISTINCT f.cpfResponsavel
    FROM (SELECT DISTINCT cnpj_empresa FROM temp_CGUSC.fp.teia_fonte_nivel2) n2
    INNER JOIN temp_CGUSC.fp.dados_farmacia f ON f.cnpj = n2.cnpj_empresa
    WHERE f.cpfResponsavel IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM db_CNPJ.dbo.socios s WHERE s.cnpj = f.cnpj)
) novos
WHERE cpf IS NOT NULL;
GO

CREATE CLUSTERED INDEX ix_novos_cpfs_n3 ON #novos_cpfs_n3 (cpf);
GO

-- Amplia o Seguro Defeso para os CPFs descobertos no N3.
-- O primeiro lote cobre apenas socios/responsaveis diretos das farmacias (N1).
DROP TABLE IF EXISTS #seguro_defeso_requerimentos_n3;
GO
SELECT
    R.NumeroRequerimento,
    CAST(R.CPFRequerente AS CHAR(11)) AS cpf,
    R.QtdParcelasPagas,
    R.ValorParcelasPagas
INTO #seguro_defeso_requerimentos_n3
FROM db_seguro_defeso.dbo.Pescador_Requerimentos R
INNER JOIN #novos_cpfs_n3 N
    ON N.cpf = R.CPFRequerente
WHERE R.CPFRequerente IS NOT NULL
  AND R.StatusRequerimento IN ('Habilitado', 'Notificado')
  AND R.SituacaoRequerimento IN ('Beneficiario', 'Segurado')
  AND NOT EXISTS (
      SELECT 1
      FROM #seguro_defeso_cpfs D
      WHERE D.cpf = R.CPFRequerente
  );
GO
CREATE CLUSTERED INDEX ix_seguro_defeso_requerimentos_n3
ON #seguro_defeso_requerimentos_n3(NumeroRequerimento, cpf);
GO

INSERT INTO #seguro_defeso_cpfs (cpf)
SELECT DISTINCT S.cpf
FROM (
    SELECT B.cpf
    FROM #seguro_defeso_requerimentos_n3 B
    WHERE ISNULL(B.QtdParcelasPagas, 0) > 0
       OR ISNULL(B.ValorParcelasPagas, 0) > 0

    UNION

    SELECT B.cpf
    FROM #seguro_defeso_requerimentos_n3 B
    INNER JOIN db_seguro_defeso.dbo.Pescador_Parcelas P
        ON P.NumeroRequerimento = B.NumeroRequerimento
    WHERE P.SituacaoAtualParcela IN (
        'Parcela Paga',
        'Parcela Paga por Compensação',
        'Parcela Emitida',
        'Parcela Reemitida'
    )
) S
WHERE NOT EXISTS (
    SELECT 1
    FROM #seguro_defeso_cpfs D
    WHERE D.cpf = S.cpf
);
GO

DROP TABLE IF EXISTS #cpfs_metadata_lote;
GO
SELECT DISTINCT
    novos.cpf
INTO #cpfs_metadata_lote
FROM #novos_cpfs_n3 novos
WHERE NOT EXISTS (
    SELECT 1
    FROM #temp_metadata_cpfs M
    WHERE M.CPF = novos.cpf
);
GO
CREATE CLUSTERED INDEX ix_cpfs_metadata_lote ON #cpfs_metadata_lote(cpf);
GO

DROP TABLE IF EXISTS #cpf_data_lote;
GO
SELECT
    C.CPF,
    MAX(CAST(C.dataNascimento AS DATE)) AS dataNascimento
INTO #cpf_data_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = L.cpf
WHERE C.CPF IS NOT NULL
GROUP BY C.CPF;
GO
CREATE CLUSTERED INDEX ix_cpf_data_lote ON #cpf_data_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadastro_lote;
GO
SELECT
    D.CPF,
    CAST(temp_CGUSC.dbo.InitCapEachWord(LEFT(MAX(CAST(C.nome AS VARCHAR(100))), 100)) AS VARCHAR(100)) AS nome,
    D.dataNascimento
INTO #cpf_cadastro_lote
FROM #cpf_data_lote D
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = D.CPF
   AND (
          CAST(C.dataNascimento AS DATE) = D.dataNascimento
       OR (C.dataNascimento IS NULL AND D.dataNascimento IS NULL)
   )
GROUP BY
    D.CPF,
    D.dataNascimento;
GO
CREATE CLUSTERED INDEX ix_cpf_cadastro_lote ON #cpf_cadastro_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadunico_lote;
GO
SELECT DISTINCT
    L.cpf AS CPF
INTO #cpf_cadunico_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CadUnico.dbo.tb_00_consolid CAD
    ON CAD.CPF_CAD_UNICO = L.cpf
WHERE CAD.CPF_CAD_UNICO IS NOT NULL;
GO
CREATE CLUSTERED INDEX ix_cpf_cadunico_lote ON #cpf_cadunico_lote(CPF);
GO

INSERT INTO #temp_metadata_cpfs (CPF, nome, dataNascimento, is_cadunico)
SELECT
    B.CPF,
    B.nome,
    B.dataNascimento,
    CASE WHEN CAD.CPF IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico
FROM #cpf_cadastro_lote B
LEFT JOIN #cpf_cadunico_lote CAD
    ON CAD.CPF = B.CPF;
GO

-- (a) S�cios formais das empresas do N2
GO
DROP TABLE IF EXISTS #n3_formal;
GO
SELECT
    CAST(s.cnpj AS VARCHAR(14))                              AS cnpj_empresa,
    CAST(s.cpfcnpjSocio AS VARCHAR(14))                      AS cpf_cnpj_socio,
    CAST(s.indSocio AS CHAR(2))                              AS indicador_socio,
    CAST(LEFT(s.descQualificacaoSocio, 50) AS VARCHAR(50))   AS descricao_qualificacao,
    NULLIF(CAST(s.CpfRepresentante AS CHAR(11)), '00000000000') AS cpf_representante,
    CAST(s.dataEntradaSociedade AS DATE)                     AS data_entrada_sociedade,
    COALESCE(
        CAST(s.dataExclusaoSociedade AS DATE),
        TRY_CONVERT(DATE, NULLIF(s.datfim, '00'), 112)
    )                                                        AS data_exclusao_sociedade,
    s.CodMunicipio
INTO #n3_formal
FROM (SELECT DISTINCT cnpj_empresa FROM temp_CGUSC.fp.teia_fonte_nivel2) n2
INNER JOIN db_CNPJ.dbo.socios s ON s.cnpj = n2.cnpj_empresa
WHERE s.cpfcnpjSocio <> '99999999999999';
GO
CREATE CLUSTERED INDEX ix_n3_formal ON #n3_formal (cnpj_empresa, cpf_cnpj_socio);
GO

-- (b) Respons�veis de EI/MEI do programa que est�o no N2 (sem QSA)
GO
DROP TABLE IF EXISTS #n3_individual;
GO
SELECT
    CAST(f.cnpj AS VARCHAR(14))                              AS cnpj_empresa,
    CAST(f.cpfResponsavel AS VARCHAR(14))                    AS cpf_cnpj_socio,
    CAST('PF' AS CHAR(2))                                    AS indicador_socio,
    CAST('TITULAR PESSOA FISICA' AS VARCHAR(50))             AS descricao_qualificacao,
    CAST(NULL AS CHAR(11))                                   AS cpf_representante,
    CAST(f.dataSituacaoCadastral AS DATE)                    AS data_entrada_sociedade,
    CAST(NULL AS DATE)                                       AS data_exclusao_sociedade,
    CAST(NULL AS INT)                                        AS CodMunicipio,
    CAST(f.municipio AS VARCHAR(60))                         AS municipio_direto,
    CAST(f.uf AS CHAR(2))                                    AS uf_direto
INTO #n3_individual
FROM (SELECT DISTINCT cnpj_empresa FROM temp_CGUSC.fp.teia_fonte_nivel2) n2
INNER JOIN temp_CGUSC.fp.dados_farmacia f ON f.cnpj = n2.cnpj_empresa
WHERE f.cpfResponsavel IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_CNPJ.dbo.socios s WHERE s.cnpj = f.cnpj);
GO
CREATE CLUSTERED INDEX ix_n3_individual ON #n3_individual (cnpj_empresa, cpf_cnpj_socio);
GO

-- Consolida��o deduplicada N3
GO
DROP TABLE IF EXISTS #teia_fonte_nivel3_raw;
GO
SELECT
    raw.cnpj_empresa, raw.cpf_cnpj_socio, raw.indicador_socio,
    raw.descricao_qualificacao, raw.cpf_representante,
    raw.data_entrada_sociedade, raw.data_exclusao_sociedade, raw.CodMunicipio,
    raw.municipio_direto, raw.uf_direto
INTO #teia_fonte_nivel3_raw
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY cnpj_empresa, cpf_cnpj_socio
        ORDER BY
            CASE WHEN data_exclusao_sociedade IS NULL THEN 0 ELSE 1 END,
            data_entrada_sociedade DESC
    ) AS rn
    FROM (
        SELECT cnpj_empresa, cpf_cnpj_socio, indicador_socio, descricao_qualificacao, cpf_representante, data_entrada_sociedade, data_exclusao_sociedade, CodMunicipio, CAST(NULL AS VARCHAR(60)) AS municipio_direto, CAST(NULL AS CHAR(2)) AS uf_direto FROM #n3_formal
        UNION ALL
        SELECT cnpj_empresa, cpf_cnpj_socio, indicador_socio, descricao_qualificacao, cpf_representante, data_entrada_sociedade, data_exclusao_sociedade, CodMunicipio, municipio_direto, uf_direto FROM #n3_individual
    ) u
) raw
WHERE raw.rn = 1;
GO
CREATE CLUSTERED INDEX ix_t3_raw ON #teia_fonte_nivel3_raw (cnpj_empresa, cpf_cnpj_socio);
GO

DROP TABLE IF EXISTS #teia_nivel3_esocial;
GO
SELECT DISTINCT
    raw.cpf_cnpj_socio,
    raw.cnpj_empresa
INTO #teia_nivel3_esocial
FROM #teia_fonte_nivel3_raw raw
INNER JOIN #esocial_vinculo_trabalhista ESO
    ON ESO.cpf = raw.cpf_cnpj_socio
   AND ESO.cnpj_esocial <> raw.cnpj_empresa
WHERE raw.indicador_socio = 'PF'
  AND raw.data_exclusao_sociedade IS NULL;
GO
CREATE UNIQUE CLUSTERED INDEX ix_teia_nivel3_esocial
ON #teia_nivel3_esocial(cpf_cnpj_socio, cnpj_empresa);
GO

DROP TABLE IF EXISTS #teia_nivel3_seguro_defeso;
GO
SELECT DISTINCT
    raw.cpf_cnpj_socio,
    raw.cnpj_empresa
INTO #teia_nivel3_seguro_defeso
FROM #teia_fonte_nivel3_raw raw
INNER JOIN #seguro_defeso_cpfs DEF
    ON DEF.cpf = raw.cpf_cnpj_socio
WHERE raw.indicador_socio = 'PF'
  AND raw.data_exclusao_sociedade IS NULL;
GO
CREATE UNIQUE CLUSTERED INDEX ix_teia_nivel3_seguro_defeso
ON #teia_nivel3_seguro_defeso(cpf_cnpj_socio, cnpj_empresa);
GO

-- Teia N�vel 3 Final
GO
DROP TABLE IF EXISTS temp_CGUSC.fp.teia_fonte_nivel3_novo;
GO
SELECT
    raw.cnpj_empresa,
    raw.cpf_cnpj_socio,
    COALESCE(cobi.nome, CAST(LEFT(pj_socio.RazaoSocial, 100) AS VARCHAR(100))) AS nome_socio,
    raw.indicador_socio,
    raw.descricao_qualificacao,
    raw.cpf_representante,
    cobi_rep.nome                                            AS nome_representante,
    raw.data_entrada_sociedade,
    raw.data_exclusao_sociedade,
    COALESCE(CAST(ibge.no_municipio AS VARCHAR(60)), raw.municipio_direto) AS municipio,
    COALESCE(CAST(ibge.sg_uf AS CHAR(2)), raw.uf_direto)                  AS uf,
    CASE WHEN cobi.is_cadunico = 1 THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico,
    CASE WHEN ESO.cpf_cnpj_socio IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_esocial,
    CASE WHEN DEF.cpf_cnpj_socio IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_seguro_defeso,
    CASE WHEN obt.cpf IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_falecido
INTO temp_CGUSC.fp.teia_fonte_nivel3_novo
FROM #teia_fonte_nivel3_raw raw
LEFT JOIN #temp_metadata_cpfs cobi ON cobi.CPF = raw.cpf_cnpj_socio AND raw.indicador_socio = 'PF'
LEFT JOIN db_CNPJ.dbo.CNPJ pj_socio ON pj_socio.cnpj = raw.cpf_cnpj_socio AND raw.indicador_socio = 'PJ'
LEFT JOIN #temp_metadata_cpfs cobi_rep ON cobi_rep.CPF = raw.cpf_representante
LEFT JOIN db_CNPJ.dbo.Municipio mun ON mun.SkMunicipio = raw.CodMunicipio
LEFT JOIN temp_CGUSC.fp.dados_ibge ibge ON ibge.id_ibge7 = mun.CodIbge
LEFT JOIN #teia_nivel3_esocial ESO
    ON ESO.cpf_cnpj_socio = raw.cpf_cnpj_socio
   AND ESO.cnpj_empresa = raw.cnpj_empresa
LEFT JOIN #teia_nivel3_seguro_defeso DEF
    ON DEF.cpf_cnpj_socio = raw.cpf_cnpj_socio
   AND DEF.cnpj_empresa = raw.cnpj_empresa
LEFT JOIN temp_CGUSC.fp.obito_unificada obt ON obt.cpf = raw.cpf_cnpj_socio;
GO
CREATE CLUSTERED INDEX cx_t3_final ON temp_CGUSC.fp.teia_fonte_nivel3_novo (cnpj_empresa, cpf_cnpj_socio);
GO

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.fp.teia_fonte_nivel3_novo)
BEGIN
    THROW 50013, 'A nova tabela fp.teia_fonte_nivel3 ficou vazia. A publicacao foi cancelada.', 1;
END;

IF COL_LENGTH('temp_CGUSC.fp.teia_fonte_nivel3_novo', 'is_esocial') IS NULL
   OR COL_LENGTH('temp_CGUSC.fp.teia_fonte_nivel3_novo', 'is_seguro_defeso') IS NULL
BEGIN
    THROW 50014, 'A nova tabela fp.teia_fonte_nivel3 nao possui as colunas obrigatorias de alertas.', 1;
END;
GO

BEGIN TRY
    BEGIN TRANSACTION;
    DROP TABLE IF EXISTS temp_CGUSC.fp.teia_fonte_nivel3;
    EXEC sys.sp_rename
        N'fp.teia_fonte_nivel3_novo',
        N'teia_fonte_nivel3',
        N'OBJECT';
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO


--------------------------------------------------------------
-- ETAPA 6: Expans�o N�vel 4
-- Outras empresas dos s�cios/titulares do N3
-- Inclui EI/MEI via fp.dados_farmacia
--------------------------------------------------------------

-- Enriquecer dicion�rio com representantes do N4
DROP TABLE IF EXISTS #cpfs_metadata_lote;
GO
SELECT DISTINCT
    s.CpfRepresentante AS cpf
INTO #cpfs_metadata_lote
FROM (
    SELECT DISTINCT cpf_cnpj_socio
    FROM temp_CGUSC.fp.teia_fonte_nivel3
    WHERE cpf_cnpj_socio IS NOT NULL
      AND cpf_cnpj_socio <> '99999999999999'
) n3
INNER JOIN db_CNPJ.dbo.socios s
    ON s.cpfcnpjSocio = n3.cpf_cnpj_socio
WHERE s.CpfRepresentante <> '00000000000'
  AND s.CpfRepresentante IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM #temp_metadata_cpfs M
      WHERE M.CPF = s.CpfRepresentante
  );
GO
CREATE CLUSTERED INDEX ix_cpfs_metadata_lote ON #cpfs_metadata_lote(cpf);
GO

DROP TABLE IF EXISTS #cpf_data_lote;
GO
SELECT
    C.CPF,
    MAX(CAST(C.dataNascimento AS DATE)) AS dataNascimento
INTO #cpf_data_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = L.cpf
WHERE C.CPF IS NOT NULL
GROUP BY C.CPF;
GO
CREATE CLUSTERED INDEX ix_cpf_data_lote ON #cpf_data_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadastro_lote;
GO
SELECT
    D.CPF,
    CAST(temp_CGUSC.dbo.InitCapEachWord(LEFT(MAX(CAST(C.nome AS VARCHAR(100))), 100)) AS VARCHAR(100)) AS nome,
    D.dataNascimento
INTO #cpf_cadastro_lote
FROM #cpf_data_lote D
INNER JOIN db_CPF.dbo.CPF C
    ON C.CPF = D.CPF
   AND (
          CAST(C.dataNascimento AS DATE) = D.dataNascimento
       OR (C.dataNascimento IS NULL AND D.dataNascimento IS NULL)
   )
GROUP BY
    D.CPF,
    D.dataNascimento;
GO
CREATE CLUSTERED INDEX ix_cpf_cadastro_lote ON #cpf_cadastro_lote(CPF);
GO

DROP TABLE IF EXISTS #cpf_cadunico_lote;
GO
SELECT DISTINCT
    L.cpf AS CPF
INTO #cpf_cadunico_lote
FROM #cpfs_metadata_lote L
INNER JOIN db_CadUnico.dbo.tb_00_consolid CAD
    ON CAD.CPF_CAD_UNICO = L.cpf
WHERE CAD.CPF_CAD_UNICO IS NOT NULL;
GO
CREATE CLUSTERED INDEX ix_cpf_cadunico_lote ON #cpf_cadunico_lote(CPF);
GO

INSERT INTO #temp_metadata_cpfs (CPF, nome, dataNascimento, is_cadunico)
SELECT
    B.CPF,
    B.nome,
    B.dataNascimento,
    CASE WHEN CAD.CPF IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico
FROM #cpf_cadastro_lote B
LEFT JOIN #cpf_cadunico_lote CAD
    ON CAD.CPF = B.CPF;
GO

-- (a) V�nculos formais do N4
GO
DROP TABLE IF EXISTS #n4_formal;
GO
SELECT
    s.cpfcnpjSocio                                           AS cpf_cnpj_socio,
    CAST(s.cnpj AS VARCHAR(14))                              AS cnpj_empresa,
    CAST(s.indSocio AS CHAR(2))                              AS indicador_socio,
    CAST(LEFT(s.descQualificacaoSocio, 60) AS VARCHAR(60))   AS descricao_qualificacao,
    NULLIF(CAST(s.CpfRepresentante AS CHAR(11)), '00000000000') AS cpf_representante,
    CAST(s.dataEntradaSociedade AS DATE)                     AS data_entrada_sociedade,
    COALESCE(
        CAST(s.dataExclusaoSociedade AS DATE),
        TRY_CONVERT(DATE, NULLIF(s.datfim, '00'), 112)
    )                                                        AS data_exclusao_sociedade
INTO #n4_formal
FROM (SELECT DISTINCT cpf_cnpj_socio FROM temp_CGUSC.fp.teia_fonte_nivel3 WHERE cpf_cnpj_socio IS NOT NULL AND cpf_cnpj_socio <> '99999999999999') n3
INNER JOIN db_CNPJ.dbo.socios s ON s.cpfcnpjSocio = n3.cpf_cnpj_socio;
GO
CREATE CLUSTERED INDEX ix_n4_formal ON #n4_formal (cpf_cnpj_socio, cnpj_empresa);
GO

-- (b) V�nculos individuais do N4: farm�cias EI onde CPFs do N3 s�o respons�veis
GO
DROP TABLE IF EXISTS #n4_individual;
GO
SELECT
    f.cpfResponsavel                                         AS cpf_cnpj_socio,
    CAST(f.cnpj AS VARCHAR(14))                              AS cnpj_empresa,
    CAST('PF' AS CHAR(2))                                    AS indicador_socio,
    CAST('TITULAR PESSOA FISICA' AS VARCHAR(60))             AS descricao_qualificacao,
    CAST(NULL AS CHAR(11))                                   AS cpf_representante,
    CAST(f.dataSituacaoCadastral AS DATE)                    AS data_entrada_sociedade,
    CAST(NULL AS DATE)                                       AS data_exclusao_sociedade
INTO #n4_individual
FROM (SELECT DISTINCT cpf_cnpj_socio FROM temp_CGUSC.fp.teia_fonte_nivel3 WHERE cpf_cnpj_socio IS NOT NULL AND cpf_cnpj_socio <> '99999999999999') n3
INNER JOIN temp_CGUSC.fp.dados_farmacia f ON f.cpfResponsavel = n3.cpf_cnpj_socio
WHERE NOT EXISTS (SELECT 1 FROM db_CNPJ.dbo.socios s WHERE s.cnpj = f.cnpj);
GO
CREATE CLUSTERED INDEX ix_n4_individual ON #n4_individual (cpf_cnpj_socio, cnpj_empresa);
GO

-- Consolida��o deduplicada N4
GO
DROP TABLE IF EXISTS #teia_fonte_nivel4_raw;
GO
SELECT
    raw.cpf_cnpj_socio, raw.cnpj_empresa, raw.indicador_socio,
    raw.descricao_qualificacao, raw.cpf_representante,
    cobi_rep.nome                                            AS nome_representante,
    raw.data_entrada_sociedade, raw.data_exclusao_sociedade
INTO #teia_fonte_nivel4_raw
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY cpf_cnpj_socio, cnpj_empresa
        ORDER BY
            CASE WHEN data_exclusao_sociedade IS NULL THEN 0 ELSE 1 END,
            data_entrada_sociedade DESC
    ) AS rn
    FROM (
        SELECT cpf_cnpj_socio, cnpj_empresa, indicador_socio, descricao_qualificacao, cpf_representante, data_entrada_sociedade, data_exclusao_sociedade FROM #n4_formal
        UNION ALL
        SELECT cpf_cnpj_socio, cnpj_empresa, indicador_socio, descricao_qualificacao, cpf_representante, data_entrada_sociedade, data_exclusao_sociedade FROM #n4_individual
    ) u
) raw
LEFT JOIN #temp_metadata_cpfs cobi_rep ON cobi_rep.CPF = raw.cpf_representante
WHERE raw.rn = 1;
GO
CREATE CLUSTERED INDEX ix_t4_raw ON #teia_fonte_nivel4_raw (cpf_cnpj_socio, cnpj_empresa);
GO

-- Enriquecer metadados das NOVAS empresas do N4
GO
DROP TABLE IF EXISTS #universo_n4;
GO
SELECT DISTINCT cnpj_empresa INTO #universo_n4 FROM #teia_fonte_nivel4_raw;
GO

INSERT INTO #metadata_empresas (cnpj_empresa, razao_social, nome_fantasia, id_cnae_principal, situacao_rf, municipio, uf)
SELECT DISTINCT
    u.cnpj_empresa,
    CAST(LEFT(c.RazaoSocial, 100) AS VARCHAR(100)),
    CAST(LEFT(c.NomeFantasia, 100) AS VARCHAR(100)),
    TRY_CAST(c.CnaeFiscal AS INT),
    CAST(sit.ds_situacao_cnpj AS VARCHAR(60)),
    CAST(ibge.no_municipio AS VARCHAR(60)),
    CAST(ibge.sg_uf AS CHAR(2))
FROM #universo_n4 u
INNER JOIN db_CNPJ.dbo.CNPJ c ON c.cnpj = u.cnpj_empresa
LEFT JOIN db_CNPJ.dbo.dime_situacao_cadastral_cnpj sit ON sit.cd_situacao_cnpj = c.SituacaoCadastral
LEFT JOIN db_CNPJ.dbo.Municipio mun ON mun.SkMunicipio = c.CodMunicipio
LEFT JOIN temp_CGUSC.fp.dados_ibge ibge ON ibge.id_ibge7 = mun.CodIbge
WHERE NOT EXISTS (SELECT 1 FROM #metadata_empresas m WHERE m.cnpj_empresa = u.cnpj_empresa);
GO

-- Teia N�vel 4 Final
GO
DROP TABLE IF EXISTS temp_CGUSC.fp.teia_fonte_nivel4_novo;
GO
SELECT DISTINCT
    raw.cpf_cnpj_socio,
    raw.cnpj_empresa,
    m.razao_social,
    m.nome_fantasia,
    m.id_cnae_principal,
    raw.indicador_socio,
    raw.descricao_qualificacao,
    raw.cpf_representante,
    raw.nome_representante,
    raw.data_entrada_sociedade,
    raw.data_exclusao_sociedade,
    m.situacao_rf,
    m.municipio,
    m.uf,
    CASE WHEN lst.cnpj IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_farmacia_fp,
    CASE WHEN cobi.is_cadunico = 1 THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_cadunico,
    CASE WHEN obt.cpf IS NOT NULL THEN CAST(1 AS TINYINT) ELSE CAST(0 AS TINYINT) END AS is_falecido
INTO temp_CGUSC.fp.teia_fonte_nivel4_novo
FROM #teia_fonte_nivel4_raw raw
INNER JOIN #metadata_empresas m ON m.cnpj_empresa = raw.cnpj_empresa
LEFT JOIN temp_CGUSC.fp.lista_cnpjs lst ON lst.cnpj = raw.cnpj_empresa
LEFT JOIN #temp_metadata_cpfs cobi ON cobi.CPF = raw.cpf_cnpj_socio
LEFT JOIN temp_CGUSC.fp.obito_unificada obt ON obt.cpf = raw.cpf_cnpj_socio;
GO
CREATE CLUSTERED INDEX cx_t4_final ON temp_CGUSC.fp.teia_fonte_nivel4_novo (cpf_cnpj_socio, cnpj_empresa);
GO

IF NOT EXISTS (SELECT 1 FROM temp_CGUSC.fp.teia_fonte_nivel4_novo)
BEGIN
    THROW 50015, 'A nova tabela fp.teia_fonte_nivel4 ficou vazia. A publicacao foi cancelada.', 1;
END;
GO

BEGIN TRY
    BEGIN TRANSACTION;
    DROP TABLE IF EXISTS temp_CGUSC.fp.teia_fonte_nivel4;
    EXEC sys.sp_rename
        N'fp.teia_fonte_nivel4_novo',
        N'teia_fonte_nivel4',
        N'OBJECT';
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT
    'OK' AS status,
    'ETAPAS_2_A_6_FINALIZADAS' AS etapa,
    (SELECT COUNT_BIG(*) FROM temp_CGUSC.fp.dados_socios) AS qtd_dados_socios,
    (
        SELECT COUNT_BIG(*)
        FROM temp_CGUSC.fp.dados_socios
        WHERE is_esocial = 1
    ) AS qtd_socios_esocial,
    (
        SELECT COUNT_BIG(*)
        FROM temp_CGUSC.fp.dados_socios
        WHERE is_seguro_defeso = 1
    ) AS qtd_socios_seguro_defeso,
    (SELECT COUNT_BIG(*) FROM temp_CGUSC.fp.teia_fonte_nivel2) AS qtd_teia_nivel2,
    (SELECT COUNT_BIG(*) FROM temp_CGUSC.fp.teia_fonte_nivel3) AS qtd_teia_nivel3,
    (
        SELECT COUNT_BIG(*)
        FROM temp_CGUSC.fp.teia_fonte_nivel3
        WHERE is_esocial = 1
    ) AS qtd_n3_esocial,
    (
        SELECT COUNT_BIG(*)
        FROM temp_CGUSC.fp.teia_fonte_nivel3
        WHERE is_seguro_defeso = 1
    ) AS qtd_n3_seguro_defeso,
    (SELECT COUNT_BIG(*) FROM temp_CGUSC.fp.teia_fonte_nivel4) AS qtd_teia_nivel4;
GO
