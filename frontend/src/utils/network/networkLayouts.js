import { computeRadialNetworkLayout } from "./networkLayoutEngine";

export const DENSE_GRAPH_NODE_THRESHOLD = 28;
export const MAX_DENSE_LAYOUT_SCALE = 2.8;
const CORRIDOR_MIN_SPAN = 190;
const CORRIDOR_NODE_GAP = 96;
const CORRIDOR_GROUP_GAP = 56;
const CORRIDOR_BASE_DISTANCE = 270;
const CORRIDOR_CURVE_FACTOR = 0.24;

export function sortGraphNodes(nodes) {
  return nodes.sort((a, b) => {
    const labelA = a.data("fullLabel") || a.data("label") || a.id();
    const labelB = b.data("fullLabel") || b.data("label") || b.id();
    return String(labelA).localeCompare(String(labelB), "pt-BR");
  });
}

export function getDenseLayoutScale(nodeCount) {
  if (nodeCount <= DENSE_GRAPH_NODE_THRESHOLD) return 1;
  return Math.min(
    MAX_DENSE_LAYOUT_SCALE,
    Math.sqrt(nodeCount / DENSE_GRAPH_NODE_THRESHOLD),
  );
}

function positionOnEllipse(center, radiusX, radiusY, angle) {
  return {
    x: center.x + Math.cos(angle) * radiusX,
    y: center.y + Math.sin(angle) * radiusY,
  };
}

function getAnchorSide(anchor, center) {
  const dx = anchor.x - center.x;
  const dy = anchor.y - center.y;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "right" : "left";
  return dy >= 0 ? "bottom" : "top";
}

function getGroupLaneSpan(count) {
  return Math.max(CORRIDOR_MIN_SPAN, (Math.max(1, count) - 1) * CORRIDOR_NODE_GAP + 120);
}

function allocateCorridors(groups, getAnchor, center, getCount) {
  const layoutByGroup = new Map();
  const groupsBySide = new Map();

  groups.forEach((group) => {
    const anchor = getAnchor(group);
    if (!anchor) return;
    const side = getAnchorSide(anchor, center);
    if (!groupsBySide.has(side)) groupsBySide.set(side, []);
    groupsBySide.get(side).push({
      group,
      anchor,
      side,
      preferredLaneCenter:
        side === "right" || side === "left" ? anchor.y : anchor.x,
      span: getGroupLaneSpan(getCount(group)),
    });
  });

  groupsBySide.forEach((entries) => {
    entries.sort((a, b) => a.preferredLaneCenter - b.preferredLaneCenter);
    let previousEnd = -Infinity;
    let preferredSum = 0;
    let packedSum = 0;

    entries.forEach((entry) => {
      const halfSpan = entry.span / 2;
      entry.laneCenter = Math.max(
        entry.preferredLaneCenter,
        previousEnd + CORRIDOR_GROUP_GAP + halfSpan,
      );
      previousEnd = entry.laneCenter + halfSpan;
      preferredSum += entry.preferredLaneCenter;
      packedSum += entry.laneCenter;
    });

    const recenterOffset = (preferredSum - packedSum) / Math.max(entries.length, 1);
    entries.forEach((entry) => {
      layoutByGroup.set(entry.group, {
        anchor: entry.anchor,
        side: entry.side,
        laneCenter: entry.laneCenter + recenterOffset,
        laneSpan: entry.span,
      });
    });
  });

  return layoutByGroup;
}

function computeCorridorFanPosition({ layout, index, count }) {
  const safeCount = Math.max(1, count || 1);
  const safeIndex = Math.max(0, Math.min(index || 0, safeCount - 1));
  const slot = safeCount === 1 ? 0 : safeIndex / (safeCount - 1) - 0.5;
  const usableSpan = Math.max(0, layout.laneSpan - 70);
  const laneOffset = slot * usableSpan;

  if (layout.side === "right" || layout.side === "left") {
    const direction = layout.side === "right" ? 1 : -1;
    const y = layout.laneCenter + laneOffset;
    const x =
      layout.anchor.x +
      direction *
        (CORRIDOR_BASE_DISTANCE +
          Math.abs(y - layout.anchor.y) * CORRIDOR_CURVE_FACTOR);
    return { x, y };
  }

  const direction = layout.side === "bottom" ? 1 : -1;
  const x = layout.laneCenter + laneOffset;
  const y =
    layout.anchor.y +
    direction *
      (CORRIDOR_BASE_DISTANCE +
        Math.abs(x - layout.anchor.x) * CORRIDOR_CURVE_FACTOR);
  return { x, y };
}

export function createNetworkLayouts({
  getCy,
  getContainer,
  getCurrentLevel,
  getCurrentLayout,
  setCurrentLayout,
  getHasActiveSearch,
  fitGraphToView,
  applyGraphHighlights,
  applyVisibilityFilters,
  getGraphRightReservePx,
  initialFitPadding,
}) {
  let n2PresentationZoom = null;
  let n3PresentationZoom = null;
  let n4PresentationZoom = null;

  const getLayoutBoundingBox = () => {
    const cy = getCy();
    const container = getContainer();
    if (!cy || !container) return undefined;

    const width = container.clientWidth || cy.width();
    const height = container.clientHeight || cy.height();
    if (!width || !height) return undefined;

    const rightReserve = getGraphRightReservePx(width);

    return {
      x1: -width * 0.15,
      y1: height * 0.12,
      w: Math.max(width * 0.82, width * 1.3 - rightReserve),
      h: height * 0.74,
    };
  };

  const stopCurrentLayout = () => {
    const currentLayout = getCurrentLayout();
    if (!currentLayout) return;
    try {
      currentLayout.stop();
    } catch (e) {}
    setCurrentLayout(null);
  };

  const rememberN2PresentationZoom = () => {
    const cy = getCy();
    if (!cy || getCurrentLevel() !== "N2") return;
    n2PresentationZoom = cy.zoom();
  };

  const rememberPresentationZoom = (level) => {
    const cy = getCy();
    if (!cy) return;
    if (level === "N2") n2PresentationZoom = cy.zoom();
    if (level === "N3") n3PresentationZoom = cy.zoom();
    if (level === "N4") n4PresentationZoom = cy.zoom();
  };

  const getPresentationZoom = (level) => {
    const rememberedZoom = {
      N2: n2PresentationZoom,
      N3: n3PresentationZoom,
      N4: n4PresentationZoom,
    }[level];
    return Math.max(1, Math.min(rememberedZoom || 1.08, 1.16));
  };

  const normalizeLayoutScale = (level = "N2") => {
    const cy = getCy();
    const container = getContainer();
    if (!cy || !container) return;

    const visibleNodes = cy.nodes(":visible");
    if (visibleNodes.empty()) return;
    const denseTargetZoom = 1 / getDenseLayoutScale(visibleNodes.length);
    const targetZoom = Math.min(getPresentationZoom(level), denseTargetZoom);
    const root = visibleNodes
      .filter((node) => node.data("type") === "PJ_ALVO")
      .first();
    if (!root.length) return;

    const { clientWidth, clientHeight } = container;
    if (!clientWidth || !clientHeight) return;

    const rootPosition = root.position();
    const targetCenter = {
      x: clientWidth / 2,
      y: clientHeight * 0.54,
    };
    const available = {
      left: Math.max(80, (targetCenter.x - initialFitPadding) / targetZoom),
      right: Math.max(
        80,
        (clientWidth - targetCenter.x - initialFitPadding) / targetZoom,
      ),
      top: Math.max(80, (targetCenter.y - initialFitPadding) / targetZoom),
      bottom: Math.max(
        80,
        (clientHeight - targetCenter.y - initialFitPadding) / targetZoom,
      ),
    };
    const extents = visibleNodes.reduce(
      (acc, node) => {
        const position = node.position();
        const dx = position.x - rootPosition.x;
        const dy = position.y - rootPosition.y;
        return {
          left: Math.max(acc.left, Math.max(0, -dx)),
          right: Math.max(acc.right, Math.max(0, dx)),
          top: Math.max(acc.top, Math.max(0, -dy)),
          bottom: Math.max(acc.bottom, Math.max(0, dy)),
        };
      },
      { left: 0, right: 0, top: 0, bottom: 0 },
    );
    const scale = Math.min(
      1,
      extents.left ? available.left / extents.left : 1,
      extents.right ? available.right / extents.right : 1,
      extents.top ? available.top / extents.top : 1,
      extents.bottom ? available.bottom / extents.bottom : 1,
    );
    if (scale >= 0.98) return;

    visibleNodes.positions((node) => {
      const position = node.position();
      return {
        x: rootPosition.x + (position.x - rootPosition.x) * scale,
        y: rootPosition.y + (position.y - rootPosition.y) * scale,
      };
    });
  };

  const applyN2RadialLayout = () => {
    const cy = getCy();
    const container = getContainer();
    if (!cy || !container) return;

    const width = container.clientWidth || cy.width();
    const height = container.clientHeight || cy.height();
    if (!width || !height) return;

    const visibleNodes = cy.nodes(":visible");
    if (visibleNodes.empty()) return;

    const positions = computeRadialNetworkLayout({
      nodes: visibleNodes.map((node) => ({
        id: node.id(),
        type: node.data("type"),
        label: node.data("label"),
        fullLabel: node.data("fullLabel"),
      })),
      edges: cy.edges(":visible").map((edge) => ({
        source: edge.source().id(),
        target: edge.target().id(),
      })),
      width,
      height,
    });

    positions.forEach((position, nodeId) => {
      const node = cy.getElementById(nodeId);
      if (node.length) node.position(position);
    });
  };

  const finishAnimatedLayout = (rememberLevel, animationDuration) => {
    if (!getHasActiveSearch()) {
      window.setTimeout(() => {
        fitGraphToView(initialFitPadding, { animate: true, duration: 420 });
        if (rememberLevel) rememberPresentationZoom(rememberLevel);
      }, animationDuration + 40);
    } else {
      applyGraphHighlights();
    }
  };

  const applyLayeredRadialView = ({
    rememberLevel = getCurrentLevel(),
    animationDuration = 520,
  } = {}) => {
    const cy = getCy();
    const container = getContainer();
    if (!cy || !container) return;

    stopCurrentLayout();
    cy.elements().stop();

    const width = container.clientWidth || cy.width();
    const height = container.clientHeight || cy.height();
    if (!width || !height) return;

    const visibleNodes = cy.nodes(":visible");
    const visibleEdges = cy.edges(":visible");
    if (visibleNodes.empty()) return;

    const root = visibleNodes
      .filter((node) => node.data("type") === "PJ_ALVO")
      .first();
    if (!root.length) return;

    const center = { x: width / 2, y: height * 0.54 };
    const nodeById = new Map(visibleNodes.map((node) => [node.id(), node]));
    const adjacency = new Map();

    visibleNodes.forEach((node) => adjacency.set(node.id(), new Set()));
    visibleEdges.forEach((edge) => {
      const sourceId = edge.source().id();
      const targetId = edge.target().id();
      if (!adjacency.has(sourceId) || !adjacency.has(targetId)) return;
      adjacency.get(sourceId).add(targetId);
      adjacency.get(targetId).add(sourceId);
    });

    const rootId = root.id();
    const distanceById = new Map([[rootId, 0]]);
    const queue = [rootId];

    for (let index = 0; index < queue.length; index += 1) {
      const nodeId = queue[index];
      const nextDistance = distanceById.get(nodeId) + 1;
      adjacency.get(nodeId)?.forEach((neighborId) => {
        if (distanceById.has(neighborId)) return;
        distanceById.set(neighborId, nextDistance);
        queue.push(neighborId);
      });
    }

    const maxConnectedDistance = Math.max(0, ...distanceById.values());
    const rings = new Map();
    visibleNodes.forEach((node) => {
      if (node.id() === rootId) return;
      const distance = distanceById.get(node.id()) || maxConnectedDistance + 1;
      if (!rings.has(distance)) rings.set(distance, []);
      rings.get(distance).push(node);
    });

    const densityScale = Math.sqrt(getDenseLayoutScale(visibleNodes.length));
    const ringStepX = Math.max(190, Math.min(width * 0.17, 300)) * densityScale;
    const ringStepY = Math.max(105, Math.min(height * 0.14, 195)) * densityScale;
    const angleById = new Map([[rootId, -Math.PI / 2]]);
    const targetPositions = new Map([[rootId, center]]);

    Array.from(rings.keys())
      .sort((a, b) => a - b)
      .forEach((distance) => {
        const nodes = sortGraphNodes(rings.get(distance));
        const radiusX = ringStepX * distance;
        const radiusY = ringStepY * distance;

        if (distance <= 1) {
          nodes.forEach((node, index) => {
            const angle =
              -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(nodes.length, 1);
            angleById.set(node.id(), angle);
            targetPositions.set(
              node.id(),
              positionOnEllipse(center, radiusX, radiusY, angle),
            );
          });
          return;
        }

        const groupsByParent = new Map();
        const fallbackNodes = [];

        nodes.forEach((node) => {
          const parent = sortGraphNodes(
            node
              .connectedEdges(":visible")
              .connectedNodes(":visible")
              .filter((other) => {
                const parentDistance = distanceById.get(other.id());
                return (
                  Number.isFinite(parentDistance) &&
                  parentDistance < distance &&
                  targetPositions.has(other.id())
                );
              })
              .toArray(),
          ).sort((a, b) => {
            const distanceDiff =
              (distanceById.get(b.id()) || 0) - (distanceById.get(a.id()) || 0);
            if (distanceDiff) return distanceDiff;
            const labelA = a.data("fullLabel") || a.data("label") || a.id();
            const labelB = b.data("fullLabel") || b.data("label") || b.id();
            return String(labelA).localeCompare(String(labelB), "pt-BR");
          })[0];

          if (!parent) {
            fallbackNodes.push(node);
            return;
          }

          if (!groupsByParent.has(parent.id())) {
            groupsByParent.set(parent.id(), { parent, nodes: [] });
          }
          groupsByParent.get(parent.id()).nodes.push(node);
        });

        const parentGroups = Array.from(groupsByParent.values()).sort((a, b) => {
            const angleA = angleById.get(a.parent.id()) ?? 0;
            const angleB = angleById.get(b.parent.id()) ?? 0;
            if (angleA !== angleB) return angleA - angleB;
            const labelA =
              a.parent.data("fullLabel") || a.parent.data("label") || a.parent.id();
            const labelB =
              b.parent.data("fullLabel") || b.parent.data("label") || b.parent.id();
            return String(labelA).localeCompare(String(labelB), "pt-BR");
          });
        const corridorByGroup = allocateCorridors(
          parentGroups,
          (group) => targetPositions.get(group.parent.id()),
          center,
          (group) => group.nodes.length,
        );

        parentGroups.forEach((group) => {
            const { parent, nodes: childNodes } = group;
            const corridor = corridorByGroup.get(group);
            if (!corridor) return;
            sortGraphNodes(childNodes).forEach((node, index) => {
              const position = computeCorridorFanPosition({
                layout: corridor,
                index,
                count: childNodes.length,
              });
              targetPositions.set(node.id(), position);
              angleById.set(
                node.id(),
                Math.atan2(position.y - center.y, position.x - center.x),
              );
            });
          });

        fallbackNodes.forEach((node, index) => {
          const angle =
            -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(fallbackNodes.length, 1);
          angleById.set(node.id(), angle);
          targetPositions.set(
            node.id(),
            positionOnEllipse(center, radiusX, radiusY, angle),
          );
        });
      });

    targetPositions.forEach((position, nodeId) => {
      const node = nodeById.get(nodeId);
      if (!node) return;
      node.animate(
        { position },
        { duration: animationDuration, easing: "ease-out-cubic" },
      );
    });

    finishAnimatedLayout(rememberLevel, animationDuration);
  };

  const applyRingView = ({
    rememberLevel = getCurrentLevel(),
    animationDuration = 520,
  } = {}) => {
    const cy = getCy();
    const container = getContainer();
    if (!cy || !container) return;

    stopCurrentLayout();
    cy.elements().stop();

    const width = container.clientWidth || cy.width();
    const height = container.clientHeight || cy.height();
    if (!width || !height) return;

    const visibleNodes = cy.nodes(":visible");
    if (visibleNodes.empty()) return;

    const root = visibleNodes
      .filter((node) => node.data("type") === "PJ_ALVO")
      .first();
    if (!root.length) return;

    const center = { x: width / 2, y: height * 0.54 };
    const rootId = root.id();
    const nodeById = new Map(visibleNodes.map((node) => [node.id(), node]));
    const directNeighborIds = new Set(
      root
        .connectedEdges(":visible")
        .connectedNodes(":visible")
        .filter((node) => node.id() !== rootId)
        .map((node) => node.id()),
    );
    const typeOrder = {
      PF: 1,
      PJ_FARMACIA_POPULAR: 2,
      PJ_OUTRAS_FARMACIAS: 3,
      PJ_DEMAIS_EMPRESAS: 4,
      PJ: 5,
    };
    const nodes = visibleNodes
      .filter((node) => node.id() !== rootId)
      .toArray()
      .sort((a, b) => {
        const directDiff =
          Number(directNeighborIds.has(b.id())) -
          Number(directNeighborIds.has(a.id()));
        if (directDiff) return directDiff;

        const typeDiff =
          (typeOrder[a.data("type")] || 99) - (typeOrder[b.data("type")] || 99);
        if (typeDiff) return typeDiff;

        const labelA = a.data("fullLabel") || a.data("label") || a.id();
        const labelB = b.data("fullLabel") || b.data("label") || b.id();
        return String(labelA).localeCompare(String(labelB), "pt-BR");
      });

    const densityScale = Math.sqrt(getDenseLayoutScale(visibleNodes.length));
    const ringCapacities = [14, 24, 36, 48, 64];
    const rings = [];
    let cursor = 0;

    for (let ringIndex = 0; cursor < nodes.length; ringIndex += 1) {
      const capacity =
        ringCapacities[Math.min(ringIndex, ringCapacities.length - 1)];
      rings.push(nodes.slice(cursor, cursor + capacity));
      cursor += capacity;
    }

    const targetPositions = new Map([[rootId, center]]);
    const baseRadiusX =
      Math.max(230, Math.min(width * 0.24, 390)) * densityScale;
    const baseRadiusY =
      Math.max(125, Math.min(height * 0.21, 245)) * densityScale;
    const stepX = Math.max(180, Math.min(width * 0.16, 285)) * densityScale;
    const stepY = Math.max(100, Math.min(height * 0.13, 175)) * densityScale;

    rings.forEach((ringNodes, ringIndex) => {
      const radiusX = baseRadiusX + ringIndex * stepX;
      const radiusY = baseRadiusY + ringIndex * stepY;
      const offset = ringIndex % 2 ? Math.PI / Math.max(ringNodes.length, 1) : 0;

      ringNodes.forEach((node, index) => {
        const angle =
          -Math.PI / 2 +
          offset +
          (Math.PI * 2 * index) / Math.max(ringNodes.length, 1);
        targetPositions.set(
          node.id(),
          positionOnEllipse(center, radiusX, radiusY, angle),
        );
      });
    });

    targetPositions.forEach((position, nodeId) => {
      const node = nodeById.get(nodeId);
      if (!node) return;
      node.animate(
        { position },
        { duration: animationDuration, easing: "ease-out-cubic" },
      );
    });

    finishAnimatedLayout(rememberLevel, animationDuration);
  };

  const applyN4CommunityGridView = ({
    rememberLevel = "N4",
    animationDuration = 560,
  } = {}) => {
    const cy = getCy();
    const container = getContainer();
    if (!cy || !container) return;

    stopCurrentLayout();
    cy.elements().stop();

    const width = container.clientWidth || cy.width();
    const height = container.clientHeight || cy.height();
    if (!width || !height) return;

    const visibleNodes = cy.nodes(":visible");
    const visibleEdges = cy.edges(":visible");
    if (visibleNodes.empty()) return;

    const root = visibleNodes
      .filter((node) => node.data("type") === "PJ_ALVO")
      .first();
    if (!root.length) return;

    const rootId = root.id();
    const center = { x: width * 0.18, y: height * 0.54 };
    const nodeById = new Map(visibleNodes.map((node) => [node.id(), node]));
    const communitiesByPivot = new Map();
    const assignedNodeIds = new Set([rootId]);
    const directRootNeighborIds = new Set(
      root
        .connectedEdges(":visible")
        .connectedNodes(":visible")
        .filter((node) => node.id() !== rootId)
        .map((node) => node.id()),
    );

    visibleEdges
      .filter((edge) => edge.data("expansion_level") === "N4")
      .forEach((edge) => {
        const source = edge.source();
        const target = edge.target();
        const sourceIsPerson = source.data("type") === "PF";
        const targetIsPerson = target.data("type") === "PF";
        const anchor = sourceIsPerson ? source : targetIsPerson ? target : null;
        const leaf = anchor?.id() === source.id() ? target : source;

        if (!anchor || !leaf || leaf.id() === rootId || leaf.data("type") === "PF")
          return;
        if (!communitiesByPivot.has(anchor.id())) {
          communitiesByPivot.set(anchor.id(), { pivot: anchor, members: [] });
        }
        if (!assignedNodeIds.has(leaf.id())) {
          communitiesByPivot.get(anchor.id()).members.push(leaf);
          assignedNodeIds.add(leaf.id());
        }
      });

    const fallbackPivots = visibleNodes
      .filter((node) => node.data("type") === "PF" && node.id() !== rootId)
      .filter(
        (node) =>
          node
            .connectedEdges(":visible")
            .connectedNodes(":visible")
            .filter(
              (other) => other.id() !== rootId && other.data("type") !== "PF",
            ).length > 0,
      );

    fallbackPivots.forEach((pivot) => {
      if (!communitiesByPivot.has(pivot.id())) {
        communitiesByPivot.set(pivot.id(), { pivot, members: [] });
      }
      pivot
        .connectedEdges(":visible")
        .connectedNodes(":visible")
        .filter((other) => other.id() !== rootId && other.data("type") !== "PF")
        .forEach((member) => {
          if (assignedNodeIds.has(member.id())) return;
          communitiesByPivot.get(pivot.id()).members.push(member);
          assignedNodeIds.add(member.id());
        });
    });

    const densityScale = Math.sqrt(getDenseLayoutScale(visibleNodes.length));
    const targetPositions = new Map([[rootId, center]]);
    const coreNodes = sortGraphNodes(
      visibleNodes
        .filter((node) => node.id() !== rootId && !assignedNodeIds.has(node.id()))
        .toArray(),
    );
    const directCoreNodes = coreNodes.filter((node) =>
      directRootNeighborIds.has(node.id()),
    );
    const indirectCoreNodes = coreNodes.filter(
      (node) => !directRootNeighborIds.has(node.id()),
    );
    const coreColumns = Math.max(
      1,
      Math.ceil(Math.sqrt(Math.max(coreNodes.length, 1))),
    );
    const coreGapX = 135 * densityScale;
    const coreGapY = 92 * densityScale;
    const coreStartX = center.x + 220 * densityScale;
    const coreStartY =
      center.y - ((Math.ceil(coreNodes.length / coreColumns) - 1) * coreGapY) / 2;

    [...directCoreNodes, ...indirectCoreNodes].forEach((node, index) => {
      const col = index % coreColumns;
      const row = Math.floor(index / coreColumns);
      targetPositions.set(node.id(), {
        x: coreStartX + col * coreGapX,
        y: coreStartY + row * coreGapY,
      });
    });

    const communities = Array.from(communitiesByPivot.values())
      .filter((community) => community.members.length > 0)
      .sort((a, b) => {
        if (b.members.length !== a.members.length)
          return b.members.length - a.members.length;
        const labelA =
          a.pivot.data("fullLabel") || a.pivot.data("label") || a.pivot.id();
        const labelB =
          b.pivot.data("fullLabel") || b.pivot.data("label") || b.pivot.id();
        return String(labelA).localeCompare(String(labelB), "pt-BR");
      });

    if (!communities.length) {
      applyLayeredRadialView({ rememberLevel, animationDuration });
      return;
    }

    const blockGapX = Math.max(520, Math.min(width * 0.36, 760)) * densityScale;
    const blockGapY = Math.max(420, Math.min(height * 0.42, 620)) * densityScale;
    const blockColumns = Math.max(
      1,
      Math.min(3, Math.ceil(Math.sqrt(communities.length))),
    );
    const blockStartX = center.x + 330 * densityScale;
    const blockStartY =
      center.y -
      ((Math.ceil(communities.length / blockColumns) - 1) * blockGapY) / 2;

    const communityLayouts = communities.map((community, communityIndex) => {
      const blockCol = communityIndex % blockColumns;
      const blockRow = Math.floor(communityIndex / blockColumns);
      return {
        ...community,
        blockCenter: {
          x: blockStartX + blockCol * blockGapX,
          y: blockStartY + blockRow * blockGapY,
        },
      };
    });
    const corridorByCommunity = allocateCorridors(
      communityLayouts,
      ({ blockCenter }) => blockCenter,
      center,
      ({ members }) => members.length,
    );

    communityLayouts.forEach((communityLayout) => {
      const { pivot, members, blockCenter } = communityLayout;
      const sortedMembers = sortGraphNodes(members);
      const corridor = corridorByCommunity.get(communityLayout);

      targetPositions.set(pivot.id(), blockCenter);
      if (!corridor) return;
      sortedMembers.forEach((member, index) => {
        targetPositions.set(
          member.id(),
          computeCorridorFanPosition({
            layout: corridor,
            index,
            count: sortedMembers.length,
          }),
        );
      });
    });

    targetPositions.forEach((position, nodeId) => {
      const node = nodeById.get(nodeId);
      if (!node) return;
      node.animate(
        { position },
        { duration: animationDuration, easing: "ease-out-cubic" },
      );
    });

    finishAnimatedLayout(rememberLevel, animationDuration);
  };

  const applyRadialView = ({
    rememberN2Zoom = false,
    rememberLevel = null,
  } = {}) => {
    applyN2RadialLayout();
    fitGraphToView(initialFitPadding);
    if (rememberN2Zoom) rememberN2PresentationZoom();
    if (rememberLevel) rememberPresentationZoom(rememberLevel);
  };

  const runGraphLayout = (preset = "base", options = {}) => {
    const cy = getCy();
    const container = getContainer();
    if (!cy) return;

    const {
      hideDuringLayout = false,
      fitAfter = true,
      animationDuration = preset === "expanded" ? 700 : 800,
    } = options;

    stopCurrentLayout();

    const layoutOptions = (() => {
      if (preset === "expanded")
        return {
          nodeRepulsion: () => 8000,
          idealEdgeLength: () => 120,
          gravity: 1.2,
          numIter: 900,
          randomize: true,
        };

      if (preset === "n2")
        return {
          nodeRepulsion: () => 11000,
          idealEdgeLength: () => 96,
          gravity: 1.05,
          numIter: 800,
          randomize: true,
          componentSpacing: 90,
          nodeOverlap: 18,
        };

      if (preset === "n3")
        return {
          nodeRepulsion: () => 9000,
          idealEdgeLength: () => 110,
          gravity: 1.15,
          numIter: 850,
          randomize: true,
          componentSpacing: 95,
          nodeOverlap: 18,
        };

      return {
        nodeRepulsion: () => 8500,
        idealEdgeLength: () => 58,
        gravity: 1.35,
        numIter: 900,
        randomize: true,
      };
    })();

    if (hideDuringLayout && container) {
      container.style.opacity = "0";
    }

    const layout = cy.elements(":visible").layout({
      name: "cose",
      animate: true,
      animationDuration,
      fit: false,
      initialTemp: 1000,
      coolingFactor: 0.99,
      minTemp: 1.0,
      boundingBox: getLayoutBoundingBox(),
      ...layoutOptions,
    });
    setCurrentLayout(layout);

    cy.one("layoutstop", () => {
      const latestContainer = getContainer();
      if (latestContainer) {
        latestContainer.style.opacity = "";
        latestContainer.style.pointerEvents = "";
      }

      applyVisibilityFilters();
      if (preset === "n2" || preset === "n3") {
        normalizeLayoutScale(preset === "n3" ? "N3" : "N2");
      }
      if (fitAfter && !getHasActiveSearch()) {
        fitGraphToView(initialFitPadding);
      }
    });

    layout.run();
  };

  return {
    getLayoutBoundingBox,
    rememberPresentationZoom,
    applyRadialView,
    applyLayeredRadialView,
    applyRingView,
    applyN4CommunityGridView,
    runGraphLayout,
  };
}
