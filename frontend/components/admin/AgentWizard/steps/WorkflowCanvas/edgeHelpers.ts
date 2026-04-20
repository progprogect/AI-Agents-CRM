/** Converts between WorkflowFormStep[]/WorkflowFormAutoStep[] and React Flow nodes/edges. */

import type { Edge, Node } from "@xyflow/react";
import type { WorkflowFormAutoStep, WorkflowFormStep } from "@/lib/utils/agentConfig";

// ── Constants ─────────────────────────────────────────────────────────────────

export const START_NODE_ID = "__start__";
const STEP_WIDTH = 240;
const STEP_HEIGHT = 110;
const AUTO_STEP_WIDTH = 220;
const AUTO_STEP_HEIGHT = 90;
const H_GAP = 100;
const V_GAP = 80;

/** Marker added to edges that connect to/from AutoStepNodes. */
export const TIMED_EDGE_TYPE = "timedEdge";

// ── Auto-layout (simple horizontal chain with vertical stacking) ────────────

/**
 * Returns a position for step at `index` when no stored `_position` is
 * available.  Steps are arranged left-to-right; if there are more than 4 steps
 * per row they wrap into a second row.
 */
function autoPosition(index: number): { x: number; y: number } {
  const cols = 4;
  const col = index % cols;
  const row = Math.floor(index / cols);
  return {
    x: 160 + col * (STEP_WIDTH + H_GAP),
    y: 80 + row * (STEP_HEIGHT + V_GAP),
  };
}

function autoAutoStepPosition(
  sourcePosition: { x: number; y: number },
  chainIndex: number
): { x: number; y: number } {
  return {
    x: sourcePosition.x + AUTO_STEP_WIDTH + H_GAP,
    y: sourcePosition.y + chainIndex * (AUTO_STEP_HEIGHT + V_GAP),
  };
}

function formatDelayLabel(seconds: number): string {
  if (seconds >= 86400 && seconds % 86400 === 0) return `${seconds / 86400} дн`;
  if (seconds >= 3600 && seconds % 3600 === 0) return `${seconds / 3600} ч`;
  if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60} мин`;
  return `${seconds} с`;
}

// ── steps[] → nodes / edges ───────────────────────────────────────────────────

export function stepsToFlow(
  steps: WorkflowFormStep[],
  startStepId: string
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Start node
  nodes.push({
    id: START_NODE_ID,
    type: "startNode",
    position: { x: 0, y: 140 },
    data: {},
    draggable: true,
  });

  // Edge from start to first step
  if (startStepId) {
    edges.push({
      id: `__start__→${startStepId}`,
      source: START_NODE_ID,
      target: startStepId,
      type: "smoothstep",
      animated: false,
      style: { stroke: "#251D1C", strokeWidth: 2 },
    });
  }

  // Step nodes
  steps.forEach((step, idx) => {
    nodes.push({
      id: step.id,
      type: "stepNode",
      position: step._position ?? autoPosition(idx),
      data: { step },
      draggable: true,
    });

    // Transition edges
    step.transitions.forEach((tr, trIdx) => {
      const edgeId = `${step.id}→${tr.next_step_id}__${trIdx}`;
      const isFallback = tr.is_fallback === true;
      const isForced = tr.is_forced === true;

      const edgeStyle = isFallback
        ? { stroke: "#9A9590", strokeWidth: 1.5, strokeDasharray: "5 4" }
        : isForced
        ? { stroke: "#ef4444", strokeWidth: 2 }
        : { stroke: "#251D1C", strokeWidth: 1.5 };

      const edgeLabelBgStyle = isFallback
        ? { fill: "#fff", fillOpacity: 0.85, stroke: "#9A9590" }
        : isForced
        ? { fill: "#fff", fillOpacity: 0.85, stroke: "#ef4444" }
        : { fill: "#fff", fillOpacity: 0.85, stroke: "#BEBAB7" };

      const edgeLabel = isFallback
        ? "Иначе"
        : tr.condition
        ? tr.condition.length > 38
          ? tr.condition.slice(0, 36) + "…"
          : tr.condition
        : undefined;

      edges.push({
        id: edgeId,
        source: step.id,
        target: tr.next_step_id,
        type: "smoothstep",
        label: edgeLabel,
        labelStyle: { fontSize: 11, fill: isFallback ? "#9A9590" : "#251D1C" },
        labelBgStyle: edgeLabelBgStyle,
        style: edgeStyle,
        data: {
          stepId: step.id,
          transitionIndex: trIdx,
          condition: tr.condition,
          is_forced: tr.is_forced,
          is_fallback: tr.is_fallback ?? false,
          next_step_id: tr.next_step_id,
        },
      });
    });
  });

  return { nodes, edges };
}

// ── configToFlow: steps + auto_steps → nodes / edges ─────────────────────────

/**
 * Extended version of `stepsToFlow` that also renders `WorkflowAutoStep` nodes
 * and the dashed "timed" edges connecting them to their sources.
 */
export function configToFlow(
  steps: WorkflowFormStep[],
  autoSteps: WorkflowFormAutoStep[],
  startStepId: string
): { nodes: Node[]; edges: Edge[] } {
  const { nodes, edges } = stepsToFlow(steps, startStepId);

  // Build a lookup of node positions (needed for auto-placement).
  const posById = new Map<string, { x: number; y: number }>();
  nodes.forEach((n) => posById.set(n.id, n.position));

  // Track how many auto-steps are chained off each source to stagger vertically.
  const chainCountBySource = new Map<string, number>();

  autoSteps.forEach((as) => {
    const sourcePos = posById.get(as.source_id) ?? { x: 500, y: 80 };
    const chainIdx = chainCountBySource.get(as.source_id) ?? 0;
    chainCountBySource.set(as.source_id, chainIdx + 1);

    const position = as._position ?? autoAutoStepPosition(sourcePos, chainIdx);
    posById.set(as.id, position);

    nodes.push({
      id: as.id,
      type: "autoStepNode",
      position,
      data: { autoStep: as },
      draggable: true,
    });

    // Timed (dashed, purple) edge from source to auto-step.
    const delayLabel = formatDelayLabel(as.delay_seconds);
    edges.push({
      id: `timed:${as.source_id}→${as.id}`,
      source: as.source_id,
      target: as.id,
      type: "smoothstep",
      animated: true,
      label: `⏱ ${delayLabel}`,
      labelStyle: { fontSize: 11, fill: "#7C3AED", fontWeight: 600 },
      labelBgStyle: { fill: "#F5F3FF", fillOpacity: 0.9, stroke: "#C4B5FD" },
      style: { stroke: "#7C3AED", strokeWidth: 1.5, strokeDasharray: "6 3" },
      data: {
        isTimed: true,
        autoStepId: as.id,
        sourceId: as.source_id,
        delay_seconds: as.delay_seconds,
      },
    });
  });

  return { nodes, edges };
}

// ── flowToAutoSteps: nodes / edges → WorkflowFormAutoStep[] ──────────────────

export function flowToAutoSteps(
  nodes: Node[],
  edges: Edge[],
  existingAutoSteps: WorkflowFormAutoStep[]
): WorkflowFormAutoStep[] {
  const asMap = new Map<string, WorkflowFormAutoStep>();
  existingAutoSteps.forEach((a) => asMap.set(a.id, a));

  const updated: WorkflowFormAutoStep[] = [];

  nodes
    .filter((n) => n.type === "autoStepNode")
    .forEach((n) => {
      const existing = asMap.get(n.id);
      if (!existing) return;

      // Find the incoming timed edge to determine source_id.
      const incomingTimedEdge = edges.find(
        (e) => e.target === n.id && (e.data as { isTimed?: boolean })?.isTimed
      );
      const sourceId = incomingTimedEdge?.source ?? existing.source_id;

      updated.push({
        ...existing,
        source_id: sourceId,
        _position: n.position,
      });
    });

  return updated;
}

// ── nodes / edges → steps[] ───────────────────────────────────────────────────

export function flowToSteps(
  nodes: Node[],
  edges: Edge[],
  existingSteps: WorkflowFormStep[]
): WorkflowFormStep[] {
  const stepMap = new Map<string, WorkflowFormStep>();
  existingSteps.forEach((s) => stepMap.set(s.id, s));

  // Rebuild transitions from edges (exclude start-node edges)
  const transitionsBySource = new Map<string, { condition: string; is_forced: boolean; is_fallback: boolean; next_step_id: string }[]>();

  edges.forEach((edge) => {
    if (edge.source === START_NODE_ID) return;
    const list = transitionsBySource.get(edge.source) ?? [];
    list.push({
      condition: (edge.data as { condition?: string })?.condition ?? (edge.label as string) ?? "",
      is_forced: (edge.data as { is_forced?: boolean })?.is_forced ?? false,
      is_fallback: (edge.data as { is_fallback?: boolean })?.is_fallback ?? false,
      next_step_id: edge.target,
    });
    transitionsBySource.set(edge.source, list);
  });

  // Preserve node order from `nodes`, skipping start node
  const updated: WorkflowFormStep[] = [];
  nodes
    .filter((n) => n.id !== START_NODE_ID && n.type === "stepNode")
    .forEach((n) => {
      const existing = stepMap.get(n.id);
      if (!existing) return;
      updated.push({
        ...existing,
        transitions: transitionsBySource.get(n.id) ?? [],
        _position: n.position,
      });
    });

  return updated;
}

/** Derives start_step_id from edges (target of the __start__ edge). */
export function deriveStartStepId(edges: Edge[]): string {
  const startEdge = edges.find((e) => e.source === START_NODE_ID);
  return startEdge?.target ?? "";
}
