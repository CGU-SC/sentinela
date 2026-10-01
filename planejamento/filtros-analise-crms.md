# Filtros dos médicos — tela Análises de CRMs (`/analises`)

Lista de filtros propostos para o painel **"Filtros dos médicos"** (coluna da direita de `/analises`) e o que já foi implementado.

Última atualização: 30/09/2026.

## Legenda

**Situação**

- ✅ **Feito:** implementado e validado.
- ⬜ **Pendente:** proposto, ainda não implementado.
- ❌ **Descartado:** decidido que não será feito.
- ⏸️ **Adiado:** depende de outra tarefa antes (motivo na observação).

**Viabilidade** (depende de onde está o dado em escala nacional)

- 🟢 **Pronto:** o dado já está em cache nacional por médico; o filtro é uma agregação direta.
- 🟡 **Agregação nova:** os dados existem, mas é preciso cruzar caches (médico × farmácia × cadastro).
- 🔴 **Pré-cálculo:** exige uma tabela nova por médico, porque hoje o cálculo existe só médico a médico (modal do histórico e alertas do ranking, limitados a 100 médicos por consulta).

## Regras gerais (decididas)

- **Período:** todos os filtros usam o período da página, o mesmo do ranking.
- **Onde valem:** mapa, ranking e aba Por mês. Somam-se aos filtros da barra esquerda (período, território e farmácias). O universo é: médicos das farmácias do recorte **∩** médicos que passam nos filtros de médico.
- **Onde são aplicados:** sempre no backend, porque o ranking é paginado e ordenado no servidor e o mapa agrega médicos.
- **Persistência:** os filtros valem só durante a sessão. Não são salvos.
- **Filtro de farmácias da barra esquerda:** nos filtros de Atuação (grupo 4), considerar **todas** as farmácias do médico, e não só as filtradas. É a mesma regra que o ranking já usa para taxa e meses. *(Ainda a confirmar quando o grupo 4 for implementado.)*

## 0. Busca

| Situação | Filtro | Tipo | Fonte | Viabilidade |
|---|---|---|---|---|
| ✅ | Buscar médico por nome, nº do CRM ou CRM/UF (`800/SC`, `800-SC`, `CRM-SC 800`…) | texto | `dados_medico` | 🟢 |

Observação: a busca vale para o ranking e a aba Por mês, **não** para o mapa. Ela foi movida do cabeçalho do ranking para o topo do painel, aparece como chip e conta nos filtros ativos.

## 1. Cadastro CFM

| Situação | Filtro | Tipo | Fonte | Viabilidade |
|---|---|---|---|---|
| ✅ | Situação no CFM (localizado / não localizado) | opções | `dados_medico` | 🟢 |
| ✅ | UF do CRM | multisseleção | UF do próprio `id_medico` (ex.: `123/SC`); vale também para os não localizados | 🟢 |
| ✅ | Prescreveu antes da 1ª inscrição | sim/não | `dados_medico` × `crm_medico_brasil_mes` | 🟢 |

Observações:

- **Antes da 1ª inscrição:** usa a mesma regra do ponto de atenção do modal do histórico (algum mês com prescrição no período anterior ao mês da 1ª inscrição). Médicos sem data de inscrição (4.435 localizados) não são avaliados. O controle fica desabilitado quando "Não localizado" está marcado.
- **Qualidade das datas de inscrição:** há ~89 datas anteriores a 1940 (ex.: `1900-01-01`) e 81 posteriores a 2024. Isso deixou de afetar a UI com o descarte do filtro de tempo de inscrição.

## 2. Produção e intensidade

| Situação | Filtro | Tipo | Fonte | Viabilidade |
|---|---|---|---|---|
| ✅ | Taxa diária (prescrições ÷ dias com prescrição) | faixa mín–máx | `crm_medico_brasil_mes` | 🟢 |
| ✅ | Total de prescrições | faixa | `crm_medico_brasil_mes` | 🟢 |
| ⬜ | Dias com prescrição | faixa | `crm_medico_brasil_mes` | 🟢 |
| ⬜ | Meses ativos | faixa | `crm_medico_brasil_mes` | 🟢 |
| ⬜ | % de meses com taxa elevada (> P95) | faixa | `crm_medico_brasil_mes` × `crm_limiar_p95_mes` | 🟢 |
| ⬜ | Maior sequência de meses consecutivos com taxa elevada | mínimo | `crm_medico_brasil_mes` × `crm_limiar_p95_mes` | 🟢 |
| ⬜ | Pior mês: × o P95 (ex.: ≥ 3×) | mínimo | `crm_medico_brasil_mes` × `crm_limiar_p95_mes` | 🟢 |
| ⏸️ | Valor total prescrito (R$) | faixa | a definir (ver observação) | 🔴 |

Observações:

- **Taxa diária e total de prescrições:** usam o número do médico **no recorte da página** (Brasil, UF, região ou município), o mesmo das colunas TAXA / DIA e PRODUÇÃO do ranking. As faixas são inclusivas, e qualquer limite pode ficar vazio. A taxa é comparada arredondada a 2 casas, como é exibida. Na aba **Por mês**, cada linha é um médico × mês, então as faixas filtram os **meses** (taxa e prescrições do mês, as colunas da aba). Ali, só os demais filtros de médico, os de farmácia e a busca escolhem os médicos. A regra da faixa fica num lugar só: `FiltrosMedico.expressao_faixas`.
- **Valor total prescrito (adiado):** a única fonte com valor por médico (`crm_prescritores_global`, 271 milhões de linhas) não confere com a base do ranking. Em 2024, 150 mil dos 627 mil médicos não aparecem nela, o total de prescrições é menor (mediana de 81%) e a soma nacional leva ~14 s. Para fazer o filtro de forma consistente, acrescentar o valor autorizado aos módulos `crm_medico_brasil_mes` e `crm_medico_territorio_mes` (SQL e sincronização, seguindo a regra de Parquets do `CLAUDE.md`). Com isso, o valor também poderia virar coluna do ranking.

## 3. Pontos de atenção (os mesmos do modal do histórico)

| Situação | Filtro | Tipo | Fonte | Viabilidade |
|---|---|---|---|---|
| ✅ | Autorizações em sequência, único CRM: severidade mínima (alta / grave / crítica / extrema) | opções | `crm_concentracao_unico_alertas_global` | 🟢 |
| ✅ | Nº de dias com sequência (na severidade mínima escolhida) | faixa mín–máx | `crm_concentracao_unico_alertas_global` | 🟢 |
| ✅ | Autorizações em sequência na **farmácia** (barra lateral esquerda, grupo Integridade), com tipo Único CRM / Múltiplos CRMs / Qualquer | tipo + severidade mínima + faixa de dias | `crm_concentracao_unico_alertas_global` e `crm_concentracao_multiplo_alertas_global` | 🟢 |
| ⬜ | Farmácias distantes no mesmo mês (> 400 km) | sim/não | `geografico_global` | 🟡 |
| ⬜ | Maior distância no mesmo mês (km) | mínimo | `geografico_global` | 🔴 |
| ⬜ | Combinação: "tem qualquer ponto de atenção" / "tem N ou mais" | contagem | todos acima | 🔴 |

Observações sobre as autorizações em sequência:

- **Único CRM (feito):** é o ponto de atenção "Autorizações em sequência (único CRM)" do modal do histórico, com a mesma tabela e a mesma contagem (dias distintos com sequência, todas as farmácias, no período). Conferido no modal: 1.597 dias, 9 farmácias, extrema = 1.597, 9, extrema.
- **Regra:** a severidade mínima define quais dias contam; a faixa de dias é contada nesse nível. Só a severidade = pelo menos 1 dia nesse nível. Médico sem nenhuma sequência tem 0 dias. Nacional, escolhe médicos em todas as abas.
- **Desempenho:** a tabela tem 1,9 mi linhas; a agregação por médico leva ~0,03 s em qualquer período.
- **Dados (2020–2024):** 36.008 médicos (5% dos ativos) têm alguma sequência; mediana de 3 dias; 10% passam de 44 dias; máximo de 1.597. Pior severidade: alta 19.963, grave 2.922, crítica 6.334, extrema 6.789.
- **Filtro de farmácia na barra esquerda (feito):** seção "Autorizações em sequência" no grupo Integridade, com Tipo (Qualquer, Único CRM, Múltiplos CRMs), Severidade mínima e Dias. Dias = datas distintas de `dt_alerta` da farmácia no período, a mesma contagem da Cronologia da aba Autorizações; em "Qualquer", o dia com os dois tipos conta uma vez. O tipo sozinho não liga o filtro: ele só vai para a API com severidade ou dias. Vale em todas as telas; na Análise de CRMs, restringe aos médicos que prescreveram nessas farmácias. Parâmetros `seq_tipo`, `seq_severidade_min`, `seq_dias_min` e `seq_dias_max`; regra em `apply_seq_filter` (`alertas_alvos.py`). O filtro por médico do painel direito continua separado, para a análise por médico. Em 2020–2024 (≥ 1 dia): único 13.076, múltiplos 13.842, qualquer 16.530 farmácias; severidade extrema: 3.241, 4.683 e 5.424.
- **Múltiplos CRMs como filtro de médico (descartado):** a tabela de alertas de múltiplos CRMs não identifica os médicos. O único vínculo é um indicador por médico × farmácia × mês na `crm_prescritores_global` (base que não confere com o ranking), e ele marca 308.664 médicos (41%) em 2020–2024. Um filtro tão amplo serve pouco para triagem.

## 4. Atuação nas farmácias

| Situação | Filtro | Tipo | Fonte | Viabilidade |
|---|---|---|---|---|
| ✅ | Nº de farmácias onde atuou | faixa mín–máx | `crm_farmacia_medico_ano` + `crm_medico_estabelecimento_mes` (mesmo cálculo da exclusividade) | 🟡 |
| ✅ | Nº de municípios onde atuou | faixa mín–máx | `crm_farmacia_medico_ano` + `crm_medico_estabelecimento_mes` × `perfil_estabelecimento` (cálculo próprio) | 🟡 |
| ⬜ | Nº de UFs onde atuou | faixa | `crm_medico_estabelecimento_mes` × `perfil_estabelecimento` | 🟡 |
| ✅ | Exclusividade na farmácia principal (%), antes chamada "concentração na farmácia principal" | faixa mín–máx | `crm_farmacia_medico_ano` + `crm_medico_estabelecimento_mes` | 🟡 |
| ⬜ | Concentração nas 3 principais (%) | mínimo | `crm_medico_estabelecimento_mes` | 🟡 |
| ✅ | CRM exclusivo (uma única farmácia no período): atalho "100% (uma farmácia)" do filtro de exclusividade | sim/não | `crm_farmacia_medico_ano` + `crm_medico_estabelecimento_mes` | 🟡 |
| ⬜ | % das prescrições fora da UF do CRM | mínimo | `crm_medico_estabelecimento_mes` × `dados_medico` | 🟡 |

Observações sobre o nº de municípios:

- **Definição:** municípios distintos (`id_ibge7` da farmácia) com prescrição do médico no período, no Brasil. É o KPI "municípios" do modal do histórico (conferido: 244 = 244). Regra igual à dos demais filtros de atuação.
- **Estratégia de cálculo (benchmark, resultados idênticos):** cálculo próprio, médico → município, em vez de juntá-lo ao cálculo da exclusividade e do nº de farmácias. Juntar pesaria nos outros filtros e saiu 30–60% mais lento:

  | Período | Junto do cálculo atual | **Separado (adotado)** |
  |---|---|---|
  | 2020–2024 | 3,2 s | **1,2 s** |
  | 07/2015–12/2024 | 6,4 s | **4,7 s** |
  | 03/2021–08/2024 | 4,1 s | **2,1 s** |
  | 03–08/2023 | 1,3 s | **0,6 s** |

  No servidor, a primeira consulta fria de um período novo ficou entre 2,9 s (anos inteiros) e 7,0 s (meses quebrados); depois, 0,07–0,2 s.
- **Distribuição (2020–2024):** mediana de 8 municípios; 25% em até 4; 10% em mais de 23; 1% em mais de 60; máximo de 244. 55.403 médicos atuaram num único município.
- **Atalhos:** 1 (um município), até 3, ≥ 10, ≥ 30, ≥ 60.

Observações sobre o nº de farmácias:

- **Definição:** farmácias distintas com prescrição do médico no período, no Brasil. É o KPI "farmácias" do modal do histórico (conferido: 1.267 = 1.267).
- **Regra e cálculo:** os mesmos da exclusividade (nacional, escolhe médicos em todas as abas). Sai da mesma passada de `_atuacao_por_medico`, sem custo extra.
- **Distribuição (2020–2024):** mediana de 20 farmácias; 25% em até 8; 10% em mais de 90; 1% em mais de 292; máximo de 1.421.
- **Atalhos:** 1 (uma farmácia), até 5, ≥ 50, ≥ 100, ≥ 300. "1 farmácia" equivale a "exclusividade 100%" (30.895 médicos nos dois, 2020–2024).

Observações sobre a exclusividade:

- **Definição:** prescrições do médico na farmácia onde ele mais prescreveu ÷ total dele no Brasil, no período. É a coluna Exclusividade da aba CRMs do estabelecimento, olhando a farmácia principal, e bate com o KPI de concentração do modal do histórico (conferido: 97,49% = 97,49%).
- **Abrangência:** nacional (todas as farmácias do médico), independe do recorte territorial e dos filtros de farmácia. Escolhe médicos em todas as abas, inclusive na Por mês.
- **Atalhos:** ≥ 50% (atenção) e ≥ 80% (alto), os mesmos `CRM_EXCLUSIVIDADE_THRESHOLDS` da coluna; ≥ 95%; 100% (uma farmácia).
- **Estratégia de cálculo (escolhida por benchmark, todas com resultado idêntico):**

  | Estratégia | 2020–2024 | 07/2015–12/2024 | 03/2021–08/2024 | 03–08/2023 |
  |---|---|---|---|---|
  | A: só a tabela mensal (329 mi linhas) | 6,2 s | 15,0 s | 4,8 s | 1,0 s |
  | B: anual nos anos inteiros + mensal nas pontas | 3,1 s | 7,9 s | 3,9 s | 1,0 s |
  | **B2: B com chave Int64 única médico × farmácia (adotada)** | **2,2 s** | **4,4 s** | **2,4 s** | **0,8 s** |
  | C: tabela anual em memória (+1,4 GB) | 3,1 s | 6,3 s | 3,9 s | 0,9 s |
  | D: pré-cálculo por intervalo de anos na sincronização | ~5 min a mais na sincronização e não cobre períodos com meses quebrados | | | |

  O resultado fica em cache por período. Depois da primeira consulta, mudar a faixa ou os outros filtros leva ~0,05–0,1 s.
- **Custo da primeira consulta:** somam-se a exclusividade e a montagem do universo de médicos por território (comum a todos os filtros de médico, maior quando o período tem muitos meses soltos nas pontas). No servidor de desenvolvimento, a primeira consulta de um período novo ficou em 3–5 s com anos inteiros e chegou a 13 s em 05/2016–10/2021 (18 meses soltos). Se isso incomodar, o próximo passo é otimizar esse universo quando não há filtro de farmácia.

## 5. Perfil das farmácias onde atua (cruzamento com o risco da farmácia)

| Situação | Filtro | Tipo | Fonte | Viabilidade |
|---|---|---|---|---|
| ⬜ | % das prescrições em farmácias de risco crítico/alto | mínimo | `crm_medico_estabelecimento_mes` × matriz de risco | 🔴 |
| ⬜ | Atuou em farmácia com CNPJ inativo na Receita | sim/não | `crm_medico_estabelecimento_mes` × `situacao_rf` | 🟡 |
| ⬜ | Atuou em farmácia com conexão MS inativa | sim/não | `crm_medico_estabelecimento_mes` × `is_conexao_ativa` | 🟡 |
| ⬜ | Atuou em farmácia da lista de interesse | sim/não | `crm_medico_estabelecimento_mes` × preferências | 🟡 |

## Ideias que dependem de dado que não temos

| Situação | Filtro | Dado necessário |
|---|---|---|
| ⬜ | Prescreveu após cancelamento ou falecimento do médico | Situação do médico no CFM (ativo, cancelado, falecido). O cadastro atual traz só nome, UF e data de inscrição. |
| ⬜ | Especialidade médica (cruzamento com incompatibilidade patológica) | Especialidade do médico. |

## Entrega em ondas

1. **Onda 1 (🟢):** Cadastro CFM e Produção e intensidade.
   - Feito: busca, situação no CFM, UF do CRM, antes da 1ª inscrição, taxa diária e total de prescrições.
   - Pendente: os demais filtros do grupo 2 (dias com prescrição, meses ativos, % de meses com taxa elevada, maior sequência e pior mês).
   - Adiado: valor total prescrito, que depende de incluir o valor nos módulos CRM.
2. **Onda 2 (🟡):** Atuação e os pontos de atenção de sequência e distância em versão sim/não. Pede uma agregação médico × farmácia no backend, cacheada por período.
3. **Onda 3 (🔴):** Tabela pré-calculada de pontos de atenção por médico e mês. Destrava os filtros combinados ("qualquer ponto de atenção", "N ou mais") e permitiria tirar o limite de 100 médicos dos alertas do ranking.
   - Pela regra de sincronização de Parquets do `CLAUDE.md`, qualquer tabela nova entra no `data_cache.py`, na validação do boot rápido e no `src/scripts/sincronizar_cache.py`.

## Onde está implementado

- **Backend:**
  - regras e cache dos filtros de médico: `backend/api/services/analytics/crm_filtros_medico.py`;
  - universo farmácias ∩ médicos (mapa, ranking e aba Por mês): `backend/api/services/analytics/crm_analysis_filtrado.py`;
  - parâmetros da API: `situacao_cfm`, `uf_crm` (lista), `antes_inscricao`, `taxa_dia_min`, `taxa_dia_max`, `prescricoes_min`, `prescricoes_max`, `exclusividade_min`, `exclusividade_max`, `farmacias_min`, `farmacias_max`, `municipios_min`, `municipios_max`, `sequencia_severidade_min`, `sequencia_dias_min` e `sequencia_dias_max` em `/crm-prescricoes-analise` e `/crm-prescricoes-mensal`; `medico_query` para a busca.
- **Frontend:**
  - estado: `frontend/src/stores/crmFiltrosMedico.js`;
  - opções e rótulos: `frontend/src/config/crmFiltrosMedico.js`;
  - painel: `frontend/src/views/components/analises/AnalysisSidebar.vue` e faixas em `CrmFiltroFaixa.vue`;
  - chips: `frontend/src/views/components/analises/CrmFiltrosAtivos.vue`;
  - parâmetros: `buildCrmAnalysisParams` em `frontend/src/composables/useCrmPrescricoesAnalysis.js`.
