import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { test } from 'node:test';

const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { computed, ref } = require('vue');
const { defineStore, createPinia, setActivePinia } = require('pinia');
const filename = new URL('../frontend/src/stores/farmaciaLists.js', import.meta.url);
const source = fs.readFileSync(filename, 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace('export const useFarmaciaListsStore', 'const useFarmaciaListsStore');
const pharmacy = { cnpj: '00000000000001', razaoSocial: 'Farmácia' };
const evidence = { id: 'a', cnpj: pharmacy.cnpj };
const endpoints = {
  preferences: '/preferences', preferencesWatchlist: '/preferences/watchlist',
  preferencesRecoveryStatus: '/preferences/recovery/status', preferencesRecovery: '/preferences/recovery',
  preferencesWatchlistUltimaRemocao: '/preferences/watchlist/ultima-remocao',
  preferencesWatchlistDesfazerRemocao: '/preferences/watchlist/desfazer-remocao',
};

async function setup({ failPut = false, failReload = false, confirm = true, oldContract = false,
  backup = null } = {}) {
  setActivePinia(createPinia());
  const calls = [];
  let list = [pharmacy];
  let removed = [];
  let serverEvidence = [evidence];
  const evidencias = {
    loadState: 'ready', itens: [evidence],
    garantirCarregado: async () => {},
    contar: () => 1,
    confirmarRemocaoFarmacia: async () => confirm,
    removerDoCnpj: () => { throw new Error('Não pode excluir evidências em chamada separada.'); },
    carregar: async () => {
      calls.push({ method: 'evidenciasGET' });
      evidencias.loadState = failReload ? 'error' : 'ready';
      if (!failReload) evidencias.itens = serverEvidence;
    },
  };
  const axios = {
    get: async (url) => ({ data: url === endpoints.preferences ? { watchlist: list }
      : url === endpoints.preferencesWatchlistUltimaRemocao ? {
        removido_em: removed.length ? '2026-10-01T12:00:00+00:00' : null,
        farmacias: removed.map((item) => ({ cnpj: item.cnpj, razaoSocial: item.razaoSocial, evidencias_count: 1 })),
      } : backup ? backup : oldContract ? {
      backup: { exists: true, valid: true, watchlist_count: 1 },
    } : {
      backup: { exists: true, valid: true, kind: 'separate', watchlist_count: 1,
        missing_watchlist_count: 0, missing_evidencias_count: 1, evidencias_count: 1,
        evidencias_backup_valid: true, farmacias_mantidas_count: 0 },
      corrupt: { exists: false, valid: false, kind: 'separate', watchlist_count: null,
        missing_watchlist_count: null, missing_evidencias_count: null, evidencias_count: null,
        evidencias_backup_valid: false, farmacias_mantidas_count: null },
    } }),
    put: async (url, payload) => {
      calls.push({ method: 'PUT', url, payload });
      if (failPut) throw new Error('gravação falhou');
      removed = list.filter((item) => !payload.interesse.some((next) => next.cnpj === item.cnpj));
      list = payload.interesse;
      serverEvidence = [];
      return { data: { watchlist: list } };
    },
    post: async (url, payload, config) => {
      calls.push({ method: 'POST', url, payload, config });
      removed = [];
      list = [pharmacy];
      serverEvidence = [evidence];
      return { data: { watchlist: list } };
    },
  };
  const context = {
    computed, ref, defineStore, axios, API_ENDPOINTS: endpoints,
    useEvidenciasStore: () => evidencias,
    localStorage: { getItem: () => null, setItem: () => {} },
    console: { warn: () => {}, error: () => {} },
  };
  const store = vm.runInNewContext(`${source}\nuseFarmaciaListsStore();`, context);
  await new Promise(setImmediate); // aguarda o carregamento inicial da store
  return { store, calls, evidencias };
}

test('remoção envia uma atualização coordenada e recarrega as evidências', async () => {
  const { store, calls, evidencias } = await setup();
  assert.equal(await store.removerInteresse(pharmacy.cnpj), true);
  assert.deepEqual(calls.map((call) => call.method), ['PUT', 'evidenciasGET']);
  assert.equal(store.interesse.length, 0);
  assert.equal(evidencias.itens.length, 0);
});

test('cancelar a confirmação mantém a lista e as evidências', async () => {
  const { store, calls, evidencias } = await setup({ confirm: false });
  assert.equal(await store.removerInteresse(pharmacy.cnpj), null);
  assert.equal(calls.length, 0);
  assert.equal(store.interesse.length, 1);
  assert.equal(evidencias.itens.length, 1);
});

test('falha na atualização mantém as evidências no cliente', async () => {
  const { store, calls, evidencias } = await setup({ failPut: true });
  assert.equal(await store.removerInteresse(pharmacy.cnpj), false);
  assert.deepEqual(calls.map((call) => call.method), ['PUT']);
  assert.equal(store.interesse.length, 1);
  assert.equal(evidencias.itens.length, 1);
});

test('restauração envia a escolha explícita e atualiza uma cesta já carregada', async () => {
  const { store, calls, evidencias } = await setup();
  evidencias.itens = [];
  assert.equal(await store.restoreFromFile('backup', true), true);
  assert.equal(calls[0].config.params.incluir_evidencias_backup, true);
  assert.deepEqual(calls.map((call) => call.method), ['POST', 'evidenciasGET']);
  assert.equal(evidencias.itens.length, 1);
});

test('falha na recarga informa que a restauração já foi concluída', async () => {
  const { store } = await setup({ failReload: true });
  assert.equal(await store.restoreFromFile('backup'), true);
  assert.match(store.error, /restauração foi concluída no servidor/);
  assert.equal(store.interesse.length, 1);
});

test('aviso de recuperação aparece para evidência ausente mesmo com lista preenchida', async () => {
  const { store } = await setup();
  assert.equal(store.interesse.length, 1);
  assert.equal(store.recoveryAvailable, true);
});

test('contrato antigo não vira uma recuperação silenciosa sem evidências', async () => {
  const { store } = await setup({ oldContract: true });
  assert.equal(store.recoveryOptions, null);
  assert.match(store.recoveryError, /servidor está atualizado/);
});

test('remoção feita de propósito mostra o Desfazer, não o aviso de recuperação', async () => {
  const joint = {
    backup: { exists: true, valid: true, kind: 'separate', watchlist_count: 2, missing_watchlist_count: 1,
      missing_evidencias_count: 0, evidencias_count: 2, evidencias_backup_valid: true, farmacias_mantidas_count: 0 },
    corrupt: { exists: false, valid: false, kind: 'separate', watchlist_count: null, missing_watchlist_count: null,
      missing_evidencias_count: null, evidencias_count: null, evidencias_backup_valid: false,
      farmacias_mantidas_count: null },
  };
  const { store, calls } = await setup({ backup: joint });
  await store.adicionarInteresse('00000000000002', 'Outra');
  assert.equal(await store.removerInteresse(pharmacy.cnpj), true);
  assert.equal(store.recoveryAvailable, false);
  assert.deepEqual(Array.from(store.ultimaRemocao, (item) => item.cnpj), [pharmacy.cnpj]);
  assert.equal(await store.desfazerRemocao(pharmacy.cnpj), true);
  const undo = calls.find((call) => call.url === endpoints.preferencesWatchlistDesfazerRemocao);
  assert.equal(undo.payload.cnpj, pharmacy.cnpj);
  assert.equal(store.ultimaRemocao.length, 0);
});
