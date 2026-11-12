# Caches derivados e cópia entre máquinas: 503 após copiar o cache

Status: **plano revisado (revisão 4, assinatura por hash do rodapé do parquet). Nenhuma alteração de código feita.** Aguardando as decisões da seção 14 e autorização explícita para cada escrita de arquivo.

Histórico:

- Revisão 1: correção só da ponte `crm_concentracao_multiplo_medico_global`, com hash.
- Revisão 2: padrão generalizado para todos os derivados, com hash completo, novo módulo e fase 2.
- Revisão 3: escopo reduzido. A assinatura passava a ser tamanho + número de linhas, sem `mtime`. Hash completo e fase 2 saíram do plano principal (ver seção 9).
- Revisão 4 (atual): a assinatura passa a ser **tamanho + hash do rodapé do parquet**, sem `mtime`. Detecta também troca de valores com o mesmo volume e custa menos que a contagem de linhas (seções 7, 8 e 10 reescritas). O volume do hash completo foi corrigido de ≈7,7 GB para 4,81 GB, medido (seção 9).

---

## 1. Resumo

O Sentinela funciona na máquina original. Ao copiar `modules/global` para outro computador, o histórico de CRMs mostra erro e a API responde **503 Service Unavailable**.

**Causa:** a ponte e o índice de bitmaps gravam, para cada fonte, o `mtime` e o tamanho, e comparam esses valores a cada consulta. A cópia pode alterar o `mtime` mesmo com os mesmos bytes. A checagem então rejeita um cache válido.

**Correção:** a assinatura gravada passa a ser **tamanho em bytes + hash do rodapé do parquet** de cada fonte. Os dois valores não mudam na cópia. Uma re-sincronização que traz dados diferentes muda o rodapé (volume, tamanhos dos blocos ou estatísticas) e continua sendo detectada. O `mtime` sai da comparação.

**Limites aceitos:** uma troca de valores que preserve todos os tamanhos e estatísticas dos blocos não é detectada, e uma regravação idêntica com outra versão do escritor pode gerar um erro de reconstrução, no lado seguro (seção 8.3).

---

## 2. Sintomas observados

**Mensagem 1 (histórico do CRM, cabeçalho):**

> Alertas do CRM indisponíveis: crm_concentracao_multiplo_medico_global montado com outra versão de crm_raiox_tx_global / crm_concentracao_multiplo_alertas_global; sincronize o módulo novamente.

**Mensagem 2 (aba de prescrições):**

> Os dados gerenciais de prescrições ainda não estão disponíveis. Sincronize o módulo de análise de CRMs e tente novamente.

**Log do servidor na máquina nova:**

```
GET /api/v1/analytics/crm-prescricoes-analise?...&uf_crm=MG&... 503 Service Unavailable
GET /api/v1/cache/status 200 OK
```

Observações:

- A mensagem 1 vem de `ModuloDesatualizado` em [backend/crm_multiplo_medico.py:170](../backend/crm_multiplo_medico.py:170).
- A mensagem 2 é genérica: [frontend/src/stores/crmPrescricoesAnalysis.js:44](../frontend/src/stores/crmPrescricoesAnalysis.js:44) transforma **qualquer** 503 nessa frase. Ela não mostra a causa real.
- `/cache/status` responde 200: o servidor sobe. Só as consultas que usam os derivados falham.

---

## 3. Causa raiz

1. A ponte grava, nos metadados do parquet, a assinatura `(mtime_ns, tamanho)` de suas fontes:
   - assinatura: [backend/data_cache.py:454-457](../backend/data_cache.py:454) (`get_global_cache_signature`);
   - gravação: [backend/crm_multiplo_medico.py:66](../backend/crm_multiplo_medico.py:66) e [:142-145](../backend/crm_multiplo_medico.py:142).
2. A cada consulta, o sistema recalcula a assinatura e compara com a gravada:
   - [backend/crm_multiplo_medico.py:156-172](../backend/crm_multiplo_medico.py:156) (`conferir_fontes`);
   - chamado em [crm_filtros_medico.py:627](../backend/api/services/analytics/crm_filtros_medico.py:627) e [crm_medico_evidencias.py:184](../backend/api/services/analytics/crm_medico_evidencias.py:184).
3. Ao copiar, o `mtime` pode mudar (depende do método: zip, pendrive FAT/exFAT, nuvem, Git, alguns programas de cópia). Os bytes continuam iguais, mas a comparação falha.
4. A ponte só é reconstruída no passo 55 da sincronização ("CRM ConcMulti por Medico (local, depois de 16/36)"): [src/scripts/sincronizar_cache.py:393](../src/scripts/sincronizar_cache.py:393). A sincronização normal (lista `TASKS`, [backend/data_cache.py:5440-5448](../backend/data_cache.py:5440)) não a reconstrói. No boot, ela só é marcada como pronta ([backend/data_cache.py:5348](../backend/data_cache.py:5348)).
   - Por isso, sincronizar de novo na máquina nova não resolveu: a ponte copiada mantém a assinatura antiga.

### Evidência a favor

- Na máquina original, a ponte (`crm_concentracao_multiplo_medico_global.smod`, 155,5 MB, gravada em 02/10/2026 09:30) é **posterior** às fontes (`crm_raiox_tx_global.smod` e `crm_concentracao_multiplo_alertas_global.smod`, ambas de 18/06/2026). Na origem, a assinatura bate e o sistema funciona.
- O comportamento "funciona aqui, falha na cópia" é exatamente o que esse mecanismo produz.

---

## 4. Escopo

### 4.1 Pontos que usam `mtime` na checagem

| # | Onde | Checagem atual | Efeito após cópia | Situação neste plano |
|---|---|---|---|---|
| A | [crm_multiplo_medico.py:169](../backend/crm_multiplo_medico.py:169) (ponte) | `mtime` + tamanho de 2 fontes | **503** (o erro reportado) | **Incluído** |
| B | [crm_indice_bitmaps.py:321](../backend/crm_indice_bitmaps.py:321) (índice, 928,9 MB) | `mtime` + tamanho de 6 fontes | **503** "índice desatualizado" (ainda não reportado) | **Incluído** |
| C | [cache_producers/crm.py](../backend/cache_producers/crm.py:99) (8 pontos) | fonte global com `mtime` mais novo que o parquet por CNPJ | regeneração silenciosa (custo, não erro) | Fora do plano (seção 9) |
| D | [analytics/_cache.py:179-212](../backend/api/services/analytics/_cache.py:179) (teia) | `mtime` das fontes contra o grafo, com `except Exception: pass` | regeneração silenciosa, erros mascarados | Fora do plano (seção 9) |
| E | `dados_medico` e `mais_medicos` ([data_cache.py:5644-5673](../backend/data_cache.py:5644)), [crm_analysis.py:784-798](../backend/api/services/analytics/crm_analysis.py:784) | `mtime` + tamanho em memória | nenhum (vale só dentro do processo) | Não precisa mudar |

### 4.2 Fontes da ponte e do índice (tamanhos medidos em `modules/global`)

| Derivado | Fontes e tamanhos | Total |
|---|---|---|
| Ponte (A) | `crm_raiox_tx_global` (1.819,6 MB, **144.796.723 linhas**), `crm_concentracao_multiplo_alertas_global` (71,5 MB) | 1,9 GB |
| Índice (B) | `crm_medico_dim` (4,1 MB), `crm_farmacia_medico_ano` (330,0 MB), `crm_medico_estabelecimento_mes` (883,3 MB), `crm_medico_territorio_ano` (317,8 MB), `crm_medico_territorio_mes` (1.162,4 MB), `crm_limiar_p95_mes` (0,0 MB) | 2,6 GB |

Os tamanhos da tabela estão em MiB (1 MiB = 1.048.576 bytes). Em bytes, a ponte tem 1.982.916.988 e o índice 2.828.514.603 (4,81 GB no conjunto). O rodapé de cada fonte foi medido (seção 8.5); não há contagem de linhas a obter na implementação.

---

## 5. O que está confirmado e o que não está

| Item | Situação |
|---|---|
| Checagens A e B usam `mtime_ns` e tamanho | Confirmado no código |
| A ponte é conferida a cada consulta | Confirmado no código |
| A ponte só é reconstruída no passo 55 | Confirmado no código |
| Hash do rodapé é rápido: 1,76 ms para o Raio-X (1,8 GiB) e 0,21 ms para as alertas; 1,74 ms para as 2 fontes da ponte e 9,96 ms para as 6 do índice, em regime (seção 8.5) | **Medido** |
| Tamanho e rodapé não mudam na cópia | Esperado pela natureza da cópia (mesmos bytes); **confirmar na máquina nova** |
| A diferença de `mtime` existe na máquina nova | **Não confirmado**: falta rodar o diagnóstico (seção 12) |
| O índice (B) já falha após cópia | **Não confirmado**: o mesmo mecanismo sugere, mas não foi testado |
| Método de cópia usado | **Não informado** |
| Corpo do 503 de `crm-prescricoes-analise` | **Não confirmado**: provavelmente o mesmo `ModuloDesatualizado`; conferir a resposta na aba Network do navegador |
| Papel do OneDrive | Descartado como causa única: o erro persistiu depois de mover o projeto para fora dele |

---

## 6. Por que não basta usar a versão, nem remover a checagem

**Versão.** Cada produtor grava uma versão como coluna constante em todas as linhas. Exemplos:

- Raio-X: `CRM_RAIOX_TX_CACHE_VERSION = 3` ([backend/cache_files.py:4](../backend/cache_files.py:4)), gravado em [data_cache.py:1941](../backend/data_cache.py:1941).
- Alertas: `_CRM_ALERTS_CACHE_VERSION = 4` ([cache_producers/crm.py:30](../backend/cache_producers/crm.py:30)).
- Os metadados do arquivo do Raio-X só têm o schema Arrow. A versão não está lá.

A versão muda quando o **código** muda. Ela não muda quando uma nova sincronização traz **dados** novos com o mesmo código.

**Cenário concreto.** O Raio-X é re-sincronizado e ganha autorizações novas. A versão continua 3. A ponte antiga não tem essas autorizações, e o histórico mostra evidência incompleta sem nenhum erro. Isso pode acontecer, porque o mapa de dependências de sincronização ([src/scripts/sincronizar_cache.py:405-410](../src/scripts/sincronizar_cache.py:405)) não liga os módulos 16 e 36 à reconstrução da ponte (55).

**Remover a checagem.** Elimina o 503, mas troca um erro visível por um resultado silencioso. Em ferramenta de auditoria, isso é pior. Por isso, a checagem fica, com um critério que não depende de `mtime`.

---

## 7. Alternativas consideradas

| Alternativa | Resolve o 503 na cópia | Detecta re-sincronização | Custo | Situação |
|---|---|---|---|---|
| Remover a checagem | sim | não | zero | Descartada: resultado errado sem aviso |
| Só a versão | sim | não | zero | Descartada: versão não descreve dados |
| Tamanho + número de linhas (revisão 3) | sim | só quando o volume muda | ≈4,3 ms por consulta da ponte, sem memória | Descartada na revisão 4: não percebe troca de valores com o mesmo volume e custa mais que o hash do rodapé |
| **Tamanho + hash do rodapé do parquet** | sim | sim, para qualquer re-sincronização que mude tamanhos ou estatísticas dos blocos | ≈1,7 ms (ponte) e ≈10 ms (índice), sem memória (seção 8.5) | **Recomendada** |
| Hash completo do conteúdo | sim | sim, qualquer byte | leitura de ≈4,48 GiB (4,81 GB) no conjunto; tempo não medido | Pendência separada (seção 9) |
| Ajustar o `mtime` na cópia | depende da ferramenta | — | — | Descartada: não é controlável pelo sistema |

### 7.1 Por que o rodapé

O rodapé (footer) de um arquivo parquet fica no fim do arquivo e guarda: o schema, o número de linhas, e, para cada bloco (row group) e cada coluna, os offsets, os tamanhos comprimidos e descomprimidos, as estatísticas (mínimo, máximo, nulos) e os metadados chave-valor. Não guarda os valores.

- Uma re-sincronização que traga dados diferentes muda o rodapé: muda o volume, os tamanhos dos blocos ou as estatísticas. Isso inclui o caso que a revisão 3 não detectava (mesmo número de linhas, valores diferentes), desde que os valores alterados mexam em algum tamanho comprimido ou em alguma estatística.
- A cópia do arquivo não altera o rodapé: são os mesmos bytes. O `mtime`, que está fora do arquivo, não participa.
- A leitura é a mesma que a contagem de linhas já fazia (os últimos bytes do arquivo), e foi mais rápida na medição: 1,76 ms contra 3,43 ms no Raio-X, 0,21 ms contra 0,84 ms nas alertas.

---

## 8. Mudança proposta

### 8.1 Assinatura persistida

- Para cada fonte: `[tamanho_em_bytes, hash_do_rodape]`.
- `hash_do_rodape`: BLAKE2b de 16 bytes (32 caracteres hexadecimais) sobre os bytes do rodapé do parquet. O tamanho do rodapé está nos 4 bytes que antecedem o marcador final `PAR1`.
- O tamanho entra porque custa só um `stat`. Um arquivo truncado já falharia na leitura do marcador, mas o tamanho mantém a mensagem de diagnóstico da seção 12 útil ("diferente em tamanho" separa cópia incompleta de conteúdo diferente).
- Gravada no próprio derivado: na ponte, no metadado que já existe (chave `fontes`); no índice, no registro `meta` que já existe (campo `fontes`).
- Conferida em cada uso. Se algum valor diferir, o erro é explícito e **nomeia a fonte**.
- Nenhuma decisão de validade usa `mtime`.
- Falha explícita, sem valor padrão: fonte inexistente (`FileNotFoundError`), arquivo menor que 12 bytes ou sem o marcador `PAR1` no fim (erro nomeando o arquivo).

### 8.2 Memória do processo

- A função nova guarda o resultado em memória, com chave `(caminho, mtime, tamanho)`, com `threading.Lock`. É o mesmo padrão de `get_dados_medico_df` ([backend/data_cache.py:5637-5654](../backend/data_cache.py:5637)) e de `obter_indice` ([crm_indice_bitmaps.py:296-310](../backend/crm_indice_bitmaps.py:296)).
- O `mtime` entra **só** como chave de cache: decide quando reler o rodapé. A validade do derivado continua sendo decidida pelos valores gravados.
- Sem a memória, a ponte releria os rodapés das duas fontes a cada requisição (≈1,7 ms medido), porque `conferir_fontes` é chamado em cada consulta ([crm_filtros_medico.py:627](../backend/api/services/analytics/crm_filtros_medico.py:627), [crm_medico_evidencias.py:184](../backend/api/services/analytics/crm_medico_evidencias.py:184), via `conferir_crm_concentracao_multiplo_medico_global` em [data_cache.py:5752](../backend/data_cache.py:5752)). Hoje essa verificação custa ≈0,1 ms.

### 8.3 Limites aceitos

- **Troca de valores que preserve todos os tamanhos comprimidos e todas as estatísticas** de cada bloco: não é detectada. É improvável, mas não está provado que seja impossível. O rodapé não lê os valores.
- **Falso positivo, no lado seguro:** regravar o mesmo conteúdo com outra versão do escritor (por exemplo, atualizar o polars) pode mudar o rodapé. O sistema responde com o erro explícito e pede para reconstruir a ponte e o índice. Custa uma reconstrução, nunca um resultado errado.
- Se o primeiro limite não for aceitável, a alternativa é o hash completo (seção 9).

### 8.4 Versões

- Subir `CRM_INDICE_BITMAPS_VERSION` e `CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION` de `1` para `2` ([backend/cache_files.py:10-11](../backend/cache_files.py:10)).
- Derivados no formato antigo (fontes gravadas como `[mtime_ns, tamanho]`) são recusados com erro de versão. **Não há fallback** para comparação por `mtime`.

### 8.5 Custo medido

Medido com os arquivos de `modules/global` no ambiente de desenvolvimento. O sistema operacional mantinha os arquivos em cache; a leitura a frio do disco não foi medida. Os rodapés lidos somam 1,00 MB na ponte e 6,35 MB no índice.

| Operação | Tempo |
|---|---|
| Verificação atual da ponte (ler metadados do derivado), mediana de 10 repetições (revisão 3) | 0,12 ms |
| Hash do rodapé do Raio-X (952.753 bytes), mediana de 10 | 1,76 ms |
| Hash do rodapé das alertas (46.242 bytes), mediana de 10 | 0,21 ms |
| **2 fontes da ponte, sem memória**, mediana de 10 | **1,74 ms** |
| **6 fontes do índice, sem memória**, mediana de 10 | **9,96 ms** |
| `stat` das 2 fontes, caminho com memória, mediana (revisão 3) | 0,01 ms |
| Para comparação, contagem de linhas: Raio-X / alertas, mediana de 10 | 3,43 ms / 0,84 ms |
| Primeira consulta de um processo novo, ponte e índice (revisão 3, com contagem de linhas; **não refeito** com o hash) | 8,5 a 14,6 ms e 47,8 ms |

Consequências:

- Com memória, a checagem da ponte continua no patamar de hoje: ≈0,1 ms por consulta, mais ≈0,01 ms do `stat`.
- Sem memória, custaria ≈1,7 ms por consulta. Por isso, a memória faz parte da mudança.
- O índice confere as fontes só quando a chave de memória muda ([crm_indice_bitmaps.py:308-310](../backend/crm_indice_bitmaps.py:308)). O custo de ≈10 ms ocorre uma vez por processo, não em cada consulta.
- O tempo da primeira consulta com o hash não foi remedido; pelas medidas acima, fica abaixo do valor da revisão 3.

---

## 9. Fora deste plano (pendências separadas)

- **Regeneração silenciosa dos parquets por CNPJ** ([cache_producers/crm.py](../backend/cache_producers/crm.py:99), 8 pontos que comparam `mtime`). Não causa 503. A mensagem de motivo na linha 105 também está errada: diz "versão de cache defasada" quando o motivo é a data do arquivo. Precisa de análise de impacto em produção.
- **Teia** ([analytics/_cache.py:179-212](../backend/api/services/analytics/_cache.py:179)): mesma comparação por `mtime`, e `except Exception: pass` nas linhas 211-212. O CLAUDE.md proíbe esse tipo de fallback silencioso. Corrigir em separado.
- **Hash completo do conteúdo**, se o primeiro limite da seção 8.3 precisar ser eliminado. Volume a ler, **medido**: ponte 1,85 GiB (1,98 GB) e índice 2,63 GiB (2,83 GB), total **4,48 GiB (4,81 GB)**, uma vez por processo. O tempo de leitura e de hash **não foi medido**. Correção: a revisão 3 citava ≈7,7 GB, valor sem fonte reproduzível, substituído pela soma medida.
- **Identificador de conteúdo gravado pelo produtor**, que exige reprocessar o Raio-X, o passo mais pesado do sistema.

---

## 10. Plano de implementação (fase única)

### 10.1 Diagnóstico antes de implementar

Rodar o diagnóstico da seção 12 na máquina nova. Ele confirma a hipótese do `mtime`. O comando vale para o código atual (fontes gravadas como `mtime` e tamanho). Depois da mudança, o campo `fontes` terá tamanho e hash do rodapé.

### 10.2 Arquivos

1. [backend/data_cache.py:454](../backend/data_cache.py:454): nova função `get_global_content_signature(name) -> tuple[int, str]`, ao lado de `get_global_cache_signature`. Retorna `(tamanho, hash_do_rodape)`. Lê os últimos 8 bytes, valida o marcador `PAR1`, lê o rodapé e calcula o BLAKE2b. Memoizada como descrito na seção 8.2.
   - A função atual continua existindo, para `dados_medico`, `mais_medicos` ([data_cache.py:5644,5664](../backend/data_cache.py:5644)), [crm_analysis.py:784-798](../backend/api/services/analytics/crm_analysis.py:784) e para a chave de memória.
2. [backend/crm_multiplo_medico.py:45-48](../backend/crm_multiplo_medico.py:45): `_assinatura_fontes()` passa a usar a função nova, sem o `[1:]`. `construir()` (linha 66, metadados em 142-145) grava o novo formato. `conferir_fontes()` ([156-172](../backend/crm_multiplo_medico.py:156)) mantém a lógica e as mensagens de erro. Atualizar o texto da docstring do módulo (linhas 18-20), que descreve a assinatura como "data e tamanho".
3. [backend/crm_indice_bitmaps.py:94](../backend/crm_indice_bitmaps.py:94) (`construir_indice`) e [:321](../backend/crm_indice_bitmaps.py:321) (`obter_indice`): trocar para a função nova. A chave de memória de [:303-304](../backend/crm_indice_bitmaps.py:303) continua com `get_global_cache_signature`. Atualizar a docstring do módulo que descreve a assinatura (linha 16).
4. [backend/cache_files.py:10-11](../backend/cache_files.py:10): versões `1` → `2`.
5. Testes (seção 10.4).

Não há módulo novo nem mudança no registro de caches (`cache_registry.py`) neste escopo.

### 10.3 Ordem de implantação

1. Implementar e rodar a suíte: `.\.venv\Scripts\python.exe -m pytest`.
2. Na máquina original, reconstruir a ponte (passo 55 da sincronização) e o índice (passo 54, `sincronizar_cache.py:371`). O passo 54 não depende da ponte e vice-versa; a ordem entre os dois não importa. Sem isso, os derivados antigos são recusados pela nova versão.
3. Copiar `modules/global` para a máquina nova. Tamanho e rodapé não mudam na cópia, então a ponte e o índice funcionam **sem reconstrução**.

Critérios de aceite:

- Na máquina nova, o histórico de CRMs carrega sem reconstruir a ponte.
- `get_global_content_signature("crm_raiox_tx_global")` devolve o mesmo valor nas duas máquinas (confirma que a cópia preserva o rodapé).
- Re-sincronizar uma fonte com dados diferentes gera erro que nomeia a fonte.
- Derivado no formato antigo gera erro explícito.

### 10.4 Testes

Obrigatórios. O CLAUDE.md exige cobertura de linhas do backend em 100%.

- Mesmo conteúdo com `mtime` diferente (arquivo copiado e `os.utime` alterado): a verificação passa.
- Fonte regravada com valores diferentes e o **mesmo número de linhas**: o hash do rodapé muda e o erro nomeia a fonte (o caso que a revisão 3 não cobria). Usar valores que alterem a estatística máxima da coluna.
- Fonte com número de linhas diferente: erro que nomeia a fonte.
- Fonte inexistente: erro, sem valor padrão.
- Arquivo menor que 12 bytes ou sem o marcador `PAR1`: erro explícito nomeando o arquivo.
- Derivado com fontes no formato antigo (com `mtime`): erro de versão.
- Memória: relê o rodapé quando `mtime` ou tamanho mudam; não relê quando não mudam (contar as leituras).
- Atualizar os monkeypatches existentes, que hoje substituem `get_global_cache_signature` e passam a substituir `get_global_content_signature`:
  - [tests/backend/test_crm_multiplo_medico.py](../tests/backend/test_crm_multiplo_medico.py) (linhas 50, 92, 96);
  - [tests/backend/test_crm_indice_bitmaps.py](../tests/backend/test_crm_indice_bitmaps.py) (linhas 65, 173, 177; as linhas 173 e 177 tratam da chave de memória do `obter_indice`, que continua usando `get_global_cache_signature`, e só mudam se o teste depender da assinatura gravada).

---

## 11. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Custo por requisição: a ponte confere a cada consulta | Memória por processo (seção 8.2). Sem ela, ≈1,7 ms por consulta, contra ≈0,1 ms hoje (seção 8.5). |
| Limite: valores alterados que preservem todos os tamanhos e estatísticas dos blocos | Aceitar, ou abrir a pendência do hash completo (seção 9). |
| Falso positivo: regravação idêntica com outra versão do escritor muda o rodapé | Erro explícito pedindo reconstrução (lado seguro). Reconstruir a ponte e o índice (seção 8.3). |
| Migração de versões | Reconstrução única dos dois derivados. Documentar na release. |
| `mtime` como chave de memória | Afeta só quando reler. A validade é decidida pelos valores gravados. |

---

## 12. Diagnóstico a rodar na máquina nova

Rodar a partir da pasta do projeto. Mostra a assinatura gravada na ponte e a assinatura atual das fontes:

```bash
.\.venv\Scripts\python.exe -c "import sys, json, polars as pl; sys.path.insert(0, 'backend'); import data_cache as dc; from crm_multiplo_medico import META_CHAVE, _assinatura_fontes; print('gravado:', json.loads(pl.read_parquet_metadata(dc._CRM_CONCENTRACAO_MULTIPLO_MEDICO_GLOBAL_PARQUET_PATH)[META_CHAVE])['fontes']); print('atual:  ', _assinatura_fontes())"
```

Interpretação (para o código atual, com `mtime` e tamanho):

- **Iguais:** a ponte está válida; o erro vem de outra causa. Investigar a partir da resposta do 503.
- **Diferentes só em `mtime`, tamanho igual:** confirma a hipótese. A mudança da seção 8 resolve.
- **Diferentes em tamanho:** os arquivos não são cópias idênticas (cópia incompleta ou versão diferente). O problema é de conteúdo, e a nova verificação também acusa a diferença.

---

## 13. Release

Como a mudança vai para produção, o CLAUDE.md exige o processo completo: `version.json` e `frontend/package.json` na mesma versão, `CHANGELOG.md`, manifesto `docs/updates/v2/manifest.json` assinado, builds, tag, push e GitHub Release. Cada etapa exige autorização explícita. Não executar sem ela.

---

## 14. Decisões pendentes

1. **Aprovar a mudança** (tamanho + hash do rodapé do parquet, sem `mtime` na comparação)?
2. **Incluir o índice de bitmaps** nesta mudança? Recomendado: sim, porque usa o mesmo padrão e deve falhar do mesmo jeito na cópia.
3. **Chave de memória:** manter o `mtime` como chave de cache, como `obter_indice` faz hoje (recomendado), ou usar só (caminho, tamanho)? Na segunda opção, uma troca de arquivo com o mesmo tamanho só seria percebida depois de reiniciar o processo.
4. **Limites aceitos** (seção 8.3): valores alterados que preservem todos os tamanhos e estatísticas dos blocos não são detectados (improvável, não provado impossível), e uma regravação com outra versão do escritor exige reconstruir os derivados. Aceitar, ou abrir a pendência do hash completo (4,81 GB a ler)?
5. **Release:** só uso local por enquanto, ou preparar o release?
6. **Método de cópia** usado (informativo; não muda o plano).

Depois das respostas, a implementação começa pela seção 10.1 (diagnóstico) e depois pela seção 10.2, com autorização explícita para cada escrita de arquivo.
