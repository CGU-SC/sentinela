# Inventário de rotas e fluxos do Sentinela

**Levantamento estático do código:** 1º de outubro de 2026  
**Escopo:** rotas da SPA, operações HTTP da API, navegação, fluxos de negócio e integrações identificáveis no repositório.  
**Status:** inventário para planejamento de QA; não representa validação funcional em ambiente conectado ao SQL Server.

## Como interpretar este inventário

- Rotas de tela são URLs resolvidas pelo Vue Router.
- Rotas de API são operações HTTP registradas no FastAPI. O prefixo comum da API é `/api/v1`.
- Um endpoint registrado não prova que a tela funciona de ponta a ponta. É necessário exercitar o frontend, API, caches e dependências de dados.
- “Não localizado caller” significa que a busca estática não encontrou consumidor direto no frontend; pode haver uso externo, indireto ou legado.
- Cobertura “100%” exige validar os caminhos condicionais, permissões, dados, estados de erro e diferenças Web/Desktop em ambiente executável. Este documento mapeia o que está registrado no código e aponta o que falta confirmar.

## Visão de navegação

O frontend é uma SPA Vue 3. Em desenvolvimento, o Vite serve as telas e encaminha chamadas HTTP para o FastAPI. No modo desktop/produção, o FastAPI também serve os artefatos estáticos do frontend e suporta history mode.

Fluxo básico:

1. Inicialização da aplicação e consulta do estado dos caches.
2. Carregamento de preferências, filtros, localidades e dados necessários ao shell.
3. Navegação entre análises e domínios operacionais.
4. Chamadas à API, que combina regras de negócio, caches Parquet e consultas ao SQL Server.
5. Apresentação de resultados, evidências e exportações.

### Rotas de tela do Vue Router

| Caminho | Tela/componente | Fluxo principal |
|---|---|---|
| `/` | `NationalView` | Visão nacional, KPIs, filtros globais, mapa e navegação para níveis inferiores. |
| `/dispersao-beneficio` | `BenefitDispersionView` | Dispersão do benefício e análise geográfica/operacional associada. |
| `/municipios` | `MunicipalView` | Análise municipal e drill-down a partir do contexto geográfico/filtros. |
| `/estabelecimentos` | `CnpjView` | Lista de estabelecimentos filtrada, busca e abertura de detalhe. |
| `/estabelecimentos/:cnpj` | `CnpjDetailView` | Validação do CNPJ, carregamento das abas de auditoria, exportações e navegação entre CNPJs. |
| `/analises` | `AnalysesView` | Página de análises; confirmar em runtime o conteúdo e as ações vinculadas. |
| `/alvos` | `TargetsView` | Consulta de alvos temáticos, com seleção de tipo por query string. |
| `/regional` | `RegionalView` | Comparativos regionais, UF/região, percentis e animações. |
| `/listas` | `WatchlistView` | Lista de interesse, observações, evidências e ações de remoção/desfazer. |
| `/configuracoes` | `SettingsView` | Preferências, limiares/configurações e operações administrativas disponíveis na tela. |

### Redirecionamentos e parâmetros

| Caminho legado/alternativo | Destino | Observação para QA |
|---|---|---|
| `/municipio` | `/municipios` | Confirmar URL final, histórico do navegador e preservação de query string. |
| `/cnpj` | `/estabelecimentos` | Confirmar comportamento sem CNPJ. |
| `/estabelecimento/:cnpj` | `/estabelecimentos/:cnpj` | Verificar CNPJ válido, inválido e ausente da base. |
| `/alvos/:pathMatch(.*)*` | `/alvos` | Segmentos após `/alvos` são redirecionados; conferir impacto em links antigos. |
| `/indicadores` | `/estabelecimentos` | Rota antiga aponta para lista de estabelecimentos, não para a análise cruzada. |

O router não apresenta uma rota catch-all de tela explícita. Testar URL desconhecida, refresh em rota interna e acesso direto pelo modo Web e pelo aplicativo desktop.

### Observações de navegação a confirmar

- `/dispersao` não aparece entre as rotas atuais; confirmar se é URL antiga, funcionalidade removida ou rota ausente.
- `/indicadores` redireciona para estabelecimentos, enquanto a análise de indicadores existe como operação de API e pode ser acessada por outro fluxo/tela. Confirmar o destino funcional esperado.
- `/regional`, `/dispersao-beneficio` e `/alvos` não aparecem como itens principais na navegação identificada. Confirmar acesso por links secundários, permissões ou links diretos.
- Foram encontrados condicionais da sidebar para `/alvos/cluster` e `/alvos/rede`, embora segmentos de `/alvos/...` sejam redirecionados para `/alvos`. Confirmar se essas condições são alcançáveis.
- A tela de detalhe tem abas e slugs próprios. Verificar sincronização entre aba selecionada, URL, back/forward e carregamento inicial.

## Detalhe de estabelecimento

O detalhe é acessado por `/estabelecimentos/:cnpj`. O fluxo identificado valida o CNPJ pela API, limpa o estado anterior ao trocar de estabelecimento e carrega dados para as abas. Abas/slugs registrados no frontend:

| Aba/slug | Conteúdo a cobrir |
|---|---|
| `movimentacao` | Movimentação agregada por período e produtos/GTIN; estados sem dados e erro. |
| `diagnostico` | Diagnóstico e alertas de integridade do estabelecimento. |
| `memoria` | Memória de cálculo e detalhamento de GTIN. |
| `indicadores` | Indicadores do CNPJ, benchmarks locais e evolução de benchmark. |
| `autorizacoes` | Autorizações relacionadas a CRM/evidências, conforme integração disponível. |
| `socios` | Quadro societário e navegação para relações societárias. |
| `teia` | Grafo societário, níveis N2/N3/N4, filtros, busca e painel do nó. |
| `regional` | Contexto geográfico e benchmarks local/regional. |

Também há funções relacionadas a evolução financeira, repasses, incompatibilidades clínicas, falecidos, CRM, timeline, Nota Técnica e relatório PDF. Conferir correspondência exata entre abas visíveis, slugs, chamadas da store e operações da API.

## Inventário da API

As rotas abaixo são relativas ao prefixo `/api/v1`. O grupo Analytics usa `/api/v1/analytics`; os demais grupos têm os prefixos indicados. Parâmetros de query e modelos de corpo devem ser extraídos dos schemas/assinaturas ao detalhar casos de teste.

### Analytics — 57 operações

| Método | Caminho relativo a `/api/v1/analytics` | Uso/fluxo identificado |
|---|---|---|
| GET | `/crm-prescricoes-analise` | Análise de prescrições por CRM. |
| GET | `/crm-prescricoes-mensal` | Agregação mensal de prescrições. |
| GET | `/crm-prescricoes-serie-mensal` | Série mensal de prescrições. |
| GET | `/crm-prescricoes-alertas` | Alertas de prescrições/CRM. |
| GET | `/crm-medico-evidencias` | Evidências associadas a médico. |
| GET | `/crm-medico-evidencias/autorizacoes` | Autorizações associadas às evidências do médico. |
| GET | `/crm-medico-evidencias/exportar` | Exportação de evidências do médico. |
| GET | `/crm-medico-historico` | Histórico de atuação do médico. |
| POST | `/client-perf` | Recebe dados de desempenho/telemetria do cliente. |
| GET | `/cnpj/{cnpj}/bootstrap` | Dados iniciais agregados para detalhe do estabelecimento. |
| GET | `/cnpj/{cnpj}/status` | Valida formato e presença do CNPJ na base. |
| GET | `/cnpj/{cnpj}/cadastro` | Cadastro e geografia do estabelecimento. |
| GET | `/cnpj/{cnpj}/socios` | Quadro societário. |
| GET | `/alertas-panorama` | Panorama de alertas. |
| GET | `/cnpj/{cnpj}/alertas-integridade` | Alertas de integridade por estabelecimento. |
| GET | `/cnpj/{cnpj}/network` | Grafo societário inicial. |
| GET | `/cnpj/{cnpj}/network/expand/{target_id}` | Expande nó CPF/CNPJ. |
| GET | `/cnpj/{cnpj}/network/level/3` | Expansão em lote do nível 3. |
| GET | `/cnpj/{cnpj}/network/level/4` | Expansão em lote do nível 4. |
| GET | `/resumo` | KPIs, UFs, municípios e estabelecimentos para análise geral. |
| GET | `/producao-semestral` | Dados de produção semestral. |
| GET | `/faixas-risco` | Distribuição por faixas de risco. |
| GET | `/cnpj/{cnpj}/evolucao` | Evolução financeira semestral. |
| GET | `/cnpj/{cnpj}/evolucao-mensal-gtin` | Evolução mensal agrupada por GTIN. |
| GET | `/cnpj/{cnpj}/repasses` | Repasses do estabelecimento. |
| GET | `/cnpj/{cnpj}/gtin-detalhamento-mensal` | Ranking/detalhamento de GTIN por período. |
| GET | `/cnpj/{cnpj}/indicadores` | Indicadores detalhados do CNPJ. |
| GET | `/cnpj/{cnpj}/indicadores/{indicador}/benchmark-local` | Benchmark local para indicador. |
| GET | `/cnpj/{cnpj}/indicadores/{indicador}/evolucao-benchmark` | Evolução do benchmark de indicador. |
| GET | `/cnpj/{cnpj}/geografico/origem-uf` | Origem geográfica das vendas. |
| GET | `/cnpj/{cnpj}/geografico/benchmark-local` | Benchmark geográfico local. |
| GET | `/cnpj/{cnpj}/clinico/incompatibilidades` | Incompatibilidades clínicas. |
| GET | `/cnpj/{cnpj}/falecidos` | Resumo e transações associadas a falecidos. |
| GET | `/cnpj/{cnpj}/falecidos/exportar` | Exportação de dados de falecidos. |
| GET | `/rede/{cnpj_raiz}` | Dados consolidados da rede por raiz CNPJ. |
| GET | `/cpf/{cpf}/timeline` | Timeline de CPF, com contexto de CNPJ. |
| GET | `/regional-benchmarking` | Benchmark regional/UF. |
| GET | `/regional-benchmarking-animation` | Série temporal para animação regional. |
| GET | `/cnpj/{cnpj}/crm-data` | KPIs e dados CRM do CNPJ. |
| GET | `/cnpj/{cnpj}/crm/medico-atuacao/{id_medico:path}` | Atuação do médico no CNPJ. |
| GET | `/cnpj/{cnpj}/crm/timeline-dataset` | Dataset para timeline CRM. |
| GET | `/cnpj/{cnpj}/crm/raio-x` | Detalhamento CRM por data/hora. |
| GET | `/cnpj/{cnpj}/crm/raio-x/exportar` | Exportação do raio-X CRM. |
| POST | `/cnpj/{cnpj}/crm/prescritores/exportar` | Exporta prescritores conforme filtros enviados. |
| GET | `/indicadores-analise` | Análise cruzada por indicador. |
| GET | `/indicadores-analise/cnpjs` | Lista/paginação de CNPJs para análise de indicador. |
| GET | `/cnpj/{cnpj}/movimentacao` | Memória de cálculo/movimentação por GTIN. |
| GET | `/cnpj-lookup` | Busca/autocomplete slim de CNPJ. |
| GET | `/metric-percentiles-animation` | Percentis para animação temporal. |
| GET | `/metric-percentiles` | Percentis por escopo regional, UF ou Brasil. |
| GET | `/nota-tecnica/regionais` | Opções/contexto regional da Nota Técnica. |
| GET | `/cnpj/{cnpj}/nota-tecnica/readiness` | Verifica prontidão para gerar Nota Técnica. |
| POST | `/cnpj/{cnpj}/nota-tecnica/prepare` | Prepara dados/caches para Nota Técnica. |
| GET | `/cnpj/{cnpj}/relatorio-pdf/readiness` | Verifica prontidão para gerar relatório PDF. |
| POST | `/cnpj/{cnpj}/relatorio-pdf/prepare` | Prepara dados para relatório PDF. |
| GET | `/cnpj/{cnpj}/nota-tecnica` | Gera/baixa documento da Nota Técnica. |

### Demais grupos

#### Alvos — `/api/v1/targets`

| Método | Caminho | Uso/fluxo identificado |
|---|---|---|
| GET | `/parkinson-menor-50` | Lista temática de alvos com Parkinson e idade menor que 50. |
| GET | `/diabetes-menor-20` | Lista temática de alvos com diabetes e idade menor que 20. |

#### Geografia — `/api/v1/geo`

| Método | Caminho | Uso/fluxo identificado |
|---|---|---|
| GET | `/localidades` | Hierarquia territorial e unidades do programa. |
| GET | `/estabelecimentos` | Coordenadas e risco de estabelecimentos para mapas/PDF. |

#### Cache — `/api/v1/cache`

| Método | Caminho | Uso/fluxo identificado |
|---|---|---|
| GET | `/status` | Estado do carregamento/sincronização. |
| POST | `/refresh` | Atualiza caches globais. |

#### Preferências — `/api/v1/preferences`

| Método | Caminho | Uso/fluxo identificado |
|---|---|---|
| GET | `/` | Lê preferências. |
| PUT | `/` | Atualiza preferências gerais. |
| PUT | `/filters` | Persiste filtros. |
| PUT | `/watchlist` | Persiste lista de interesse. |
| GET | `/watchlist/ultima-remocao` | Consulta última remoção para desfazer. |
| POST | `/watchlist/desfazer-remocao` | Desfaz remoção da lista. |
| PUT | `/ui` | Persiste preferências de interface. |
| PUT | `/nota-tecnica` | Persiste preferências da Nota Técnica. |
| GET | `/recovery/status` | Estado de recuperação/backup de preferências. |
| POST | `/recovery` | Recupera preferências. |
| GET | `/metodologia` | Lê metodologia configurável. |
| PUT | `/metodologia` | Atualiza metodologia configurável. |

#### Evidências — `/api/v1/evidencias`

| Método | Caminho | Uso/fluxo identificado |
|---|---|---|
| GET | `/` | Lista evidências. |
| GET | `/resumo` | Resumo agregado de evidências. |
| POST | `/` | Cria evidência. |
| PATCH | `/{evidencia_id}` | Atualiza evidência. |
| GET | `/cnpj/{cnpj}/exportar` | Exporta evidências por CNPJ. |
| DELETE | `/cnpj/{cnpj}` | Remove evidências do CNPJ. |
| DELETE | `/{evidencia_id}` | Remove uma evidência. |

#### Sistema/atualização — `/api/v1/system`

| Método | Caminho | Uso/fluxo identificado |
|---|---|---|
| GET | `/update-status` | Estado da versão/atualização. |
| POST | `/check-update` | Consulta atualização disponível. |
| POST | `/download-update` | Inicia download. |
| GET | `/download-progress` | Consulta progresso. |
| POST | `/apply-update` | Aplica atualização baixada. |
| POST | `/cancel-update` | Cancela operação de atualização. |

### Rotas fora dos grupos versionados

| Método | Caminho | Condição/uso |
|---|---|---|
| GET | `/saude` | Health check do FastAPI. |
| GET | `/` | Serve entrada da SPA quando frontend compilado está disponível. |
| GET | `/{full_path:path}` | Fallback de history mode quando os arquivos de frontend estão disponíveis; confirmar a ordem de registro e o comportamento em execução. |
| GET | `/openapi.json` | Esquema OpenAPI padrão do FastAPI. |
| GET | `/docs` | Interface Swagger padrão, se habilitada. |
| GET | `/docs/oauth2-redirect` | Callback padrão do Swagger, se habilitado. |
| GET | `/redoc` | Interface ReDoc padrão, se habilitada. |

## Fluxos de ponta a ponta identificados

### 1. Inicialização e disponibilidade

1. Backend inicia e tenta carregar/sincronizar os caches no lifespan.
2. Frontend consulta estado do cache, configurações, dados do dashboard e dados geográficos.
3. Quando a sincronização está em andamento, o frontend acompanha o estado e exibe carregamento.
4. A aplicação pode sinalizar modo degradado quando o cache não está pronto.

**Testar:** cache pronto, carregando, erro, timeout, API indisponível, falta de conexão com banco, reabertura depois de falha e diferença entre Vite e pacote desktop.

### 2. Filtros globais e navegação geográfica

1. Usuário altera período, UF, região, município, unidade PF e demais filtros.
2. Estado normalizado fica na store Pinia e é persistido localmente/no backend.
3. A cascata geográfica ajusta filtros dependentes.
4. Chamadas de análise são refeitas e os resultados alimentam KPIs, tabelas e mapas.

**Testar:** combinação e limpeza de filtros, restauração após reload, precedência da seleção, mudança rápida, debounce, falha de persistência e coerência entre URL/estado/API. Regiões devem usar `id_regiao_saude`/`regiao_id`; município usa `id_ibge7`.

### 3. Análises nacional, regional e municipal

1. Tela consome resumo, faixas de risco, localidades e dados de estabelecimentos.
2. Seleção no mapa/filtros altera o escopo.
3. Navegação aprofunda para UF/região/município e lista de estabelecimentos.
4. Animações consomem endpoints de séries em chamada única.

**Testar:** universo nacional, filtros territoriais, dados vazios, dados parciais, limites de período, troca rápida de escopo, sincronização mapa/tabela/KPI, percentis e navegação de retorno.

### 4. Busca e auditoria de estabelecimento

1. Busca/autocomplete localiza CNPJ.
2. Lista filtrada abre `/estabelecimentos/:cnpj`.
3. Detalhe valida o CNPJ e inicializa/limpa estado.
4. Abas carregam dados financeiros, indicadores, CRM, sócios, geografia e rede societária.
5. Usuário troca de estabelecimento ou aba; a store mantém caches por chave contextual.

**Testar:** CNPJ malformado (422), CNPJ ausente (404), CNPJ válido, resposta parcial, troca rápida de CNPJ, isolamento do cache entre estabelecimentos, refresh em subrota, abas em erro e deep link.

### 5. CRM e evidências médicas

1. Tela de detalhe ou análises consulta indicadores e séries de CRM.
2. Usuário abre alertas, atuação/histórico, dia/hora e raio-X.
3. Dados podem ser exportados como evidência/relatório.

**Testar:** identificador médico com caracteres especiais, filtros de data/hora, fronteiras de período, vazio, volume alto, exportação, erro de geração e consistência de registros.

### 6. Teia societária

1. API sincroniza dados de grafo por CNPJ e retorna nível inicial.
2. Frontend desenha nós/arestas e oferece seleção, busca, zoom e filtros.
3. Usuário expande CPF para nível 4 ou CNPJ para nível 3, individualmente ou em lote.
4. Flags de risco dos nós são exibidas em estilos, alertas e painel de detalhe.

**Testar:** nós isolados, grafo denso, expansão repetida, nó inválido, carga lenta, flags ausentes/inconsistentes, filtros visuais e falha durante sincronização.

### 7. Listas e evidências

1. Usuário inclui/edita estabelecimento, observação ou evidência.
2. Alterações sincronizam com preferências/API.
3. Remoção pode ser desfeita pela última remoção.
4. Evidências podem ser filtradas, editadas, removidas e exportadas por CNPJ.

**Testar:** persistência após reload, duplicidade, concorrência, validação, remoção individual/em lote, desfazer após nova operação, erro de rede e autorização funcional conforme o modelo de acesso.

### 8. Configurações e metodologia

1. Tela lê configurações, limiares, preferências da interface e metodologia.
2. Alterações são validadas e persistidas.
3. Algumas configurações mudam a apresentação ou a classificação de risco.

**Testar:** valores de fronteira, tipo inválido, persistência, recuperação, efeito imediato, reload e consistência entre cores/badges/tabelas e cálculo.

### 9. Exportações e documentos

1. Usuário solicita PDF, Nota Técnica ou exportação CRM/falecidos/evidências.
2. Algumas gerações consultam readiness e podem exigir etapa de preparação.
3. Backend compõe arquivo e retorna download.

**Testar:** readiness positivo/negativo, preparação idempotente, timeout, erro no arquivo, nome/MIME, conteúdo, filtros aplicados, caracteres pt-BR e memória sob volume grande.

### 10. Atualização do aplicativo

1. Consulta versão disponível.
2. Inicia download e consulta progresso.
3. Aplica ou cancela a atualização.

**Testar:** sem atualização, atualização disponível, download lento/interrompido, cancelamento, arquivo inválido, aplicação bem-sucedida e reinício. Executar em ambiente isolado da instalação usada pelo usuário.

## Ligações entre telas e operações: pontos a confirmar

A busca estática não localizou caller frontend direto para estas operações ou não comprovou seu caminho de uso; revisar antes de concluir cobertura:

- `GET /api/v1/analytics/rede/{cnpj_raiz}`
- `GET /api/v1/analytics/cnpj/{cnpj}/status` (pode estar encapsulada em bootstrap ou store)
- `GET /api/v1/geo/estabelecimentos`
- `GET /api/v1/evidencias/resumo`
- `POST /api/v1/system/cancel-update`
- Algumas operações de CRM médico/evidências podem ser acionadas por componentes com chamadas indiretas.

Também é necessário conferir se todo endpoint listado possui ao menos uma tela/ação consumidora e se cada ação de tela tem sua operação, permissões e tratamento de erro correspondentes.

## Fontes técnicas a revisar ao transformar o mapa em casos

- Frontend: router, layouts, views, componentes de domínio, stores, composables e configuração de endpoints.
- Backend: `backend/api/router.py`, routers de endpoints, schemas Pydantic e services.
- Dados: `backend/data_cache.py`, caches globais e por CNPJ, `src/scripts/sincronizar_cache.py`.
- Indicadores/metodologia: SQLs em `src/indicadores/` e configuração/mapeamento de indicadores no frontend/backend.
- Integrações: SQL Server via SQLAlchemy/ODBC, sistema de atualização desktop, geração de documentos e arquivos locais de preferências.

## Próximos artefatos de QA recomendados

1. Catálogo de telas, rotas, papéis de usuário e ações.
2. Matriz de rastreabilidade: requisito/fluxo → tela → API → dados → casos de teste.
3. Casos de teste por fluxo, começando por inicialização, filtros, análise geográfica e detalhe CNPJ.
4. Contratos de API e testes de validação de schemas/erros.
5. Plano de dados de teste: CNPJ válido/inválido, registros limítrofes, vazios e grandes volumes.
6. Plano de automação unitária, integração, componente e ponta a ponta.
7. Execução manual em Web e Desktop, com evidências, ambiente, versão e resultado.

## Limites deste levantamento

- É um mapa estático dos registros encontrados; não confirma disponibilidade de banco, cache, arquivos locais ou atualizador.
- Não foi executado teste funcional, build, chamada de endpoint ou geração de documento neste levantamento.
- A contagem de operações da API corresponde aos routers identificados no código: Analytics 57, targets 2, geo 2, cache 2, preferences 12, evidências 7 e system 6; total de 88 operações modulares, além das rotas de saúde/SPA/OpenAPI.
- A completude funcional depende de validar runtime, permissões, parâmetros e ligações indiretas descritas nos itens “a confirmar”.
