import { defineStore } from 'pinia';
import { ref, computed, shallowRef } from 'vue';
import axios from 'axios';
import { API_ENDPOINTS } from '../config/api';

export const useGeoStore = defineStore('geo', () => {
  const localidades = ref([]);
  const isLoading = ref(false);
  const estabelecimentos = ref([]);  // [{cnpj, razao_social, lat, lon, id_ibge7, score_risco, classificacao_risco}]
  const estabelecimentosKey = ref(null);

  // Mapa O(1) para buscas rápidas (id_ibge7 -> localidade)
  const localidadesByIbge7 = computed(() => {
    const map = new Map();
    for (const l of localidades.value) {
      if (l.id_ibge7 != null) {
        map.set(Number(l.id_ibge7), l);
      }
    }
    return map;
  });

  // GeoJSON de municípios — carregado no boot, filtrado por UF sob demanda.
  // shallowRef: 22 MB e 642 mil pontos; so e trocado inteiro, nunca editado por
  // dentro. Sem reatividade profunda, filtrar a UF e ler coordenadas fica ~5x
  // mais rapido e o ECharts recebe o objeto puro.
  const municipiosGeoJson = shallowRef(null);

  async function loadMunicipiosGeo() {
    try {
      municipiosGeoJson.value = await fetch('/geo/brasil-mun.json').then(r => r.json());
    } catch (err) {
      console.error('Erro ao carregar GeoJSON de municípios:', err);
    }
  }

  const UF_IBGE = {
    RO:'11', AC:'12', AM:'13', RR:'14', PA:'15', AP:'16', TO:'17',
    MA:'21', PI:'22', CE:'23', RN:'24', PB:'25', PE:'26', AL:'27', SE:'28', BA:'29',
    MG:'31', ES:'32', RJ:'33', SP:'35',
    PR:'41', SC:'42', RS:'43',
    MS:'50', MT:'51', GO:'52', DF:'53',
  };

  function getMunicipiosGeoByUF(uf) {
    if (!municipiosGeoJson.value || !uf || uf === 'Todos') return null;
    const prefix = UF_IBGE[uf];
    if (!prefix) return null;
    return {
      type: 'FeatureCollection',
      features: municipiosGeoJson.value.features.filter(f =>
        String(f.properties.id).startsWith(prefix)
      ),
    };
  }


  async function fetchLocalidades() {
    isLoading.value = true;
    try {
      const response = await axios.get(API_ENDPOINTS.geoLocalidades);
      localidades.value = response.data.localidades;
    } catch (err) {
      console.error('Erro ao buscar localidades:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchEstabelecimentos(inicio = null, fim = null) {
    const key = `${inicio || ''}|${fim || ''}`;
    if (estabelecimentosKey.value === key) return;

    try {
      const params = {};
      if (inicio) params.data_inicio = inicio;
      if (fim)    params.data_fim    = fim;
      const response = await axios.get(API_ENDPOINTS.geoEstabelecimentos, { params });
      estabelecimentos.value = response.data.estabelecimentos;
      estabelecimentosKey.value = key;
    } catch (err) {
      console.error('Erro ao buscar estabelecimentos geo:', err);
    }
  }

  // Lista slim [{cnpj, razao_social}] para autocomplete na sidebar
  const cnpjLookup = ref([]);

  async function fetchCnpjLookup() {
    try {
      const response = await axios.get(API_ENDPOINTS.analyticsCnpjLookup);
      cnpjLookup.value = response.data;
    } catch (err) {
      console.error('Erro ao buscar lookup de CNPJs:', err);
    }
  }

  // Lookup O(1) por id_ibge7 → lista de estabelecimentos
  const estabelecimentosPorIbge7 = computed(() => {
    const map = new Map();
    for (const e of estabelecimentos.value) {
      if (e.id_ibge7 == null) continue;
      const key = Number(e.id_ibge7); // normaliza: string "4207205" e number 4207205 viram o mesmo tipo
      if (isNaN(key)) continue;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(e);
    }
    return map;
  });

  // UFs distintas (sempre fixo, mas derivado dos dados reais)
  const ufs = computed(() => {
    const set = new Set(localidades.value.map(l => l.sg_uf));
    return ['Todos', ...Array.from(set).sort()];
  });

  // Regiões de saúde filtradas pela UF selecionada
  function regioesPorUF(uf) {
    const filtradas = uf === 'Todos'
      ? localidades.value
      : localidades.value.filter(l => l.sg_uf === uf);
    
    // Agrupa por ID para garantir unicidade e pegar o nome canônico
    const map = new Map();
    filtradas.forEach(l => {
      if (l.id_regiao_saude) {
        map.set(String(l.id_regiao_saude), l.no_regiao_saude);
      }
    });

    const list = Array.from(map.entries()).map(([id, nome]) => ({
      label: nome,
      value: id
    }));

    list.sort((a, b) => a.label.localeCompare(b.label));
    return [{ label: 'Todos', value: 'Todos' }, ...list];
  }

  // Unidades da PF filtradas por UF, Região de Saúde e/ou Município
  function jurisdicoesPorFiltro(uf, regiao, municipioValue) {
    let filtradas = localidades.value;
    if (uf && uf !== 'Todos') filtradas = filtradas.filter(l => l.sg_uf === uf);
    if (regiao && regiao !== 'Todos') filtradas = filtradas.filter(l => String(l.id_regiao_saude) === String(regiao));
    
    if (municipioValue && municipioValue !== 'Todos') {
      filtradas = filtradas.filter(l => String(l.id_ibge7) === String(municipioValue));
    }

    // Filtra nulos e vazios
    const set = new Set(filtradas.map(l => l.unidade_pf).filter(Boolean));
    return ['Todos', ...Array.from(set).sort()];
  }

  // Municípios filtrados por UF e/ou Região de Saúde (Com tratamento de homônimos)
  function qtdMunicipiosPorRegiao(regiao) {
    if (!regiao) return null;
    const municipios = new Set(
      localidades.value
        .filter((l) => String(l.id_regiao_saude) === String(regiao))
        .map((l) => l.no_municipio)
    );
    return municipios.size || null;
  }

  function municipiosPorFiltro(uf, regiao, unidade) {
    let filtradas = localidades.value;
    if (uf && uf !== 'Todos') filtradas = filtradas.filter(l => l.sg_uf === uf);
    if (regiao && regiao !== 'Todos') filtradas = filtradas.filter(l => String(l.id_regiao_saude) === String(regiao));
    if (unidade && unidade !== 'Todos') filtradas = filtradas.filter(l => l.unidade_pf === unidade);
    
    // Gera lista de objetos únicos { label, value }
    const list = filtradas.map(l => ({
        label: uf === 'Todos' ? `${l.no_municipio} - ${l.sg_uf}` : l.no_municipio,
        value: String(l.id_ibge7), // Agora usamos ID IBGE7 como PK profissional
        nome: l.no_municipio,
        uf: l.sg_uf
    }));

    // Remove duplicatas e ordena
    const unique = Array.from(new Map(list.map(item => [item.value, item])).values());
    unique.sort((a, b) => a.label.localeCompare(b.label));

    return [{ label: 'Todos', value: 'Todos' }, ...unique];
  }

  // Auxiliares para tradução de IBGE7 para formato de Filtro (Nome|UF)
  function getFilterValueByIbge7(ibge7) {
    if (!ibge7 || ibge7 === 'Todos') return 'Todos';
    const found = localidadesByIbge7.value.get(Number(ibge7));
    return found ? `${found.no_municipio}|${found.sg_uf}` : 'Todos';
  }

  function getMunicipioNomeByIbge7(ibge7) {
    if (!ibge7 || ibge7 === 'Todos') return null;
    const found = localidadesByIbge7.value.get(Number(ibge7));
    return found ? found.no_municipio : null;
  }

  function getRegiaoByIbge7(ibge7) {
    if (!ibge7 || ibge7 === 'Todos') return 'Todos';
    const found = localidadesByIbge7.value.get(Number(ibge7));
    return found ? String(found.id_regiao_saude) : 'Todos';
  }

  function getRegiaoNomeById(regiaoId) {
    if (!regiaoId || regiaoId === 'Todos') return null;
    const found = localidades.value.find(
      l => String(l.id_regiao_saude) === String(regiaoId)
    );
    return found?.no_regiao_saude ?? null;
  }

  return {
    localidades,
    isLoading,
    fetchLocalidades,
    ufs,
    regioesPorUF,
    jurisdicoesPorFiltro,
    municipiosPorFiltro,
    qtdMunicipiosPorRegiao,
    getFilterValueByIbge7,
    getMunicipioNomeByIbge7,
    getRegiaoByIbge7,
    getRegiaoNomeById,
    municipiosGeoJson,
    loadMunicipiosGeo,
    getMunicipiosGeoByUF,
    estabelecimentos,
    fetchEstabelecimentos,
    estabelecimentosPorIbge7,
    cnpjLookup,
    fetchCnpjLookup,
  };
})
