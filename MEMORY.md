# Memory — davinci_memanto

> Generated: 2026-11-09 20:26:05  
> Total memories: **105**  
> Breakdown: instruction: 3, fact: 19, decision: 25, commitment: 1, preference: 19, context: 2, learning: 25, artifact: 3, error: 8

---

## Instructions

*Standing rules, constraints, and guidelines to always follow.*

### Nuvoinvest workflow rule (from user, relayed by Jo...

> Nuvoinvest workflow rule (from user, relayed by Joti): do NOT write or run tests for a change while it is under review - tests are applied ONLY after the user validates the screen visually and confirms it is working. Favorites screen already validated (approve state: instant delete + atomic zebra + soft fade only on entering row + zero-effect pagination via keepPreviousData); alerts screen awaits user validation before its guard spec is (re)written.

*Confidence: 1 | Status: active | Created: 2026-09-18T12:14:26 | Tags: `workflow`, `testing`, `frontend`*

### Nuvoinvest workflow rule from user: never run the ...

> Nuvoinvest workflow rule from user: never run the full test suite (frontend vitest run without filters, or equivalent) without explicit authorization - it is too large. Always run only the targeted spec files relevant to the changed code.

*Confidence: 1 | Status: active | Created: 2026-09-18T10:03:45 | Tags: `testing`, `workflow`, `frontend`*

### Overflowing card rows in NuvoInvest use pagination...

> NuvoInvest home radar pager (HomeRadarSnapshot): the user ACCEPTED the current chevron-pager carousel on 2026-09-23 ('esta funcionando agora') — chevron PrimeVue buttons step a scroll-snap-type: x mandatory strip, a window-track shows progress, and is-peek (86% flex-basis) lets the next card peek as a swipe cue. This SUPERSEDES the earlier dots-only/no-arrows/no-partial-cards rule for the home radar; do not flag this implementation as a violation again. For a NEW overflowing card row in another context, ask the user which style they want instead of assuming either pattern.

*Confidence: 1 | Status: active | Created: 2026-09-24T00:07:01 | Tags: `ui`, `carousel`, `pagination`, `home`, `radar`*

---

## Facts

*Verified information, project status, and established truths.*

### O gate de visibilidade por status de import (plano...

> O gate de visibilidade por status de import (plano do guard FRE) nao remove o lixo legado ja commitado: em 2026-09-16 havia 13 grupos de linhas FRE em cadastro CANCELADA com gemeo ATIVO (incl. Itau CNPJ 60.872.504/0001-23 com 1259 linhas), todos de imports COMPLETED — invisiveis aos leitores (presos ao cvm_code antigo) mas persistentes. Re-import --force limpa share_counts por ano, porem linhas de ownership presas a cadastro CANCELADA sobrevivem ao re-import porque o upsert de sync_ownership so encontra linhas chaveadas pelo cadastro ATIVO; a limpeza correta exige DELETE dirigido das linhas FRE em cadastro nao-ATIVO com gemeo ATIVO.

*Confidence: 0.95 | Status: active | Created: 2026-09-16T23:42:26 | Tags: `fre`, `cvm`, `guard`, `legado`, `cleanup`, `itau`, `bmg`*

### A API de indicadores fundamentalistas do Nuvoinves...

> A API de indicadores fundamentalistas do Nuvoinvest roda exclusivamente listing-first e materializada: rotas GET /api/v1/assets/listings/{asset_listing_id}/fundamental-indicators[/history] leem fundamental_indicator_current JOIN fundamental_indicator_snapshots; a versão anual ativa vem da tabela fundamental_methodology_registry (famílias annual/current, max 1 ACTIVE). A flag FUNDAMENTAL_INDICATOR_SOURCE e as rotas /stocks/{ticker}/indicators foram removidas; radar continua no cálculo legado por decisão de escopo. Listagens EXCLUDED do universo do radar (73, ex.: BBAS3, ITSA4) não têm snapshot e recebem 503 explícito na página da ação — política, não bug.

*Confidence: 1 | Status: active | Created: 2026-09-15T23:10:56 | Tags: `fundamentals`, `snapshots`, `listing-first`, `api`, `radar-universe`*

### Multi-row INSERT com pg_insert tem teto de 65535 p...

> Multi-row INSERT com pg_insert tem teto de 65535 parametros por statement no PostgreSQL: fundamental_indicator_snapshots usa 58 params/linha (19 fixos + 39 indicadores), limitando a 1129 linhas por insert; ao expandir o universo (ex.: FIIs) ou criar inserts multi-row novos, fazer chunking (~500 linhas) mantendo a soma dos RETURNING por chunk

*Confidence: 0.95 | Status: active | Created: 2026-09-16T17:05:15 | Tags: `postgres`, `insert-limit`, `fundamental-indicators`, `chunking`*

### BAZA3/HETA4/JOPA3/RPMG3/RIAA3 nunca terao share counts do FRE (so Subscrito/Autorizado ou ausentes)

> Empresas que o FRE da CVM nunca declara composicao utilizavel (so 'Capital Subscrito' ou 'Capital Autorizado', tipos que o parser filtra de proposito) ficam sem share counts em qualquer ano e seus emissores sao NULL permanente no radar/indicadores: BAZA3 (BCO Amazonia, so Capital Subscrito), HETA4 (Hercules, so Subscrito), JOPA3 (Josapar, so Autorizado), RPMG3 (Manguinhos, ausente do FRE), RIAA3 (Riachuelo, ausente do FRE e sem registration no cadastro). Confirmado nos arquivos brutos fre_cia_aberta_capital_social 2025 e 2026 em 2026-09-15. Nao e instabilidade de import: nunca tiveram valor no radar desde 2026-09-10.

*Confidence: 1 | Status: active | Created: 2026-09-16T00:29:46 | Tags: `fre`, `cvm`, `share-counts`, `capital-subscrito`, `capital-autorizado`, `baza3`, `jopa3`*

### FRE grava share counts em registration CANCELADA quando CNPJ tem dois cvm_codes

> Quando um mesmo CNPJ tem duas cvm_company_registrations (codigo antigo CANCELADA + codigo novo Ativo), o sync_cvm_fre grava os share counts na registration que o dict de load_registrations (chave tax_id, SELECT sem ORDER BY) retornar por ultimo - resultado nao deterministico. O radar e o loader de valor de emissor resolvem o cvm_code via asset_issuer_identifiers priorizando provider B3, que aponta para o codigo NOVO. Se os counts cairem no cadastro antigo, o emissor fica NULL permanentemente (join sem match). Vitimas confirmadas em 2026-09-15: ITUB 1279/19348, BMG 1716/24600, VIBRA 14249/24295, LWSA 21407/24910, SHOW 21326/22454. LWSA3 e VBBR3 ficaram NULL apos os re-imports FRE forçados de 2026-09-14; ITUB e BMGB4 nunca tiveram valor. Correcao provavel: load_registrations deve preferir registration_status='Ativo' (ORDER BY deterministico) ou deduplicar por CNPJ.

*Confidence: 1 | Status: active | Created: 2026-09-16T00:29:40 | Tags: `fre`, `cvm`, `share-counts`, `radar`, `determinismo`, `registrations`*

### No Nuvoinvest, o metadata do Screener (ScreenerUni...

> No Nuvoinvest, o metadata do Screener (ScreenerUniverseMetadata) declara a moeda do universo no backend (campo currency, ex: BRL para B3); o frontend nunca hardcodar moeda em formatacoes de chips/criterios, e os valores de sort_by/strategy vindos da URL sao validados contra o catalogo do metadata (sorts/default_sort) com fallback ao default antes de chamar a API, em vez de propagar 422.

*Confidence: 0.9 | Status: active | Created: 2026-09-15T16:46:01 | Tags: `screener`, `frontend`, `metadata`, `currency`, `url-validation`*

### Cobertura de proventos do NuvoInvest: asset_divide...

> Cobertura de proventos do NuvoInvest: asset_dividend_events (fonte INVESTIDOR10) so tem eventos de BR_STOCK, e nem de toda acao (ex.: PETR4 nao tem, PETR3 tem). Para FIIs, ETFs e acoes sem eventos, market_daily_prices_adjusted e so preco. Qualquer retorno 'com proventos' deve decidir cobertura por listagem e marcar o resto como somente preco, sem comparar com quem inclui proventos.

*Confidence: 1 | Status: active | Created: 2026-10-08T01:55:50 | Tags: `data`, `dividends`, `adjusted-prices`, `analytics`, `comparator`*

### O refresh do Radar é idempotente por hora: quando ...

> O refresh do Radar é idempotente por hora: quando o snapshot da hora tem schema/metodologia e itens compatíveis, uma execução manual o reutiliza e republica sem gerar nova versão. O status DEGRADED pode ser esperado quando há misses do Redis cobertos por fallback PostgreSQL; a condição crítica é missing_price_count igual a zero.

*Confidence: 1 | Status: active | Created: 2026-09-14T01:39:51 | Tags: `radar`, `snapshot`, `idempotency`, `redis-fallback`, `data-quality`*

### cvm_company_registrations.registration_status mist...

> cvm_company_registrations.registration_status mistura dois vocabularios: o CAD grava ATIVO/CANCELADA e o FCA grava Ativo/Cancelado/Suspenso na mesma coluna, e a ultima sincronizacao vence. Para decidir se um cadastro esta no FCA atual use fca_source_import_id IS NOT NULL, nunca o texto de situacao; presenca no FCA nao equivale a ativo (ha Cancelado e Suspenso no FCA).

*Confidence: 0.95 | Status: active | Created: 2026-10-13T16:10:37 | Tags: `cvm`, `cadastro`, `status`, `fca`, `armadilha`*

### No NuvoInvest, uma rota publica do backend precisa...

> No NuvoInvest, uma rota publica do backend precisa constar em DUAS listas: backend/auth/perimeter_middleware.py e frontend/server/utils/backendAuthPolicy.ts (BFF), mais os testes tests/test_perimeter_middleware.py e frontend/tests/unit/server/backendAuthPolicy.spec.ts. Faltando qualquer uma, a rota responde 401 (Missing NuvoInvest BFF assertion) mesmo sem exigir login.

*Confidence: 1 | Status: active | Created: 2026-10-08T01:55:46 | Tags: `backend`, `frontend`, `bff`, `auth`, `public-routes`*

### Nao criar indices por reference_date nas tabelas F...

> Nao criar indices por reference_date nas tabelas FRE cvm_company_shareholders e cvm_company_ownership_summaries sem medida que justifique: verificado com EXPLAIN ANALYZE na serie completa carregada (304k acionistas, 2015-2026) em 2026-09-16, todos os fetches bulk do sync_ownership custam ~40ms por import de ano; so reconsiderar se a serie crescer cerca de 10x

*Confidence: 0.9 | Status: active | Created: 2026-09-16T03:28:40 | Tags: `fre`, `cvm`, `performance`, `indexes`, `backfill`*

### O backend legado do Radar de oportunidades (backen...

> O backend legado do Radar de oportunidades (backend/api/endpoints/radar.py com /radar/assets, /radar/metadata, /radar/methodology e as tabelas radar_snapshots em models_radar.py) esta ULTRAPASSADO/abandonado conforme o usuario (2026-09-22): a integracao do Radar da home deve consumir dados do Screener (endpoints /api/v1/screener/*, incluindo /screener/strategies), nunca essas rotas antigas.

*Confidence: 0.95 | Status: active | Created: 2026-09-22T18:10:45 | Tags: `radar`, `screener`, `integration`, `deprecated`, `home`*

### BPAC sem classe_acao no FRE 2026 e MULT3/RIAA3 com identifiers B3 divergentes do cadastro CVM

> Dois gaps de identidade que produzem emissor NULL no loader de valor de mercado: (1) O FRE 2026 do BTG Pactual (BPAC) nao tem nenhuma linha em fre_cia_aberta_capital_social_classe_acao_2026 (em 2025 tinha PNA/PNB), entao o snapshot 2026-12-31 fica sem breakdown por classe e o lookup PNA do loader retorna NULL -> BPAC3/BPAC5 NULL (D4b). (2) O catalogo B3 pode dar identifiers divergentes ao emissor: MULT3 recebeu CVM_CODE 900441 e CNPJ 29401298000123 via B3, mas o cadastro CVM tem Multiplan como codigo 20982/CNPJ 07816890000153 com 12 share counts - os dados existem mas o join do loader nunca bate. Identifier-based join (ORDER BY provider, id LIMIT 1) deve ser reconciliado com o cadastro.

*Confidence: 1 | Status: active | Created: 2026-09-16T00:30:01 | Tags: `fre`, `cvm`, `bpac5`, `mult3`, `riaa3`, `classes`, `identifiers`*

### O importador de FRE da CVM (sync_cvm_fre) passou d...

> O importador de FRE da CVM (sync_cvm_fre) passou de fotografia para serie historica: purge por escopo de ano (source_import_id via cvm_fre_imports.reference_year) em vez de clear-all, modo CLI --from-year/--to-year com strict_registrations=False para anos antigos (empresas fora do cadastro viram contador visivel, nao bloqueiam). O parser resolve multiplos grupos de Capital Emitido na mesma data (caso JBS N.V. 2024: dois ID_Capital_Social) mantendo o de maior ID, com contador multiple_capital_groups; so divergencia no MESMO ID e erro. Format variance dos anos antigos: colunas booleanas S/N vazias = False, e placeholder 00.000.000/0000-00 em CPF_CNPJ_Acionista = ausente. Colunas percent das tabelas FRE alargadas de Numeric(9,6) para Numeric(18,6) (fonte traz percentuais como 34644%). Serie importada em dev: 2015-2026. A convensao DT_REFER muda em 2023: antes 01/01 do ciclo, depois 31/12; zip do ano Y sempre corresponde ao ano fiscal Y. Backfill anual publicou catálogo completo (mcap, P/VP, VPA, payout, EV) com contagem da epoca: 1524 linhas OK; validado com Oi (grupamento 100:1: 6,6bi -> 66mi acoes) e Petrobras.

*Confidence: 1 | Status: active | Created: 2026-09-14T19:44:19 | Tags: `fre`, `cvm`, `historico`, `share-counts`, `backfill`, `parser`*

### Lucro dos controladores (conta 3.11.01 da DRE CVM)...

> Lucro dos controladores (conta 3.11.01 da DRE CVM) virou coluna de primeira classe controllers_net_income em asset_income_statements (migration 20260914_2300 com backfill scale-aware do raw_payload; 21.496 registros 1:1 com o payload). O importador popula via INCOME_STATEMENT_MAP ('3.11.01'), compute_ttm e o ttm_income do assembler do Radar somam TTM com COALESCE fallback para net_income quando um trimestre nao traz a conta. LPA, P/L e earnings yield usam essa base (controladores, minoritarios excluidos) tanto no atual (TTM) quanto no anual; ROE e margens seguem consolidados. Validacao: PETR4 atual P/L 5,04 (TTM controladores ~ R33bi, igual ao Investidor10), anual 2022 LPA 14,44 = declarado na DRE. TTM do assembler: cuidado que o CTE ttm_income lista colunas explicitas — campo novo precisa ser adicionado la tambem, nao so no CASE.

*Confidence: 1 | Status: active | Created: 2026-09-15T00:16:36 | Tags: `dre`, `cvm`, `ttm`, `controladores`, `lpa`, `metodologia`*

### Fallback de rateio de classes no backfill anual (2...

> Fallback de rateio de classes no backfill anual (2026-09-14): quando o FRE do ano declara o total de preferenciais mas nao traz o detalhe PNA/PNB (caso Usiminas 2025), o valor de mercado consolidado usa o ultimo detalhamento por classe declarado em anos anteriores, com flag CLASS_RATIO_ESTIMATED na linha. Tambem: listings UNIT sao excluidos do somatorio do emissor (sao cestos de ON+PN, sem quantidade propria); classes sem pregao na data de referencia usam o ultimo preco do ano fiscal com flag STALE_CLASS_PRICE. Estado final em dev: 2412 linhas anuais, 2122 OK, 290 PARTIAL (116 com mcap + aviso), cobertura de mcap 2238/2412 (93%). Suíte 2161 passed.

*Confidence: 1 | Status: active | Created: 2026-09-14T21:41:44 | Tags: `fre`, `backfill`, `rateio`, `flags`, `metodologia`*

### Em cvm_company_registrations o CNPJ nao e chave un...

> Em cvm_company_registrations o CNPJ nao e chave unica: ha 34 CNPJs com mais de um cadastro. Entre eles, 13 tem um cadastro ativo presente no FCA (fca_source_import_id nao nulo) e 21 tem somente cadastros CANCELADA. Vinculos por CNPJ devem considerar o conjunto FCA atual, nunca apenas o CNPJ.

*Confidence: 0.95 | Status: active | Created: 2026-10-13T15:56:42 | Tags: `cvm`, `cnpj`, `cadastro`, `fca`*

### O CSV de valor mobiliario do FCA da CVM pode traze...

> O CSV de valor mobiliario do FCA da CVM pode trazer Codigo_Negociacao em minusculas; nao garante uppercase nem formato de ticker. Preservar o texto de origem nao torna segura uma busca por igualdade com o ticker da URL convertido para maiusculas. Evidencia: arquivo local de 2026 contem tgma3 (B3) e muuu4.

*Confidence: 1 | Status: active | Created: 2026-10-13T17:16:01 | Tags: `cvm-fca`, `ticker`, `case-sensitivity`, `source-contract`*

### As linhas de composicao de capital do FRE da CVM s...

> As linhas de composicao de capital do FRE da CVM sao inconsistentes no rótulo Tipo_Capital: muitos empresa-anos (sobretudo antes da padronizacao de 2022) so trazem 'Capital Integralizado', nunca 'Capital Emitido'. O parse_share_counts usa precedencia documentada Emitido -> Integralizado (nunca Autorizado, que e teto) com contador integralizado_fallback_keys no resultado do import. Com isso o backfill anual recuperou 509 linhas (888 -> 379 PARTIAL; 1524 -> 2033 OK): as 107 empresas 'sem FRE' eram na maioria presentes nos arquivos, apenas sem a linha Emitido (EMAE4, EQTL3, CSAN3, ALPA3, CYRE3). Diagnostico com grep em CSV latin1 precisa de grep -a (trata como binario e engana).

*Confidence: 1 | Status: active | Created: 2026-09-14T20:23:14 | Tags: `fre`, `cvm`, `integralizado`, `parser`, `partiais`*

---

## Decisions

*Architectural choices, approach selections, and their rationale.*

### Todo leitor das tabelas FRE (cvm_company_share_cou...

> Todo leitor das tabelas FRE (cvm_company_share_counts, cvm_company_ownership_summaries, cvm_company_shareholders) deve aplicar o helper rows_from_completed_imports(model) de backend/db/repositories/cvm_fre.py — gate de publicacao que restringe linhas a imports COMPLETED, porque o importador commita em lotes intermediarios e linhas de import PROCESSING/FAILED existem fisicamente. Lookups internos do importador (purge, adoption, sync) nao usam o filtro. Implementado no plano do guard FRE (fase 1, 2026-09-16).

*Confidence: 0.95 | Status: active | Created: 2026-09-16T23:50:54 | Tags: `fre`, `cvm`, `publication-gate`, `leitores`, `arquitetura`*

### No Nuvoinvest, a lista de universos (classes de at...

> No Nuvoinvest, a lista de universos (classes de ativo) do toggle do /screener deve permanecer uma lista fixa no frontend (SCREENER_KNOWN_ASSET_CLASSES em types/screener.ts + assetClassOptions em screener.vue); nao criar endpoint dinamico de listagem de universos — o usuario rejeitou a ideia por ser uma chamada a mais para algo que raramente muda. Ao adicionar um novo universo, atualizar: SCREENER_KNOWN_ASSET_CLASSES, assetClassOptions, mapas de metricas em useScreener.ts e POPULAR_METRICS_BY_ASSET_CLASS, chaves i18n screener.assetClasses.*, e o adapter em backend/screener/universes.py

*Confidence: 0.95 | Status: active | Created: 2026-09-23T00:26:12 | Tags: `screener`, `frontend`, `asset-class`, `hardcoded`, `decisao-usuario`*

### No NuvoInvest, ativos deslistados ou fora do unive...

> No NuvoInvest, ativos deslistados ou fora do universo elegivel devem MANTER sua linha congelada em fundamental_indicator_current (nunca deletar): o usuario definiu que dados/historico de tickers deslistados devem permanecer acessiveis. Jobs de enriquecimento devem pular linha sem dado recente em vez de sobrescrever com NULL.

*Confidence: 1 | Status: active | Created: 2026-09-17T01:34:05 | Tags: `nuvoinvest`, `screener`, `delisted`, `data-retention`, `fundamental_indicator_current`*

### No frontend do NuvoInvest, NormalizedHttpError inc...

> No frontend do NuvoInvest, NormalizedHttpError inclui origem explicita (http, transport, local ou cancelled); somente falhas de transporte verificadas e status HTTP transitórios permitidos são retryable. A ausência de status nunca deve, sozinha, classificar erro local ou violação de contrato como falha de rede.

*Confidence: 1 | Status: active | Created: 2026-09-21T18:57:32 | Tags: `nuvoinvest`, `frontend`, `error-handling`, `retry`, `contracts`*

### No NuvoInvest, ausencia de dado conhecida nao e 40...

> No NuvoInvest, ausencia de dado conhecida nao e 404: um recurso existente sem itens responde lista vazia com o status da fonte (o que foi confirmado vs. nao sabido), e a UI so afirma 'nao houve' quando a fonte confirmou; 404 fica para recurso inexistente.

*Confidence: 0.9 | Status: active | Created: 2026-11-09T11:08:08 | Tags: `nuvoinvest`, `api`, `contract`, `empty-state`*

### Rota publica de entidade com identidade de negocio...

> Rota publica de entidade com identidade de negocio (titulo do Tesouro): o slug e persistido com constraint unica e gravado uma vez, nunca recalculado na leitura, porque a URL precisa ser estavel. O nome da API do Tesouro Direto prevalece (traz o ano); o nome do Transparente so da rota a titulo ja vencido, porque a API nao lista vencidos. Colisao recusa a importacao inteira com a identificacao dos titulos. Catalogo e /atuais listam so titulos com rota; listing sem titulo de varejo tem rota nula e o builder devolve null.

*Confidence: 0.9 | Status: active | Created: 2026-10-13T14:54:01 | Tags: `url-routing`, `identity`, `stable-slug`, `tesouro-direto`*

### O historico anual de indicadores fundamentalistas ...

> O historico anual de indicadores fundamentalistas (fundamentals-v1-annual) usa o lucro por acao declarado na DRE CVM (conta 3.99.01 da classe ON/PN da listagem) para calcular P/L, LPA e earnings yield por ano fiscal, sem precisar da serie historica de contagem de acoes; indicadores dependentes de acoes por ano ficam NULL com flag MISSING_HISTORICAL_SHARE_COUNT ate a importacao da serie de capital da CVM; LPA exatamente zero na DRE e tratado como nao declarado (flag MISSING_DISCLOSED_EPS), perdas negativas sao validas. O Investidor10 usa a mesma abordagem (metodologia confirmada por engenharia reversa da API historico-indicadores).

*Confidence: 1 | Status: active | Created: 2026-09-14T18:29:37 | Tags: `fundamentals`, `backfill`, `dre`, `cvm`, `eps`, `metodologia`*

### Nuvoinvest: listas archive de paginas (padrao /new...

> Nuvoinvest: listas archive de paginas (padrao /news) devem usar stale-while-loading em trocas de contexto (busca, filtro, locale): a lista anterior permanece montada e esmaecida (.archive-grid.is-refreshing com opacity .5 + pointer-events none) enquanto a nova carrega, com skeleton apenas quando nao ha nada a exibir (primeira carga, lista anterior vazia) e painel de erro assumindo em falha. Implementado em frontend/app/pages/news/index.vue: archivePending = (articlesStatus idle || articles vazio) && !articlesError; loadMore bloqueia appends enquanto isLoadingDisplayed (sentinel permanece montado durante stale-while-loading). Validado com 821 testes unitarios e instrumentacao de DOM mostrando zero unmount de archive-body entre ciclos de busca.

*Confidence: 0.95 | Status: active | Created: 2026-09-21T17:17:30 | Tags: `frontend`, `news`, `stale-while-loading`, `flicker`, `ux`*

### No NuvoInvest, dado declarado pela empresa (ex.: L...

> No NuvoInvest, dado declarado pela empresa (ex.: LPA da DRE) nunca e corrigido por regra automatica: regras automaticas so escolhem linha de forma deterministica ou rejeitam incoerencia comprovada (com flag); correcao de valor so via tabela de overrides revisados (identidade da linha da fonte + valor visto, motivo, evidencia, autor, revogavel), no padrao de asset_corporate_action_overrides.

*Confidence: 0.9 | Status: active | Created: 2026-11-09T12:24:35 | Tags: `nuvoinvest`, `data-quality`, `overrides`, `fundamentals`*

### No Nuvoinvest, o estado do screener segue um model...

> No Nuvoinvest, o estado do screener segue um modelo duplo: tudo que define o conjunto de resultados (search, filtros, sort, strategy, page) vive apenas na URL para links compartilhaveis, enquanto page_size e preferencia de UI por usuario persistida em localStorage (nuvoinvest_screener_view_state:<user_id>, mesmo modelo do favorites view state). O parser (parseScreenerQuery) so usa o valor persistido quando a URL omite page_size — URL sempre vence; apenas mudanca explicita de tamanho no dropdown (setPage com pageSize diferente do atual) regrava a preferencia, e a validacao no restore e contra as opcoes do dropdown (SCREENER_PAGE_SIZE_OPTIONS, fonte unica na composable useScreener.ts).

*Confidence: 0.9 | Status: active | Created: 2026-09-22T18:45:13 | Tags: `frontend`, `screener`, `pagination`, `localstorage`, `url-state`, `preferences`*

### No Nuvoinvest (2026-09-22), as estrategias prontas...

> No Nuvoinvest (2026-09-22), as estrategias prontas do Screener ficaram escopadas por universo: screener_strategies.asset_class (NOT NULL, sem server default; todo seed deve declarar) e registro SCREENER_UNIVERSES em backend/api/endpoints/screener.py com pares (market_scope, asset_class) — hoje B3/BR_STOCK e B3/BR_FII. /screener/strategies e /screener/fundamentals aceitam market_scope/asset_class, rejeitam par nao registrado com 422 e recusam estrategia de outro universo com 422. /screener/fundamentals/metadata continua mono-universo (BR_STOCK) de proposito. Metricas em screener_metric_definitions continuam GLOBAIS por decisao: scoping de metricas so quando a engine de indicadores de FII existir. Primeira estrategia BR_FII semeada: dividendos-imobiliarios (dividend_yield>=8, price_book<=1.2), registrada a frente dos dados — /strategies?asset_class=BR_FII responde 503 (universo nao materializado) ate a engine de FIIs rodar. Migration: 20260922_1100.

*Confidence: 0.95 | Status: active | Created: 2026-09-22T18:46:16 | Tags: `screener`, `strategies`, `asset-class`, `universes`, `fii`, `migration`, `api`*

### NuvoInvest esta em pre-lancamento e nao tem usuari...

> NuvoInvest esta em pre-lancamento e nao tem usuarios ativos (confirmado pelo usuario em 2026-10-13). Enquanto isso valer, nao manter compatibilidade com URLs, contratos ou links antigos e nao criar redirecionamentos legados. Reavaliar no lancamento.

*Confidence: 0.9 | Status: active | Created: 2026-10-13T14:16:49 | Tags: `nuvoinvest`, `product-stage`, `backward-compatibility`*

### No Nuvoinvest, o card de pagina inteira 'temporari...

> No Nuvoinvest, o card de pagina inteira 'temporariamente indisponivel' (ServiceUnavailableState) e reservado ao recurso principal da pagina (ex: catalogo de filtros e resultados do screener); lookups secundarios (ex: strategies do screener) falham com painel inline na propria secao, com retry proprio e latch de erro — nunca acoplar requests secundarios ao gate de prontidao da pagina inteira, nem combinar erros de requests independentes em uma unica superficie de erro.

*Confidence: 0.9 | Status: active | Created: 2026-09-21T11:24:17 | Tags: `frontend`, `screener`, `availability-states`, `error-handling`, `ui`*

### Selo de viabilidade do NuvoInvest: objetivo e publ...

> Selo de viabilidade do NuvoInvest: objetivo e publicar um rotulo por ativo na pagina do ativo, calculado pelo job periodico de indicadores como um campo a mais (sem relatorio de pesquisa separado). Bancos e seguradoras ficam como perfil nao coberto; direitos (tag along) exigem revisao por listagem. O usuario prefere planos simples.

*Confidence: 0.9 | Status: active | Created: 2026-10-13T21:27:26 | Tags: `selo-viabilidade`, `asset-quality`, `produto`, `pipeline`*

### Cotacoes em lote do NuvoInvest: GET /api/v1/assets...

> Cotacoes em lote do NuvoInvest: GET /api/v1/assets/latest-market-prices?listing_ids=a,b,c (max 20) devolve {listing_id, ticker, currency, latest_market_price} resolvendo snapshots canonicos do Redis via MGET com fallback Postgres que repovoa o cache em pipeline unico (store_last_prices); ids desconhecidos -> 404 explicito. A busca da home consome com debounce de 350ms (uma chamada por busca estabilizada, nunca por tecla) e TTL local de 60s por listing_id na market store (re-busca dentro do TTL nao refaz request); a view por opcao e um computed map indexado por listing_id, exibindo preco + daily_change_percent na linha reservada sob cada sugestao, com shimmer enquanto carrega

*Confidence: 0.95 | Status: active | Created: 2026-09-22T14:52:23 | Tags: `backend-api`, `market`, `quotes`, `home-search`, `batch-endpoint`*

### No NuvoInvest, a busca de ativos da Home tem dois ...

> No NuvoInvest, a busca de ativos da Home tem dois contextos: a Hero pode exibir um painel amplo com a lista de ativos e noticias relacionadas; a busca Sticky permanece compacta e exibe apenas a lista de ativos. Ambas compartilham o catalogo, limitam a cinco sugestoes e nao devem impor uma viewport interna com scrollbar artificial.

*Confidence: 1 | Status: active | Created: 2026-09-22T16:29:14 | Tags: `frontend`, `search`, `hero`, `sticky`, `ux`*

### No sync_ownership do importador CVM FRE (cvm_fre.p...

> No sync_ownership do importador CVM FRE (cvm_fre.py), nenhum indice de resolucao pode materializar entidades ORM: todos os upserts usam indices de tupla (id, owning_year) com updates via UPDATE direto por pk, porque objetos ORM lidos apos os commits intermediarios do batch_callback expiram (expire_on_commit=True) e custam um refresh SELECT por linha. Toda mudanca nesse upsert deve ser precedida dos testes de caracterizacao em test_cvm_fre_repository.py (estado final + dict completo de contadores com batch_size=2) e validada contra o baseline historico do core_job_runs.

*Confidence: 1 | Status: active | Created: 2026-09-16T23:25:52 | Tags: `fre`, `cvm`, `sync-ownership`, `tuple-index`, `performance`, `refactor`*

### Suspensao de retry de transporte (ofetch) em ciclo...

> Suspensao de retry de transporte (ofetch) em ciclos de retry concorrentes deve usar contador de leases por tentativa (increment na entrada, decrement clampado no finally), nunca flag booleana compartilhada; o finally de um ciclo nao pode derrubar a suspensao de outro. Aplicado em alerts.vue via transportRetryLeases + getTransportRetry.

*Confidence: 0.9 | Status: active | Created: 2026-09-21T13:23:48 | Tags: `nuvoinvest`, `frontend`, `retry`, `retry-cycle`, `ofetch`, `tanstack-query`, `concurrency`*

### No Nuvoinvest, enquanto o sistema estiver em desen...

> No Nuvoinvest, enquanto o sistema estiver em desenvolvimento e sem usuários, migrações de API não mantêm caminho legado, flag de rollback nem janela de transição: o código antigo é removido no mesmo change e o rollback operacional é redeploy da versão anterior. Aplicado na migração da API de indicadores fundamentalistas (fundamental_indicator_snapshots): rotas listing-first por asset_listing_id, rotas /stocks/{ticker}/indicators removidas, flag FUNDAMENTAL_INDICATOR_SOURCE deletada do config, radar fica fora do escopo (migração futura para snapshots).

*Confidence: 1 | Status: active | Created: 2026-09-15T21:50:00 | Tags: `fundamentals`, `snapshots`, `api-migration`, `no-legacy`, `listing-first`*

### Busca de noticias do NuvoInvest: GET /api/v1/news ...

> Busca de noticias do NuvoInvest: GET /api/v1/news aceita title_only (default false) que restringe os tres caminhos de busca (query_by do Typesense, filtro Postgres de artigos pendentes de indexacao e fallback degradado) a casar apenas no titulo; apenas o widget de busca da home envia title_only=true e exibe article.title no card — a pagina /news permanece full-text (titulo+dek+corpo) com snippets destacados

*Confidence: 0.95 | Status: active | Created: 2026-09-22T14:03:50 | Tags: `news`, `search`, `typesense`, `home-widget`, `backend-api`*

### Convenções dos jobs de materialização no Nuvoinves...

> Convenções dos jobs de materialização no Nuvoinvest: guards de contrato (como a metodologia ativa) executam dentro do callback do run_audited_job; na deduplicação de snapshots a comparação de payloads divergentes exclui calculated_at; ping() existe apenas no PostgresAdvisoryJobLock do scheduler. Nomenclatura: naming_convention do Base.metadata compõe 'ck_<tabela>_' sobre o nome passado — CheckConstraint usa nome curto sem prefixo; nomes já prefixados viram duplicados truncados com sufixo '_' + md5(nome_completo)[-4:] mantendo 55 chars. A dívida de nomes foi totalmente eliminada: migrations 20260916_0200 e 20260916_0600 (DO blocks com IF EXISTS, idempotentes). O publication gate do FRE (rows_from_completed_imports / COMPLETED_IMPORT_GATE_SQL em cvm_fre.py) deve ser aplicado a TODO leitor de cvm_company_share_counts, incluindo SQL cru (radar, inputs, fundamental_indicators). user_activity não tem FK: órfãs de contas apagadas são removidas pelo job auth_data_retention. ALTER TABLE de reparo exige MIGRATION_DATABASE_URL (papel da aplicação não é dono das tabelas). Dev tem deriva histórica do replay fresco — higiene devem ser idempotentes (IF EXISTS).

*Confidence: 0.95 | Status: active | Created: 2026-09-16T18:17:22 | Tags: `fundamentals`, `jobs`, `conventions`, `postgres`, `naming`*

### No Radar do NuvoInvest, os nomes de teses exibidos...

> No Radar do NuvoInvest, os nomes de teses exibidos ao usuário são Valor, Dividendos, Qualidade, Solidez financeira e Crescimento; os códigos internos permanecem estáveis e uma tese só pode ser exibida quando possui metodologia e score materializados.

*Confidence: 1 | Status: active | Created: 2026-09-13T17:30:40 | Tags: `nuvoinvest`, `radar`, `terminology`, `i18n`*

### Modelo de acesso Nuvoinvest em 3 camadas: (1) user...

> Modelo de acesso Nuvoinvest em 3 camadas: (1) user_login_events e auditoria de seguranca append-only, escrita apenas pelo BFF Nuxt via recordLoginEvent (login_success/login_failed/logout), nunca recebera eventos de visita; (2) user_activity (tabela backend, uma linha por usuario) registra ultimo-visto com throttle em DOIS niveis — gate L1 em memoria por processo (dict user_id->monotonic, teto 10k entradas, em backend/auth/activity.py: so pula trabalho, nunca autoriza escrita extra) e guard L2 Redis SET NX EX de 300s (chave user_last_seen_throttle_key); scheduling via run_in_executor para nao bloquear o event loop; (3) engajamento permanece no PostHog. Reentrada com sessao valida NAO gera linha de auditoria por design. Job auth_data_retention (diario 04:30) apaga sessoes better_auth expiradas ha mais de expired_session_retention_days (30) e login_events mais antigos que login_events_retention_days (180), com delete em lotes de 10k (ctid in select limit) e commit por lote para user_login_events.

*Confidence: 1 | Status: active | Created: 2026-09-16T20:49:47 | Tags: `auth`, `audit`, `activity`, `redis`, `backend`, `lgpd`, `scheduler`*

### No Nuvoinvest, gates de UI que dependem de estado ...

> No Nuvoinvest, gates de UI que dependem de estado vivo do browser (largura do viewport, media queries) devem ser reativos: medir o matchMedia em um ref com listener de change e inclui-lo no readySource do useStickyToolbar (ou equivalente reativo). Gate avaliado apenas uma vez no setup nunca re-arma/teardown quando o estado muda sem remontagem -- a barra sticky de /alertas parava de fixar ao alargar a janela de mobile para desktop porque enabled() so rodava no setup; a opcao enabled foi removida do composable.

*Confidence: 0.9 | Status: active | Created: 2026-09-16T17:31:13 | Tags: `frontend`, `use-sticky-toolbar`, `media-query`, `responsive`, `intersection-observer`*

### No NuvoInvest, a politica de escopo de demonstrati...

> No NuvoInvest, a politica de escopo de demonstrativos e POR EMISSOR: se o cvm_code tem QUALQUER linha CONSOLIDATED, INDIVIDUAL nao e persistido nem usado; emissores que so publicam a variante individual (distribuidoras, bancos BACEN) recebem IND com statement_scope='INDIVIDUAL'. A identidade de importacao de cvm_financial_imports inclui statement_type (ex.: DFP_INDIVIDUAL), entao o import IND tem auditoria propria e nunca reseta a importacao CON do mesmo zip. Upserts falham visivelmente em conflito de escopo; TTM nunca deve misturar bases.

*Confidence: 1 | Status: active | Created: 2026-09-17T02:52:15 | Tags: `nuvoinvest`, `cvm`, `statement-scope`, `importador`, `arquitetura`*

---

## Goals

*Objectives, targets, and milestones to track progress.*

*No memories of this type.*

---

## Commitments

*Promises, obligations, and TODOs that need follow-through.*

### Open data-quality items on CVM financial statement...

> Open data-quality items on CVM financial statements to investigate later (listed in AGENTS.md, section 'Base contabil por periodo'): (1) ABCB4: individual net income differs ~36% from consolidated (2023: 1104 vs 814 mi) - check the bank income-statement mapping and which line is mapped to net_income; (2) OIBR3: our TTM (individual basis, FY2025: revenue ~1.58 bi, net income ~-36.4 bi) diverges from Investidor10 (12M revenue ~227.75 mi, net income ~-1.84 bi) - re-evaluate now that both bases are stored and compose_best_ttm picks the newest basis; (3) banks with NULL/zero totals (BMIN3, BPAR3): rows with some totals NULL and others zero.

*Confidence: 0.9 | Status: active | Created: 2026-10-14T20:00:55 | Tags: `cvm`, `financials`, `data-quality`, `todo`, `abcb4`, `oibr3`, `bmin3`, `bpar3`*

---

## Preferences

*User and entity preferences for personalization.*

### Nuvoinvest asset pages: no gray skeleton loaders. ...

> Nuvoinvest asset pages: no gray skeleton loaders. Loading state shows empty frames with the real page geometry and a single spinner centered in the chart area; the spinner must never move (horizontal or vertical) between the placeholder and the real content. Navigating between assets from in-page widgets (e.g. sector map) must keep the scroll position instead of jumping to the top.

*Confidence: 0.9 | Status: active | Created: 2026-11-09T00:42:51 | Tags: `frontend`, `ux`, `loading-state`, `scroll`, `asset-page`*

### No NuvoInvest, todo estado indisponivel exibido ao...

> No NuvoInvest, todo estado indisponivel exibido ao usuario deve dizer O QUE falta (codigo especifico vindo do backend, com contagens/anos, texto curto na linha + v-tooltip explicativo), nunca um 'Indisponivel' ou categoria generica; o backend decide o fato a partir dos mesmos insumos que tornaram o item indisponivel.

*Confidence: 0.9 | Status: active | Created: 2026-11-09T10:35:16 | Tags: `nuvoinvest`, `ui`, `unavailable-reason`, `checklist`*

### Every NuvoInvest frontend UI change must be design...

> Every NuvoInvest frontend UI change must be designed and visually verified at phone width, not only desktop; mobile quality is an acceptance criterion.

*Confidence: 0.95 | Status: active | Created: 2026-09-23T17:35:56 | Tags: `frontend`, `mobile`, `ux`, `verification`*

### Para o feed de mercado do X no NuvoInvest, preferi...

> Para o feed de mercado do X no NuvoInvest, preferir publicacoes de uma lista curada de perfis economicos e fontes oficiais; buscas abertas por nome ou ticker tendem a trazer ruido. O feed social complementa as noticias de sites, com visao geral na Home e relevancia por ativo nas paginas de ativos.

*Confidence: 0.9 | Status: active | Created: 2026-10-08T13:11:52 | Tags: `x-feed`, `news`, `source-curation`, `asset-pages`*

### Frontend fixes should use explicit state-driven be...

> Frontend fixes should use explicit state-driven behavior with targeted tests, avoiding CSS or DOM hacks.

*Confidence: 1 | Status: active | Created: 2026-09-20T11:54:59 | Tags: `frontend`, `ui-state`, `testing`, `quality`*

### Backend NuvoInvest: endpoints de leitura sobre dad...

> Backend NuvoInvest: endpoints de leitura sobre dados publicados/agregados com chave global usam o helper read-through canonico backend/cache/read_through.py (single-flight lock com escrita fenced, dupla checagem dentro do lock, payload invalido descartado e reconstruido do PostgreSQL, queda de Redis degrada para PostgreSQL). Chaves de cache e de lock declaradas em backend/cache/keys.py, TTLs/locks em core/config.py. Chaves por-usuario com lookup barato ficam no par simples load/store_cached_json de json_cache, mas toda leitura de cache DEVE ter try/except defensivo (drift de schema vira warn+recompute, nunca 500 ate o TTL expirar).

*Confidence: 0.95 | Status: active | Created: 2026-09-23T23:36:59 | Tags: `backend`, `redis`, `cache`, `architecture`*

### Cards de resumo da Home do NuvoInvest mostram um r...

> Cards de resumo da Home do NuvoInvest mostram um recorte fixo (destaque e poucos itens) e apontam para a pagina completa pelo link 'Ver todos'; nao expandir o card para listar tudo.

*Confidence: 0.85 | Status: active | Created: 2026-10-13T17:50:47 | Tags: `home`, `summary-cards`, `ui-lists`*

### Codigo do Nuvoinvest sem duplicacao: antes de escr...

> Codigo do Nuvoinvest sem duplicacao: antes de escrever um utilitario, helper, trava, cliente HTTP ou checagem, procurar o que ja existe e reaproveitar; quando houver copias repetidas no codigo tocado, extrair uma versao unica e trocar as copias. Jobs novos seguem o padrao dos jobs existentes (run_audited_job, trava de dominio, ledger de importacao com hash, CLI de backfill, registro no scheduler).

*Confidence: 0.9 | Status: active | Created: 2026-11-09T15:17:34 | Tags: `nuvoinvest`, `code-quality`, `duplication`, `jobs`*

### New NuvoInvest backend read endpoints over publish...

> New NuvoInvest backend read endpoints over published/aggregated data ship with Redis read-through cache from day one, following backend/cache/screener_catalog.py (keys in keys.py, single-flight lock, schema_version validation, PostgreSQL fallback, publication marker in the key), even when benchmarks show small gains.

*Confidence: 0.9 | Status: active | Created: 2026-09-23T18:42:01 | Tags: `backend`, `redis`, `cache`, `architecture`*

### As cores de marca do comparador NuvoInvest devem s...

> As cores de marca do comparador NuvoInvest devem ser extraídas e atualizadas automaticamente a partir das logos, sem etapa de revisão manual; a apresentação preserva contraste por tema e distinção entre séries.

*Confidence: 1 | Status: active | Created: 2026-10-08T18:46:51 | Tags: `nuvoinvest`, `comparador`, `cores-marca`, `automacao`*

### Nos cards de indisponibilidade do NuvoInvest, cicl...

> Nos cards de indisponibilidade do NuvoInvest, ciclos automáticos de retry devem manter a mensagem de erro estável e indicar atividade apenas pelo spinner e estado desabilitado do botão; não exibir rótulos textuais por tentativa ou contagem regressiva do ciclo interno.

*Confidence: 1 | Status: active | Created: 2026-09-20T13:29:00 | Tags: `nuvoinvest`, `frontend`, `retry`, `error-state`, `ux`*

### O usuario quer o estado visivel de telas de dados ...

> O usuario quer o estado visivel de telas de dados (ativo, periodo, metrica, series) refletido na URL, para que o link reproduza a visao que ele esta vendo. Confirmado para a pagina /tesouro em 2026-10-13.

*Confidence: 0.8 | Status: active | Created: 2026-10-13T14:16:54 | Tags: `url-state`, `frontend`, `routing`*

### View defaults (the initial selection when the URL ...

> View defaults (the initial selection when the URL names no item) never show an error to the user: if the preferred option is missing, open any other available option. Explicit user exception to the no-silent-fallback rule, limited to view defaults and never applied to data or contracts. First applied to the Tesouro default title (IPCA+ family), 2026-10-13.

*Confidence: 1 | Status: active | Created: 2026-10-13T15:57:00 | Tags: `frontend`, `ux`, `default-state`, `fallback`*

### Migrações arquiteturais substanciais do NuvoInvest...

> Migrações arquiteturais substanciais do NuvoInvest devem ser divididas em fases independentes, com implementação, testes e gate de aceite concluídos antes de avançar para a fase seguinte.

*Confidence: 1 | Status: active | Created: 2026-09-17T12:08:20 | Tags: `nuvoinvest`, `workflow`, `migracao-arquitetural`, `testes`, `gates`*

### Navegacao no frontend: trocar de entidade (titulo,...

> Navegacao no frontend: trocar de entidade (titulo, ativo) usa push, para o Voltar retornar a entidade anterior; ajustar a visao da mesma tela (periodo, metrica, series) usa replace, sem poluir o historico. Confirmado pelo usuario na pagina /tesouro em 2026-10-13.

*Confidence: 0.85 | Status: active | Created: 2026-10-13T14:54:06 | Tags: `url-state`, `navigation`, `push-replace`, `frontend`*

### Em listas de ativos do NuvoInvest, a linha inteira...

> Em listas de ativos do NuvoInvest, a linha inteira ativa o item (ex.: abre o grafico do titulo) e controles de acao dentro da linha (ex.: sino de alerta) mantem a propria acao. Clicar na linha ja ativa nao rola a pagina nem navega.

*Confidence: 0.9 | Status: active | Created: 2026-10-13T17:45:52 | Tags: `ui-lists`, `row-click`, `stretched-link`*

### Time axes of price/history charts must adapt the l...

> Time axes of price/history charts must adapt the label format to the visible span (day+month up to ~13 months, month/year up to ~4 years, year beyond), placing month/year labels on period boundaries; reference implementation frontend/app/utils/priceAxisLabels.ts

*Confidence: 0.8 | Status: active | Created: 2026-11-08T19:17:45 | Tags: `ui`, `charts`, `nuvoinvest`*

### Nunca executar suites de teste (pytest, vitest, e2...

> Nunca executar suites de teste (pytest, vitest, e2e) neste projeto: outra IA as roda. Escrever os testes, mas validar apenas com lint, checagem de tipos, SQL de leitura e verificacao visual.

*Confidence: 1 | Status: active | Created: 2026-10-14T14:28:31 | Tags: `testing`, `workflow`, `user-preference`*

### Em paginas com um item aberto pela URL (grafico ou...

> Em paginas com um item aberto pela URL (grafico ou detalhe) e uma lista com filtro por categoria, o filtro deve acompanhar o item aberto, para que lista e grafico mostrem a mesma familia. Escolher outro filtro a mao nao muda o item aberto.

*Confidence: 0.8 | Status: active | Created: 2026-10-13T18:00:49 | Tags: `url-state`, `filters`, `consistency`, `tesouro`*

---

## Relationships

*Entity connections, team context, and collaboration patterns.*

*No memories of this type.*

---

## Context

*Session summaries, status updates, and conversation state.*

### Screener do Nuvoinvest alinhado ao padrao TanStack...

> Screener do Nuvoinvest alinhado ao padrao TanStack da casa (opcao A, 2026-09-22): catalogo (metadata+strategies) migrado de useAsyncData para useQuery em useScreenerMetadata.ts com locale na query key, staleTime 30min, builders puros exportados (screenerMetadataOptions/screenerStrategiesOptions/screenerCatalogKeys); ensure* agora via queryClient.fetchQuery (dedupe nativo) e retries via refetchQueries type:all (nao lanca erro; a pagina grafa tentativas pelos refs error/ready apos nextTick); plugin vue-query.ts ganhou defaults ['screener'] (staleTime 1min, gcTime 5min, retry false, sem refetch por foco/reconexao); query de resultados com gate enabled: import.meta.client (sem fetch servidor descartado); dehydrate/hydrate SSR rejeitado por design. Nota: specs de pagina favoritesAvailability/favoritesDeleteRowEntry/newsInitialHydration sao flaky sob carga da suíte cheia mas passam isolados.

*Confidence: 0.95 | Status: active | Created: 2026-09-22T13:40:25 | Tags: `frontend`, `screener`, `tanstack-query`, `vue-query`, `migration`*

### Investigacao pendente combinada no Nuvoinvest: str...

> Investigacao de streams SSE de /api/stream/notifications morrendo a cada ~1-2 min em dev: RESOLVIDA/nao reproduzivel. O usuario confirmou que as mortes pararam apos o teardown graceful (eventStream.close + fallback destroy 1s em notifications.get.ts). Nota tecnica: o teardown graceful muda o COMO o stream termina (limpo, sem ERR_INCOMPLETE_CHUNKED_ENCODING), nao o porve; se as mortes precoces voltarem, o gatilho provavel sera a revalidacao de sessao (revalidate a cada 60s via userEventsSessionCheckMs, timeout 5s = teto do clamp em user_event_config.ts, contra validacao de sessao lenta no dev). Diagnostico pronto: contadores do log {"event":"user_events_metrics"} no terminal do nuxt dev (server/plugins/user_events.ts, cada 60s) -- session_unavailable, writer_closed, subscriber_degraded, closed.

*Confidence: 0.9 | Status: active | Created: 2026-09-19T14:01:21 | Tags: `sse`, `notifications`, `user-events`, `investigation`, `session-revalidation`*

---

## Events

*Important conversations, milestones, and temporal occurrences.*

*No memories of this type.*

---

## Learnings

*Knowledge acquired from experience, corrections, and insights.*

### Na busca de ativos da Home do NuvoInvest, o estado...

> Na busca de ativos da Home do NuvoInvest, o estado abaixo do minimo de 3 caracteres deve sempre exibir a mensagem de orientacao; somente com 3 ou mais caracteres, quando o catalogo foi realmente consultado, o estado vazio pode exibir a mensagem de nenhum resultado.

*Confidence: 1 | Status: active | Created: 2026-09-22T17:20:29 | Tags: `frontend`, `search`, `validation`, `empty-state`, `ux`*

### Dentro da AppNavbar, o seletor global .neutral-act...

> No NuvoInvest, controles PrimeVue renderizados dentro da AppNavbar devem seguir o contrato nav-link; popups teletransportados para document.body devem usar p-menu-item-link e os tokens compartilhados. O seletor global .neutral-action pode sobrescrever color/background dos triggers, estados active locais podem divergir dos menus irmãos, e estilizar apenas o botão interno não cobre o hover na área lateral: também estilize p-menu-item-content com --text-color e --menu-item-hover-bg.

*Confidence: 1 | Status: active | Created: 2026-09-16T01:02:10 | Tags: `navbar`, `primevue`, `css-tokens`, `language-selector`*

### No Radar, redis_miss_count significa que o snapsho...

> No Radar, redis_miss_count significa que o snapshot do Redis não foi aceito como utilizável, inclusive quando a chave existe mas o preço ultrapassa o limite de stale; não significa necessariamente ausência da chave. missing_price_count=0 apenas confirma que o PostgreSQL preencheu todos os preços, não que todos estejam atuais.

*Confidence: 1 | Status: active | Created: 2026-09-14T01:47:21 | Tags: `radar`, `redis`, `stale-data`, `price-quality`, `fallback`*

### Em interfaces Vue com mutações otimistas, controle...

> Em interfaces Vue com mutações otimistas, controles de layout compartilhados não devem depender exclusivamente do objeto removido do cache; durante a transição, use uma âncora de seleção estável para manter a geometria montada até a nova seleção ser confirmada.

*Confidence: 1 | Status: active | Created: 2026-09-21T14:07:54 | Tags: `frontend`, `vue`, `optimistic-update`, `layout`*

### Ranking de ativos mais buscados (/api/v1/assets/po...

> Ranking de ativos mais buscados (/api/v1/assets/popular, Home hero) so exibe itens quando um ativo tem >= ASSET_POPULARITY_MIN_UNIQUE_SEARCHERS pesquisadores unicos (default 3) na janela movel de 30 dias. A retencao (apply_asset_popularity_retention) apaga linhas com a mesma fronteira da janela, entao um pico pontual de buscas esvazia o ranking quando envelhece. Com trafego baixo, o ranking fica vazio sem bug de codigo; diagnosticar pelos dados (asset_listing_searchers, core_job_runs.result_summary) antes de mexer na consulta.

*Confidence: 0.9 | Status: active | Created: 2026-10-13T20:48:03 | Tags: `popularity`, `home`, `ranking`, `retention`, `threshold`, `data-window`*

### No NuvoInvest, o importador de demonstrativos CVM ...

> No NuvoInvest, o importador de demonstrativos CVM (backend/providers/cvm_financials/client.py) persiste APENAS a variante CONSOLIDADA (_con_) dos zips DFP/ITR; toda variante INDIVIDUAL (_ind_) e descartada com motivo VARIANTE_INDIVIDUAL_NAO_PERSISTIDA. Pelo menos 26 emissores listados (distribuidoras de energia/gas, bancos BACEN, Sanepar, Westwing, etc.) so publicam a variante INDIVIDUAL no portal de dados abertos da CVM, logo ficam com zero linhas em asset_income_statements, snapshot com financial_period_end NULL e publicacao do screener abortada pela validacao de linhagem.

*Confidence: 1 | Status: active | Created: 2026-09-17T01:51:42 | Tags: `nuvoinvest`, `cvm`, `dfp`, `itr`, `importador`, `screener`, `individual`, `consolidated`*

### No NuvoInvest, as CHECK constraints NOT VALID do e...

> No NuvoInvest, as CHECKs de linhagem do envelope em fundamental_indicator_current foram VALIDADAS e as quatro colunas ficaram NOT NULL (migracao 20260917_0300): a janela NULL esta FECHADA e o banco rejeita qualquer linha publicada sem envelope completo. Writers devem sempre fornecer envelope completo; o filtro calculation_inputs IS NOT NULL em writers parciais permanece como defesa em profundidade e preservacao de valores congelados de ativos fora do universo.

*Confidence: 1 | Status: active | Created: 2026-09-17T01:34:20 | Tags: `nuvoinvest`, `postgresql`, `check-constraint`, `lineage`, `screener`*

### Nuvoinvest: o boot do app shell (app.vue) depende ...

> Nuvoinvest: o boot do app shell (app.vue) depende de requestAnimationFrame (MIN_BOOT_DURATION_MS 650) e mantem .nuvoinvest-app-shell--booting com visibility:hidden ate o primeiro frame; em panes do navegador IAB ocultas/oclusas o rAF fica congelado (visibilityState visible mas rafCount 0), o boot nunca completa e o Playwright reporta todos os elementos como hidden para actionability. Ao testar frontend Nuvoinvest no IAB: chamar browser.capabilities.get('visibility').set(true), nao interpretar boot travado como regressao, e preferir verificacao por mutacao de DOM via dispatchEvent de eventos input (Vue reage via microtasks, independente de rAF) quando frames estiverem congelados. Ao instrumentar window.fetch via monkeypatch, sempre usar new URL(raw, location.href) dentro de try/catch: o app pode chamar fetch com URL relativa e um wrapper ingenuo com new URL(url) quebra o request com 'Invalid URL' e injeta falso painel de erro.

*Confidence: 0.9 | Status: active | Created: 2026-09-21T17:17:32 | Tags: `frontend`, `testing`, `browser-use`, `iab`, `raf`, `instrumentation`*

### Na validacao frontend do NuvoInvest com o browser ...

> Na validacao frontend do NuvoInvest com o browser in-app do ZCode, cliques via locator Playwright costumam expirar por actionability em overlays PrimeVue (dialog/autocomplete); usar cua.click por coordenadas obtidas de screenshot/evaluate ou el.click() via evaluate, e medir layout com getComputedStyle(el).gridTemplateColumns, que retorna os trilhos resolvidos em px

*Confidence: 0.9 | Status: active | Created: 2026-09-21T20:42:49 | Tags: `frontend`, `validacao`, `browser`, `primevue`, `zcode-iab`*

### Fixture de testes para o ecossistema de historico ...

> Fixture de testes para o ecossistema de historico fundamentalista (tests/test_fundamental_history_repository.py): cvm_company_registrations exige source_import_id apontando para cvm_company_imports (dataset_key CIA_ABERTA_CAD) e last_seen_at/cad/fca_last_seen_at NOT NULL sem default; share counts apontam para cvm_fre_imports; o lateral de precos do valuation (_get_issuer_market_value) junta market_instruments.asset_listing_id = listing.id, entao o instrumento de teste PRECISA desse vinculo ou o valuation volta None silenciosamente. Os testes de backfill do job dao monkeypatch em get_fundamental_indicator_history — coberturas de SQL real desse repositorio devem ficar no arquivo de historico.

*Confidence: 0.95 | Status: active | Created: 2026-09-16T17:13:38 | Tags: `pytest`, `fixtures`, `sql`, `fundamentals`, `test-database`*

### No ambiente de validacao do NuvoInvest com o brows...

> No ambiente de validacao do NuvoInvest com o browser in-app do ZCode: quando a janela esta sem foco, o Chromium congela requestAnimationFrame, o que trava transicoes Vue (ex.: favorites-fade em mode out-in) e impede trocas de secao; shim de teste window.requestAnimationFrame = cb => setTimeout(cb, 16) contorna sem alterar codigo. O backend roda uvicorn sem --reload sob um supervisor que respawn o processo se o PID for morto; FastAPI ignora silenciosamente query params desconhecidos, entao validar endpoint novo exige reiniciar o backend e conferir /openapi.json

*Confidence: 0.9 | Status: active | Created: 2026-09-21T23:46:30 | Tags: `frontend`, `backend`, `validacao`, `browser`, `vue-transitions`, `fastapi`, `zcode-iab`*

### Em helpers genericos sobre useQuery do @tanstack/v...

> Em helpers genericos sobre useQuery do @tanstack/vue-query, placeholderData e tipado como PlaceholderDataFunction<NonFunctionGuard<T>>, tipo condicional que o TypeScript nao resolve para T generico (NonFunctionGuard nao e exportado). Solucao adotada no Academy: um unico cast de tipo das options para MaybeRefOrGetter<UseQueryOptions<T, Error, T, T, readonly unknown[]>>, documentado inline, e passar o tipo explicito ao helper de placeholder (inferencia cai em undefined).

*Confidence: 0.85 | Status: active | Created: 2026-10-06T13:20:48 | Tags: `frontend`, `tanstack-query`, `vue-query`, `typescript`*

### No Nuvoinvest, a sticky toolbar de listagens (comp...

> No Nuvoinvest, a sticky toolbar de listagens (composable useStickyToolbar, convencao sentinela-irmao-acima) cobre alerts, favorites, portfolio/positions e agora o screener. Restricao de layout nao obvia: position: sticky é limitado pela caixa do pai — dentro de um card curto a barra sai da tela apos ~1 altura de card; a barra precisa viver num wrapper que atravessa a pagina ate o fim dos resultados (ex: .screener__body com position: relative), com a sentinela absolute no topo do wrapper (ponto de repouso da barra), o que tambem evita criar track/gap extra no grid da pagina. Tratamento stuck da casa: faixa frosted full-bleed via ::before com width 100vw + blur; favorites mantem sticky no mobile, alerts desativa em <=768px.

*Confidence: 0.9 | Status: active | Created: 2026-09-22T19:11:24 | Tags: `frontend`, `screener`, `sticky`, `use-sticky-toolbar`, `css`, `layout`*

### Na Home do NuvoInvest, sucesso HTTP e TTL de cache...

> Na Home do NuvoInvest, sucesso HTTP e TTL de cache não comprovam atualidade da fonte: o destaque de notícias usa a publicação mais recente sem corte por data, o heatmap pode servir cotações antigas, e a agenda de proventos expõe synced_at sem usá-lo na UI. Avalie frescor por contrato específico de cada fonte.

*Confidence: 0.95 | Status: active | Created: 2026-09-27T12:04:46 | Tags: `home`, `news`, `market-heatmap`, `dividend-agenda`, `data-freshness`*

### In Nuxt, a page whose dynamic route params only sw...

> In Nuxt, a page whose dynamic route params only switch its content in place must set a constant definePageMeta key. The default key is the interpolated path, so each param change remounts the page and runs the global out-in pageTransition, which shows as a blink. Verified on the Tesouro title page.

*Confidence: 0.95 | Status: active | Created: 2026-10-13T16:08:34 | Tags: `nuxt`, `page-transition`, `route-key`, `frontend`*

### No frontend Nuxt/Vue 3 do NuvoInvest, instalar @ta...

> No frontend Nuxt/Vue 3 do NuvoInvest, instalar @tanstack/vue-query v5 com npm pode falhar por ERESOLVE devido ao peerOptional legado @vue/composition-api/Vue 2; use --legacy-peer-deps para essa instalação e valide com lint, Vitest e build.

*Confidence: 0.95 | Status: active | Created: 2026-09-17T16:11:41 | Tags: `frontend`, `npm`, `tanstack-query`, `vue3`, `dependency-resolution`*

### Titulos do Tesouro Direto nao tem identidade pelo ...

> Titulos do Tesouro Direto nao tem identidade pelo nome: a unicidade real e (codigo SELIC, data de vencimento) (uq_public_bonds_code_maturity). O display_name do catalogo /api/v1/tesouro/titulos omite o ano em muitos titulos (historicos e Prefixado sem vintage), e ha varios titulos da mesma familia no mesmo ano de vencimento (ex.: 4 Prefixados vencendo em 2006). Qualquer identificador legivel de titulo (slug de URL, rotulo de ano) deve ser derivado ou validado contra essa chave, nunca presumido a partir do nome.

*Confidence: 0.9 | Status: active | Created: 2026-10-13T14:07:06 | Tags: `tesouro-direto`, `public-bonds`, `identity`, `url-routing`*

### Em paginas Nuxt do Nuvoinvest, watch sem immediate...

> Em paginas Nuxt do Nuvoinvest, selecao padrao derivada de computed sobre estado Pinia em cache exige immediate:true em TODOS os watchs da cadeia de retransmissao. O callback immediate roda sincronamente no registro do proprio watch: um elo upstream imediato seta o valor durante o setup, e o watcher downstream registrado depois cacheia esse valor como baseline inalterado e nunca dispara se nao for imediato ele tambem (peguei isso com teste ao corrigir a pagina /tesouro: immediate so no primeiro elo deixou fetchHistory em 0 chamadas). Regra: cadeia de derivacao em relay = immediate em cada elo, ou inicializacao explicita fora de watchs.

*Confidence: 0.95 | Status: active | Created: 2026-09-21T11:15:09 | Tags: `vue-reactivity`, `nuxt-pages`, `pinia`, `watch-immediate`, `default-selection`*

### Em specs de componentes Nuvoinvest que disparam um...

> Em specs de componentes Nuvoinvest que disparam um useRetryCycle real (ex.: clique em retry de allocation targets), o wrapper deve ser desmontado apos flushPromises: o onBeforeUnmount do composable e o unico mecanismo que cancela o setInterval do backoff pendente; sem o unmount, o ciclo fantasma vaza para o teste seguinte e so termina por sorte quando o beforeEach zera o erro da store.

*Confidence: 0.9 | Status: active | Created: 2026-09-21T18:15:08 | Tags: `frontend`, `testing`, `vitest`, `retry-cycle`, `vue`*

### Ao testar o frontend Nuvoinvest em janela ocluida/...

> Ao testar o frontend Nuvoinvest em janela ocluida/background (browser de automacao), o AppBootOverlay ('Nuvoinvest carregando') parece travado porque o app.vue so o remove dentro de requestAnimationFrame, que nao dispara sem renderizacao — nao e bug real. Remover .app-boot-overlay via evaluate e checar hasVueApp para ver o conteudo real. Alem disso, ao varrer o grafo de modulos do Vite com regex de imports, comentarios de codigo (ex.: 'copied from d3.js' no echarts) geram falsos 404: validar cada falha contra o fonte do importador.

*Confidence: 0.9 | Status: active | Created: 2026-09-17T00:42:30 | Tags: `nuxt`, `nuvoinvest`, `boot-overlay`, `raf`, `ui-automation`, `troubleshooting`*

### Em specs vitest de codigo server do Nuxt (frontend...

> Em specs vitest de codigo server do Nuxt (frontend/tests/unit/server), useRuntimeConfig bare deve ser mockado com mockNuxtImport de @nuxt/test-utils/runtime; stub em globalThis e ignorado porque o auto-import do Nuxt resolve o simbolo direto do nuxt.js e falha com 'nuxt instance unavailable'.

*Confidence: 0.9 | Status: active | Created: 2026-09-16T13:19:43 | Tags: `vitest`, `nuxt`, `testing`, `server-routes`*

### Nuvoinvest /favorites pagination final state: zero...

> Nuvoinvest /favorites pagination final state: zero visible effect on navigation (alerts-page parity). Stack: (1) placeholderData keepPreviousData holds the previous page's rows while the next page fetches over the network - guarded by a unit test with a 110-item list whose workspace snapshot covers only 100, forcing the last page through a delayed HTTP mock (note: test env backendBaseUrl is RELATIVE /api/backend, so URL parsing in fetch mocks needs a base). (2) No dim, no skeleton, no reserve state during navigation. (3) Entry fade is a plain @keyframes animation on .soft-enter, marked per-row by the pre-flush watcher only inside mutation windows - keyframes chosen over @starting-style for pipeline compatibility. If a user still reports pagination fade after this, suspect stale HMR CSS in their browser - ask for a hard reload.

*Confidence: 0.95 | Status: active | Created: 2026-09-18T11:46:31 | Tags: `frontend`, `watchlist`, `favorites`, `pagination`, `tanstack-query`*

### A identidade de um snapshot contábil fundamentalis...

> A identidade de um snapshot contábil fundamentalista deve incluir explicitamente financial_period_end e, quando aplicável, share_count_reference_date; usar somente os valores de FundamentalInputs pode colapsar períodos contábeis distintos quando os números se repetem.

*Confidence: 1 | Status: active | Created: 2026-09-16T11:37:50 | Tags: `fundamentals`, `snapshots`, `fingerprint`, `accounting-period`*

### Migrations that remove asset-class scoping must fa...

> Migrations that remove asset-class scoping must fail visibly when scoped records remain or when the enumerated catalog has drifted; only drop the scope column after both guards pass.

*Confidence: 0.95 | Status: active | Created: 2026-09-22T23:11:26 | Tags: `alembic`, `migrations`, `asset-class`, `screener`, `catalog`*

### Nuvoinvest /news: piscada dupla dos cards ao digit...

> Nuvoinvest /news: piscada dupla dos cards ao digitar na busca tem causas confirmadas por instrumentacao de DOM: (1) debounce de 300ms do searchInput dispara um ciclo de busca completo a cada pausa >300ms durante a digitacao (2 ciclos = 2 piscadas); (2) a cada disparo, archivePending (mudanca de articlesContextKey) troca os cards montados pelo skeleton com visibility:hidden, deixando a area em branco durante o request inteiro (medido 142-850ms local) sem manter resultados anteriores; (3) na resposta, playContentRefreshFade anima opacity 0.6->1 em 320ms nos .news-entry-fade-target, entao os cards voltam escurecidos e acendem. O double flash historico de route transition ja foi corrigido com pageTransition:false + syncQuery(false). Fix candidatos: manter resultados anteriores durante nova busca (estilo keepPreviousData) e/ou suprimir o fade 0.6->1 em trocas de busca.

*Confidence: 0.95 | Status: active | Created: 2026-09-21T15:25:22 | Tags: `frontend`, `news`, `flicker`, `debounce`, `search`*

---

## Observations

*Patterns noticed, behavioral notes, and recurring themes.*

*No memories of this type.*

---

## Artifacts

*Tool outputs, files, reports, and external references.*

### Plano de migracao da fatia 'saved' (artigos salvos...

> Plano de migracao da fatia 'saved' (artigos salvos) de useNewsStore para TanStack Query vive em docs/news-saved-articles-tanstack-migration-plan.md; status planejado aguardando autorizacao. Escopo exclui a parte publica da store (latest/popular/arquivo SSR). Decisoes-chave: keys sob ['news', userId, 'saved']; savedIds staleTime 60min (paridade com TTL manual atual de 1h); search do endpoint salvo permanece SEM normalizeSearchText (paridade); visao salvos de /news usa useInfiniteQuery (append atual) enquanto /favorites usa query paginada com page na key; purge ['news'] no layout substitui clearSavedState; backend inalterado. Pendencia: useHomeData busca pagina 1 de salvos (5 itens) sem consumidor visivel na Home - verificar antes do corte.

*Confidence: 0.95 | Status: active | Created: 2026-09-22T11:57:02 | Tags: `frontend`, `news`, `tanstack-query`, `pinia`, `migration-plan`, `favorites`, `watchlist`*

### O plano de resiliencia e multiplexacao do SSE publ...

> O plano de resiliencia e multiplexacao do SSE publico de precos do NuvoInvest vive em docs/public-price-sse-resilience-and-multiplexing-plan.md; ele cobre ressincronizacao REST apos reconnect, hub client-only por aba para /api/stream/public-prices, adocao por watchlist, screener, pagina de ativo e portfolio publico, sem incluir streams privados, notificacoes ou administracao.

*Confidence: 0.95 | Status: active | Created: 2026-09-22T18:18:50 | Tags: `frontend`, `sse`, `market-prices`, `tanstack-query`, `multiplexing`*

### Plano revisado de migração do portfolio para TanStack Query

> Plano de migracao do portfolio para TanStack Query vive em docs/portfolio-tanstack-migration-plan.md; revisado por terceiros e reauditado contra o backend em 2026-09-22. Estrutura final: invariantes obrigatorios (fachada sem cache, contexto financeiro = base_currency+valuation_timezone NA key, mutation context com identity_generation, rollback localizado, merge FX monotonico por observed_at, single-flight no refresh derivado); 5 fases (fundacao inativa; ativacao do QueryClient no nucleo com fachada delegante; transacoes+analytics; settings/contas/backup/alocacao; remocao e hardening). Contratos verificados: 46 rotas em backend/api/endpoints/portfolios.py; transacoes limit 1..200, sort enums lowercase, sort_by trade_date default; proceeds usam alias 'status', eventos limit 1..100 sort cumDate; performance benchmarks sao lista repetida (estabilizar array na key); shared/{token} e fx/rates/latest sao PUBLICOS sem verify_user; rewarm e operacional (nao chamado pelo frontend); deleteAccount exige confirmation_name+impact_fingerprint e reconcilia so os affected_portfolios; summary SSE patch e DELTA sobre total_value (preserva parcela renda fixa, null se valuation PARTIAL); ideal_percent nunca recalculado por tick.

*Confidence: 1 | Status: active | Created: 2026-09-22T16:12:16 | Tags: `frontend`, `portfolio`, `tanstack-query`, `migration-plan`, `identity-safety`*

---

## Errors

*Failure records, bugs, and lessons learned from mistakes.*

### Dedup por conteudo do fundamental_indicator_snapsh...

> Loader batch e SQL legacy de valor consolidado de emissor compartilham PRICEABLE_SHARE_CLASS_SPECIFICATIONS (ON,PN,PNA..PNF) em fundamental_indicator_inputs.py; o loader classifica cada listing pela spec do preco mais recente e filtra UNT/DRN/CI no WHERE antes do COUNT(*) FILTER (D4b preservado para classes de verdade). Corrigido e verificado em dev em 2026-09-15: TAEE3/4, ALUP3/4, ENGI3/4, KLBN3/4, SAPR3 e AZUL3 publicaram market cap e P/L (status OK); SANB11/BPAC11/BBSE3 permanecem fora por metodologia (unit nao suportada / setor Financeiro). BTG tem FRE sem breakdown por classe: PNA sem quantidade anula tambem o legacy (problema de dados independente, em aberto). Testes de contrato em test_fundamental_indicator_inputs.py.

*Confidence: 1 | Status: active | Created: 2026-09-15T12:55:24 | Tags: `fundamentals`, `snapshots`, `dedup`, `fingerprint`, `data-duplication`*

### No sync FRE da CVM, commits intermediarios por lot...

> No sync FRE da CVM, commits intermediarios por lote (_commit_batch, P2-5) rompem a atomicidade do guard assert_fre_rows_on_active_registrations: o guard roda apenas apos todos os lotes commitados (sync_cvm_fre.py), entao ao falhar o rollback so descarta o ultimo lote parcial e as linhas dos lotes anteriores (incluindo o purge do ano, commitado junto do primeiro lote) ficam publicadas com import FAILED — e nenhum consumidor (valuations.py, fundamental_indicators.py, classifications.py) filtra por source_import_id ou status do import. Toda mudanca que introduzir commits intermediarios em import com guard de contrato precisa revalidar a pre-condicao do guard antes do primeiro commit.

*Confidence: 0.95 | Status: active | Created: 2026-09-16T22:07:53 | Tags: `fre`, `cvm`, `guard`, `batch-commit`, `atomicidade`, `import`*

### No frontend Nuvoinvest (TanStack vue-query + Vue t...

> No frontend Nuvoinvest (TanStack vue-query + Vue templates), as flags do resultado de useQuery (isPending, isFetching, isError, data) sao refs dentro de um objeto simples: nunca ler o objeto bruto da query direto no template, pois cada propriedade acessada e o objeto Ref inteiro, sempre truthy (v-if preso para sempre mesmo com dados carregados). Padrao obrigatorio: expor computeds no script lendo .value (ex.: listingAlertsPending = computed(() => q.isPending.value)) e usa-los no template. Causa real: painel Meus alertas do AssetAlertDialog congelou no spinner apos a migracao TanStack (commit 8b2f2e5, 2026-09-17); corrigido tambem com estado de erro explicito via ResourceErrorPanel.

*Confidence: 0.95 | Status: active | Created: 2026-09-21T19:49:58 | Tags: `vue-query`, `tanstack-query`, `vue-templates`, `asset-alert-dialog`, `frontend`*

### Nuvoinvest: /favorites table row-delete flicker ha...

> Nuvoinvest: /favorites table row-delete flicker has three confirmed causes (reproduced via instrumented DOM): (1) removeItem in favorites.vue refetches without orderItemsByPreviousListingOrder, so client-pinned row order from the inline-add flow is replaced by server canonical ADDED_AT DESC order and all keyed rows physically move in the DOM; only the inline picker flow (refreshItemsPreservingOrder) preserves order. (2) Two overlapping refetch cycles (mutation onSettled invalidation + manual loadItems refetch) toggle .favorites-table.refreshing opacity twice within ~90ms. (3) keepConfirmedRemovalInCurrentPage double-decrements total (onMutate already decremented) and itemsTotal subtracts confirmedRemovedListingIds.size again on fresh server data, so the pagination total stays wrong until list switch and can reach 0, replacing the table with the empty state while items still exist. Fix directions: reuse order preservation in removeItem, deduplicate the refresh, clear confirmedRemovedListingIds after the post-mutation refetch lands.

*Confidence: 0.95 | Status: active | Created: 2026-09-18T01:40:50 | Tags: `frontend`, `watchlist`, `favorites`, `tanstack-query`, `flicker`*

### No frontend Nuvoinvest, todo caminho de recarga fo...

> No frontend Nuvoinvest, todo caminho de recarga fora do proprio ciclo de retry que substitui requests em voo via abort guard compartilhado deve chamar xxxRetryCycle.cancel() antes de recarregar (ex.: watch de locale do academy); sem isso a proxima tentativa do ciclo aborta o request novo e a pagina fica presa no painel de indisponibilidade com loadError obsoleto. Corrigido no watch(academyLocale) em 2026-09; alerts/tesouro/favorites ja seguem o padrao. A home (useAsyncData watch locale) tem variante mais branda sem abort guard compartilhado.

*Confidence: 0.95 | Status: active | Created: 2026-09-21T15:45:25 | Tags: `frontend`, `retry-cycle`, `abort-guard`, `academy`, `vue`*

### No importador histórico do CVM FRE, o purge usa cv...

> No importador histórico do CVM FRE, o purge usa cvm_fre_imports.reference_year, enquanto as tabelas de snapshot têm unicidade por empresa e reference_date sem source_import_id; portanto um arquivo do ano N+1 que contenha DT_REFER do ano N pode colidir com o snapshot retido de N e gerar IntegrityError.

*Confidence: 1 | Status: active | Created: 2026-09-15T13:25:01 | Tags: `fre`, `cvm`, `historico`, `integrity-error`, `unique-constraint`*

### O loader batch de valor consolidado de emissor (lo...

> O loader batch de valor consolidado de emissor (load_issuer_market_values_by_issuer) nao deve incluir specs nao precificaveis (UNT/DRN/CI) na agregacao: o CASE sem filtro gera class_shares NULL e o COUNT(*) FILTER anula o emissor inteiro, divergindo do SQL legacy que filtra SPLIT_PART(spec) IN (ON,PN,PNA..PNF) no WHERE. Vitimas reais em dev (PARTIAL + MISSING_ISSUER_MARKET_CAP): TAEE3/4, ALUP3/4, ENGI3/4, KLBN3/4, SAPR3, AZUL3. Os exemplos SANB11/BPAC11/BBSE3 estao errados para o sintoma: units sao excluidas do universo por UNSUPPORTED_LISTING_FORM e Bancos/Seguradoras/IGTI por FINANCIAL_COMPANY (root Financeiro). BTG (BPAC) tem alem disso FRE sem breakdown por classe: PNA sem quantidade anula tambem o legacy. Correcao: centralizar lista de specs precificaveis usada por loader e legacy + teste de paridade com emissor ON+PN+UNT.

*Confidence: 1 | Status: active | Created: 2026-09-15T13:28:58 | Tags: `fundamentals`, `issuer-market-value`, `screener`, `specification-filter`, `data-duplication`*

### No coordenador de user-events do NuvoInvest, reque...

> No coordenador de user-events do NuvoInvest, requestSync coalesce chamadas concorrentes devolvendo running, mas a execucao captura por closure apenas a policy do primeiro chamador; uma tentativa explicita da UI pode herdar retry de transporte, intervalo minimo e reagendamento de um sync de fundo. Policies restritivas de retry nao podem ser descartadas no coalescing, e alterar somente a policy futura nao muda um fetch que ja iniciou.

*Confidence: 1 | Status: active | Created: 2026-09-21T12:07:16 | Tags: `frontend`, `user-events`, `retry`, `coalescing`, `ofetch`*

---

*End of memory export.*
