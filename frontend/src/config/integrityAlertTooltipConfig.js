/**
 * Textos concisos dos alertas de integridade do detalhe do CNPJ.
 *
 * O componente transforma esta estrutura em HTML para o PrimeVue Tooltip.
 * Os critérios descritos aqui devem permanecer alinhados às regras usadas no
 * backend para gerar cada tipo de alerta.
 */
export const INTEGRITY_ALERT_TOOLTIP_COPY = Object.freeze({
  volume_atipico: {
    title: 'Crescimento semestral atípico',
    intro: 'Compara semestres válidos de movimentação para identificar crescimento expressivo do estabelecimento.',
    sections: [
      {
        label: 'Cálculo',
        formula: '((Valor do semestre atual − Valor do semestre anterior) ÷ Valor do semestre anterior) × 100',
      },
      {
        label: 'Critério',
        text: 'O semestre inicial precisa ter pelo menos quatro meses de dados. O alerta ocorre quando o crescimento percentual supera o limite e o aumento financeiro atinge o mínimo exigido. Por padrão: crescimento superior a 50% e aumento mínimo de R$ 10.000,00.',
      },
      {
        label: 'Interpretação',
        text: 'Sinaliza aumento relevante em relação ao semestre comparável anterior e deve ser analisado com as movimentações correspondentes.',
      },
    ],
  },
  socio_menor_idade: {
    title: 'Sócio menor de idade',
    intro: 'Identifica sócio pessoa física com idade inferior a 18 anos na data de processamento da base.',
    sections: [
      {
        label: 'Critério',
        formula: 'Idade calculada < 18 anos',
      },
      {
        label: 'Como interpretar',
        text: 'A idade considera se o aniversário já ocorreu na data de referência. A regra é aplicada a vínculo societário ativo e deve ser confrontada com os documentos cadastrais.',
      },
    ],
  },
  socio_menor_21: {
    title: 'Sócio com menos de 21 anos',
    intro: 'Identifica sócio pessoa física com idade inferior a 21 anos, sem repetir o alerta específico de menor de idade.',
    sections: [
      {
        label: 'Critério',
        text: 'Na prática, este alerta abrange sócios com idade entre 18 e 20 anos, calculada na data de processamento, em vínculo societário ativo.',
      },
      {
        label: 'Como interpretar',
        text: 'Sinaliza uma situação cadastral que deve ser confrontada com os documentos societários e de identificação.',
      },
    ],
  },
  socio_maior_80: {
    title: 'Sócio com mais de 80 anos',
    intro: 'Identifica sócio pessoa física com idade superior a 80 anos na data de processamento da base.',
    sections: [
      {
        label: 'Critério',
        formula: 'Idade calculada > 80 anos',
      },
      {
        label: 'Como interpretar',
        text: 'Pessoas com exatamente 80 anos não entram nesta regra. O alerta se aplica a vínculo societário ativo e não representa, isoladamente, uma irregularidade.',
      },
    ],
  },
  par_teia_n2: {
    title: 'CNPJ Nível 2 da Teia com PAR',
    intro: 'Identifica empresa relacionada aos sócios do estabelecimento, no Nível 2 da teia societária, com registro na base PAR.',
    sections: [
      {
        label: 'Como é identificado',
        text: 'O sistema percorre a relação estabelecimento → sócio → empresa relacionada no Nível 2 e verifica se essa empresa aparece na base PAR.',
      },
      {
        label: 'Importante',
        text: 'O alerta indica PAR em empresa relacionada no Nível 2. Não significa necessariamente PAR direto do estabelecimento e não corresponde ao PAR localizado no Nível 4.',
      },
    ],
  },
  cnpj_cnae_farmacia_ausente: {
    title: 'CNAE incompatível com atividade farmacêutica',
    intro: 'Verifica se o CNPJ possui atividade econômica principal ou secundária compatível com a atividade farmacêutica.',
    sections: [
      {
        label: 'Critério',
        text: 'São considerados os CNAEs 4771701 e 4771702. O alerta ocorre quando nenhum deles é localizado no CNAE principal ou nos CNAEs secundários.',
      },
      {
        label: 'Como interpretar',
        text: 'Indica ausência, no cadastro consultado, de CNAE correspondente às atividades farmacêuticas consideradas na metodologia.',
      },
    ],
  },
  cnpj_dispersao_uf_nao_vizinha: {
    title: 'Vendas para UFs sem fronteira',
    intro: 'Verifica a participação das vendas destinadas a pacientes de UFs que não fazem fronteira com a UF do estabelecimento.',
    sections: [
      {
        label: 'Cálculo',
        formula: 'Valor autorizado para UFs não vizinhas ÷ Valor autorizado total × 100',
      },
      {
        label: 'Critério',
        text: 'A própria UF e suas UFs fronteiriças são consideradas próximas. O alerta ocorre quando as vendas para as demais UFs superam 10% do valor autorizado. O recorte atual é anual.',
      },
    ],
  },
  socio_falecido: {
    title: 'Sócio Ativo Falecido',
    intro: 'Identifica sócio pessoa física cujo CPF consta na base unificada de óbitos e que ainda possui vínculo societário ativo.',
    sections: [
      {
        label: 'Critério',
        formula: 'CPF localizado na base de óbitos + vínculo societário sem data de exclusão',
      },
      {
        label: 'Como interpretar',
        text: 'Aponta possível inconsistência cadastral. A situação deve ser validada com as datas de óbito, entrada e eventual saída da sociedade.',
      },
    ],
  },
  socio_cadunico: {
    title: 'Sócio inscrito no CadÚnico',
    intro: 'Identifica sócio pessoa física cujo CPF foi localizado na base consolidada do Cadastro Único.',
    sections: [
      {
        label: 'Critério',
        text: 'O alerta ocorre quando o CPF do sócio com vínculo societário ativo é encontrado no CadÚnico.',
      },
      {
        label: 'Como interpretar',
        text: 'O registro no CadÚnico, isoladamente, não comprova irregularidade e deve ser analisado com as demais informações do estabelecimento.',
      },
    ],
  },
  socio_esocial: {
    title: 'Sócio com vínculo trabalhista em outro CNPJ',
    intro: 'Identifica sócio pessoa física com vínculo trabalhista ativo no eSocial em CNPJ diferente do estabelecimento analisado.',
    sections: [
      {
        label: 'Critério',
        text: 'O vínculo precisa estar sem data de rescisão e possuir CBO válido incluído na lista de ocupações considerada pela metodologia. Não basta qualquer registro no eSocial.',
      },
      {
        label: 'Como interpretar',
        text: 'Sinaliza possível vínculo profissional ativo do sócio com outra empresa, sujeito à conferência da situação societária e trabalhista.',
      },
    ],
  },
  socio_seguro_defeso: {
    title: 'Sócio beneficiário do Seguro Defeso',
    intro: 'Identifica sócio pessoa física com registro de Seguro Defeso compatível com os critérios de situação e pagamento da metodologia.',
    sections: [
      {
        label: 'Critério',
        text: 'O requerimento deve estar como Habilitado ou Notificado e como Beneficiario ou Segurado, além de possuir parcela paga, valor pago ou parcela Emitida/Reemitida.',
      },
      {
        label: 'Abrangência',
        text: 'A regra é aplicada a vínculo societário ativo. O CPF é verificado nas bases de requerimentos e parcelas do Seguro Defeso.',
      },
    ],
  },
});

const PANORAMA_ALERT_TOOLTIP_COPY = Object.freeze({
  volume_atipico: INTEGRITY_ALERT_TOOLTIP_COPY.volume_atipico,
  cnpj_dispersao_uf_nao_vizinha: INTEGRITY_ALERT_TOOLTIP_COPY.cnpj_dispersao_uf_nao_vizinha,
  cnpj_cnae_farmacia_ausente: INTEGRITY_ALERT_TOOLTIP_COPY.cnpj_cnae_farmacia_ausente,
  socio_falecido: INTEGRITY_ALERT_TOOLTIP_COPY.socio_falecido,
  socio_esocial: INTEGRITY_ALERT_TOOLTIP_COPY.socio_esocial,
  par_teia_n2: INTEGRITY_ALERT_TOOLTIP_COPY.par_teia_n2,
  socio_beneficio_social: {
    title: 'Sócio inscrito no CadÚnico ou beneficiário do Seguro Defeso',
    intro: 'Identifica sócio pessoa física com vínculo societário ativo localizado no CadÚnico ou nas bases do Seguro Defeso.',
    sections: [
      {
        label: 'Critério',
        text: 'O alerta ocorre quando o CPF de sócio ativo é encontrado no CadÚnico ou atende aos critérios de situação e pagamento do Seguro Defeso.',
      },
      {
        label: 'Como interpretar',
        text: 'O registro isolado em uma base de benefício social não comprova irregularidade e deve ser analisado com as demais informações do estabelecimento.',
      },
    ],
  },
  socio_idade_atipica: {
    title: 'Sócio com idade atípica',
    intro: 'Identifica sócio pessoa física com vínculo societário ativo e idade inferior a 21 anos ou superior a 80 anos na data de processamento.',
    sections: [
      {
        label: 'Critério',
        formula: 'Idade calculada < 21 anos ou > 80 anos',
      },
      {
        label: 'Como interpretar',
        text: 'Sinaliza uma situação cadastral que deve ser confrontada com os documentos societários e de identificação. Pessoas com exatamente 21 ou 80 anos não entram nesta regra.',
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

function renderTooltipSection(section) {
  if (!section?.label) {
    throw new Error('Seção de tooltip de alerta sem título.');
  }

  const content = section.items
    ? `<ul>${section.items.map((item) => `<li>${escapeTooltipHtml(item)}</li>`).join('')}</ul>`
    : section.formula
      ? `<div class="integrity-tooltip-formula"><span>Fórmula</span><strong>${escapeTooltipHtml(section.formula)}</strong></div>`
      : section.text
        ? `<p>${escapeTooltipHtml(section.text)}</p>`
        : (() => {
          throw new Error(`Seção de tooltip de alerta incompleta: ${section.label}`);
        })();

  return `
    <section class="integrity-tooltip-section">
      <strong class="integrity-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      ${content}
    </section>
  `;
}

function createIntegrityAlertHtmlTooltip(copy) {
  if (!copy?.title || !copy?.intro || !Array.isArray(copy.sections) || copy.sections.length === 0) {
    throw new Error('Texto de tooltip de alerta incompleto.');
  }

  return {
    value: `
      <div class="integrity-tooltip-content">
        <div class="integrity-tooltip-heading">
          <i class="pi pi-info-circle" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="integrity-tooltip-intro">${escapeTooltipHtml(copy.intro)}</p>
        <div class="integrity-tooltip-sections">
          ${copy.sections.map(renderTooltipSection).join('')}
        </div>
      </div>
    `,
    escape: false,
    class: 'integrity-alert-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

export function panoramaAlertTooltip(alerta, { aumentoMinimo } = {}) {
  const tipo = alerta?.tipo;
  const baseCopy = PANORAMA_ALERT_TOOLTIP_COPY[tipo];
  const quantidade = Number(alerta?.qtd_cnpjs);

  if (!baseCopy) {
    throw new Error(`Texto de tooltip do panorama não encontrado: ${tipo}`);
  }
  if (!Number.isFinite(quantidade) || quantidade < 0) {
    throw new Error(`Quantidade de estabelecimentos inválida no alerta: ${tipo}`);
  }
  if (tipo === 'volume_atipico' && !aumentoMinimo) {
    throw new Error('Valor mínimo de aumento não informado para o alerta de volume atípico.');
  }

  const sections = baseCopy.sections.map((section) => {
    if (tipo === 'volume_atipico' && section.label === 'Critério') {
      return {
        ...section,
        text: section.text.replace('R$ 10.000,00', aumentoMinimo),
      };
    }
    return section;
  });

  sections.push({
    label: 'Abrangência',
    text: `${new Intl.NumberFormat('pt-BR').format(quantidade)} ${quantidade === 1 ? 'estabelecimento apresenta' : 'estabelecimentos apresentam'} este alerta no recorte atual.`,
  });

  return createIntegrityAlertHtmlTooltip({
    ...baseCopy,
    sections,
  });
}

export function integrityAlertTooltip(alert) {
  const copy = INTEGRITY_ALERT_TOOLTIP_COPY[alert?.tipo];
  if (!copy) {
    throw new Error(`Texto de tooltip de alerta não encontrado: ${alert?.tipo}`);
  }
  return createIntegrityAlertHtmlTooltip(copy);
}
