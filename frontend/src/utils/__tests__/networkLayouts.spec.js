import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DENSE_GRAPH_NODE_THRESHOLD,
  MAX_DENSE_LAYOUT_SCALE,
  createNetworkLayouts,
  getDenseLayoutScale,
  sortGraphNodes,
} from '@/utils/network/networkLayouts'

const node = ({ id, label, fullLabel }) => ({
  id: () => id,
  data: (key) => ({ label, fullLabel })[key],
})

class FakeCollection {
  constructor(graph, items = []) { this.graph = graph; this.items = items; this.length = items.length }
  [Symbol.iterator]() { return this.items[Symbol.iterator]() }
  empty() { return this.items.length === 0 }
  first() { return new FakeCollection(this.graph, this.items.slice(0, 1)) }
  id() { return this.items[0]?.id() }
  data(key) { return this.items[0]?.data(key) }
  position(value) { return this.items[0]?.position(value) }
  connectedEdges(selector) { return this.items[0]?.connectedEdges(selector) || new FakeCollection(this.graph) }
  connectedNodes(selector) {
    if (this.items[0] instanceof FakeEdge) {
      return new FakeCollection(this.graph, [...new Set(this.items.flatMap((edge) => [edge.sourceNode, edge.targetNode]))]);
    }
    return this.items[0]?.connectedNodes(selector) || new FakeCollection(this.graph)
  }
  map(callback) { return this.items.map(callback) }
  forEach(callback) { this.items.forEach(callback) }
  reduce(callback, initial) { return this.items.reduce(callback, initial) }
  toArray() { return [...this.items] }
  filter(predicate) {
    const items = typeof predicate === 'function'
      ? this.items.filter(predicate)
      : this.items.filter((item) => item.visible !== false)
    return new FakeCollection(this.graph, items)
  }
  positions(callback) { this.items.forEach((item) => item.position(callback(item))); }
  stop() { this.graph.stopElements(); return this }
  layout(options) { this.graph.layoutOptions = options; return this.graph.layout }
}

class FakeNode {
  constructor(graph, id, data = {}, position = { x: 0, y: 0 }) {
    this.graph = graph; this.nodeId = id; this.attributes = data; this.currentPosition = position;
    this.visible = true; this.length = 1; this.animations = [];
  }
  id() { return this.nodeId }
  data(key) { return this.attributes[key] }
  position(position) {
    if (position) { this.currentPosition = position; return this }
    return this.currentPosition
  }
  animate(properties, options) { this.position(properties.position); this.animations.push({ properties, options }); }
  connectedEdges() {
    return new FakeCollection(this.graph, this.graph._edges.filter((edge) => edge.sourceNode === this || edge.targetNode === this));
  }
  connectedNodes() {
    const nodes = [];
    this.connectedEdges().forEach((edge) => { nodes.push(edge.sourceNode, edge.targetNode); });
    return new FakeCollection(this.graph, [...new Set(nodes)]);
  }
}

class FakeEdge {
  constructor(sourceNode, targetNode, data = {}) {
    this.sourceNode = sourceNode; this.targetNode = targetNode; this.attributes = data; this.visible = true;
  }
  source() { return this.sourceNode }
  target() { return this.targetNode }
  data(key) { return this.attributes[key] }
}

function makeGraph({ width = 1400, height = 900, community = true } = {}) {
  const graph = {
    width, height, _nodes: [], _edges: [], zoomLevel: 1.1, layoutStop: null, layoutOptions: null,
    layout: { stop: vi.fn(), run: vi.fn() },
    stopElements: vi.fn(),
    one: vi.fn((_event, callback) => { graph.layoutStop = callback; }),
    zoom: () => graph.zoomLevel,
    elements: () => new FakeCollection(graph, [...graph._nodes, ...graph._edges]),
    nodes: () => new FakeCollection(graph, graph._nodes.filter((item) => item.visible !== false)),
    edges: () => new FakeCollection(graph, graph._edges.filter((item) => item.visible !== false)),
    getElementById: (id) => new FakeCollection(graph, graph._nodes.filter((item) => item.id() === id)),
  };
  graph.width = () => width;
  graph.height = () => height;
  const addNode = (id, type, label = id) => {
    const created = new FakeNode(graph, id, { type, label, fullLabel: label });
    graph._nodes.push(created);
    return created;
  };
  const connect = (source, target, expansion_level = 'N3') => {
    const edge = new FakeEdge(source, target, { expansion_level });
    graph._edges.push(edge);
    return edge;
  };
  const root = addNode('root', 'PJ_ALVO', 'Alvo');
  const north = addNode('north', 'PF', 'Ana');
  const east = addNode('east', 'PF', 'Bruno');
  const south = addNode('south', 'PF', 'Caio');
  const west = addNode('west', 'PF', 'Dora');
  const companyNorthA = addNode('north-a', 'PJ', 'Empresa A');
  const companyNorthB = addNode('north-b', 'PJ', 'Empresa B');
  const companyEast = addNode('east-a', 'PJ_FARMACIA_POPULAR', 'Farmácia');
  const companySouth = addNode('south-a', 'PJ_OUTRAS_FARMACIAS', 'Outra');
  const companyWest = addNode('west-a', 'PJ_DEMAIS_EMPRESAS', 'Demais');
  const extra = addNode('extra', 'PJ', 'Extra');
  const isolatedA = addNode('isolated-a', 'PJ', 'Isolada A');
  const isolatedB = addNode('isolated-b', 'PJ', 'Isolada B');
  connect(root, north); connect(root, east); connect(root, south); connect(root, west);
  connect(north, companyNorthA, 'N4'); connect(north, companyNorthB, 'N4');
  connect(east, companyEast, 'N4'); connect(south, companySouth, 'N4'); connect(west, companyWest, 'N4');
  connect(companyNorthA, extra, 'N3');
  if (community) {
    connect(north, companyNorthA, 'N4');
    connect(north, east, 'N4');
    connect(companyNorthB, companyEast, 'N4');
    connect(root, addNode('external', 'PJ', 'Fora do conjunto'), 'N4');
  }
  return { graph, root, north, east, south, west, companyNorthA, companyNorthB, companyEast, companySouth, companyWest, extra, isolatedA, isolatedB };
}

function makeLayouts(graphState, overrides = {}) {
  const { graph } = graphState;
  const container = { clientWidth: 1400, clientHeight: 900, style: {} };
  let currentLayout = null;
  const setCurrentLayout = vi.fn((layout) => { currentLayout = layout; });
  const fitGraphToView = vi.fn();
  const applyGraphHighlights = vi.fn();
  const applyVisibilityFilters = vi.fn();
  const api = createNetworkLayouts({
    getCy: () => graph,
    getContainer: () => container,
    getCurrentLevel: () => 'N2',
    getCurrentLayout: () => currentLayout,
    setCurrentLayout,
    getHasActiveSearch: () => false,
    fitGraphToView,
    applyGraphHighlights,
    applyVisibilityFilters,
    getGraphRightReservePx: () => 120,
    initialFitPadding: 60,
    ...overrides,
  });
  return { api, container, setCurrentLayout, fitGraphToView, applyGraphHighlights, applyVisibilityFilters };
}

describe('networkLayouts helpers', () => {
  it('ordena elementos por rótulo com localização pt-BR e usa ID como último recurso', () => {
    const nodes = [node({ id: 'c', label: 'Zebra' }), node({ id: 'a', fullLabel: 'Árvore', label: 'A' }), node({ id: 'b' })]
    expect(sortGraphNodes(nodes).map((item) => item.id())).toEqual(['a', 'b', 'c'])
    expect(nodes.map((item) => item.id())).toEqual(['a', 'b', 'c'])
  })

  it('mantém escala normal até o limite de densidade e limita o aumento em grafos grandes', () => {
    expect(getDenseLayoutScale(0)).toBe(1)
    expect(getDenseLayoutScale(DENSE_GRAPH_NODE_THRESHOLD)).toBe(1)
    expect(getDenseLayoutScale(DENSE_GRAPH_NODE_THRESHOLD * 4)).toBe(2)
    expect(getDenseLayoutScale(100000)).toBe(MAX_DENSE_LAYOUT_SCALE)
  })

  it('usa o ID como último rótulo e normaliza um grafo mínimo sem extensão', () => {
    const unlabeled = node({ id: 'sem-rotulo' })
    const labeled = node({ id: 'rotulado', label: 'Alvo' })
    expect(sortGraphNodes([unlabeled, labeled]).map((item) => item.id()))
      .toEqual(['rotulado', 'sem-rotulo'])

    const minimal = makeGraph({ community: false })
    minimal.graph._nodes = [minimal.root]
    minimal.graph._edges = []
    const layouts = makeLayouts(minimal, { getCurrentLevel: () => 'N3' })
    expect(layouts.api.getLayoutBoundingBox()).toEqual({ x1: -210, y1: 108, w: 1700, h: 666 })
    layouts.api.applyRadialView({ rememberN2Zoom: true })
    layouts.api.runGraphLayout('n3', { fitAfter: false })
    minimal.graph.layoutStop()

    const withoutCy = makeLayouts(minimal, { getCy: () => null })
    expect(withoutCy.api.getLayoutBoundingBox()).toBeUndefined()
    withoutCy.api.rememberPresentationZoom('N3')
    withoutCy.api.applyRadialView({ rememberN2Zoom: true })
    withoutCy.api.applyLayeredRadialView()
    withoutCy.api.applyRingView()
    withoutCy.api.applyN4CommunityGridView()
    withoutCy.api.runGraphLayout()

    const withoutContainer = makeLayouts(minimal, { getContainer: () => null })
    expect(withoutContainer.api.getLayoutBoundingBox()).toBeUndefined()
    withoutContainer.api.applyRadialView()
    withoutContainer.api.applyLayeredRadialView()
    withoutContainer.api.applyRingView()
    withoutContainer.api.applyN4CommunityGridView()
    withoutContainer.api.runGraphLayout('n2')
    minimal.graph.layoutStop()

    const edgeOutsideVisibleNodes = makeGraph({ community: false })
    const external = new FakeNode(edgeOutsideVisibleNodes.graph, 'external', { type: 'PJ' })
    edgeOutsideVisibleNodes.graph._nodes = [edgeOutsideVisibleNodes.root]
    edgeOutsideVisibleNodes.graph._edges = [new FakeEdge(edgeOutsideVisibleNodes.root, external)]
    makeLayouts(edgeOutsideVisibleNodes).api.applyLayeredRadialView({ animationDuration: 1 })
  })

  it('posiciona comunidade quando a aresta N4 aponta para a pessoa pivô', () => {
    const state = makeGraph({ community: false })
    const reversePivot = new FakeNode(state.graph, 'pivo-inverso', { type: 'PF', label: 'Pivô inverso' })
    const leaf = new FakeNode(state.graph, 'empresa-inversa', { type: 'PJ', label: 'Empresa inversa' })
    state.graph._nodes.push(reversePivot, leaf)
    state.graph._edges.push(new FakeEdge(leaf, reversePivot, { expansion_level: 'N4' }))

    makeLayouts(state).api.applyN4CommunityGridView({ animationDuration: 1 })

    expect(leaf.animations).toHaveLength(1)
  })

  it('aloca corredor acima do centro quando o único pai direto fica ao norte', () => {
    const state = makeGraph({ community: false })
    state.graph._nodes = [state.root, state.north, state.companyNorthA]
    state.graph._edges = [
      new FakeEdge(state.root, state.north),
      new FakeEdge(state.north, state.companyNorthA),
    ]
    const { api } = makeLayouts(state, { getHasActiveSearch: () => true })

    api.applyLayeredRadialView({ animationDuration: 1 })

    expect(state.companyNorthA.animations).toHaveLength(1)
    expect(state.companyNorthA.position().y).toBeLessThan(486)
  })

  it('ignora normalização quando os nós, o alvo ou as dimensões somem durante o layout', () => {
    const hidden = makeGraph({ community: false })
    const hiddenLayouts = makeLayouts(hidden, { getHasActiveSearch: () => true })
    hiddenLayouts.api.runGraphLayout('n2')
    hidden.graph._nodes.forEach((item) => { item.visible = false })
    hidden.graph.layoutStop()

    const noRoot = makeGraph({ community: false })
    const noRootLayouts = makeLayouts(noRoot, { getHasActiveSearch: () => true })
    noRootLayouts.api.runGraphLayout('n2')
    noRoot.root.attributes.type = 'PF'
    noRoot.graph.layoutStop()

    const noDimensions = makeGraph({ community: false })
    const noDimensionsLayouts = makeLayouts(noDimensions, { getHasActiveSearch: () => true })
    noDimensionsLayouts.api.runGraphLayout('n2')
    noDimensionsLayouts.container.clientWidth = 0
    noDimensionsLayouts.container.clientHeight = 0
    noDimensions.graph.layoutStop()
  })

  it('executa layouts radial, em camadas, anéis e comunidades sobre componentes visíveis', async () => {
    vi.useFakeTimers();
    const state = makeGraph();
    const { api, container, fitGraphToView, applyGraphHighlights, applyVisibilityFilters } = makeLayouts(state);

    expect(api.getLayoutBoundingBox()).toEqual({ x1: -210, y1: 108, w: 1700, h: 666 });
    api.rememberPresentationZoom('N2');
    api.rememberPresentationZoom('N3');
    api.rememberPresentationZoom('N4');
    api.applyRadialView({ rememberN2Zoom: true, rememberLevel: 'N4' });
    expect(state.root.position()).toMatchObject({ x: 700, y: expect.closeTo(486) });
    expect(fitGraphToView).toHaveBeenCalledWith(60);

    api.applyLayeredRadialView({ animationDuration: 5 });
    expect(state.north.animations.length).toBeGreaterThan(0);
    expect(state.isolatedA.animations.length).toBeGreaterThan(0);
    state.graph._edges.push(new FakeEdge(state.companyEast, state.extra, { expansion_level: 'N3' }));
    api.applyLayeredRadialView({ animationDuration: 5 });
    api.applyRingView({ animationDuration: 5 });
    expect(state.root.animations.at(-1).properties.position).toMatchObject({ x: 700, y: expect.closeTo(486) });
    const fallbackPivot = new FakeNode(state.graph, 'fallback-pivot', { type: 'PF', label: 'Pivô reserva' });
    state.graph._nodes.push(fallbackPivot);
    state.graph._edges.push(new FakeEdge(state.root, fallbackPivot, { expansion_level: 'N3' }));
    state.graph._edges.push(new FakeEdge(fallbackPivot, state.isolatedA, { expansion_level: 'N3' }));
    api.applyN4CommunityGridView({ animationDuration: 5 });
    expect(state.companyNorthA.animations.length).toBeGreaterThan(0);
    expect(fallbackPivot.animations.length).toBeGreaterThan(0);
    await vi.advanceTimersByTimeAsync(1000);

    const noCommunities = makeGraph({ community: false });
    const fallbackLayouts = makeLayouts(noCommunities);
    fallbackLayouts.api.applyN4CommunityGridView({ animationDuration: 1 });
    expect(noCommunities.graph._nodes.some((item) => item.animations.length > 0)).toBe(true);

    const withoutN4Edges = makeGraph();
    withoutN4Edges.graph._edges = withoutN4Edges.graph._edges.filter(
      (edge) => edge.data('expansion_level') !== 'N4',
    );
    const emptyCommunityLayouts = makeLayouts(withoutN4Edges);
    emptyCommunityLayouts.api.applyN4CommunityGridView({ animationDuration: 1 });
    expect(withoutN4Edges.graph._nodes.some((item) => item.animations.length > 0)).toBe(true);

    const searchLayouts = makeLayouts(state, { getHasActiveSearch: () => true });
    searchLayouts.api.applyRingView({ animationDuration: 1 });
    expect(searchLayouts.applyGraphHighlights).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(100);

    api.runGraphLayout('n2', { hideDuringLayout: true, animationDuration: 10 });
    expect(container.style.opacity).toBe('0');
    expect(state.graph.layoutOptions).toMatchObject({ name: 'cose', animationDuration: 10, nodeOverlap: 18 });
    state.isolatedA.position({ x: -20000, y: 30000 });
    state.graph.layoutStop();
    expect(container.style.opacity).toBe('');
    expect(container.style.pointerEvents).toBe('');
    expect(applyVisibilityFilters).toHaveBeenCalledOnce();
    expect(fitGraphToView).toHaveBeenCalledWith(60);

    api.runGraphLayout('n3', { fitAfter: false });
    expect(state.graph.layoutOptions).toMatchObject({ nodeOverlap: 18, componentSpacing: 95 });
    expect(state.graph.layoutOptions.nodeRepulsion()).toBe(9000);
    expect(state.graph.layoutOptions.idealEdgeLength()).toBe(110);
    api.runGraphLayout('n2', { fitAfter: false });
    expect(state.graph.layoutOptions).toMatchObject({ nodeOverlap: 18, componentSpacing: 90 });
    expect(state.graph.layoutOptions.nodeRepulsion()).toBe(11000);
    expect(state.graph.layoutOptions.idealEdgeLength()).toBe(96);
    state.graph.layout.stop.mockImplementationOnce(() => { throw new Error('já parado'); });
    api.runGraphLayout('expanded');
    expect(state.graph.layoutOptions.nodeRepulsion()).toBe(8000);
    expect(state.graph.layoutOptions.idealEdgeLength()).toBe(120);
    api.runGraphLayout('base');
    expect(state.graph.layoutOptions).toMatchObject({ idealEdgeLength: expect.any(Function), gravity: 1.35 });
    expect(state.graph.layoutOptions.idealEdgeLength()).toBe(58);
    expect(state.graph.layoutOptions.nodeRepulsion()).toBe(8500);
    state.graph.layoutStop();
    await vi.advanceTimersByTimeAsync(1000);
    vi.useRealTimers();
  });

  it('devolve sem operação para grafo ausente, vazio, sem alvo ou sem dimensão', () => {
    const emptyGraph = makeGraph({ width: 0, height: 0, community: false });
    const { api, container } = makeLayouts(emptyGraph);
    container.clientWidth = 0;
    container.clientHeight = 0;
    api.applyRadialView();
    api.applyLayeredRadialView();
    api.applyRingView();
    api.applyN4CommunityGridView();
    api.runGraphLayout();

    const noRoot = makeGraph({ community: false });
    noRoot.graph._nodes = noRoot.graph._nodes.filter((item) => item.data('type') !== 'PJ_ALVO');
    const noRootLayouts = makeLayouts(noRoot);
    noRootLayouts.api.applyLayeredRadialView();
    noRootLayouts.api.applyRingView();
    noRootLayouts.api.applyN4CommunityGridView();

    const disconnected = makeGraph({ community: false });
    disconnected.graph._nodes.forEach((item) => { item.visible = false; });
    const disconnectedLayouts = makeLayouts(disconnected);
    disconnectedLayouts.api.applyRadialView();
    disconnectedLayouts.api.applyLayeredRadialView();
    disconnectedLayouts.api.applyRingView();
    disconnectedLayouts.api.applyN4CommunityGridView();
  });

  it('distribui mais de cinco anéis em grafos densos e limita escala a partir das dimensões do Cytoscape', () => {
    const graph = {
      _width: 1600,
      _height: 1000,
      _nodes: [],
      _edges: [],
      zoom: () => 1.1,
      width() { return this._width; },
      height() { return this._height; },
      nodes() { return new FakeCollection(this, this._nodes); },
      edges() { return new FakeCollection(this, this._edges); },
      elements() { return new FakeCollection(this, [...this._nodes, ...this._edges]); },
      getElementById(id) { return new FakeCollection(this, this._nodes.filter((item) => item.id() === id)); },
      one() {},
      stopElements() {},
      layout: { stop: vi.fn(), run: vi.fn() },
    };
    const root = new FakeNode(graph, 'root', { type: 'PJ_ALVO', label: 'Alvo' });
    graph._nodes.push(root);
    for (let index = 0; index < 190; index += 1) {
      const item = new FakeNode(graph, `n-${index}`, {
        type: ['PF', 'PJ_FARMACIA_POPULAR', 'PJ_OUTRAS_FARMACIAS', 'PJ_DEMAIS_EMPRESAS', 'PJ', 'UNKNOWN'][index % 6],
        label: `Nome ${index}`,
      });
      graph._nodes.push(item);
      if (index < 8) graph._edges.push(new FakeEdge(root, item));
    }
    const { api } = makeLayouts({ graph }, { getContainer: () => ({ clientWidth: 0, clientHeight: 0, style: {} }) });
    api.applyRingView({ animationDuration: 1 });
    expect(graph._nodes.every((item) => item.animations.length === 1)).toBe(true);
  });

  it('distribui descendentes ao sul e ordena nós sem rótulo pelo ID', () => {
    const south = makeGraph({ community: false });
    const company = new FakeNode(south.graph, 'company-south', { type: 'PJ' });
    south.graph._nodes = [south.root, south.north, south.east, south.south, south.west, company];
    south.graph._edges = [
      new FakeEdge(south.root, south.north),
      new FakeEdge(south.root, south.east),
      new FakeEdge(south.root, south.south),
      new FakeEdge(south.root, south.west),
      new FakeEdge(south.south, company),
    ];
    makeLayouts(south).api.applyLayeredRadialView({ animationDuration: 1 });
    expect(company.position().y).toBeGreaterThan(south.south.position().y);

    const unlabeled = makeGraph({ community: false });
    const first = new FakeNode(unlabeled.graph, 'company-a', { type: 'PJ' });
    const second = new FakeNode(unlabeled.graph, 'company-b', { type: 'PJ' });
    unlabeled.graph._nodes = [unlabeled.root, first, second];
    unlabeled.graph._edges = [];
    makeLayouts(unlabeled).api.applyRingView({ animationDuration: 1 });
    expect(first.animations).toHaveLength(1);
    expect(second.animations).toHaveLength(1);
  });

  it('ordena comunidades de mesmo tamanho pelo ID do pivô quando não há rótulo', () => {
    const state = makeGraph({ community: false });
    const pivotA = new FakeNode(state.graph, 'pivot-a', { type: 'PF' });
    const pivotB = new FakeNode(state.graph, 'pivot-b', { type: 'PF' });
    const companyA = new FakeNode(state.graph, 'company-a', { type: 'PJ' });
    const companyB = new FakeNode(state.graph, 'company-b', { type: 'PJ' });
    state.graph._nodes = [state.root, pivotA, pivotB, companyA, companyB];
    state.graph._edges = [
      new FakeEdge(state.root, pivotA),
      new FakeEdge(state.root, pivotB),
      new FakeEdge(pivotA, companyA, { expansion_level: 'N4' }),
      new FakeEdge(pivotB, companyB, { expansion_level: 'N4' }),
    ];

    makeLayouts(state).api.applyN4CommunityGridView({ animationDuration: 1 });

    expect(companyA.animations).toHaveLength(1);
    expect(companyB.animations).toHaveLength(1);
  });

  it('ordena candidatos a pai com a mesma distância usando IDs quando não há rótulos', () => {
    const state = makeGraph({ community: false });
    const parentA = new FakeNode(state.graph, 'parent-a', { type: 'PF' });
    const parentB = new FakeNode(state.graph, 'parent-b', { type: 'PF' });
    const child = new FakeNode(state.graph, 'child', { type: 'PJ' });
    state.graph._nodes = [state.root, parentA, parentB, child];
    state.graph._edges = [
      new FakeEdge(state.root, parentA),
      new FakeEdge(state.root, parentB),
      new FakeEdge(parentA, child),
      new FakeEdge(parentB, child),
    ];

    makeLayouts(state).api.applyLayeredRadialView({ animationDuration: 1 });

    expect(child.animations).toHaveLength(1);
    expect(Number.isFinite(child.position().x) && Number.isFinite(child.position().y)).toBe(true);
  });
})

afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });
