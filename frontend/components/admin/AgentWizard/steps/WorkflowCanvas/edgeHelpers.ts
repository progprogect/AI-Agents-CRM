/** Converts between WorkflowFormStep[] and React Flow nodes/edges. */

import type { Edge, Node } from "@xyflow/react";
import type { WorkflowFormStep } from "@/lib/utils/agentConfig";

// ── Constants ─────────────────────────────────────────────────────────────────

export const START_NODE_ID = "__start__";
const STEP_WIDTH = 240;
const STEP_HEIGHT = 110;
const H_GAP = 100;
const V_GAP = 80;

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
      edges.push({
        id: edgeId,
        source: step.id,
        target: tr.next_step_id,
        type: "smoothstep",
        label: tr.condition
          ? tr.condition.length > 38
            ? tr.condition.slice(0, 36) + "…"
            : tr.condition
          : undefined,
        labelStyle: { fontSize: 11 },
        labelBgStyle: {
          fill: "#fff",
          fillOpacity: 0.85,
          stroke: tr.is_forced ? "#ef4444" : "#BEBAB7",
        },
        style: {
          stroke: tr.is_forced ? "#ef4444" : "#251D1C",
          strokeWidth: tr.is_forced ? 2 : 1.5,
        },
        data: {
          stepId: step.id,
          transitionIndex: trIdx,
          condition: tr.condition,
          is_forced: tr.is_forced,
          next_step_id: tr.next_step_id,
        },
      });
    });
  });

  return { nodes, edges };
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
  const transitionsBySource = new Map<string, { condition: string; is_forced: boolean; next_step_id: string }[]>();

  edges.forEach((edge) => {
    if (edge.source === START_NODE_ID) return;
    const list = transitionsBySource.get(edge.source) ?? [];
    list.push({
      condition: (edge.data as { condition?: string })?.condition ?? (edge.label as string) ?? "",
      is_forced: (edge.data as { is_forced?: boolean })?.is_forced ?? false,
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
