/**
 * Tooltips explicativos da sidebar de filtros.
 *
 * O PrimeVue recebe HTML por meio de `escape: false`, como nos tooltips
 * metodológicos da tela de indicadores. O conteúdo desta configuração é
 * estático e os valores dinâmicos são escapados antes da interpolação.
 */

const FILTER_TOOLTIP_COPY = Object.freeze({
  uf: {
    title: 'Unidade Federativa (UF)',
    body: 'Filtra os estabelecimentos pela UF registrada no cadastro da farmácia.',
  },
  regiao: {
    title: 'Região de Saúde',
    body: 'Filtra os estabelecimentos pela região de saúde associada ao município cadastrado.',
    sections: [
      {
        label: 'Dependência do filtro',
        text: 'As opções são carregadas conforme a UF selecionada. Ao escolher uma região, os filtros de município e jurisdição PF passam a respeitar esse recorte.',
      },
    ],
  },
  municipio: {
    title: 'Município',
    body: 'Filtra os estabelecimentos pelo município associado ao seu código IBGE7.',
    sections: [
      {
        label: 'Dependência do filtro',
        text: 'As opções respeitam a UF, a Região de Saúde e a Jurisdição PF selecionadas. A escolha do município também ajusta os filtros geográficos relacionados.',
      },
    ],
  },
  unidadePf: {
    title: 'Jurisdição PF',
    body: 'Filtra os estabelecimentos pela unidade da Polícia Federal associada ao município do cadastro.',
    sections: [
      {
        label: 'Dependência do filtro',
        text: 'As opções são obtidas a partir do vínculo entre o código IBGE do município e a jurisdição da Polícia Federal, respeitando os demais filtros geográficos.',
      },
    ],
  },
  situacao: {
    title: 'Situação cadastral na Receita Federal',
    body: 'Filtra os estabelecimentos pela situação cadastral registrada na Receita Federal.',
    sections: [
      {
        label: 'Opções disponíveis',
        items: [
          'Ativa, Baixada, Suspensa ou Inapta.',
          'Sem filtro: inclui todas as situações disponíveis na base.',
        ],
      },
    ],
  },
  ms: {
    title: 'Conexão com o Ministério da Saúde',
    body: 'Filtra pela situação da conexão do estabelecimento com o Ministério da Saúde.',
    sections: [
      {
        label: 'Regra de classificação',
        text: 'Ativa quando a última data de movimentação do estabelecimento está dentro dos 30 dias anteriores ao último mês disponível na base. Fora desse intervalo, é classificada como Inativa.',
      },
    ],
  },
  porte: {
    title: 'Porte do CNPJ',
    body: 'Filtra o estabelecimento conforme o porte empresarial registrado no cadastro.',
    sections: [
      {
        label: 'Classificações disponíveis',
        items: [
          'Microempresa (ME).',
          'Empresa de Pequeno Porte (EPP).',
          'Demais.',
        ],
      },
    ],
  },
  grandeRede: {
    title: 'Grande Rede',
    body: 'Filtra estabelecimentos conforme a quantidade de CNPJs distintos com movimentação na mesma raiz do CNPJ.',
    sections: [
      {
        label: 'Regra de classificação',
        text: 'É considerada grande rede quando a raiz possui 15 ou mais estabelecimentos com movimentação na base. Os demais casos são classificados como Não.',
      },
    ],
  },
  estabelecimento: {
    title: 'Filtro de estabelecimento',
    body: 'Digite o CNPJ completo, a raiz de oito dígitos ou parte da razão social.',
    sections: [
      {
        label: 'Como a busca funciona',
        items: [
          'CNPJ completo: filtra o estabelecimento exato.',
          'Raiz do CNPJ: filtra toda a rede empresarial correspondente.',
          'Texto livre: localiza estabelecimentos pela razão social.',
        ],
      },
    ],
  },
  parTeia: {
    title: 'CNPJs com PAR',
    body: 'Filtra estabelecimentos conforme a existência de um Processo Administrativo de Responsabilização (PAR) na teia societária.',
    sections: [
      {
        label: 'Níveis considerados',
        items: [
          'CNPJ nível 2 da teia com PAR.',
          'CNPJ nível 4 da teia com PAR.',
          'Qualquer CNPJ com PAR: considera os níveis 2 ou 4.',
        ],
      },
    ],
  },
  cnaeIncompativel: {
    title: 'CNPJ com CNAE incompatível',
    body: 'Filtra estabelecimentos cujo CNAE principal ou secundário não indica atividade farmacêutica compatível com o programa.',
  },
  socioIdadeAtipica: {
    title: 'Sócio com idade atípica',
    body: 'Filtra estabelecimentos com ao menos um sócio pessoa física ativo com idade inferior a 21 anos ou superior a 80 anos na data de referência do período selecionado.',
  },
  socioFalecido: {
    title: 'Sócio ativo identificado como falecido',
    body: 'Filtra estabelecimentos com ao menos um sócio pessoa física cujo vínculo societário está ativo e que foi identificado como falecido na base de óbitos.',
  },
  socioBeneficio: {
    title: 'Sócio no CadÚnico ou Seguro Defeso',
    body: 'Filtra estabelecimentos conforme a presença de sócios com vínculo ativo e registro em base de benefício social.',
    sections: [
      {
        label: 'Níveis considerados',
        items: [
          'Sócio direto: vínculo ativo na farmácia alvo.',
          'Sócio N3: vínculo ativo em empresa do nível 2 da teia.',
          'Sócio direto ou N3: considera qualquer um desses níveis.',
        ],
      },
      {
        label: 'Bases consultadas',
        text: 'CadÚnico ou Seguro Defeso.',
      },
    ],
  },
  socioEsocial: {
    title: 'Sócio com vínculo no eSocial',
    body: 'Filtra estabelecimentos conforme a existência de vínculo societário ativo e vínculo trabalhista não gerencial em outro CNPJ.',
    sections: [
      {
        label: 'Níveis considerados',
        items: [
          'Sócio direto: vínculo ativo na farmácia alvo.',
          'Sócio N3: vínculo ativo em empresa do nível 2 da teia.',
          'Sócio direto ou N3: considera qualquer um desses níveis.',
        ],
      },
      {
        label: 'Regra trabalhista',
        text: 'O vínculo identificado no eSocial deve exercer função não gerencial em outro CNPJ.',
      },
    ],
  },
  dispersaoUfSemFronteira: {
    title: 'Vendas para UFs sem fronteira',
    body: 'Filtra estabelecimentos cujo percentual mínimo de vendas foi direcionado a unidades federativas que não fazem fronteira com a UF da farmácia.',
    sections: [
      {
        label: 'Período de referência',
        text: 'Os dados de origem são anuais: o cálculo usa o ano inteiro de cada ano tocado pelo período de análise. Ex.: 03/2023 a 05/2023 considera todo o ano de 2023.',
      },
    ],
  },
  seq: {
    title: 'Autorizações em sequência',
    body: 'Filtra estabelecimentos com dias de muitas autorizações em poucos minutos, no período de análise. É o mesmo alerta e a mesma contagem de dias da Cronologia da aba Autorizações do estabelecimento.',
    sections: [
      {
        label: 'Tipo',
        text: 'Único CRM: o mesmo médico concentra as autorizações. Múltiplos CRMs: vários médicos diferentes no mesmo intervalo. Qualquer: soma os dias dos dois tipos, contando uma vez o dia que tiver os dois.',
      },
      {
        label: 'Severidade mínima',
        text: 'Define quais dias contam: "Grave ou pior" conta os dias graves, críticos e extremos. Sozinha, traz os estabelecimentos com pelo menos 1 dia nesse nível.',
      },
      {
        label: 'Dias com sequência',
        text: 'Quantidade de dias com o alerta no período, na severidade escolhida (sem ela, qualquer severidade). Cerca de metade dos estabelecimentos tem ao menos 1 dia; use a quantidade de dias ou a severidade para destacar os casos relevantes.',
      },
    ],
  },
  volumeAtipico: {
    title: 'Aumento semestral atípico',
    body: 'Filtra estabelecimentos com crescimento percentual atípico e aumento absoluto mínimo de R$ 10.000 em relação ao semestre anterior.',
    sections: [
      {
        label: 'Período de referência',
        text: 'A comparação é feita por semestre (janeiro a junho e julho a dezembro). Entra todo semestre tocado pelo período de análise, mesmo que só em parte. Ex.: 05/2023 a 08/2023 avalia o 1º e o 2º semestres de 2023, cada um comparado ao semestre anterior.',
      },
    ],
  },
  percentual: {
    title: '% de não comprovação',
    body: 'Filtra estabelecimentos pelo percentual de valor sem comprovação no período de análise.',
    sections: [
      {
        label: 'Cálculo',
        text: 'Percentual = valor sem comprovação ÷ valor total de vendas × 100, calculado separadamente para cada estabelecimento. O intervalo inclui os limites selecionados.',
      },
      {
        label: 'Como escolher',
        text: 'Use um atalho (todos ou a partir de 10%, 20%, 40%, 60% ou 80%) ou informe uma faixa personalizada ("De" e "Até") e clique em Aplicar.',
      },
    ],
  },
  periodo: {
    title: 'Período de análise',
    body: 'Define os meses incluídos nos cálculos e nas consultas do sistema.',
    sections: [
      {
        label: 'Regra do intervalo',
        text: 'O mês inicial e o mês final são incluídos. A base atualmente cobre de julho de 2015 a dezembro de 2024.',
      },
      {
        label: 'Como escolher',
        text: 'Use um atalho (período completo, 2020 a 2024 ou um ano) ou escolha o intervalo na grade: clique no mês inicial e depois no final.',
      },
    ],
  },
  populacaoMunicipio: {
    title: 'População do município',
    body: 'Filtra estabelecimentos pela população do município onde ficam, segundo o cadastro de municípios do IBGE usado pelo sistema.',
    sections: [
      {
        label: 'Porte do município',
        text: 'Pequeno porte: até 50 mil habitantes. Médio: 50 mil a 100 mil. Grande: 100 mil a 900 mil. Metrópole: acima de 900 mil.',
      },
      {
        label: 'Como escolher',
        text: 'Use um atalho ou informe uma faixa personalizada ("De" e "Até", em habitantes) e clique em Aplicar. Os limites são inclusivos; deixe um lado vazio para não limitar.',
      },
    ],
  },
  valorMin: {
    title: 'Valor mínimo sem comprovação',
    body: 'Filtra estabelecimentos cujo valor acumulado sem comprovação atinge ou supera o limite selecionado.',
    sections: [
      {
        label: 'Período de cálculo',
        text: 'O valor é somado por estabelecimento dentro do período de análise. O limite vai de R$ 0 a R$ 1.000.000.',
      },
      {
        label: 'Como escolher',
        text: 'Use um atalho (sem valor mínimo ou a partir de R$ 100 mil, R$ 300 mil ou R$ 500 mil) ou informe um valor personalizado e clique em Aplicar. Os botões − e + ajustam de R$ 10.000 em R$ 10.000.',
      },
    ],
  },
});

function escapeTooltipHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function renderSection(section) {
  if (!section?.label) {
    throw new Error('Seção de tooltip de filtro sem título.');
  }

  const content = section.items
    ? `<ul>${section.items.map((item) => `<li>${escapeTooltipHtml(item)}</li>`).join('')}</ul>`
    : section.text
      ? `<p>${escapeTooltipHtml(section.text)}</p>`
      : (() => {
          throw new Error(`Seção de tooltip de filtro incompleta: ${section.label}`);
        })();

  return `
    <section class="filter-tooltip-section">
      <strong class="filter-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      ${content}
    </section>
  `;
}

function createFilterHtmlTooltip(copy) {
  if (!copy?.title || !copy?.body) {
    throw new Error('Texto de tooltip de filtro incompleto.');
  }

  return {
    value: `
      <div class="filter-tooltip-content">
        <div class="filter-tooltip-heading">
          <i class="pi pi-info-circle" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="filter-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
        ${copy.sections?.length
          ? `<div class="filter-tooltip-sections">${copy.sections.map(renderSection).join('')}</div>`
          : ''}
      </div>
    `,
    escape: false,
    class: 'filter-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

export function filterTooltip(key) {
  const copy = FILTER_TOOLTIP_COPY[key];
  if (!copy) {
    throw new Error(`Texto de tooltip de filtro não encontrado: ${key}`);
  }
  return createFilterHtmlTooltip(copy);
}

export function filterActionTooltip(title, body, icon = 'pi-info-circle') {
  if (!title || !body) {
    throw new Error('Tooltip de ação de filtro incompleto.');
  }

  return {
    value: `
      <div class="filter-tooltip-content">
        <div class="filter-tooltip-heading">
          <i class="pi ${escapeTooltipHtml(icon)}" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(title)}</span>
        </div>
        <p class="filter-tooltip-body">${escapeTooltipHtml(body)}</p>
      </div>
    `,
    escape: false,
    class: 'filter-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}
