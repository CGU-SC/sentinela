# Changelog

Todas as mudanças relevantes do Sentinela serão registradas neste arquivo.

O versionamento segue o padrão SemVer: `MAJOR.MINOR.PATCH`.


## [1.6.11] - 2026-09-15

### Alterado
- **Terminologia dos alertas de CRM padronizada.** As ocorrências anteriormente apresentadas como "CRM inexistente" passaram a ser exibidas como "CRM não localizado" nas telas, tooltips, exportação em PDF, relatórios e documentação, preservando a distinção em relação aos CRMs irregulares.
- **Primeiro parágrafo da constatação de CRMs atualizado na Nota Técnica.** O texto agora contempla CRM e RMS, considera registros de CRM ou RMS não localizados e prescrições anteriores à primeira inscrição do médico na UF de registro, além de indicar a possibilidade de incompatibilidade com os requisitos legais do PFPB.
- **Orientação ao auditor incluída na constatação de CRMs.** A NT passou a exibir uma nota de auditoria orientando a consulta ao Painel Mais Médicos para registros não localizados e a inclusão do nome do médico nas tabelas do corpo da constatação e do ANEXO I.
- **Nota de rodapé numerada adicionada à constatação de CRMs.** A referência nº 17 aponta para a relação de médicos ativos no Painel Mais Médicos - APS do Ministério da Saúde.

## [1.6.10] - 2026-09-11

### Alterado
- **Tooltips das telas de detalhe de estabelecimento convertidos para HTML estruturado.** As explicações dos cards de CRM, da linha do tempo e Raio-X, dos alertas, dos falecidos e dos indicadores agora usam conteúdo formatado com título, descrição, seções explicativas e destaques visuais.
- **Ícones informativos adicionados aos componentes com tooltip.** Cards, controles, marcações do gráfico de análise horária, alertas CRM, indicadores e colunas de tabelas passaram a sinalizar explicitamente a disponibilidade da explicação contextual.
- **Conteúdo explicativo dos indicadores e comparativos ampliado.** Os textos passaram a explicar o significado dos resultados da farmácia, das medianas por região de saúde, UF e Brasil e dos respectivos riscos.
- **Estilo visual dos tooltips padronizado.** Todos os tooltips HTML da tela seguem o mesmo padrão visual escuro, com borda, sombra, acento laranja e tokens globais do tema.

### Corrigido
- **Tooltips que ultrapassavam as bordas da viewport reposicionados.** Ajustado o posicionamento dos tooltips ancorados nos primeiros componentes e nos filtros para que o conteúdo permaneça visível dentro da tela.
- **Mediana regional inválida no card "TOP 5 CRMs - VOLUME R$" removida.** O valor de `0.00%` vinha de um benchmark regional indisponível para o estabelecimento e era mascarado por uma inicialização silenciosa no backend. A informação foi retirada do card, da exportação em PDF e do contrato de dados do CRM, mantendo o percentual e o valor financeiro do Top 5.

## [1.6.9] - 2026-09-10

### Corrigido
- **Erro 422 ao gerar Nota Técnica por GTIN de Parkinson não encontrado na tabela de medicamentos sem comprovação.** Na função `_add_parkinson_gtin_sem_comprovacao_text` (`nota_tecnica_criticidades.py`), a correlação entre o achado clínico de Doença de Parkinson e a tabela de medicamentos com vendas sem comprovação buscava exclusivamente um único GTIN fixo (`7896226506371` - Prolopa). Quando a farmácia apresentava o achado em outros medicamentos de Parkinson (ex.: Carbidol) ou o GTIN fixado não possuía vendas sem comprovação no período, o gerador abortava a emissão da Nota Técnica com erro 422. Corrigido para identificar dinamicamente na lista de medicamentos sem comprovação aqueles associados à patologia de Parkinson, selecionando o principal para citação ou omitindo o parágrafo complementar caso nenhum medicamento do grupo possua venda sem comprovação no estabelecimento.
- **Erro 422 ao gerar Nota Técnica para farmácias em municípios com faixas etárias suprimidas no Censo IBGE 2022.** O Censo IBGE 2022 registra `NULL` em `nu_populacao` para faixas etárias (ex.: 85-89, 90-94, 95-99, 100+ anos) em que não há habitantes no município — comportamento esperado da base. O código de geração de Nota Técnica (`nota_tecnica_criticidades.py`) e o módulo clínico (`clinico.py`) tratavam esses nulos como dado corrompido e abortavam com erro fatal, impedindo a geração do documento. Corrigido substituindo `null` por `0` via `.fill_null(0)` no cast de `nu_populacao`, e removida a verificação que lançava exceção. Afetava centenas de municípios pequenos; identificado concretamente no CNPJ `14.239.517/0001-42` (`id_ibge7=1506161`).

## [1.6.8] - 2026-08-05

### Corrigido
- **Parágrafo inicial da "Conclusão e Encaminhamento" exibia "recebeu do Ministério da Saúde R$ 0,00" para CNPJs filiais sem ordens bancárias diretas.** Quando o CNPJ analisado é uma filial da rede e não há registros de ordens bancárias do PFPB vinculados diretamente a ele no SIAFI (`repasses_ctx["sem_repasses"]`), o valor efetivamente repassado é R$ 0,00 mesmo havendo faturamento declarado via SAV — porque o Ministério frequentemente registra os repasses no CNPJ da matriz da rede, como já era ressalvado no subitem 6 do documento. O texto da Conclusão, porém, seguia afirmando que a farmácia "recebeu R$ 0,00, correspondentes a supostas dispensações", uma frase contraditória. Em `backend/api/services/analytics/nota_tecnica.py`, o parágrafo agora usa uma redação alternativa para esse cenário: informa que não foram identificadas ordens bancárias diretamente vinculadas ao CNPJ da filial, aponta a possibilidade de repasse ao CNPJ da matriz e ancora o restante do raciocínio (percentual de "vendas sem comprovação") no valor faturado declarado via SAV, em vez do valor de repasse. O texto para CNPJs com repasses identificados e para CNPJs matriz sem repasses permanece inalterado.

## [1.6.7] - 2026-08-05

### Corrigido
- **Pontuação incorreta nos resumos de falecidos e de concentração de CRM na seção "Conclusão e Encaminhamento" da Nota Técnica.** Em `_build_resumo_falecidos` e em `_build_resumo_criticidade` (indicador `hhi_crm`), dois literais de string f-string adjacentes eram concatenados implicitamente pelo Python antes da chamada `.replace(',', '.')`, que deveria formatar apenas o separador de milhar do número seguinte. Isso fazia com que vírgulas do texto anterior (ex.: `"Registros, {período}, de"` e `"CRM {crm}, com"`) também fossem convertidas em ponto, gerando trechos como `"Registros. no período de julho de 2015 a dezembro de 2024. de 9 vendas..."`. Corrigido em `backend/api/services/analytics/nota_tecnica.py` pré-calculando o número formatado em uma variável separada antes de montar a string final, isolando o `.replace()` do texto ao redor.

## [1.6.6] - 2026-07-09

### Alterado
- **Home reorganizada para priorizar o mapa de risco territorial.** O mapa passou a ocupar a coluna direita da área analítica, atravessando verticalmente as duas linhas de gráficos, enquanto os gráficos de evolução semestral, ranking de UFs e faixas de não comprovação ficaram agrupados na coluna esquerda.
- **Proporção dos gráficos da Home ajustada.** A coluna esquerda agora divide a altura igualmente entre o gráfico de evolução semestral e a linha inferior com `Top 10 UFs` e `Estabelecimentos por faixa de não comprovação`.
- **Cards superiores da Home refinados.** A altura mínima dos cards de Sistema, Integridade, Escopo monitorado e Produção foi ajustada para preservar o layout compacto após a reorganização dos gráficos.
- **KPIs da tela de estabelecimentos compactados.** O espaçamento entre cards e o bloco visual dos ícones foram reduzidos para melhorar o encaixe dos KPIs em telas menores, mantendo todos os cards em uma única linha.


## [1.6.5] - 2026-07-02

### Alterado
- **Orientação sobre o comparativo entre faturamento e repasses na Nota Técnica.** O texto de atenção exibido após a tabela de ordens bancárias foi revisado para orientar a análise do montante faturado em relação ao valor efetivamente pago pelo Ministério da Saúde, distinguindo situações em que a possível fraude logrou sucesso daquelas em que permaneceu apenas na tentativa e indicando a avaliação correspondente na seção “Conclusão e Encaminhamento”.

### Corrigido
- **Referência à tabela de dispensações na seção de medicamentos sem comprovação.** O texto introdutório deixou de apontar incorretamente para o `Quadro 01` e agora referencia a tabela de dispensações do SAV, utilizando sua numeração dinâmica para permanecer correto mesmo quando tabelas opcionais alterarem a sequência do documento.


## [1.6.4] - 2026-06-26

### Alterado
- **Nota Técnica com sumário nativo do Word.** O sumário manual com numeração de páginas hardcoded foi substituído por um campo nativo `TOC` no DOCX, com `updateFields=true`, para que o Word atualize automaticamente a paginação ao abrir o documento. A geração voltou a ser rápida, sem automação COM/abertura invisível do Word no backend.
- **Refino tipográfico da Nota Técnica.** Removidos negritos remanescentes de textos corridos nas seções 3, 5.1, 5.2, 6 e nas criticidades, preservando títulos, cabeçalhos e estrutura das tabelas. O sumário permanece em fonte 12.
- **Tabelas clínicas refinadas.** Removido o negrito dos dados das colunas `Valor incompatível` e `Part. valor mun.` nas tabelas de comparativo municipal e ranking municipal do recorte de Doença de Parkinson.

### Corrigido
- **Correção de encoding em textos da seção 7 da Nota Técnica.** Reparado mojibake em `nota_tecnica_criticidades.py`, evitando saídas como `patolÃ³gica`, `ticket mÃ©dio` e `regiÃ£o` no documento gerado.

### Pendência operacional (fora do versionamento)
- O arquivo `docs/updates/manifest.sig` precisa ser refeito com a chave privada Ed25519 antes da publicação do manifesto no GitHub Pages.

## [1.6.3] - 2026-06-26

### Corrigido
- **Tooltip da badge "Estabelecimentos" no header do CNPJ reposicionado para `bottom-right`** em `frontend/src/views/components/cnpj/CnpjHeader.vue`. A versão 1.6.2 havia mudado para `bottom` (centralizado com a badge), mas como a badge está no canto esquerdo do header, a metade esquerda do tooltip saía do viewport. Agora usa `v-tooltip.bottom-right` (tooltip ancorado ao canto inferior-direito da badge, alinhado para dentro da viewport). Tooltip text agora é controlado por `redeBadgeTooltip` computed: `"Clique para ver todos os estabelecimentos desta rede"` quando `qtd > 1`, `"Esta farmácia é a única da rede"` quando `qtd === 1`.

### Alterado
- **Modal "Estabelecimentos da Rede" (`RedeEstabelecimentosDialog.vue`) agora usa paginação e ordenação server-side.** Antes o modal fazia 1 única chamada com `page_size: 200` (limitado a 200 CNPJs) e a tabela só ordenava localmente nos 200 itens (sem chamar o backend ao clicar no header de uma coluna). Agora o modal usa o mesmo padrão de `/estabelecimentos`: `paginator=true` + `lazy=true` no `DataTable`, com `@page` e `@sort` ambos chamando `fetchPage(page)` que repassa `page`, `page_size: 50`, `sort_field` e `sort_order` para o endpoint `/api/v1/analytics/indicadores-analise/cnpjs`. O sort padrão é `val_sem_comp desc`; clicar em qualquer header ordenável faz fetch do servidor (não local). Sort novo reseta para página 1. Paginator no rodapé mostra total e navegação `[« 1 2 3 ... »]`. Suporta redes com qualquer quantidade de CNPJs (sem o limite de 200).
- **Overlay de loading inicial no modal "Estabelecimentos"** em `RedeEstabelecimentosDialog.vue` agora segue exatamente o mesmo padrão visual e markup do overlay usado em `IndicatorDetailPanel.vue` (classe `.indicator-loading-overlay`, `position: absolute; inset: 0`, `backdrop-filter: blur(2px)`, `z-index: 5`, transition `ind-overlay-fade` com fade in/out de 0.18s, box centralizado com spinner + texto "Carregando os dados..."). Aparece quando o modal abre (clique na badge) e some quando o primeiro fetch termina. Mantido o `pt-options` no Dialog (correção de prop type feita anteriormente) e o `compact` prop no `EstablishmentRiskTable` para a tabela caber no modal de 70vh.

### Pendência operacional (fora do versionamento)
- O arquivo `docs/updates/manifest.sig` foi regenerado durante os ciclos de teste. A re-assinatura Ed25519 com a chave privada (que **não** fica no repositório) precisa ser refeita em conjunto com o `manifest.json` desta versão antes de publicar no GitHub Pages.


## [1.6.2] - 2026-06-26

### Corrigido
- **Badge "Estabelecimentos" no header do CNPJ agora aparece sempre** em `frontend/src/views/components/cnpj/CnpjHeader.vue`. Antes a badge só era renderizada quando `qtd_estabelecimentos_rede > 1` (farmácia como única da rede ficava sem a informação visível). Agora a condição é `>= 1` e a badge sempre aparece. Quando `qtd === 1`, a classe `clickable-badge` não é aplicada e o cursor permanece padrão (sem affordance de clique), e o tooltip passa a exibir `"Esta farmácia é a única da rede"` em vez de `"Clique para ver todos os estabelecimentos desta rede"`. O badge continua abrindo o modal `RedeEstabelecimentosDialog` quando clicado (com mais de 1 na rede).
- **Tooltip da badge "Estabelecimentos" reposicionado** para `v-tooltip.bottom-right` (era `top`, que empurrava o tooltip para fora do viewport no canto superior-esquerdo do header) e tooltip das badges da mesma linha padronizadas em `.bottom`. Adicionado `position: fixed !important` na regra `.p-tooltip.sentinela-tooltip` em `frontend/src/assets/styles/tooltip.css` para sobrepor o `position: relative` + `overflow: hidden` do `.detail-header-new` que estava criando um novo contexto de posicionamento e cortando o tooltip pela metade.
- **KeyError `'cnaes_secundarios'` ao carregar grafo N3 ou N4 da teia societária.** O schema dos Parquets de expansão N3 em `cache_registry.py:500-515` não inclui a coluna `cnaes_secundarios` (apenas N2/N4 a têm), mas `_build_network_nodes` em `backend/api/services/analytics/network.py:225` fazia `row["cnaes_secundarios"]` direto, gerando `KeyError: 'cnaes_secundarios'` → `RuntimeError: Erro batch N3 na teia ...` → HTTP 500 nos endpoints `GET /api/v1/analytics/cnpj/{cnpj}/network/level/3` e `/level/4`. Trocado para `row.get("cnaes_secundarios", [])` (defensivo, mantém compatibilidade com N2/N4 que têm a coluna). Comportamento de N2 e N4 inalterado.


## [1.6.1] - 2026-06-26

### Adicionado
- **Preference `gerar_pdf_visualizacao` no dialog da Nota Técnica.** Novo campo booleano opcional em `PreferencesService` (backend) e na store Pinia `notaTecnicaConfig` (frontend), que controla se o checkbox "Gerar PDF" do dialog regional da NT inicia marcado ou desmarcado. Persistido em `nota_tecnica.gerar_pdf_visualizacao` no backend; validado por `_validate_gerar_pdf_visualizacao` em `backend/api/endpoints/preferences.py` (rejeita valores não booleanos com HTTP 422). Carregado na inicialização do store e reenviado em `save()`. Default `false` quando ausente, preservando o comportamento original.

### Alterado
- **Tipografia do corpo da Nota Técnica padronizada em 12pt.** Todos os `_run(..., size=10)` em texto corrido foram migrados para `size=12` em `nota_tecnica.py`, `nota_tecnica_criticidades.py`, `nota_tecnica_crm.py`, `nota_tecnica_esocial.py`, `nota_tecnica_quadros.py`, `nota_tecnica_anexo_ii.py` e `nota_tecnica_anexos.py`. Inclui citações em bloco (`p_quote1`, `p_quote2`), referências a footnotes, parágrafos `p_op`, `p_sav`, `p_intro_41` e `p_intro_51`, e a conclusão. Garante uniformidade visual com os títulos de seção e o sumário.
- **Negrito substituído por sublinhado em valores destacados do texto corrido.** Em todos os runs `_run(..., color='334155')` que originalmente tinham `bold=True` (e que foram renumerados para `size=12` na mudança anterior), foi aplicado `underline=True` no lugar do `bold`. Total de 111 runs com `underline=True` ao final do refino, distribuídos em: 4 no `p_conclusao`, 7 no `_add_falecidos_criticidade_text` / `_add_incompatibilidade_patologica_text` / `_add_parkinson_demografia_text` / `_add_dispersao_geografica_text`, 6 no `_add_hhi_crm_text` (`p2`, `p_comparativo`, `p3`, `p4`), 3 no `_add_crm_unico_complementar_text` (`qtd_alertas`, `qtd_medicos`, `nu_prescricoes`), 4 no `_add_crms_multiplos_complementar_text` (`qtd_surtos`, `qtd_medicos`, `nu_prescricoes`, `nu_crms`), 5 no `_add_crm_volume_horario_complementar_text`, 12 no `_add_teto_text` / `_add_polimedicamento_text` / `_add_ticket_medio_text` / `_add_receita_paciente_text` / `_add_per_capita_text` / `_add_alto_custo_text` / `_add_vendas_rapidas_text` / `_add_recorrencia_sistemica_text` / `_add_dias_pico_text`, 1 no `_add_esocial_context_text` (`annual_summary`) e 1 no `_add_esocial_context_text` (relação semestral). Calls em tabelas/quadros (`_write_cell`, rodapés `ATENÇÃO:`, cabeçalhos, totalizadores, notas de rodapé) **não** foram alterados, preservando a hierarquia visual das tabelas. Runs com `bold=True` em `bold=col_idx in (...)` (iteração inline de células) também não entraram, pois são parte do contexto de tabela.
- **Tamanhos dos títulos de seções (Heading 1/2/3) igualados em 12pt.** O dicionário `heading_sizes` em `nota_tecnica.py` foi alterado de `{1: 13, 2: 12, 3: 11}` para `{1: 12, 2: 12, 3: 12}`. A hierarquia visual entre os níveis passa a ser dada apenas por **negrito herdado do estilo do Word + cor slate 700 (`#334155`) + espaçamento `space_before/after`**, sem diferença de tamanho. Comportamento de fonte monoespaçada e peso máximo 600 do design system continua sendo respeitado.
- **Títulos de tabelas, quadros, figuras e mapas reduzidos de 12pt para 10pt.** 35 ocorrências atualizadas: 7 em `nota_tecnica_criticidades.py` (Enquadramento regional, Indicadores críticos, Dispensações anuais, Comparativo municipal, Farmácias do município, Memória de cálculo Parkinson, Distribuição por UF), 6 em `nota_tecnica_crm.py` (Médicos com volume > 30, Episódios CRM único, Episódios múltiplos CRMs, Horários anômalos, CRMs por valor, Médicos/CRMs por valor PFPB), 1 em `nota_tecnica_esocial.py` (Síntese movimentação sem funcionário), 11 em `nota_tecnica_quadros.py` (Quadro 01, Quadro 01-B, Sócios volume atípico, Comparativo regional, GTINs sem estoque, Evolução semestral, Medicamentos atípicos, Vínculos eSocial, Disp. SAV/NF-e, Ordens bancárias 1 e 2), 3 em `nota_tecnica_anexo_ii.py` (Resumo geral, Medicamentos sem comprovação, Tabelas por GTIN 3.x), 1 em `nota_tecnica_anexos.py` (Detalhamento vendas falecidos) e 6 em `nota_tecnica_charts.py` (Mapa 01, Posicionamento regional, Posição percentílica, Evolução semestral, Comparação Parkinson, Faixas etárias). Calls `size=12, bold=True` em linhas de **texto corrido** (não títulos) como `_add_crm_intensiva_complementar_text`, `_add_crm_volume_horario_complementar_text` e `_add_crms_irregulares_text` **não** foram alterados.
- **Seção 6.1 (Evolução das transferências)** agora inclui a relação faturamento PFPB × capital social da farmácia. Em `nota_tecnica.py`, dentro de `_add_evolucao_text`, o parágrafo `p_54_analise` passou a incluir, quando `cap_social_val > 0`: `" (a relação do faturamento no âmbito do programa sobre seu capital social, de R$ X, é de Y%). "`. Quando `cap_social_val == 0`, mantém o texto original terminando em ponto final. A nota de rodapé interna do Quadro 01 (que duplicava essa informação) foi removida de `_add_quadro_identificacao` em `nota_tecnica_quadros.py` para evitar redundância.
- **Headings 3 da Seção 7.1.1 (Incompatibilidade patológica)** padronizados com `font.size = Pt(12)` e `paragraph_format.space_after = Pt(8)` em `nota_tecnica_criticidades.py`, alinhando com o restante do documento.
- **Tabela 10 (Dispensações anuais de medicamentos para Parkinson)** deixou de aplicar `bold` nas colunas de dados 2 (`CPFs incompat.`), 5 (`Aut. incompat.`) e 7 (`Valor incompatível`). O cabeçalho da tabela permanece em negrito. Mudança aplicada em `_add_clinica_evolucao_anual_table` (`bold=col_idx in (2, 5, 7)` → `bold=False`).
- **Tabela 11 (Memória de cálculo da comparação epidemiológica de Parkinson)** deixou de aplicar `bold` na coluna de dados 1 (`Valor`). O cabeçalho permanece em negrito. Mudança aplicada em `_add_parkinson_demografia_table` (`bold=col_idx == 1` → `bold=False`).
- **Endpoint de geração da Nota Técnica** (`/api/v1/analytics/cnpj/{cnpj}/nota-tecnica`) agora loga o traceback completo em erros inesperados. O `except Exception` em `backend/api/endpoints/analytics.py` usa `logger.bind(sentinela_log="nota_tecnica_error")` para gravar o traceback via `traceback.format_exc()` e inclui o último frame do trace no `detail` do `HTTPException` retornado, permitindo identificar arquivo e linha do erro sem acesso aos logs.
- **Quebras de página entre seções primárias da Nota Técnica.** A estrutura de seções do `generate_nota_tecnica` foi ajustada em `nota_tecnica.py` para que cada seção primária (1 a 8) comece em página própria, com exceção das seções 1 e 2 (ASSUNTO e REFERÊNCIAS) que compartilham a página inicial por já serem curtas. Mudanças aplicadas: `sec_ref` (linha 933) passou de `WD_SECTION.CONTINUOUS` para `WD_SECTION.NEW_PAGE` (seção 1 em página nova após o sumário); `sec_41` (linha 1058) idem (seção 4 em página nova após seção 3); `sec_5_intro` (linha 1169) idem (seção 5 em página nova); `_start_section` antes da seção 6 (linha 1266) com `start=WD_SECTION.NEW_PAGE`; idem antes da seção 7 (linha 1481); e novo `_start_section(..., start=WD_SECTION.NEW_PAGE)` antes da seção 8 (linha 1762) para forçar a CONCLUSÃO em página nova. Subseções (`sec_42` 4.2 e `sec_51` 5.1) permanecem com `CONTINUOUS`, mantendo a coesão dentro da seção primária. **Números do sumário atualizados** em `_build_sumario` para refletir a nova paginação: seções 1 e 2 → página 3, seção 3 → 4, seção 4 → 5, seção 5 → 6, seção 6 → 7, seção 7 → 8, seção 8 → 9.
- **Espaçamento de "Fonte:" das tabelas clínicas padronizado.** Em `nota_tecnica_criticidades.py`, 7 blocos de rodapé (`p_foot` em `_add_indicador_regional_table`, `_add_indicadores_criticos_quadro`, `_add_clinica_evolucao_anual_table` — Tabela 10, `_add_clinica_municipio_resumo_table` — Tabela 11, `_add_clinica_municipio_farmacias_table` — Tabela 12, `_add_parkinson_demografia_table` — Tabela Parkinson demografia, e `_add_dispersao_geografica_origem_uf_table`) foram refatorados para usar o helper `_format_quadro_footnote(p_foot)` importado de `nota_tecnica_quadros.py`, com `space_before=Pt(5)` e `space_after=Pt(18)`. Antes usavam `space_before=Pt(3)` e `space_after=Pt(8)` manuais, que geravam texto muito colado após a tabela. Agora o respiro entre a tabela e o "Fonte:" segue o mesmo padrão das tabelas do `nota_tecnica_quadros.py` (Tabela 5 Evolução semestral, Quadro 01, etc.).
- **Linha do CNPJ removida do título do Quadro 01.** O título do Quadro 01 em `_add_quadro_identificacao` (`nota_tecnica_quadros.py`) agora é apenas `"Quadro 01 - Informações detalhadas da Farmácia {razao_social}"`, sem a segunda linha `(CNPJ {cnpj_fmt})` que duplicava a informação já exibida na primeira linha da tabela do quadro. Removido também o `_run(p_title, f"\n(CNPJ ...)", color='475569', size=12)`. O CNPJ continua aparecendo no corpo do quadro na primeira linha `('CNPJ', data.get('cnpj_fmt'))`, sem perda de informação.

### Pendência operacional (fora do versionamento)
- O arquivo `docs/updates/manifest.sig` foi regenerado durante os ciclos de teste do trabalho de TOC dinâmico. A re-assinatura Ed25519 com a chave privada (que **não** fica no repositório) precisa ser refeita em conjunto com o `manifest.json` desta versão antes de publicar no GitHub Pages, ou a próxima checagem online do app cairá em `verification_unavailable` (sem bloquear, mas sem garantia de autenticidade online até o cache expirar).


## [1.6.0] - 2026-06-25

### Adicionado
- **Modal de estabelecimentos da rede ao clicar na badge "Estabelecimentos"** em `CnpjHeader.vue`. Quando `qtd_estabelecimentos_rede > 1`, a badge exibe um modal fullscreen com a lista de todos os estabelecimentos da rede usando a tabela modelo `EstablishmentRiskTable.vue`. O modal reaproveita o endpoint existente `/api/v1/analytics/indicadores-analise/cnpjs` com `indicador=percentual_nao_comprovacao` + `cnpj_raiz` (zero alteracoes no backend). Clique na linha fecha o modal e navega para o detalhe do CNPJ (drill-down).
- **Novo componente** `frontend/src/views/components/cnpj/RedeEstabelecimentosDialog.vue`: modal PrimeVue fullscreen (70vw x 70vh) com header, loading state, empty state e tabela reusada. Reaproveita o CSS class `.clickable-badge` (cursor pointer + hover com lift) ja existente.
- **Prop `compact` em `EstablishmentRiskTable.vue`**: quando `true`, a tabela assume sua altura natural em vez de reservar 20 linhas. Aplicado via `pt` do PrimeVue (inline style no `.p-datatable-wrapper`) para bypass de escopo de CSS scoped. Default `false` preserva o comportamento original em `/estabelecimentos`.

### Alterado
- **Header do CNPJ simplificado**: a badge "Grande Rede" (Sim/Não) foi removida. A informacao da quantidade de estabelecimentos da rede agora vive sozinha em uma badge dedicada "Estabelecimentos", que e clicavel e abre o modal de rede. Resultado: a interface indica visualmente qual informacao e interativa, sem perder o conteudo. Estabelecimentos individuais (qtd = 1) nao mostram a badge.
- **Tooltip global** em `assets/styles/tooltip.css`: adicionado `position: fixed` + `pointer-events: none` no `.p-tooltip.sentinela-tooltip` para evitar clipping por ancestrais com `overflow: hidden` ou `transform`.

### Correcoes
- **Modal de rede com altura limitada**: 70vw x 70vh via `style` do `<Dialog>`, com `pt` aplicado para sobrescrever o `min-height: 840px` da tabela compartilhada quando dentro do modal.


## [1.5.1] - 2026-06-25

### Corrigido
- **Nota Técnica Preliminar não quebra mais quando a farmácia não tem repasses no SIAFI para o período.** Antes, `_build_repasses_anuais_context` em `backend/api/services/analytics/nota_tecnica_contexts.py` levantava `RuntimeError("Sem registros de repasses para CNPJ ... no período informado.")` e a geração da NT falhava. Agora retorna um contexto válido com `rows: []`, `total: 0.0`, `sem_repasses: True` e `periodo_fmt` calculado a partir do período informado (`"2020 a 2024"`, `"2024"`, `"a partir de 2020"`, `"até 2020"`, ou `"período analisado"` quando nenhum dos dois é fornecido).
- **Tabela de ordens bancárias adaptada para o cenário sem repasses.** `_add_tabela_repasses_anuais` em `backend/api/services/analytics/nota_tecnica_quadros.py` agora detecta `sem_repasses` e gera uma linha informativa mesclada (`"Não foram identificadas ordens bancárias recebidas do Ministério da Saúde para o CNPJ X no período analisado."`) em vez de tabela vazia. O título da tabela vira `"Consulta a ordens bancárias do Ministério da Saúde para a Farmácia ..."` e o texto de ATENÇÃO é substituído por um parágrafo específico: `"Não foram identificadas ordens bancárias no período analisado; portanto, a comparação entre o faturamento declarado ao MS e os valores efetivamente repassados deve ser avaliada considerando o possível repasse dos recursos para o CNPJ da Matriz."`. Total permanece R$ 0,00 e a fonte SIAFI é mantida. A numeração das tabelas da NT não é quebrada.
- **Texto introdutório da seção de ordens bancárias condicional** em `nota_tecnica.py`. Quando há repasses, mantém o texto original sobre valores efetivamente recebidos. Quando não há, vira `"Quanto aos valores efetivamente repassados pelo Ministério da Saúde, referentes ao PFPB, não foram identificados registros para o CNPJ, conforme tabela a seguir."`.

### Comportamento preservado
- Quando há repasses no período, a tabela, o título, o texto de ATENÇÃO sobre glosa e o comportamento dos números são idênticos à versão 1.5.0.
- Erros legítimos (CNPJ fora do perfil, cache/schema indisponível, colunas obrigatórias ausentes) continuam sendo levantados como exceções.
- Cobertura de testes isolados em `src/scripts/test_nota_tecnica_sem_repasses.py`: 3 cenários (sem repasses, com repasses, 5 variações de `periodo_fmt`).


## [1.5.0] - 2026-06-25

### Adicionado
- **Pre-visualizacao interna da Nota Tecnica no Sentinela Desktop.** Apos gerar e salvar o `.docx` na pasta `notas_tecnicas`, o aplicativo converte automaticamente uma copia para PDF usando Microsoft Word via `docx2pdf`/`pywin32`. O toast de sucesso passa a exibir o botao **Visualizar**, abrindo o PDF dentro do proprio Sentinela em um modal dedicado.
- **Modal global de visualizacao de documentos PDF** em `frontend/src/views/components/DocumentPreviewDialog.vue`, com opcao de abrir o arquivo externamente quando necessario.
- **Ponte nativa segura no PyWebView** para conversao DOCX/PDF e leitura do PDF em base64, restrita a pasta `notas_tecnicas`, evitando leitura arbitraria do disco.
- **Selecao de formatos de saida na Nota Tecnica.** O modal de dados da NT passa a exibir a secao **Formatos de saida**, deixando claro que a versao Word editavel sempre sera gerada e permitindo ao usuario optar por gerar ou nao a versao PDF para visualizacao.
- **Logs de desempenho da Nota Tecnica.** A geracao do DOCX agora registra `nota_tecnica_docx` com tempo em milissegundos no log de requisicoes, e a conversao DOCX/PDF no Desktop registra o tempo da conversao no log `sentinela_*.log`.

### Alterado
- **Toasts de documentos salvos** agora podem oferecer visualizacao interna quando houver PDF disponivel. O Relatorio PDF tambem passa a expor o botao **Visualizar** no modo Desktop.
- **Dependencias desktop atualizadas** com `docx2pdf` e `pywin32` para suportar a conversao fiel do DOCX usando o Microsoft Word instalado no ambiente.
- **Numero do processo SEI no modal da Nota Tecnica** agora limita a entrada aos 17 digitos obrigatorios e aplica a mascara `00000.000000/0000-00`, evitando que o usuario digite um processo maior que o contrato aceito pelo backend.
- **Toasts de sucesso para arquivos salvos** deixam de fechar automaticamente, mantendo as acoes de abrir/visualizar o documento disponiveis ate o usuario encerrar a notificacao.


## [1.4.1] - 2026-06-25

### Alterado
- **Tela de bloqueio administrativo dedicada** em `frontend/src/views/components/ExecutionBlocker.vue`. A 1.4.0 compartilhava a `UpdateBlocker.vue` entre `update_required` e `execution_blocked`; o teste de UX mostrou que a tela única confundia o operador, porque "atualização necessária" e "decisão administrativa" são contextos diferentes. A nova tela tem visual institucional e sóbrio (escuro, ícone escudo/X, eyebrow `Decisão administrativa`, pill `Bloqueado desde`, versão instalada como referência), sem a tabela de versões que só fazia sentido em `update_required`. Ações: **Verificar novamente** (primária), **Ver alterações** e **Baixar atualização** (secundárias, condicionais), **Sair** (ghost, só desktop).
- **Tela de atualização obrigatória isolada** em `frontend/src/views/components/UpdateBlocker.vue`. Voltou a ser exclusiva para `update_required`, com a tabela de versões (Sua versão / Versão mínima / Versão mais recente) e os 3 botões originais (Baixar, Ver alterações, Sair).
- `App.vue` passou a rotear o status para a tela certa:
  - `update_required` → `<UpdateBlocker />`
  - `execution_blocked` → `<ExecutionBlocker />`


## [1.4.0] - 2026-06-25

### Adicionado
- **Bloqueio administrativo de execução via manifesto assinado.** O `manifest.json` passa a aceitar um bloco `execution_policy` com a flag `blocked_execution`, título, mensagem e timestamp opcionais (`blocked_since`). Quando a flag vem `true` em um manifesto com assinatura Ed25519 válida, o backend devolve status `execution_blocked` e o frontend exibe uma tela de bloqueio fullscreen sem confirmação do usuário. O desbloqueio é automático na próxima checagem (15 min ou botão "Verificar agora") quando o manifesto volta para `blocked_execution: false`.
- **Schema do manifesto atualizado** com `ExecutionPolicy` (Pydantic) em `backend/api/schemas/system_update.py`. O campo `execution_policy` é obrigatório a partir desta versão: manifestos sem o bloco falham a validação de schema, sem fallback silencioso.
- **Status `execution_blocked`** no contrato de `UpdateStatusResponse`, propagado por `check_for_updates()` e `initialize_update_check()` em ambos os caminhos (remoto e cache offline). O cache local com assinatura válida continua aplicando o bloqueio mesmo sem rede, evitando que o usuário se proteja via desligamento de internet.
- **Tela dedicada de bloqueio administrativo** em `frontend/src/views/components/ExecutionBlocker.vue`. Visual institucional e sóbrio: tom vermelho escuro, ícone de escudo/X maior, eyebrow `Decisão administrativa` em caps, data `Bloqueado desde` em pill, versão instalada como referência. Sem tabela de versões (que não faz sentido fora do contexto de `update_required`). Ações: **Verificar novamente** (primária), **Ver alterações** e **Baixar atualização** (secundárias, condicionais), **Sair** (ghost, só desktop).
- **Tela de atualização obrigatória isolada** em `frontend/src/views/components/UpdateBlocker.vue`. Voltou a ser exclusiva para `update_required`, com a tabela de versões (Sua versão / Versão mínima / Versão mais recente) e os 3 botões originais.
- `App.vue` passou a rotear o status para a tela certa:
  - `update_required` → `<UpdateBlocker />`
  - `execution_blocked` → `<ExecutionBlocker />`
- **Store `systemUpdate.js`**: `blockTitle`, `blockMessage` e `blockedSince` permanecem como campos consumidos pela `ExecutionBlocker.vue`; `isExecutionBlocked` é o gatilho de renderização.
- **Helpers de mensagem** `_manifest_status()` e `_manifest_message()` em `backend/api/services/system_update.py` centralizam a derivação do status final e da mensagem, garantindo que o bloqueio administrativo tenha prioridade sobre `update_required`/`update_available`/`current`.

### Alterado
- **Card "Sistema" da HomeView** passa a refletir o status `execution_blocked` com tom `critical` e label "Execução bloqueada" no lugar de "Atualização obrigatória" quando o motivo do bloqueio é administrativo, evitando confundir o operador.
- **Contrato do manifesto é breaking**: campo `execution_policy` agora é obrigatório. Manifestos antigos sem o bloco serão rejeitados pela validação Pydantic, e o sistema cai em `verification_unavailable` (sem bloquear, apenas sem garantia online) até a próxima publicação já com o novo formato.


## [1.3.1] - 2026-06-25

### Alterado
- **SentinelaUpdater.exe com visual mais neutro e alinhado à identidade do Sentinela**: o ícone azul genérico do topo foi substituído pelo ícone oficial do Sentinela, embutido no HTML do updater. O botão `Fechar` deixou de usar fundo azul em degradê e passou a usar estilo neutro translúcido, com borda sutil e hover discreto. Textos das etapas e status final ficaram mais claros no tema escuro; o status de conclusão agora usa tom de sucesso.
- **Sidebar inicia sempre em estado previsível**: o grupo `Geral` abre por padrão e o grupo `Alertas` inicia fechado sempre que o sistema é carregado. A persistência do estado do acordeão da sidebar em `localStorage` foi removida; o usuário ainda pode abrir/fechar os grupos normalmente durante a sessão.


## [1.3.0] - 2026-06-25

### Adicionado
- **Novo alerta "CNPJ Nível 2 da Teia com PAR"** no card **Integridade / Quadro de Alertas** da HomeView. O alerta conta CNPJs alvo que possuem ao menos um CNPJ vinculado no nível 2 da teia societária com registro em Processo Administrativo de Responsabilização (PAR), usando o cache global `par_teia_alvos.smod` e a coluna obrigatória `has_par_n2`. Ao clicar no alerta, o sistema ativa automaticamente o filtro da sidebar `CNPJs com PAR = CNPJ Nível 2 da Teia com PAR`.

### Alterado
- **Filtro "CNPJs com PAR" refinado na sidebar**: removida a opção `Alvo com PAR`, que não possuía resultado útil para o fluxo atual. Os labels foram ajustados para `CNPJ Nível 2 da Teia com PAR`, `CNPJ Nível 4 da Teia com PAR` e `Qualquer CNPJ com PAR`.
- **Labels dos filtros de integridade societária ajustados** para linguagem mais curta e direta: `Apenas CNPJs com CNAE incompatível`, `Apenas sócios < 21 ou > 80 anos` e `Apenas CNPJs com sócio falecido`.
- **Labels do card Integridade atualizados**: `Sócio em programa social (CadÚnico/Defeso)` passou a `Sócio inscrito no CadÚnico/Defeso`, e `Sócio com idade atípica (< 21 ou > 80 anos)` passou a `Sócios < 21 ou > 80 anos`.


## [1.2.3] - 2026-06-24

### Adicionado
- **Reorganização da sidebar em 2 grupos consolidados** (AppSidebar.vue). As antigas 4 seções (`Escopo`, `Cadastro`, `Integridade societária`, `Parâmetros`) foram consolidadas em apenas 2: **Geral** (filtros de localização + cadastro + parâmetros de auditoria, com 15 filtros) e **Alertas** (sinais de risco societário e operacional, com 8 filtros). A seção `Integridade societária` foi renomeada para `Alertas` com ícone `pi pi-bell`. O filtro `Aumento Semestral Atípico` foi movido de `Parâmetros` para `Alertas` por ser um sinal de comportamento suspeito (crescimento semestral anormal de faturamento).
- **Acordeão exclusivo** entre os 2 grupos: ao abrir um, o outro fecha automaticamente. Implementado em `toggleSection(id)` usando o conjunto `SECTION_IDS = ['geral', 'integridade']` — quando o usuário clica num heading fechado, o `Set` de seções colapsadas recebe todos os outros IDs (forçando o fechamento deles). Comportamento padrão de Material Design / Linear / Notion.
- **Busca suspende o acordeão durante a digitação**. O estado manual do acordeão (`collapsedSections`) é persistido em `localStorage`, e o estado efetivo usado pelo template (`effectiveCollapsed`) é um `computed` derivado: durante a busca, qualquer seção que tenha matches é forçada a abrir (remove do Set), independente do estado manual. Ao limpar a busca, o estado manual do acordeão é restaurado automaticamente. Assim, ambos os grupos podem ficar abertos simultaneamente se a busca tiver matches em ambos.

### Corrigido
- **Filtros da seção `Cadastro` sumiam** (primeira tentativa) quando os 2 grupos estavam colapsados. Causa raiz: os 2 `<div class="grid-filters">` da seção Cadastro (que envolvem os pares Situação RF+Conexão MS e Porte CNPJ+Grande Rede) eram filhos diretos do `.sidebar-content` (`gap: 0.5rem`), mas só os `.filter-section` dentro tinham `v-show` baseado no estado de colapso. Os wrappers `.grid-filters` em si continuavam com `display: grid` no DOM, gerando espaçamento residual. Fix: adicionado `v-show="!isSectionCollapsed('geral')"` nos wrappers `.grid-filters` da seção Geral (que unificou Cadastro+Escopo+Parâmetros).
- **Bug de espaçamento**: quando a seção `Cadastro` era a única fechada, ela ganhava padding extra em relação às outras seções colapsadas (cerca de 8px), por causa do `gap: 0.5rem` do `.sidebar-content` somado aos wrappers `.grid-filters` residuais. Resolvido junto com o fix acima.
- **Bug de posicionamento dos 4 filtros de Parâmetros** (Percentual, Período, Valor Mínimo, Aumento Semestral): ao mover de Parâmetros para Geral, os filter-sections foram parar DEPOIS do heading de Alertas no DOM, fazendo eles aparecerem visualmente após o Alertas. Reorganização do template colocou os 4 dentro de um wrapper `<div v-show="!isSectionCollapsed('geral')">` posicionado entre o último filter-section de Cadastro (cnpjRaiz) e o heading de Alertas.
- **Migração automática do localStorage** ao abrir a página: usuários com chaves `['escopo']`, `['cadastro']` ou `['parametros']` salvas de versões anteriores (1.2.0 e 1.2.1) são migradas automaticamente para `['geral']` em `loadCollapsedFromStorage()`. Garante que o estado de colapso continue funcionando após o release.

### Alterado
- **Badge de contagem de matches/filtros** nos headings das seções reposicionado da esquerda para o canto direito (antes do chevron), usando `position: absolute; right: 1.8rem`. Antes, o badge aparecia entre o nome da seção e o chevron, deslocando o texto quando o badge aparecia (ao digitar na busca). Agora, o nome "Geral"/"Alertas" permanece fixo à esquerda, o badge "flutua" no canto direito reservado, e o chevron fica no canto extremo direito (`margin-left: auto`).
- **Altura do input de busca** da sidebar alinhada com a altura do filtro "Estabelecimento" (32px, `font-size: 0.75rem`), igual aos demais `.filter-input` da sidebar. Antes, o input tinha padding vertical próprio que resultava em ~35px.
- **Fundo do input de busca** no estado normal agora usa `var(--sidebar-input-bg)` (mesmo fundo dos outros inputs da sidebar) em vez de `color-mix(--sidebar-bg 60%, white 8%)`, mantendo coerência visual com o resto da sidebar. O estado focus usa o mesmo `var(--sidebar-input-bg)` (diferença fica no border-color `--primary-color` e no box-shadow `0 0 0 1px --primary-color, 0 4px 12px rgba(0,0,0,0.05)`).
- **Espaçamento entre cards de filtro** (12px). O `.sidebar-content` tem `gap: 0.75rem` e o novo wrapper `.sidebar-section-body` (que envolve os filter-sections de cada grupo colapsável) tem `gap: 0.75rem` e `display: flex; flex-direction: column`. O `margin-bottom: 0.15rem` legado do `.filter-section` foi removido (redundante com o gap). Cards ficam visualmente separados sem ficar "colados" nem "esparsos".
- **Destaque dos headings das seções** (Geral e Alertas) com `background: color-mix(--primary-color 6%, transparent)`, cor do texto 100% opacidade (em vez de 74%), e `border-top` sutil removido. O fundo azulado sutil torna os 2 grupos visualmente identificáveis como "blocos" no flow da sidebar. Hover mantém o fundo `--primary-color` 8% (já existente). `min-height` aumentado de 1.45rem para 2rem (32px), igualando à altura dos inputs.
- **Espaçamento entre label e input** dos filtros aumentado de `margin-bottom: 0.25rem` (4px) para `0.5rem` (8px) no `.filter-label`. Mais respiro entre o título do filtro e o componente.
- **Busca só ativa com 2+ caracteres**. O `computed searchTerm` retorna `""` quando o termo normalizado tem menos de 2 caracteres, fazendo `filterMatchesSearch` retornar `true` para todos os filtros (estado normal) e o badge `searchTerm` não aparecer. Evita ruído de matches com 1 letra (que retorna quase todos os grupos).
- **Filtro "Sócio em Programa Social" renomeado para "Sócio no CadÚnico/Defeso"** no `FILTER_INDEX`, alinhando com o título visível no template. Keywords ajustadas: removido "programa social" (que continha "gra" como substring, gerando match falso ao buscar "gra") e adicionado "seguro defeso" e "pobreza" (termos mais específicos do CadÚnico/Defeso).

## [1.2.2] - 2026-06-24

### Adicionado
- **Botão flutuante de "Limpar todos os filtros"** na sidebar (AppSidebar.vue), posicionado acima do badge de filtros ativos. Aparece somente quando `activeFilterCount > 0` e chama `filterStore.resetFilters()`. Visual consistente com os outros botões flutuantes (`sidebar-float-btn`, `sidebar-lock-btn`, `sidebar-filter-count-btn`), mas com tom `--risk-high` para reforçar a ação destrutiva. Ícone `pi pi-eraser`. Gap uniforme de 6px entre todos os 4 botões flutuantes da sidebar.
- **Reorganização da sidebar com acordeão colapsável + busca textual** (AppSidebar.vue). As 4 seções (`Escopo`, `Cadastro`, `Integridade societária`, `Parâmetros`) agora são `<button>` clicáveis com chevron rotativo (`pi-chevron-down` ↔ `pi-chevron-up`), estado persistido em `localStorage` (chave `sentinela_sidebar_collapsed`), e `aria-expanded`/`aria-controls` para acessibilidade. Novo input "Buscar filtro..." no topo da sidebar filtra os 23 filtros em tempo real via índice declarativo `FILTER_INDEX` (label + keywords por filtro), com normalização de acentos (`NFD` + remoção de diacríticos). Quando a busca está ativa, o badge em cada seção mostra a contagem de matches em vez da contagem de filtros ativos, e seções sem matches somem. Hover dos headings ganha fundo suave `--primary-color` 8%, focus-visible com outline `--primary-color` 2px.

### Alterado
- **Limiar do alerta "Vendas para UFs sem fronteira"** subiu de 5% para 10%: constante `LIMIAR_ALERTA_UF_NAO_VIZINHA_PCT` em `backend/api/services/analytics/geografico.py` foi de 5.0 para 10.0. Texto do tooltip do alerta (HomeView) e default do filtro da sidebar (`DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL` em `constants.js`) ajustados para 10. Chip de quick-select no AppSidebar.vue: `[5, 10, 20, 50]` → `[10, 20, 30, 50]` (5 substituído por 30).

### Corrigido
- **Filtros de integridade não ativavam a alça "Filtros ativos"** na sidebar. Os checkboxes `Sócio com vínculo eSocial` e `Sócio em programa social` eram contados normalmente, mas `Sócio ativo falecido`, `Sócio com idade atípica` e `Farmácia com CNAE incompatível` não faziam aparecer nem o badge com a contagem nem o botão de limpar todos. Causa raiz: o array `fields` do `computed activeFilterCount` em `AppSidebar.vue:448` não incluía `selectedSocioFalecido`, `selectedSocioIdadeAtipica` nem `selectedCnaeIncompativel` — a função `isFilterActive` (`AppSidebar.vue:400`) já dava suporte aos 3, mas eles nunca eram contados. Adicionados os 3 campos ao array, na mesma família de filtros de integridade (logo após `selectedSocioEsocial`).
- **Tooltips nativos (`title=""`) nos 4 botões flutuantes da sidebar** (`sidebar-clear-btn`, `sidebar-filter-count-btn`, `sidebar-float-btn`, `sidebar-lock-btn`) trocados pela diretiva `v-tooltip.right` do PrimeVue, alinhando com o restante do projeto (que usa `v-tooltip.right="'Limpar filtro'"` nos chips de filtro ativos desde a v1.1.x). Antes, os tooltips dos 4 botões que ficam colados na borda lateral da sidebar apareciam com o estilo nativo do browser (lento, sem fade, com delay alto) e o do botão de limpar não aparecia de jeito nenhum em alguns browsers.

## [1.2.1] - 2026-06-24

### Adicionado
- **Alertas do card Integridade (HomeView) são clicáveis.** Cada alerta no panorama de alertas é agora um botão que, ao clicar, ativa/desativa o filtro correspondente na sidebar (mapeamento `alerta.tipo` → `filterStore.selectedXxx` em `ALERTA_TIPO_PARA_FILTRO`). Comportamento de toggle: clique 1 ativa, clique 2 desativa. Para os filtros dropdown (`Sócio em programa social` e `Sócio com vínculo eSocial`) o valor aplicado é `direto`. Hover deixa o card levemente mais saturado e com lift de 1px; o estado ativo (filtro ligado) ganha bg/border mais saturados, `box-shadow` interna e tom da cor de risco correspondente (`--risk-high` para crítico, `--risk-medium` para atenção). Acessibilidade: `aria-pressed` reflete o estado e `aria-label` descreve a ação.

### Corrigido
- **Filtro "Sócio ativo falecido" não restringia a tabela "Farmácias por Indicador"** em `/estabelecimentos` (`/api/v1/analytics/indicadores-analise/cnpjs`). O card Escopo, Produção e Integridade e o endpoint `/resumo` reagem normalmente, mas a tabela de CNPJs por indicador mantinha o total sem filtro quando o checkbox de sócio falecido era marcado. Causa raiz: o campo `socio_falecido` não estava declarado em `_INDICADOR_SCOPE_FILTER_FIELDS` (`backend/api/services/analytics/indicadores.py`), então a função `_build_indicador_dataset_cached` filtrava o parâmetro fora do `filters` dict antes de passar para `_build_indicador_scope_base`, mesmo com a assinatura da função aceitando o parâmetro. Adicionado `("socio_falecido", _normalize_cache_bool)` à tupla, e os kwargs `socio_falecido=socio_falecido` nos 2 call sites de `_build_indicador_dataset_cached` que faltavam (no commit `084a5dc` o `replaceAll` só pegou 1 dos 3 call sites por causa de indentação diferente).

## [1.2.0] - 2026-06-24

### Adicionado
- **Filtro "Sócio ativo falecido"** na sidebar do dashboard, exibido logo após o filtro de idade atípica, permitindo restringir o dashboard a estabelecimentos com ao menos um sócio pessoa física com vínculo societário ativo identificado como falecido na base de óbitos. Reage em todos os cards (Escopo, Produção, Integridade) e KPIs. Fonte: coluna `is_falecido` de `dados_socios.parquet` (materializada no ETL do SQL Server a partir do cruzamento do CPF do sócio com a base de óbitos).
- Filtro integrado em todos os endpoints: `/resumo`, `/faixas-risco`, `/producao-semestral`, `/alertas-panorama`, `/indicadores-analise` e `/indicadores-analise/cnpjs`.
- `build_perfil_filtrado` em `alertas_alvos.py` agora aceita o parâmetro `socio_falecido: bool = False` aplicando `semi join` com `dados_socios` filtrado por `indicador_socio == 'PF'` + `data_exclusao_sociedade IS NULL` + `is_falecido == True`.

## [1.1.8] - 2026-06-24

### Adicionado
- **Filtro "Sócio com idade atípica (< 21 ou > 80 anos)"** na sidebar, permitindo restringir o dashboard a estabelecimentos com sócios PF ativos em idade fora do padrão.
- **Indicador `socio_idade_atipica`** no card Integridade do dashboard, com tooltip descritivo e contagem no panorama de alertas.
- Filtro integrado em todos os endpoints: `/resumo`, `/faixas-risco`, `/producao-semestral`, `/alertas-panorama`, `/indicadores-analise` e `/indicadores-analise/cnpjs`.
- Cache do filtro nos indicadores para recálculo automático via `_INDICADOR_SCOPE_FILTER_FIELDS`.
- Checkbox com destaque visual (clear button, `filter-active-box`, `integrityFilterCount`) consistente com os demais filtros de integridade.
- Função `build_perfil_filtrado` em `alertas_alvos.py` aplicando par_teia, socio_beneficio, socio_esocial, cnae_incompativel, socio_idade_atipica e volume_atipico em sequência, compartilhada por dashboard, fator_risco, indicadores e alertas_panorama.

### Corrigido
- **Card Integridade (HomeView) não reagia aos filtros da sidebar.** O endpoint `/alertas-panorama` e a função `get_alertas_panorama` recebiam apenas filtros geográficos e `dispersao_uf_sem_fronteira`; demais filtros da sidebar (CNAE, sócio CadÚnico/Defeso, sócio eSocial, sócio idade atípica, PAR, volume atípico) eram ignorados. O endpoint e o service agora aceitam todos os filtros globais e a função `fetchAlertasPanorama` no frontend usa `buildAnalyticsParams` para enviá-los, refletindo as contagens do card em tempo real quando o usuário marca/desmarca qualquer filtro.
- `_filtrar_id_cnpjs_por_escopo` em `alertas_panorama.py` retornava `None` (interpretado como "Brasil inteiro") sempre que não havia filtro geográfico, descartando todos os filtros de integridade aplicados via `build_perfil_filtrado`. Agora retorna os `id_cnpj` do `perfil_df` filtrado (ou `None` apenas quando o filtro atual não casa com nenhum CNPJ), refletindo corretamente o subconjunto da sidebar no card.

### Alterado
- Cálculo de idade do sócio passa a ser **on-demand** a partir de `dados_socios.parquet` (mesma lógica do `alertas_panorama`), em vez de coluna materializada `has_socio_idade_atipica` em `perfil_consolidado_estabelecimento`. Garante consistência quando um sócio cruza a fronteira dos 21 ou 80 anos após a geração do Parquet.
- Data de referência para o cálculo da idade é `data_fim` do período selecionado (com fallback para `date.today()`), alinhada ao card Integridade.
- Filtro `volume_atipico` aplicado uniformemente no `perfil_filtrado` em todos os call sites (antes era aplicado direto no `period_df` em alguns e no perfil em outros, com duplicação quando passava pelos dois caminhos).

## [1.1.7] - 2026-06-24

### Adicionado
- **Botão de refresh para verificação manual de atualizações** ao lado do label "Atualização" no card Sistema (HomeView).
  - Ícone 🔄 permite forçar verificação imediata sem aguardar os 15 minutos do polling automático.
  - Desabilitado durante a verificação com feedback visual de carregamento (ícone gira).
  - Aciona requisição POST para `/api/v1/system/check-update`.
- **Cor da barra de título da janela desktop** personalizada via `pywinstyles` (Windows 10/11): barra escura (`#1a1a1a`) alinhada ao tema visual do Sentinela.
- **Cor da barra de título do SentinelaUpdater** personalizada (`#080d1a`), alinhada ao fundo da janela de atualização.
- **Verificação automática de atualizações a cada 15 minutos** em segundo plano, sem intervenção do usuário.
- **Script `release_granian.ps1`** equivalente ao `release.ps1` para builds com Granian.

### Alterado
- **Proporcionalidade dos cards no dashboard (HomeView)**:
  - Card Sistema aumentado (0.88fr → 1fr) para melhor destaque.
  - Card Produção reduzido (1fr → 0.9fr) para melhor equilíbrio visual.
- **Ícone de atualização aumentado em tamanho** (1rem → 1.15rem, font-size: 0.6rem) para melhor visibilidade.
- **Label do filtro "Atualização"** agora exibe ícone de refresh inline usando `display: flex` com alinhamento horizontal.
- **`release.ps1`**: limpeza de tag/release anterior agora é sempre executada, independente de a tag existir localmente — corrige falha ao recriar releases.
- **`build_pywebview_granian.ps1`**: adicionado passo de build do `SentinelaUpdater.exe` antes do executável principal, garantindo que o updater seja embutido corretamente.
- **`sentinela_server2.spec`**: adicionado `SentinelaUpdater.exe` nos `datas` e nome do executável alterado para `Sentinela` (igual ao uvicorn).
- **Documentação** (`mkdocs.yml`): removida dependência do `polyfill.io` que causava prompt de login ao acessar o GitHub Pages.

## [1.1.6] - 2026-06-23

### Adicionado
- Novo filtro **"Farmácia com CNAE Incompatível"** na sidebar do dashboard para filtrar estabelecimentos com incompatibilidade de CNAE (Classificação Nacional de Atividade Econômica).
- Checkbox interativo com comportamento idêntico a outros filtros (Grande Rede, PAR, etc.), aplicando filtro em tempo real aos KPIs e tabelas.
- Filtro integrado em todos os endpoints de analytics: `/resumo`, `/faixas-risco`, `/producao-semestral`, `/indicadores-analise` e `/indicadores-analise/cnpjs`.
- Suporte completo do filtro em todas as views: Dashboard Nacional, Dashboard Regional, Estabelecimentos e Indicadores.
- Implementação de cache do filtro em indicadores para otimizar performance.

### Alterado
- Estilos de checkbox: texto alinhado com cor e peso de fonte dos labels de filtro (`--sidebar-text`, font-weight: 400).
- Integração do filtro CNAE em `_INDICADOR_SCOPE_FILTER_FIELDS` para recalcular cache automaticamente quando filtro muda.

## [1.1.5] - 2026-06-23

### Corrigido
- Nota Técnica: Tabela 8 (Repasses Anuais) centralizada corretamente no documento Word.
- Nota Técnica: remoção de bold nas linhas de dados da Tabela 9 (Indicadores Críticos) — bold mantido apenas no cabeçalho.
- Nota Técnica: apenas a palavra 'ATENÇÃO!' permanece em negrito no texto de conclusão; restante do parágrafo sem formatação especial.
- Nota Técnica: removido espaço extra antes de 'ATENÇÃO!' na capa.
- Nota Técnica: largura da Tabela 8 equalizada à Tabela 7 (7,30 polegadas no total).
- Nota Técnica: ajustes de tipagem e formatação geral nos relatórios.

### Alterado
- Aba Financeiro: visualizações de Vendas e Repasses unificadas em layout único, eliminando alternância entre abas separadas.
- Aba Financeiro: removido modal de zoom do gráfico mensal.
- Card Sistema: ícone de download pulsante exibido ao lado do label "Atualização" quando há versão disponível ou atualização obrigatória, indicando que o card é clicável.
- Dashboard: proporções dos cards ajustadas — card Sistema levemente menor, card Integridade levemente maior.

## [1.1.4] - 2026-06-20

### Adicionado
- Sistema de atualização automática no modo Desktop: ao clicar no card de Atualização, o aplicativo baixa o novo executável diretamente da release do GitHub com barra de progresso em tempo real, fecha o processo atual e reinicia automaticamente na nova versão via script auxiliar (`update.bat`).
- Modal `UpdateDialog` com barra de progresso animada, status reativo (baixando, preparando arquivos, reiniciando) e botão de tentar novamente em caso de falha.
- Endpoints internos `POST /api/v1/system/download-update` e `GET /api/v1/system/download-progress` para orquestrar e monitorar o download.

### Alterado
- Em modo Web (servidor de desenvolvimento), o card de atualização continua abrindo a página de downloads do GitHub no navegador (comportamento anterior mantido).

## [1.1.3] - 2026-06-20

### Corrigido
- Perda e não carregamento das preferências e watchlist no modo Desktop (EXE congelado), redirecionando a escrita e leitura do `preferences.json` para o diretório de dados persistentes `%LOCALAPPDATA%\Sentinela\preferences\`.

## [1.1.2] - 2026-06-20

### Corrigido
- Falha ao gerar Nota Técnica em modo Desktop (Frozen/EXE) causada por caminho de resolução incorreto para o GeoJSON `brasil-uf.json` na geração dos mapas.

## [1.1.1] - 2026-06-20

### Adicionado
- Comportamento clicável no card de atualização (HomeView) quando o sistema não está atualizado, redirecionando para a página oficial do GitHub Pages para baixar a nova versão.
- Efeito de carregamento visual premium (brilho pulsante com animação de respiração scale e onda de expansão ripple) nos botões de "Gerar Relatório PDF" e "Gerar Nota Técnica" durante a compilação/exportação dos dados.

## [1.1.0] - 2026-06-20

### Adicionado
- Sistema de verificação automática de atualizações com assinatura Ed25519 e manifesto público no GitHub Pages.
- Tela de bloqueio profissional exibida quando a versão instalada está abaixo da versão mínima suportada.
- Cache local offline do manifesto validado em `%LOCALAPPDATA%\Sentinela\updates\` com proteção anti-downgrade.
- Card Sistema expandido com linha de status de atualização (Atualizado, Atualização disponível, Verificação offline, Não verificado) e tooltip com data da última verificação.
- Link para documentação do sistema (`https://cgu-sc.github.io/sentinela/`) na barra de navegação.
- Endpoints `GET /api/v1/system/update-status` e `POST /api/v1/system/check-update`.
- Fonte única de versão do produto em `version.json` na raiz do projeto.

### Alterado
- Seletor de aparência simplificado: removida a seleção de paleta de cores; o tema Carbon Gold passa a ser fixo e apenas o alternador claro/escuro permanece na navbar.
- Linha "Atualizado" (data do cache de dados) removida do card Sistema para reduzir redundância.

## [1.0.0] - 2026-06-20

### Adicionado
- Primeira versão estável oficial do Sentinela.
- Execução web e desktop com empacotamento PyWebView.
- Geração de Nota Técnica e Relatório PDF.
- Dashboard com KPIs operacionais, produção, escopo monitorado e quadro de alertas.
- Detalhamento de estabelecimento com abas de movimentação, diagnóstico de risco, memória de cálculo, indicadores, autorizações, quadro societário, teia societária e região de saúde.
- Caches locais em módulos `.smod` para operação com dados materializados.

### Corrigido
- Correção da porta dinâmica no executável desktop quando `8002` já está ocupada.
- Correção de salvamento local de documentos gerados no executável desktop.
- Correção de altura da aba Teia Societária após inclusão de overlay de carregamento por aba.

### Alterado
- Card Sistema passa a exibir a versão atual da aplicação.
