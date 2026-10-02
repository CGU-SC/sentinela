# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## REGRA CRÍTICA: Processo de Release após Novas Funcionalidades ou Correções

**A cada nova funcionalidade ou correção de bug que vá para produção, o processo de release completo deve ser executado — sempre apresentando o plano ao usuário e aguardando autorização explícita antes de executar qualquer etapa.**

Passos obrigatórios do processo de release:
1. Atualizar `version.json` na raiz com a nova versão SemVer.
2. Atualizar `frontend/package.json` com a mesma versão.
3. Atualizar `CHANGELOG.md` com o que foi adicionado, corrigido ou alterado.
4. Atualizar `docs/updates/v2/manifest.json` (manifesto da série 2.x) com `latest_version`, `minimum_supported_version` e `published_at`.
5. Assinar o manifesto: `.\.venv\Scripts\python.exe .\src\scripts\sign_update_manifest.py` (assina o da série 2.x e confere o legado).
6. Fazer build do frontend: `npm run build` em `frontend/`.
7. Fazer build do executável: `.\build_pywebview_uvicorn.ps1` (e granian se aplicável).
8. Commit, tag e push: `git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z`
9. Criar GitHub Release com o executável: `gh release create vX.Y.Z dist/sentinela_server1.exe --title "Sentinela vX.Y.Z" --notes-file CHANGELOG.md`
10. Publicar manifesto no GitHub Pages: `.\.venv\Scripts\python.exe -m mkdocs gh-deploy --force`

Regras:
- **Nunca publicar o manifesto sem reasinar** — qualquer byte alterado invalida a assinatura.
- **Nunca alterar `manifest.json` após assinar** sem rodar o script de assinatura novamente.
- **Nunca alterar nem apagar o manifesto legado `docs/updates/manifest.json`** (+ `manifest.sig`): ele fica congelado em 1.7.0 para a série 1.x, que assim não recebe oferta da 2.0 (exige o pacote completo com as novas bases). Detalhes em `docs/updates/README.md`.
- A versão em `version.json` e `frontend/package.json` deve ser sempre idêntica.
- `minimum_supported_version` só deve subir quando a atualização for obrigatória.

---

## REGRA CRÍTICA: Autorização Antes de Qualquer Alteração

**NUNCA edite, crie ou delete arquivos sem antes apresentar o plano ao usuário e receber autorização explícita.**

Antes de qualquer mudança de código:
1. Explique o que precisa ser feito e por quê.
2. Descreva quais arquivos serão afetados e o que mudará em cada um.
3. Aguarde o usuário dizer "ok", "pode fazer", "sim" ou equivalente.
4. Só então execute as alterações.

Diagnóstico e investigação (leitura de arquivos, buscas, análise) podem ser feitos livremente. A trava é apenas para **escrita**.

## REGRA CRITICA: Proibido Usar Fallbacks

**NUNCA implemente fallbacks silenciosos para contornar schema antigo, dados ausentes, campos inexistentes, erros de integracao ou divergencias de contrato.**

Quando um dado, coluna, endpoint, configuracao ou contrato for obrigatorio:
1. Exija explicitamente esse requisito no codigo.
2. Falhe cedo e de forma visivel se o requisito nao existir.
3. Corrija a fonte do problema em vez de mascarar com valor padrao.
4. Nao substitua campo ausente por `None`, string vazia, zero, lista vazia ou heuristica alternativa sem autorizacao explicita do usuario.

Compatibilidade retroativa so pode ser adicionada quando o usuario pedir claramente. Mesmo nesses casos, documente o motivo, o escopo e o ponto exato onde o fallback sera removido.

## REGRA CRITICA: Sincronizacao de Parquets

Sempre que um arquivo Parquet for criado, removido, renomeado ou tiver schema alterado, atualize tambem o script de sincronizacao seletiva correspondente. No repo atual, isso significa `src/scripts/sincronizar_cache.py` (equivalente operacional ao `sincronizar_dados.py` citado nas rotinas do projeto).

Ao alterar caches Parquet:
1. Registre o caminho do novo/alterado Parquet no `data_cache.py`.
2. Inclua validacao de colunas obrigatorias no boot rapido do cache.
3. Inclua o modulo no script de sincronizacao seletiva.
4. Garanta que a ordem de sincronizacao respeite dependencias entre caches.
5. Nao crie Parquet vazio como fallback para erro de fonte, schema ou conexao.

## REGRA CRITICA: Nota Tecnica (`backend/api/services/analytics/nota_tecnica.py`)

O arquivo `nota_tecnica.py` deve ser mantido como orquestrador da geracao do documento. Nao volte a concentrar helpers, textos longos, graficos, anexos, quadros ou consultas nele.

Organizacao atual obrigatoria:
1. `nota_tecnica.py`: fluxo principal de `generate_nota_tecnica`, capa, secoes narrativas e orquestracao.
2. `nota_tecnica_docx_utils.py`: helpers genericos de Word/XML (`_run`, bordas, shading, footnotes, larguras de tabela, celulas).
3. `nota_tecnica_formatters.py`: formatadores puros pt-BR/BR (`_format_decimal_pt`, CPF/CNPJ, datas, semestre, listas).
4. `nota_tecnica_charts.py`: criacao e insercao de graficos/imagens.
5. `nota_tecnica_contexts.py`: builders de contexto/dados para as secoes iniciais, comparativos, GTINs, evolucao financeira e socios.
6. `nota_tecnica_criticidades.py`: mapeamento, builders e textos da secao 7 de criticidades.
7. `nota_tecnica_anexos.py`: anexos da nota tecnica, como o Anexo III de falecidos.
8. `nota_tecnica_quadros.py`: quadros/tabelas numerados da nota tecnica.

Regras da Secao 7:
1. A secao 7 deve listar somente indicadores com criticidade `critico` vindos da matriz de risco via `_get_criticos(cnpj)`.
2. Excecao: `falecidos` continua baseado nas transacoes/detalhamento de falecidos, nao apenas no snapshot da matriz.
3. A numeracao da secao 7 e dinamica. Se falecidos existir, ele e 7.1 e os demais comecam em 7.2; se nao existir, o primeiro critico da matriz comeca em 7.1.
4. Indicadores classificados apenas como `atencao` nunca devem aparecer na secao 7.
5. Quando a matriz possuir apenas percentual para um indicador, o texto deve usar percentual e multiplicadores, sem inventar valor em reais.
6. Use valor em reais somente para indicadores cuja matriz ja expose campo financeiro apropriado, como ticket medio, receita por paciente ou per capita.
7. Para novo indicador da secao 7, atualize o mapeamento em `nota_tecnica_criticidades.py`, crie o builder de contexto e o renderizador de texto no mesmo modulo, e conecte a chamada no fluxo de `generate_nota_tecnica`.

Regras regionais e matriz:
1. E proibido usar `no_regiao_saude` em logica, filtros, parametros ou integracoes. Use sempre `id_regiao_saude`.
2. `no_regiao_saude` tambem nao deve ser necessario para montar comparativos; quando precisar rotular internamente, use o ID.
3. Nao mudar a granularidade da `matriz_risco_consolidada` para snapshot anual sem pedido explicito.
4. Depois de qualquer alteracao nos modulos da Nota Tecnica, rode `python -m py_compile` nos arquivos `nota_tecnica*.py` alterados.

## Project Overview

**Sentinela** is an automated audit system for detecting irregularities in Brazil's Popular Pharmacy Program (PFPB), developed by CGU. It is a hybrid Web/Desktop application (Vue 3 SPA + FastAPI + PyWebView desktop wrapper).

---

## Commands

### Backend
```bash
# Install dependencies (Python 3.10+, requires ODBC Driver 17 for SQL Server)
pip install -r requirements.txt

# Run development server (port 8002)
python backend/main.py

# Health check
curl http://127.0.0.1:8002/saude
```

### Frontend
```bash
cd frontend

# Install dependencies
npm install

# Development server (port 5173, with hot reload)
npm run dev

# Production build → frontend/dist/
npm run build

# Preview production build
npm run preview
```

### Desktop Build
```bash
# Bundle into single .exe via PyInstaller
pyinstaller Sentinela.spec
```

### Tests
```bash
# Install test dependencies (pytest + pytest-cov on top of requirements.txt)
pip install -r requirements-test.txt

# Run the backend suite (config in pytest.ini; always measures coverage of backend/)
.\.venv\Scripts\python.exe -m pytest

# Run a single file without the coverage report
.\.venv\Scripts\python.exe -m pytest tests/backend/analytics/test_indicadores.py --no-cov
```

- Tests live in `tests/` (legacy unittest files at the root, pytest suite in `tests/backend/` split into `analytics`, `api`, `cache`, `services`).
- The suite runs without SQL Server and without the production cache: sources are replaced by fixtures/mocks (`tests/backend/conftest.py`).
- The backend suite is kept at 100% line coverage of `backend/`; new backend code should come with tests. There is no automated frontend test suite; frontend validation is still manual via the dev servers.

---

## Architecture

### Request Flow
```
Vue 3 SPA (port 5173)
  → Axios HTTP → FastAPI (port 8002)
    → Services (business logic)
      → SQLAlchemy → SQL Server (SDH-DIE-BD / temp_CGUSC, Windows Auth)
```

In production/desktop mode, the frontend is served as static files by FastAPI itself (from `frontend/dist/`).

### Backend Layers (`backend/`)
- `main.py` — FastAPI app setup, CORS, static file serving, cache preload on startup (`lifespan`)
- `database.py` — SQLAlchemy connection pool (10 connections, max overflow 20), ODBC Driver 17, Windows Trusted Auth
- `data_cache.py` — In-memory data cache loaded at startup to avoid repeated heavy queries
- `api/router.py` — Aggregates all sub-routers under `/api/v1/`
- `api/endpoints/` — HTTP route handlers (thin layer, only request/response)
- `api/services/` — All business logic and SQL queries (e.g., `analytics.py` is ~50KB of KPI calculations)
- `api/schemas/` — Pydantic models for request validation and response serialization

### Frontend Layers (`frontend/src/`)
- `config/` — **Single source of truth for all constants** (see Zero Hardcoding below)
- `stores/` — Pinia global state: `analytics`, `filters`, `geo`, `theme`, `cnpjNav`, `farmaciaLists`
- `composables/` — Reusable logic hooks (data fetching, formatting, filter sync, risk metrics, chart theming)
- `views/consolidated/` — Main navigation hierarchy: National → Regional → Municipality → CNPJ Detail (7 sub-tabs) → Indicators
- `router/` — Vue Router, history mode, single catch-all route for SPA

### View Hierarchy
The application has a drill-down structure:
1. `NationalAnalysisView` — National KPIs and map
2. `RegionalAnalysisView` — Per-UF breakdown
3. `MunicipalityAnalysisView` — Per-municipality analysis
4. `CnpjDetailView` — Pharmacy-level audit (7 sub-tabs: dispensações, risco, prescrições, etc.)
5. `IndicadoresAnalysisView` — Cross-cutting risk indicator analysis

---

## Mapa Operacional do Sistema - leitura atual em 2026-05-13

Use esta secao como mapa de navegacao antes de alterar o Sentinela. Ela descreve o sistema que esta servindo em `http://localhost:5173/`, a organizacao real das pastas e os pontos de acoplamento entre frontend, backend, cache e SQL. O objetivo e evitar que uma IA precise redescobrir os mesmos modulos a cada tarefa.

### Visao rapida
- Runtime local: frontend Vite em `http://localhost:5173/`; API FastAPI em `http://127.0.0.1:8002`; `frontend/src/config/api.js` usa `VITE_API_URL` ou cai em `http://127.0.0.1:8002`.
- Frontend: Vue 3 Composition API, Pinia, PrimeVue 3, ECharts, Cytoscape, jsPDF/html-to-image.
- Backend: FastAPI, SQLAlchemy/pyodbc, SQL Server `SDH-DIE-BD`/`temp_CGUSC`, Polars/Pandas, cache Parquet em `sentinela_cache/`.
- App desktop/producao: `backend/main.py` tambem serve `frontend/dist/` e tem catch-all para Vue Router history mode.
- Fluxo mental correto: UI -> Pinia/composable -> `API_ENDPOINTS` -> FastAPI endpoint -> `AnalyticsService`/servico -> `data_cache`/Parquet/SQL Server -> Pydantic schema -> UI.

### Pastas principais
- `frontend/src/main.js`: cria app Vue, registra Pinia, router, PrimeVue, ToastService, ConfirmationService e diretiva `v-tooltip`.
- `frontend/src/App.vue`: boot global. Consulta `/api/v1/cache/status`, aguarda sync se estiver `fetching`/`processing`, carrega dashboard, geo, lookup CNPJ e configuracoes. Exibe overlay de carga/erro antes do `router-view`.
- `frontend/src/router/index.js`: rotas reais: `/`, `/dispersao`, `/dispersao-beneficio`, `/municipios`, `/estabelecimentos`, `/estabelecimentos/:cnpj`, `/indicadores`, `/regional`, `/listas`, `/configuracoes`. Rotas antigas `/municipio`, `/cnpj`, `/estabelecimento/:cnpj` redirecionam.
- `frontend/src/layouts/`: shell visual. `AppLayout.vue` compoe `AppNavbar`, `AppSidebar`, `CnpjDialog`, `SyncDialog` e conteudo. `meta.hideSidebar` esconde a sidebar em configuracoes.
- `frontend/src/views/`: telas de alto nivel. `NationalView`, `RegionalView`, `MunicipalView`, `CnpjView`, `CnpjDetailView`, `IndicatorsView`, `BenefitDispersionView`, `SettingsView`, `lists/WatchlistView`.
- `frontend/src/views/components/`: componentes por dominio: `maps`, `charts`, `tables`, `indicadores`, `cnpj`.
- `frontend/src/views/components/cnpj/`: abas de detalhe de estabelecimento: cabecalho, evolucao financeira, memoria de calculo, indicadores, CRMs, falecidos, socios, teia societaria, contexto regional, PDF e overlays.
- `frontend/src/views/components/cnpj/network/`: controles pequenos da teia: zoom, busca, filtros de camadas, legenda, niveis, alertas, painel de detalhe.
- `frontend/src/stores/`: estado global Pinia.
- `frontend/src/composables/`: logica reaproveitavel de fetch, filtros, formatacao, PDF, charts, periodo, loading e estabilidade de abas.
- `frontend/src/config/`: fonte de verdade de endpoints, constantes, risco, cores, temas, filtros, UI e ECharts.
- `frontend/src/utils/network/`: logica pura da teia Cytoscape: stylesheet, layout, constantes, formatadores e utilitarios de nos.
- `backend/main.py`: cria FastAPI, CORS, lifespan com `load_cache(engine)`, monta `/api/v1`, serve static build e `/saude`.
- `backend/database.py`: SQLAlchemy engine para SQL Server via ODBC Driver 17 e Windows Auth; `get_db()` e dependencia FastAPI.
- `backend/data_cache.py`: sincroniza e carrega caches globais Polars/Parquet para movimentacao, localidades, rede, matriz, benchmarks CRM, farmacia, socios, teia N2/N3/N4 e medicamentos.
- `backend/api/endpoints/`: handlers HTTP finos.
- `backend/api/services/`: regra de negocio. `analytics/` e modular e exposto por `AnalyticsService` em `backend/api/services/analytics/__init__.py`.
- `backend/api/schemas/`: contratos Pydantic de entrada/saida.
- `src/indicadores/`: SQLs dos indicadores e matriz de risco. Nao sao chamados diretamente pela SPA; alimentam tabelas/cache usados pela API.
- `src/scripts/`: preparacao, pos-processamento, inspecao de cache/parquet e utilitarios de execucao.
- `docs/`: documentacao MkDocs sobre arquitetura, execucao, indicadores e fluxo de dados.

### Regras criticas de identificadores regionais
- Politica ID-first: codigo novo deve usar `id_regiao_saude` no dado e `regiao_id` em parametro de API/funcao.
- Nao criar nova logica baseada no nome textual da regiao. O nome deve ser somente label de exibicao.
- Existem trechos legados com `regiao_saude`/nome textual em frontend e backend. Ao tocar neles, migrar para ID quando o escopo permitir. Nao ampliar o uso legado.
- Municipios devem usar `id_ibge7` como valor de filtro no frontend; o nome do municipio e resolvido via `geoStore.localidades`.

### Backend - rotas e responsabilidades
- Prefixo global: `backend/api/router.py` monta tudo em `/api/v1`.
- `/api/v1/analytics/resumo`: `AnalyticsService.get_dashboard_data`. KPIs, UF, municipios e CNPJs. Motor Polars sobre `get_df()` e `get_df_dados_farmacia()`. Aceita filtros de periodo, UF, municipio, CNPJ/razao, status, rede, unidade PF e `regiao_id`.
- `/api/v1/analytics/faixas-risco`: `get_fator_risco_data`. Buckets de percentual de nao comprovacao.
- `/api/v1/analytics/resultados-detalhados`: lista consolidada historica.
- `/api/v1/analytics/regional-benchmarking`: contexto regional/UF, municipios e ranking de farmacias. Preferir `regiao_id`.
- `/api/v1/analytics/regional-benchmarking-animation`: retorna todos os trimestres/janelas para animacao em chamada unica.
- `/api/v1/analytics/metric-percentiles` e `/metric-percentiles-animation`: curvas de percentis por escopo `regiao`, `uf` ou `brasil`.
- `/api/v1/analytics/indicadores-analise`: analise cruzada de um indicador, baseada em `INDICATOR_MAPPING` e flags da matriz.
- `/api/v1/analytics/cnpj-lookup`: lista slim `{cnpj, razao_social}` para autocomplete.
- `/api/v1/analytics/cnpj/{cnpj}/status`: valida formato e existencia do CNPJ em `farmacias.parquet`; retorna 422 para formato invalido e 404 para fora da base PFPB.
- `/api/v1/analytics/cnpj/{cnpj}/cadastro`: dados cadastrais/geograficos da farmacia.
- `/api/v1/analytics/cnpj/{cnpj}/evolucao`: serie financeira semestral.
- `/api/v1/analytics/cnpj/{cnpj}/evolucao-mensal-gtin`: serie mensal agregada por GTIN.
- `/api/v1/analytics/cnpj/{cnpj}/gtin-detalhamento-mensal?periodo=YYYY-MM|YYYY-S1`: ranking de GTINs de um periodo.
- `/api/v1/analytics/cnpj/{cnpj}/movimentacao`: memoria de calculo por GTIN. Cache-first em `sentinela_cache/{cnpj}/memoria_calculo.parquet`; se faltar, le SQL comprimido, descompacta zlib/JSON, processa e salva Parquet. `check_cache=true` nao dispara processamento.
- `/api/v1/analytics/cnpj/{cnpj}/indicadores`: 18 indicadores detalhados do CNPJ a partir de `matriz_risco_consolidada`.
- `/api/v1/analytics/cnpj/{cnpj}/falecidos`: vendas a falecidos e resumo.
- `/api/v1/analytics/cpf/{cpf}/timeline?cnpj=...`: trilha temporal multi-CNPJ para CPF falecido.
- `/api/v1/analytics/cnpj/{cnpj}/crm-data`: KPIs/top CRMs.
- `/api/v1/analytics/cnpj/{cnpj}/crm/perfil-diario`: perfil diario unificado de alertas CRM.
- `/api/v1/analytics/cnpj/{cnpj}/crm/perfil-horario`: detalhamento horario unificado.
- `/api/v1/analytics/cnpj/{cnpj}/crm/raio-x?date_str=YYYY-MM-DD&hour=H`: transacoes literais de um dia/hora.
- `/api/v1/analytics/cnpj/{cnpj}/socios`: quadro societario.
- `/api/v1/analytics/cnpj/{cnpj}/network`: teia N2.
- `/api/v1/analytics/cnpj/{cnpj}/network/expand/{target_id}`: se `target_id` limpo tem 11 digitos expande CPF para N4; caso contrario expande CNPJ para N3.
- `/api/v1/analytics/cnpj/{cnpj}/network/level/3` e `/level/4`: expansao em lote de todos os N3/N4.
- `/api/v1/analytics/cnpj/{cnpj}/nota-tecnica`: gera `.docx` via `nota_tecnica.py` e retorna `StreamingResponse`.
- `/api/v1/geo/localidades`: hierarquia UF/regiao/municipio/unidade PF a partir do cache.
- `/api/v1/geo/estabelecimentos`: coordenadas e risco de farmacias geocodificadas para mapas/PDF.
- `/api/v1/cache/status` e `/refresh`: status e refresh de cache.
- `/api/v1/preferences`, `/preferences/filters`, `/preferences/watchlist`, `/preferences/ui`: preferencias locais persistidas em JSON pelo backend.

### Backend - services analytics
- `analytics/__init__.py`: fachada `AnalyticsService`; nao coloque regra nova aqui, apenas exponha funcoes dos modulos.
- `analytics/dashboard.py`: resumo do dashboard e rede por CNPJ raiz. Faz filtros/aggregations em Polars; calcula KPIs, UF, municipios e CNPJs.
- `analytics/regional.py`: faixas de risco, benchmarking regional, animacao regional, percentis e lookup CNPJ. Ponto sensivel para politica `regiao_id`.
- `analytics/farmacia.py`: status/cadastro do CNPJ e memoria de calculo. Ponto sensivel de cache por CNPJ.
- `analytics/financeiro.py`: evolucao financeira semestral, evolucao mensal GTIN e detalhamento por periodo.
- `analytics/indicadores.py`: `INDICATOR_MAPPING`, `_INDICATOR_FLAGS`, detalhe por CNPJ e analise cruzada por indicador.
- `analytics/falecidos.py`: resumo, ranking e timeline de vendas associadas a CPF falecido.
- `analytics/crm.py`: maiores arquivos de regra CRM; top prescritores, perfis diario/horario, mapas de ritmo, alertas CRM unico/multiplo e raio-x.
- `analytics/socios.py`: socios diretos de farmacia.
- `analytics/network.py`: monta `NetworkResponse` a partir de Parquets de teia; `_build_network_node` e `_build_network_edge` sao o contrato entre backend e Cytoscape.
- `analytics/_cache.py`: sync por CNPJ para arquivos Parquet de CRM, mediana horaria e teia. `sync_network(cnpj)` gera `teia_grafo_nivel2/3/4_nodes.parquet` e `..._edges.parquet`.
- `analytics/nota_tecnica.py`: geracao do Word, graficos via Pillow e composicao de quadros. Usa outros services como fonte de contexto.

### Cache e dados
- `backend/data_cache.py` define `_CACHE_DIR` e prefere `sentinela_cache/` na raiz; em alguns cenarios tambem reconhece `backend/sentinela_cache/`.
- Arquivos globais principais: `movimentacao.parquet`, `perfil_estabelecimento.parquet`, `localidades.parquet`, `redes_farmaceuticas.parquet`, `matriz_risco.parquet`, `bench_crm_uf.parquet`, `bench_crm_regiao.parquet`, `bench_crm_br.parquet`, `farmacias.parquet`, `socios.parquet`, `teia_fonte_nivel2.parquet`, `teia_fonte_nivel3.parquet`, `teia_fonte_nivel4.parquet`, `medicamentos.parquet`.
- `movimentacao.parquet` e fato mensal magra: `id_cnpj`, `periodo`, `total_vendas`, `total_sem_comprovacao`, `total_qnt_vendas`, `total_qnt_sem_comprovacao`. Cadastro/geografia ficam em `perfil_estabelecimento.parquet`.
- `perfil_estabelecimento.parquet` e a dimensao cadastral/geografica por `id_cnpj`: `cnpj`, `uf`, `id_regiao_saude`, `id_ibge7`, `no_municipio`, razao/situacao cadastral, conexao, porte, rede, matriz e unidade PF.
- Getters globais: `get_df`, `get_rede_df`, `get_localidades_df`, `get_df_matriz_risco`, `get_df_bench_crm_uf`, `get_df_bench_crm_regiao`, `get_df_bench_crm_br`, `get_df_dados_farmacia`, `get_df_perfil_estabelecimento`, `get_df_dados_socios`, `get_df_teia_fonte_nivel2/3/4`, `get_medicamentos_df`, `get_cache_status`.
- Sync global no startup: `load_cache(engine)` tenta ler Parquets e sincronizar faltantes. `refresh_cache(engine)` forca recarga.
- Cache por CNPJ: `sentinela_cache/{cnpj}/` guarda memoria de calculo, dados CRM e teia. Os stores de detalhe mantem chaves `cnpj|inicio|fim` para evitar refetch.
- Regra de fallback: nao mascarar schema antigo ou dado obrigatorio ausente. Se uma coluna obrigatoria sumir, corrija a origem/cache/schema e falhe visivelmente.

### Frontend - estado global
- `stores/analytics.js`: estado do dashboard: `kpis`, `resultadoSentinelaUF`, `resultadoSentinelaUFNacional`, `resultadoMunicipios`, `resultadoCnpjs`, `fatorRisco`. `buildAnalyticsParams` monta params de filtros; `enrichedKpis` aplica labels/icones/cores de config.
- `stores/filters.js`: estado de filtros globais, ranges, periodo, sidebar, animacao e preferencias. Persiste em `localStorage` e backend. Cascata reversa: municipio define UF/regiao; regiao define UF; unidade PF pode definir UF.
- `stores/geo.js`: localidades, GeoJSON municipal, estabelecimentos geocodificados, lookup CNPJ e helpers O(1). `regioesPorUF` retorna `{label, value}` com `value` igual ao ID da regiao.
- `stores/cnpjDetail.js`: cache client-side das abas do estabelecimento. Centraliza fetch de cadastro, evolucao, movimento, indicadores, falecidos, CRM, socios, network, percentis, nota indireta e reset ao trocar CNPJ.
- `stores/cnpjNav.js`: indice ativo das abas de CNPJ.
- `stores/farmaciaLists.js`: lista de interesse/watchlist, observacoes e sincronizacao backend.
- `stores/config.js`: thresholds/configuracoes do sistema.
- `stores/theme.js`: modo claro/escuro, paleta e tokens CSS.
- `stores/recentCnpj.js`: ultimo CNPJ aberto.
- `stores/resultados.js` e `stores/indicadores.js`: stores menores legadas/auxiliares.

### Frontend - arquitetura de filtros
- `frontend/src/stores/filters.js` e a fonte unica dos filtros normalizados do frontend. Novas telas/composables devem consumir `filterStore.apiParams` ou getters especificos, em vez de reconstruir filtros manualmente.
- `apiParams` usa o contrato interno em camelCase (`regiaoId`, `idIbge7`, `situacaoRf`, `conexaoMs`, etc.). A conversao para query params snake_case acontece nos pontos de chamada da API, como `buildAnalyticsParams()` em `stores/analytics.js` e os getters `indicadoresApiParams`/`indicadoresTabelaApiParams` em `stores/filters.js`.
- As chaves estaveis (`apiParamsKey`, `nationalContextApiParamsKey`, `estabelecimentoFilterKey`, `indicadoresApiParamsKey`, `indicadoresTabelaApiParamsKey`) sao o mecanismo padrao para watchers, debounce e comparacao de filtros. Ao adicionar filtro novo, inclua-o nas chaves especificas que representam as telas afetadas.
- Para adicionar um filtro global novo: criar o estado bruto (`selected...`), incluir em `serializeFilters`, `applySavedFilters`, `resetFilters`, no watcher de persistencia e no `return` do store; normalizar em `apiParams`; mapear para snake_case nos params da API; e aplicar no backend endpoint/service correspondente.
- Em `/indicadores`, filtros que mudam o universo de CNPJs tambem devem entrar em `backend/api/services/analytics/indicadores.py`: `_build_indicador_scope_base`, `_build_indicador_dataset_cached`, `_INDICADOR_SCOPE_FILTER_FIELDS` e normalizador adequado. Paginacao/ordenacao nao entram na chave TTL. O cache tem duas camadas: `scope_base` por filtros e `indicador_dataset` por indicador+filtros.
- Backend: os filtros de farmacia (atributos da farmacia: cadastro, % e valor sem comprovacao, socios, teia, populacao, sequencias, volume atipico, UFs sem fronteira) viajam como um objeto unico, `FiltrosFarmacia` (`backend/api/services/analytics/filtros_farmacia.py`). Os endpoints o recebem via `Depends(filtros_farmacia)` (`endpoints/analytics.py`, declarada antes do primeiro endpoint que a usa) e o repassam inteiro aos services e a `build_perfil_filtrado(perfil, filtros=...)`. Nao declare os filtros um a um em endpoint nem os repasse parametro a parametro. Territorio (`uf`, `regiao_id`, `id_ibge7`), periodo e `cnpjs` ficam fora do objeto.
- Filtro de farmacia novo no backend: (1) campo em `FiltrosFarmacia`; (2) `Query` na dependencia `filtros_farmacia`; (3) normalizador em `_INDICADOR_SCOPE_FILTER_FIELDS` (chave de cache dos indicadores e da base de `/analises`); (4) normalizacao em `montar_filtros_farmacia` (`crm_analysis.py`); (5) a regra no ponto que a aplica (`build_perfil_filtrado` para filtros de perfil, ou o service). `tests/test_filtros_farmacia.py` falha se a dependencia, a chave de cache ou a analise de CRMs nao cobrirem o campo novo.
- Filtros regionais devem seguir a politica ID-first: `id_regiao_saude` no dado, `regiao_id` na API/funcao e nome textual apenas como label. Municipios usam `id_ibge7`.

### Frontend - composables importantes
- `useFilterParameters()`: camada de compatibilidade para codigo legado. A normalizacao oficial dos filtros vive em `stores/filters.js`; novos consumidores devem preferir `filterStore.apiParams` ou getters especificos.
- `useFetchAnalytics()`: watchers para refetch do dashboard conforme filtros e freshness.
- `useFetchIndicadores()`: watchers da tela de indicadores.
- `useSliderPeriodLogic()`: logica do slider mensal e atalhos de ano.
- `useFormatting()`: BRL, numeros, percentuais, CNPJ, datas e title case.
- `useRiskMetrics()`: label/severity/class/color por thresholds.
- `useChartStyles()` e `config/chartTheme.js`: padrao ECharts com tema reativo.
- `useStableTabState()` e `useFrozenData()`: evitam flicker durante reload/refresh de abas.
- `usePdfExport()`: exportacao PDF do detalhe CNPJ. Usa refs das abas, geoStore e dados ja carregados.
- `useSyncManager()`: polling e retentativa de sync de cache.

### Fluxo das telas
- Boot: `App.vue` chama cache status, dashboard, faixas de risco, localidades, GeoJSON municipal, estabelecimentos, lookup CNPJ e thresholds. Se cache nao estiver pronto, o app ainda sobe em modo degradado e o banner informa.
- Sidebar: `AppSidebar.vue` e `filters.js` controlam filtros globais, busca de estabelecimento, periodo e lock/colapso. Varios watchers mantem filtros coerentes.
- Nacional/UF/municipio: telas usam `analyticsStore` e `geoStore`; mapas usam ECharts + GeoJSON em `public/geo/`.
- CNPJ lista: `CnpjView.vue` usa resultados filtrados e navegacao para `/estabelecimentos/:cnpj`.
- Detalhe CNPJ: `CnpjDetailView.vue` normaliza rota, valida acesso via `/status`, reseta store ao trocar CNPJ, dispara eager load de todas as abas e faz fallback visual de CNPJ invalido/fora da base. Abas atuais: Evolucao, Diagnostico, Memoria, Indicadores, CRMs, Falecidos, Socios, Teia e Regional.
- Exportacao no detalhe: PDF usa `usePdfExport`; Nota Tecnica baixa blob do endpoint `.docx`.
- Indicadores: `IndicatorsView.vue` seleciona uma chave de `INDICATOR_GROUPS`, usa `indicadores-analise`, mostra KPIs, distribuicao, mapa e tabela CNPJ.
- Regional: benchmarking por UF/regiao ID, percentis e animacoes.
- Listas: `WatchlistView.vue` e `farmaciaLists.js`.
- Configuracoes: `SettingsView.vue` mexe em calibragem/thresholds e esconde sidebar.

### Teia societaria
- Backend: `network.py` sempre chama `sync_network(cnpj)` antes de ler Parquets, depois monta `NetworkNodeSchema` e `NetworkEdgeSchema`.
- N2: CNPJ alvo, socios diretos e empresas relacionadas. N3: socios de empresas N2. N4: empresas de socios N3.
- Contrato de node inclui `id`, `label`, `type`, `razao_social`, `nome_socio`, `nome_fantasia`, CNAEs, `municipio`, `uf`, `situacao_rf`, `is_falecido`, `is_cadunico`, `is_cnae_farmacia_ausente`.
- Contrato de edge inclui `id`, `source`, `target`, `label`, `type`, `is_ativo`, datas de entrada/exclusao.
- Frontend: `NetworkTab.vue` instancia Cytoscape, mantem `cy`, `selectedNode`, zoom, filtros de camada, busca, nivel atual, expansao e alertas.
- `utils/network/networkStylesheet.js`: classes visuais Cytoscape, incluindo nos falecidos, CadUnico, CNAE ausente e empresas inativas.
- `utils/network/networkNodeUtils.js`: normalizacao de busca, flags booleanas e classes por no.
- `utils/network/networkLayouts.js`/`networkLayoutEngine.js`: radial/comunidade/aneis. `computeRadialNetworkLayout` posiciona alvo no centro, socios diretos em elipse interna e demais nos em elipse externa. Ajusta escala para grafos densos.
- Nao remova flags do backend sem atualizar schema, node utils, stylesheet, painel de detalhe e alert overlays.

### Indicadores e SQL
- `src/indicadores/` contem SQLs que alimentam a matriz e tabelas finais. Eles sao a fonte metodologica dos indicadores.
- `frontend/src/config/riskConfig.js` define `INDICATOR_GROUPS` e thresholds de exibicao. `backend/api/services/analytics/indicadores.py` define o mapeamento real de colunas da matriz. Ao adicionar indicador, atualizar os dois lados e o SQL da matriz.
- Indicadores atuais por grupo:
  - Auditoria: `percentual_nao_comprovacao`.
  - Elegibilidade/clinica: `falecidos`, `incompatibilidade_patologica`.
  - Quantidade: `teto`, `polimedicamento`.
  - Financeiro: `ticket_medio`, `receita_paciente`, `per_capita`, `alto_custo`.
  - Automacao/geografia: `vendas_rapidas`, `volume_atipico`, `recorrencia_sistemica`, `dias_pico`, `dispersao_geografica`, `compra_unica`.
  - Integridade medica: `hhi_crm`, `exclusividade_crm`, `crms_irregulares`.
- `volume_atipico.sql`: calcula crescimento semestral atipico de faturamento; semestre valido exige 6 meses presentes e valor mensal minimo; risco semestral e excesso acima de 50% multiplicado por penalidade de nao comprovacao; `RISCO_FINAL` e soma dos excessos dividida pelas comparacoes.
- SQLs devem ser escritos para bases muito grandes: filtros cedo, temp tables indexadas, joins restritos, evitar scans e evitar logica O(n^2).

### Padroes de mudanca
- Para endpoint novo: criar schema em `backend/api/schemas`, funcao em `backend/api/services/...`, rota fina em `backend/api/endpoints`, registrar endpoint em `frontend/src/config/api.js`, criar/alterar store/composable, depois componente.
- Para tela nova: rota em `router/index.js`, view em `views/`, estado em store se compartilhado, constantes em `config/`, CSS usando tokens.
- Para filtro novo: adicionar em `filters.js`, serializacao/persistencia, UI na sidebar, `useFilterParameters`, `buildAnalyticsParams` e, no backend, o roteiro de `FiltrosFarmacia` (secao "Frontend - arquitetura de filtros").
- Para campo novo no cache/schema: atualizar SQL/sync em `data_cache.py` ou `_cache.py`, schema Pydantic, service que monta resposta, store/componente e qualquer inspector em `src/scripts/check_parquet_schema.py`.
- Para CNPJ detail: respeitar `resetAll()` ao trocar CNPJ e chaves de cache `cnpj|inicio|fim`. Evite carregar uma aba por fora da store quando o dado e compartilhado.
- Para regional: usar ID numerico do territorio; nome apenas para exibicao.
- Para UI: usar tokens CSS/tema/config, PrimeVue Tooltip, ToastService e configs centralizadas. Evitar hex novo em componente salvo necessidade justificada.

### Armadilhas conhecidas
- O `CLAUDE.md` tem regras mais antigas e algumas descricoes antigas; esta secao reflete a estrutura viva observada em 2026-05-13.
- Alguns nomes legados ainda falam em `regiao_saude`; nao copie esse padrao para logica nova.
- `resultadoSentinelaUFNacional` existe para manter o mapa do Brasil mesmo quando filtros regionais estao ativos.
- `CnpjDetailView.vue` faz eager load de muitas abas; alteracoes ali podem aumentar muito o tempo inicial.
- `network.py` atualmente sincroniza antes de ler teia; mexer nisso afeta performance e consistencia dos Parquets por CNPJ.
- `data_cache.py` carrega dataframes globais em memoria; mudancas de schema precisam invalidar/recriar Parquets.
- Muitos arquivos exibem acentuacao estranha no terminal Windows, mas o conteudo fonte deve ser tratado com cuidado para nao introduzir troca massiva de encoding.
- `git status` pode mostrar alteracoes do usuario. Nao reverta nada que nao seja explicitamente parte da tarefa.

---

## 1. Arquitetura Fullstack e Tech Stack
- **Frontend**: Vue 3 (Composition API) + Pinia + PrimeVue 3 + ECharts.
- **Backend**: FastAPI (Python 3.10+) + SQLAlchemy + Pydantic.
- **Ambiente**: Híbrido (Web + Desktop). Priorize compatibilidade com Windows e caminhos de rede.

## 2. Zero Hardcoding: O Ecossistema de Configurações
NUNCA utilize valores fixos nos componentes. Consulte sempre o arquivo correspondente em `frontend/src/config/`:

- **API (`api.js`)**: Todos os endpoints devem ser registrados aqui. Use a versão exportada (`API_ENDPOINTS`).
- **Constantes Gerais (`constants.js`)**: Fonte para labels (KPI_LABEL_MAP), prioridades (KPI_PRIORITY_ORDER) e timings do sistema.
- **Temas de Interface (`themeConfig.js`)**: Definições de cores de superfície (Light/Dark) e paletas de cores primárias.
- **Estilo de KPIs (`uiConfig.js`)**: Mapeamento de ícones e cores específicas para cada métrica estratégia (ex: 'VALOR TOTAL DE VENDAS').
- **Risco e Performance (`riskConfig.js`)**: Única fonte de verdade para thresholds de risco (Critical, High, Medium, Low) e suas cores associadas em badges e alertas.
- **Gráficos (`chartTheme.js`)**: SEMPRE use o hook `useChartTheme` para configurar ECharts. Ele garante que os gráficos mudem de cor automaticamente ao trocar o tema do sistema.
- **Opções de Filtro (`filterOptions.js`)**: Contém as listas estáticas para os Dropdowns (Situação RF, Porte, Grande Rede, etc.).

## 3. Reutilização de Código: Composables e Stores
- **Composables**: Utilize os hooks em `frontend/src/composables/`.
  - `useFilterParameters`: Obrigatório para sincronizar filtros da UI com requisições de API.
- **Pinia Stores**: Utilize as stores em `src/stores/` para estado global.
  - **DICA**: Getters reativos (como `enrichedKpis`) devem ser usados para injetar ícones e cores configurados no `uiConfig.js` nos dados brutos da API.

## 4. UI/UX e Design System
- **Desktop-first operacional**: O Sentinela nao tem versao mobile/tablet como alvo de design. Nao propor drawer, accordion, navegacao mobile ou adaptacoes especificas para telas estreitas, salvo pedido explicito do usuario. Priorize layouts desktop densos, estaveis e ergonomicos.
- **Variáveis CSS**: Use `var(--bg-color)`, `var(--text-color)`, `var(--primary-color)`. Não use hexadecimais no CSS dos componentes.
- **Tooltips**: Sempre utilize o `Tooltip` do PrimeVue para dicas, explicações e interações de hover. Evite `title` nativo do HTML quando o tooltip fizer parte da experiência de usuário.
- **RESTRIÇÕES DE FONTE**: NUNCA utilize fontes BOLD (`font-weight: 700`, `font-weight: 800`, `bold`). O peso máximo permitido é Semi-Bold (`600`) ou Medium (`500`). NUNCA utilize fontes do tipo MONO ou monospaced (ex: `font-variant-numeric: tabular-nums`, `font-family: monospace`), a não ser que explicitamente exigido para código puro.
- **Arbflow Design**: Mantenha a estética de glassmorphism, bordas suaves e as animações definidas em `animations.css`.
- **Feedback**: Utilize `ToastService` para mensagens do sistema e estados de loading durante requisições de API.

## 4.1 Performance Como Requisito
- **Pense em escala sempre**: Ao desenvolver qualquer método, função, computed, endpoint, service ou query SQL, considere performance desde o desenho inicial. O sistema trabalha com bases que podem chegar a bilhões de linhas.
- **Evite complexidade desnecessária**: Não use loops O(n²), recomputações reativas pesadas, joins amplos, scans completos ou transformações em memória quando houver alternativa mais eficiente.
- **Prefira estratégias escaláveis**: Use filtros antecipados, índices, pré-agregações, estruturas `Map`/lookup O(1), paginação, lazy loading, cache controlado e processamento no backend/banco quando isso reduzir volume trafegado ou trabalho no frontend.
- **Valide o custo**: Para funções críticas, considere o tamanho esperado dos dados, o caminho de execução mais frequente e o impacto em memória, CPU, rede e banco.

## 5. Padrões de Backend (Python/FastAPI)
- **Camadas**: Separação clara entre `endpoints`, `services` e `schemas` (Pydantic).
- **Tipagem e Documentação**: SEMPRE utilize Type Hinting. Use Docstrings no estilo Google/NumPy para explicar parâmetros e retornos.

## 6. Git e Padronização
- **Nomenclatura**: PascalCase para componentes Vue, snake_case para arquivos/funções Python.
- **Commits**: Utilize Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`).
- **Documentação**: Use JSDoc para funções JS críticas, focando no "porquê" de lógicas complexas.

## 7. Nomenclatura e Identificadores — Regras Críticas
- **NUNCA** use a palavra `surto` em nomes de tabelas, colunas, variáveis ou comentários SQL.
- **NUNCA** utilize `no_regiao_saude` (o nome da região) para filtragem, agrupamento, parâmetros de funções ou lógica de negócio.
- **SEMPRE** utilize `id_regiao_saude` (o ID numérico) como identificador primário para todas as operações regionais no frontend e backend.
