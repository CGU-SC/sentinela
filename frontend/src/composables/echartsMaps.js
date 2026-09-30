/**
 * Mapa nacional (brasil-uf) do ECharts: fonte única para registrar e conferir.
 *
 * registerMap/getMap só funcionam depois que o módulo de mapas do ECharts foi
 * instalado (use([MapChart])). Antes disso o registro é ignorado sem erro —
 * por isso o módulo é instalado aqui, e o registro é conferido no próprio
 * ECharts (getMap) em vez de uma marca global.
 */
import { use, registerMap, getMap } from 'echarts/core';
import { MapChart } from 'echarts/charts';

use([MapChart]);

const BRASIL_UF = 'brasil-uf';
let registroPendente = null;

export async function ensureBrasilUfMap() {
  if (getMap(BRASIL_UF)) return;
  if (!registroPendente) {
    registroPendente = fetch('/geo/brasil-uf.json')
      .then(async (response) => {
        if (!response.ok) throw new Error('Não foi possível carregar o mapa do Brasil.');
        const geo = await response.json();
        if (geo?.type !== 'FeatureCollection' || !Array.isArray(geo.features) || !geo.features.length) {
          throw new Error('GeoJSON nacional sem territórios válidos.');
        }
        registerMap(BRASIL_UF, geo);
        if (!getMap(BRASIL_UF)) throw new Error('O ECharts não registrou o mapa do Brasil.');
      })
      .finally(() => { registroPendente = null; });
  }
  await registroPendente;
}
