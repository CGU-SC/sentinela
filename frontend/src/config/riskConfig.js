/**
 * Thresholds de classificação de risco de não-comprovação.
 * Fonte única de verdade — alterar aqui reflete em todos os gráficos,
 * tabelas e badges do sistema sem necessidade de tocar em outros arquivos.
 *
 * Regra:
 *   > CRITICAL  → Crítico  (vermelho escuro)
 *   > HIGH      → Alto     (vermelho)
 *   > MEDIUM    → Médio    (amarelo)
 *   ≤ MEDIUM    → Baixo    (verde)
 */
export const RISK_THRESHOLDS = {
  CRITICAL: 60,
  HIGH:     20,
  MEDIUM:    5,
};

/** Limiares para destaques de auditoria financeira */
export const AUDIT_THRESHOLDS = {
  HIGH_VALUE: 150000, // Valores acima de 150K recebem destaque especial
};

/** Paleta de cores hex associada a cada nível (para uso em ECharts e CSS via v-bind). */
export { RISK_COLORS } from './colors.js';

/**
 * Equivalentes RGB dos RISK_COLORS para uso em jsPDF (pdf.setFillColor/setTextColor).
 * Mantidos em sincronia com RISK_COLORS em colors.js.
 */
export const RISK_COLORS_RGB = {
  CRITICAL: [153,  27,  27],   // red-800   #991b1b
  HIGH:     [225,  29,  72],   // rose-600  #e11d48
  MEDIUM:   [245, 158,  11],   // amber-500 #f59e0b
  LOW:      [ 16, 185, 129],   // emerald-500 #10b981
  NONE:     [203, 213, 225],   // slate-300 — sem dados
};

/** Classes CSS associadas a cada nível (para uso em Tags/Badges do PrimeVue). */
export const RISK_CSS_CLASSES = {
  CRITICAL: 'risk-critical',
  HIGH:     'risk-high',
  MEDIUM:   'risk-medium',
  LOW:      'risk-low',
};

/**
 * Regras de semáforo para os cards de KPI da aba Análise de CRMs.
 * Nível de alerta: 'red' | 'orange' | 'yellow'  (verde implícito quando valor = 0)
 *
 * TOP 1 / TOP 5 usam dois limiares (3 níveis); demais são binários (0 = verde, >0 = alerta).
 */
// Mapeamento de nível → variável CSS e RGB para PDF
// 'red'    → --risk-high/critical  #ef4444  [239,68,68]
// 'orange' → --risk-medium         #f97316  [249,115,22]
// 'green'  → --risk-low            #10b981  [16,185,129]

/**
 * Regras de semáforo para os cards de KPI da aba Análise de CRMs.
 * TOP 1 / TOP 5 usam dois limiares (ambos disparam 'red'); demais são binários.
 */
export const CRM_KPI_THRESHOLDS = {
  concentracaoTop1:       { atencao: 20, critico: 40, alert: 'red'    },
  concentracaoTop5:       { atencao: 50, critico: 70, alert: 'red'    },
  lancamentosAgrupados:   { alert: 'red'    },
  prescrIntensivaLocal:   { alert: 'red'    },
  prescrIntensivaOcultos: { alert: 'red'    },
  multiFarmacia:          { alert: 'red'    },
  fraudesCrm:             { alert: 'red'    },
  distancia400km:         { alert: 'orange' },  // risco médio — prescrições distantes
};

/**
 * Taxa de exclusividade do CRM (% das prescrições do médico no PFPB feitas
 * neste estabelecimento) na tabela de CRMs de interesse.
 * alto: etiqueta vermelha suave; atencao: valor em destaque neutro.
 */
/**
 * Raio-X CRM: intervalo entre autorizações consecutivas (em segundos) abaixo do
 * qual o intervalo é destacado como lançamento em rajada.
 */
export const CRM_RAIOX_INTERVALO_CURTO_SEGUNDOS = 60;

export const CRM_EXCLUSIVIDADE_THRESHOLDS = {
  atencao: 50,
  alto: 80,
};

/**
 * Regras de semáforo para os cards de KPI da aba Falecidos.
 * Binários: verde quando 0, cor de alerta quando > 0.
 */
export const FALECIDOS_KPI_THRESHOLDS = {
  cpfsDistintos:     { alert: 'red'    },
  totalAutorizacoes: { alert: 'red'    },
  valorTotal:        { alert: 'red'    },
  mediaDias:         { alert: 'red'    },
  maxDias:           { alert: 'red'    },
  pctFaturamento:    { alert: 'orange' },
  cpfsMultiCnpj:     { alert: 'red'    },
};

/**
 * Definição dos 6 grupos de indicadores e seus 16 indicadores.
 * - key:          identificador no objeto `indicadores` retornado pela API
 * - label:        nome exibido no card
 * - formato:      'pct' | 'pct3' | 'val' | 'dec'
 * - metodologia:  texto exibido no tooltip ℹ️
 */
export const INDICATOR_GROUPS = [
  {
    id: 'auditoria',
    label: '1. Auditoria Financeira',
    indicators: [
      { key: 'percentual_nao_comprovacao', label: 'Percentual Não Comprovação', formato: 'pct',
        metodologia: 'Percentual do valor total de vendas sem comprovação fiscal/clínica na auditoria.' },
    ],
  },
  {
    id: 'elegibilidade',
    label: '2. Elegibilidade & Clínica',
    indicators: [
      { key: 'falecidos', label: 'Vendas p/ Falecidos', formato: 'pct3',
        metodologia: 'Confronto direto entre a data da dispensação e a data oficial de óbito (SIM/SIRC/SISOBI).' },
      { key: 'incompatibilidade_patologica', label: 'Incompatibilidade Patológica', formato: 'pct',
        metodologia: 'Confronta a indicação terapêutica com os dados do beneficiário (Idade e Sexo). Sinaliza: Osteoporose em homens, Parkinson <50 anos, Hipertensão <20 anos, Diabetes <20 anos.' },
    ],
  },
  {
    id: 'quantidades',
    label: '3. Padrões de Quantidade',
    indicators: [
      { key: 'teto', label: 'Dispensação em Teto Máximo', formato: 'pct',
        metodologia: 'Percentual de dispensações onde a quantidade vendida atinge exatamente o limite máximo permitido por medicamento.' },
      { key: 'polimedicamento', label: '4+ Itens por Autorização', formato: 'pct',
        metodologia: 'Percentual de autorizações (cupons fiscais) que contêm 4 ou mais medicamentos distintos dispensados no mesmo ato.' },
    ],
  },
  {
    id: 'financeiro',
    label: '4. Padrões Financeiros',
    indicators: [
      { key: 'ticket_medio', label: 'Valor do Ticket Médio', formato: 'val',
        metodologia: 'Valor monetário médio de cada autorização de venda.' },
      { key: 'receita_paciente', label: 'Faturamento Médio por Cliente', formato: 'val',
        metodologia: 'Faturamento médio mensal da farmácia dividido pelo número de CPFs distintos atendidos (normalizado pelo tempo de atividade).' },
      { key: 'per_capita', label: 'Venda Per Capita Mensal', formato: 'val',
        metodologia: 'Faturamento médio mensal da farmácia dividido pela população total do município (estimativa IBGE).' },
      { key: 'alto_custo', label: 'Medicamentos de Alto Custo', formato: 'pct',
        metodologia: 'Percentual do faturamento total proveniente de medicamentos no 90º percentil de preço.' },
    ],
  },
  {
    id: 'automacao',
    label: '5. Automação & Geografia',
    indicators: [
      { key: 'vendas_rapidas', label: 'Vendas Rápidas (<60s)', formato: 'pct',
        metodologia: 'Percentual de vendas consecutivas realizadas em intervalo inferior a 60 segundos.' },
      { key: 'volume_atipico', label: 'Crescimento semestral atípico', formato: 'val_compact',
        metodologia: 'Mede explosões de crescimento semestral atípicas no faturamento do programa.' },
      { key: 'recorrencia_sistemica', label: 'Recorrência Sistêmica', formato: 'pct',
        metodologia: 'Percentual de compras sequenciais realizadas precisamente na linha de corte do sistema (ex: 30 dias exatos), indicando possível automação.' },
      { key: 'dias_pico', label: 'Concentração em Dias de Pico', formato: 'pct',
        metodologia: 'Percentual do faturamento mensal concentrado nos 3 dias de maior movimento do mês.' },
      { key: 'dispersao_geografica', label: 'Dispersão Interestadual', formato: 'pct',
        metodologia: 'Percentual de vendas para pacientes cuja UF de residência difere da UF da farmácia.' },
    ],
  },
  {
    id: 'crm',
    label: '6. Integridade Médica',
    indicators: [
      { key: 'hhi_crm', label: 'Concentração de CRMs (HHI)', formato: 'dec',
        metodologia: 'Índice Herfindahl-Hirschman (HHI) que mede a concentração de prescrições. HHI elevado indica dependência excessiva de poucos CRMs.' },
      { key: 'crms_irregulares', label: 'Faturamento CRMs Irregulares', formato: 'pct',
        metodologia: 'Percentual do faturamento vinculado a CRMs não localizados no CFM ou com prescrições anteriores à primeira inscrição do médico na UF do CRM.' },
    ],
  },
];

export const indicadorExtraColumns = {
  volume_atipico: [
    { field: 'volume_atipico_maior_taxa_crescimento_pct', header: 'Maior Salto (%)', type: 'pct', align: 'center', width: '8%', minWidth: '90px' }
  ],
  dispersao_geografica: [
    { field: 'pct_dispersao_uf_nao_vizinha', sortField: 'pct_dispersao_uf_nao_vizinha', header: 'UF sem Fronteira', type: 'pct', align: 'center', width: '8%', minWidth: '100px', sortable: true }
  ]
};
