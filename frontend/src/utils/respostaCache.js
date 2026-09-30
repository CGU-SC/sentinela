/**
 * Cache LRU em memória para respostas de API (ex.: modais que reabrem com os
 * mesmos parâmetros). A chave deve incluir a versão do cache de dados, para
 * que uma sincronização invalide as respostas antigas.
 * @param {number} maximo quantidade máxima de respostas guardadas.
 */
export function createRespostaCache(maximo) {
  if (!Number.isInteger(maximo) || maximo < 1) throw new Error(`Tamanho de cache inválido: ${maximo}`);
  const entradas = new Map();
  return {
    get(chave) {
      if (!entradas.has(chave)) return undefined;
      const valor = entradas.get(chave);
      entradas.delete(chave);
      entradas.set(chave, valor);
      return valor;
    },
    set(chave, valor) {
      entradas.delete(chave);
      entradas.set(chave, valor);
      if (entradas.size > maximo) entradas.delete(entradas.keys().next().value);
    },
  };
}
