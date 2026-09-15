# Análise de Prescritores

O módulo de análise de prescritores, implementado em `aba_crm.py`, foca na **"ponta da caneta"** - os médicos que assinam as receitas vinculadas às vendas do Programa Farmácia Popular.

---

## 1. Objetivo

Identificar **padrões anômalos de prescrição** que podem indicar:

- Médicos fictícios ou com CRM inválido
- Esquemas de direcionamento de pacientes
- Volumes de prescrição muito acima da média
- Concentração suspeita de vendas em poucos CRMs

---

## 2. Fontes de Dados

| Tabela                  | Conteúdo                           | Uso                |
| ----------------------- | ---------------------------------- | ------------------ |
| `indicadorCRM_Completo` | Dados consolidados de prescritores | Métricas agregadas |
| `top20CRMsPorFarmacia`  | Top 20 prescritores por farmácia   | Detalhamento       |
| Base CFM                | Registro de médicos                | Validação          |

---

## 3. Métricas Calculadas

### 3.1. Por Farmácia (Agregado)

| Métrica                   | Descrição                             |
| ------------------------- | ------------------------------------- |
| `concentracao_top1`       | % das vendas do principal CRM         |
| `concentracao_top5`       | % das vendas dos 5 maiores CRMs       |
| `hhi_prescritores`        | Índice de concentração HHI            |
| `qtd_crms_invalidos`      | Número de CRMs não encontrados no CFM |
| `qtd_crms_robo`           | CRMs com >30 prescrições/dia          |
| `media_prescricoes_dia`   | Média de prescrições por dia por CRM  |
| `qtd_alertas_geograficos` | Médicos a >400km de distância         |

### 3.2. Por CRM (Individual)

| Métrica                    | Descrição                                   |
| -------------------------- | ------------------------------------------- |
| `crm`                      | Número do registro médico                   |
| `nome_medico`              | Nome completo                               |
| `uf_crm`                   | Estado de registro                          |
| `data_primeira_prescricao` | Primeira vez que prescreveu para a farmácia |
| `data_registro_cfm`        | Data de inscrição no conselho               |
| `num_prescricoes`          | Total de prescrições                        |
| `valor_total`              | Valor movimentado                           |
| `participacao_pct`         | % do faturamento da farmácia                |
| `prescricoes_dia_local`    | Média diária nesta farmácia                 |
| `prescricoes_dia_brasil`   | Média diária em todas farmácias do país     |
| `num_farmacias`            | Em quantas farmácias atua                   |
| `distancia_km`             | Distância entre médico e farmácia           |

---

## 4. Alertas Implementados

### 4.1. Tipos de Alerta

| Alerta                    | Critério                                 | Cor         | Gravidade |
| ------------------------- | ---------------------------------------- | ----------- | --------- |
| **CRM Não Localizado**    | Não encontrado no CFM                    | 🔴 Vermelho | Crítica   |
| **>30/dia Aqui**          | >30 prescrições/dia nesta farmácia       | 🔴 Magenta  | Crítica   |
| **>30/dia Rede**          | >30 prescrições/dia em todo Brasil       | 🟣 Roxo     | Alta      |
| **Multi-Farmácia**        | Atua em >20 estabelecimentos             | 🟣 Roxo     | Alta      |
| **Tempo Concentrado**     | Todas prescrições em período muito curto | 🟠 Laranja  | Média     |
| **Alerta Geográfico**     | Médico a >400km da farmácia              | 🔵 Azul     | Média     |
| **Prescrição Retroativa** | Prescrição antes do registro no CFM      | 🔴 Vermelho | Crítica   |

### 4.2. Constantes de Alerta

Definidas no código `aba_crm.py`:

| Constante               | Valor | Descrição                                  |
| ----------------------- | ----- | ------------------------------------------ |
| `LIMITE_ROBO_DIA`       | 30    | Prescrições/dia para considerar "robô"     |
| `LIMITE_MULTI_FARMACIA` | 20    | Farmácias para considerar "multi-farmácia" |
| `LIMITE_DISTANCIA_KM`   | 400   | Distância para alerta geográfico           |

---

## 5. Prescritor "Robô"

### 5.1. Conceito

Um CRM que emite mais de **30 prescrições por dia** está com comportamento compatível com "robô" - uma taxa difícil de manter de forma consistente.

### 5.2. Cálculo

$$
\text{Prescrições/Dia} = \frac{\text{Total de Prescrições}}{\text{Dias com Atividade}}
$$

Onde "Dias com Atividade" é o número de dias distintos em que o médico emitiu ao menos uma prescrição.

### 5.3. Contexto

Um médico em consultório normal atende:

- 15-25 pacientes/dia é um volume alto mas viável
- 30+ pacientes/dia é extremamente improvável
- 50+ pacientes/dia é fisicamente impossível

### 5.4. Dois Níveis de Análise

| Nível        | Verificação                    | Interpretação        |
| ------------ | ------------------------------ | -------------------- |
| **Local**    | Prescrições/dia nesta farmácia | >30 = suspeito       |
| **Nacional** | Prescrições/dia em todo Brasil | >30 = muito suspeito |

Se um médico tem >30 prescrições/dia considerando **todas as farmácias do país**, é praticamente certo que há algo errado.

---

## 6. Análise Geográfica

### 6.1. Distância Médico-Farmácia

O sistema calcula a distância entre:

- Localização do consultório do médico (endereço do CRM)
- Localização da farmácia

### 6.2. Alerta de Distância

| Distância     | Interpretação                    |
| ------------- | -------------------------------- |
| **< 50km**    | Normal                           |
| **50-200km**  | Pode ser legítimo (cidade-polo)  |
| **200-400km** | Suspeito                         |
| **> 400km**   | Crítico - médico de outra região |

### 6.3. Cenários Legítimos

- Médico atendendo em cidade vizinha
- Pacientes que viajam para especialistas
- Cidade-polo que atrai pacientes regionais

### 6.4. Cenários Suspeitos

- Médico de São Paulo prescrevendo regularmente em farmácia do Rio Grande do Sul
- Múltiplos médicos de outras regiões na mesma farmácia
- Padrão sistemático de prescrições distantes

---

## 7. Prescrição Retroativa

### 7.1. Conceito

Uma prescrição **não pode existir antes do médico ter CRM válido**. Se a data da primeira prescrição é anterior à data de registro no CFM, há fraude documental.

### 7.2. Cálculo

```
SE data_primeira_prescricao < data_registro_cfm ENTÃO
    ALERTA: Prescrição Retroativa
```

### 7.3. Causas

- Uso de CRM de médico recém-formado antes do registro ser efetivado
- Falsificação de datas nas receitas
- Uso de CRM de terceiros

---

## 8. Estrutura da Aba no Relatório

### 8.1. Seções

```
┌─────────────────────────────────────────────────────────────┐
│  CABEÇALHO                                                  │
│  CNPJ: XX.XXX.XXX/0001-XX | Razão Social | Município/UF     │
├─────────────────────────────────────────────────────────────┤
│  CARDS DE RESUMO                                            │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Top 1:  │ │Top 5:  │ │Robôs:  │ │Inválidos│ │Geográf.│    │
│  │  35%   │ │  72%   │ │   3    │ │   2    │ │   1    │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
├─────────────────────────────────────────────────────────────┤
│  TABELA DE INDICADORES VS MÉDIAS                           │
│  ┌────────────────────┬──────────┬─────────┬─────────┐     │
│  │ Indicador          │ Farmácia │ Média UF│ Média BR│     │
│  ├────────────────────┼──────────┼─────────┼─────────┤     │
│  │ Concentração Top 1 │   35%    │   15%   │   12%   │     │
│  │ HHI                │  2845    │   890   │   750   │     │
│  │ ...                │   ...    │   ...   │   ...   │     │
│  └────────────────────┴──────────┴─────────┴─────────┘     │
├─────────────────────────────────────────────────────────────┤
│  TABELA DE CRMs DE INTERESSE                               │
│  (Top 20 + CRMs com alertas, ordenados por risco/volume)   │
├─────────────────────────────────────────────────────────────┤
│  ALERTAS IDENTIFICADOS                                     │
│  Descrições textuais de cada alerta encontrado             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2. Formatação Visual

| Situação              | Formatação                   |
| --------------------- | ---------------------------- |
| CRM normal            | Fundo branco                 |
| CRM inválido          | Fundo vermelho, texto branco |
| Robô local            | Fundo magenta                |
| Robô nacional         | Fundo roxo                   |
| Multi-farmácia        | Fundo roxo                   |
| Alerta geográfico     | Fundo azul                   |
| Prescrição retroativa | Fundo vermelho               |

---

## 9. Investigação de CRMs

### 9.1. Sinais de Alerta Combinados

| Combinação                     | Interpretação      |
| ------------------------------ | ------------------ |
| CRM inválido + Alto volume     | Fraude estruturada |
| Robô + Multi-farmácia          | Esquema organizado |
| Retroativo + Concentração alta | CRM forjado        |
| Geográfico + Exclusividade     | CRM forjado        |

---

!!! tip "Próximo Passo"
Veja as [Abas do Relatório](../relatorios/index.md) para entender como esses dados são apresentados no dossiê Excel.
