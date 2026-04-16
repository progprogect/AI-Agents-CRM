/**
 * Visual workflow canvas editor.
 *
 * Architecture:
 *  - ReactFlow renders step nodes and transition edges on a pan/zoom canvas
 *  - Right-side panel shows step / edge settings when something is selected
 *  - All mutations flow back into the parent via onUpdate (same API as the
 *    old linear WorkflowStep)
 */

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type OnConnect,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  type Connection,
  type NodeMouseHandler,
  type EdgeMouseHandler,
  BackgroundVariant,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Plus } from "lucide-react";

import type { AgentConfigFormData, WorkflowFormStep } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";

import { nodeTypes } from "./nodeTypes";
import { StepPanel } from "./StepPanel";
import {
  START_NODE_ID,
  deriveStartStepId,
  flowToSteps,
  stepsToFlow,
} from "./edgeHelpers";

// ── Props ──────────────────────────────────────────────────────────────────────

interface WorkflowCanvasProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeStepId(): string {
  return `step_${Date.now()}`;
}

function makeDefaultStep(id: string, index: number): WorkflowFormStep {
  return {
    id,
    name: `Шаг ${index + 1}`,
    instructions: "",
    collect: [],
    required: false,
    transitions: [],
    timer_trigger: undefined,
  };
}

// ── Inner canvas (has access to useReactFlow) ──────────────────────────────────

function CanvasInner({ config, onUpdate }: WorkflowCanvasProps) {
  const { fitView } = useReactFlow();

  const steps: WorkflowFormStep[] = config.workflow_steps ?? [];
  const startStepId = config.workflow_start_step_id ?? steps[0]?.id ?? "";

  // ── React Flow state ───────────────────────────────────────────────────────

  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => stepsToFlow(steps, startStepId),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [] // initialise once; subsequent updates come through onNodesChange/onEdgesChange
  );

  const [nodes, setNodes] = useState<Node[]>(initNodes);
  const [edges, setEdges] = useState<Edge[]>(initEdges);

  // Track whether the canvas was updated from parent (e.g. undo / external change)
  const lastStepsRef = useRef(steps);
  useEffect(() => {
    if (JSON.stringify(lastStepsRef.current) !== JSON.stringify(steps)) {
      const { nodes: n, edges: e } = stepsToFlow(steps, startStepId);
      setNodes(n);
      setEdges(e);
      lastStepsRef.current = steps;
    }
  }, [steps, startStepId]);

  // ── Selection state ────────────────────────────────────────────────────────

  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const selectedStep = useMemo(
    () => steps.find((s) => s.id === selectedStepId) ?? null,
    [steps, selectedStepId]
  );
  const selectedEdge = useMemo(
    () => edges.find((e) => e.id === selectedEdgeId) ?? null,
    [edges, selectedEdgeId]
  );

  // ── Flush canvas state → form data ────────────────────────────────────────

  const flush = useCallback(
    (nextNodes: Node[], nextEdges: Edge[]) => {
      const nextSteps = flowToSteps(nextNodes, nextEdges, steps);
      const newStartId = deriveStartStepId(nextEdges) || nextSteps[0]?.id || "";
      // Mark as canvas-originated so the sync useEffect doesn't rebuild nodes/edges.
      lastStepsRef.current = nextSteps;
      onUpdate({
        workflow_steps: nextSteps,
        workflow_start_step_id: newStartId,
      });
    },
    [steps, onUpdate]
  );

  // ── React Flow change handlers ─────────────────────────────────────────────

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      const next = applyNodeChanges(changes, nodes);
      setNodes(next);
      // Only flush on drag-stop (not on selection or add changes)
      const hasPositionChange = changes.some(
        (c) => c.type === "position" && c.dragging === false
      );
      if (hasPositionChange) {
        flush(next, edges);
      }
    },
    [nodes, edges, flush]
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      const next = applyEdgeChanges(changes, edges);
      setEdges(next);
      const hasRemove = changes.some((c) => c.type === "remove");
      if (hasRemove) {
        flush(nodes, next);
      }
    },
    [nodes, edges, flush]
  );

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      const newEdge: Edge = {
        ...connection,
        id: `${connection.source}→${connection.target}__${Date.now()}`,
        type: "smoothstep",
        label: "",
        style: { stroke: "#251D1C", strokeWidth: 1.5 },
        data: { condition: "", is_forced: false, is_fallback: false, next_step_id: connection.target },
      };
      const next = addEdge(newEdge, edges);
      setEdges(next);
      flush(nodes, next);
    },
    [nodes, edges, flush]
  );

  // ── Click handlers ─────────────────────────────────────────────────────────

  const onNodeClick: NodeMouseHandler = useCallback((_, node) => {
    if (node.id === START_NODE_ID) return;
    setSelectedStepId(node.id);
    setSelectedEdgeId(null);
  }, []);

  const onEdgeClick: EdgeMouseHandler = useCallback((_, edge) => {
    if (edge.source === START_NODE_ID) return;
    setSelectedEdgeId(edge.id);
    setSelectedStepId(null);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedStepId(null);
    setSelectedEdgeId(null);
  }, []);

  // ── Step mutations ─────────────────────────────────────────────────────────

  const handleAddStep = useCallback(() => {
    const id = makeStepId();
    const idx = nodes.filter((n) => n.type === "stepNode").length;
    const newStep = makeDefaultStep(id, idx);

    // Position right of the last step node
    const stepNodes = nodes.filter((n) => n.type === "stepNode");
    const lastX = stepNodes.reduce((max, n) => Math.max(max, n.position.x), 160);
    const position = { x: lastX + 340, y: 140 };

    const newNode: Node = {
      id,
      type: "stepNode",
      position,
      data: { step: newStep },
    };

    const nextNodes = [...nodes, newNode];
    const nextSteps = [...steps, { ...newStep, _position: position }];
    setNodes(nextNodes);
    // Mark as canvas-originated to prevent useEffect from rebuilding canvas
    lastStepsRef.current = nextSteps;
    onUpdate({
      workflow_steps: nextSteps,
      workflow_start_step_id: config.workflow_start_step_id || id,
    });
  }, [nodes, steps, onUpdate, config.workflow_start_step_id]);

  const handleUpdateStep = useCallback(
    (stepId: string, patch: Partial<WorkflowFormStep>) => {
      const nextSteps = steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s));
      const updatedStep = nextSteps.find((s) => s.id === stepId);
      // Update node data so StepNode re-renders immediately
      setNodes((prev) =>
        prev.map((n) => (n.id === stepId ? { ...n, data: { step: updatedStep } } : n))
      );
      // Mark as canvas-originated to prevent useEffect from rebuilding canvas
      lastStepsRef.current = nextSteps;
      onUpdate({ workflow_steps: nextSteps });
    },
    [steps, onUpdate]
  );

  const handleDeleteStep = useCallback(
    (stepId: string) => {
      const nextNodes = nodes.filter((n) => n.id !== stepId);
      const nextEdges = edges.filter(
        (e) => e.source !== stepId && e.target !== stepId
      );
      setNodes(nextNodes);
      setEdges(nextEdges);
      setSelectedStepId(null);
      flush(nextNodes, nextEdges);
    },
    [nodes, edges, flush]
  );

  // ── Edge mutations ─────────────────────────────────────────────────────────

  const handleUpdateEdge = useCallback(
    (edgeId: string, data: { condition: string; is_forced: boolean; is_fallback: boolean }) => {
      const next = edges.map((e) => {
        if (e.id !== edgeId) return e;
        const { is_fallback, is_forced, condition } = data;
        const edgeStyle = is_fallback
          ? { stroke: "#9A9590", strokeWidth: 1.5, strokeDasharray: "5 4" }
          : is_forced
          ? { stroke: "#ef4444", strokeWidth: 2 }
          : { stroke: "#251D1C", strokeWidth: 1.5 };
        const edgeLabelBg = {
          fill: "#fff",
          fillOpacity: 0.85,
          stroke: is_fallback ? "#9A9590" : is_forced ? "#ef4444" : "#BEBAB7",
        };
        const edgeLabel = is_fallback
          ? "Иначе"
          : condition
          ? condition.length > 38
            ? condition.slice(0, 36) + "…"
            : condition
          : undefined;
        return {
          ...e,
          label: edgeLabel,
          labelStyle: { fontSize: 11, fill: is_fallback ? "#9A9590" : "#251D1C" },
          data: { ...e.data, ...data, next_step_id: e.target },
          style: edgeStyle,
          labelBgStyle: edgeLabelBg,
        };
      });
      setEdges(next);
      flush(nodes, next);
    },
    [edges, nodes, flush]
  );

  const handleDeleteEdge = useCallback(
    (edgeId: string) => {
      const next = edges.filter((e) => e.id !== edgeId);
      setEdges(next);
      setSelectedEdgeId(null);
      flush(nodes, next);
    },
    [edges, nodes, flush]
  );

  // ── Fit view on mount ──────────────────────────────────────────────────────

  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 80);
    return () => clearTimeout(t);
    // Mount-only: re-running when fitView identity changes causes unnecessary refits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const panelOpen = !!(selectedStep || selectedEdge);

  return (
    <div className="flex h-full w-full overflow-hidden rounded-lg border border-[#BEBAB7]">
      {/* Canvas */}
      <div className="relative flex-1 min-w-0">
        {/* Toolbar */}
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2">
          <button
            type="button"
            onClick={handleAddStep}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[#251D1C] text-white rounded-md hover:bg-[#443C3C] transition-colors shadow"
          >
            <Plus size={13} />
            Добавить шаг
          </button>

          {steps.length > 0 && (
            <span className="text-xs text-[#9A9590] bg-white/80 backdrop-blur-sm px-2 py-1 rounded border border-[#EEEAE7]">
              Перетаскивайте узлы · Соединяйте хэндлы · Кликайте для настройки
            </span>
          )}
        </div>

        <ReactFlow
          className="h-full w-full"
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          deleteKeyCode="Delete"
          minZoom={0.3}
          maxZoom={2}
          style={{ background: "#FAFAFA" }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#BEBAB7"
          />
          <Controls showInteractive={false} className="[&>button]:border-[#BEBAB7]" />
          <MiniMap
            nodeColor={(n) => (n.type === "startNode" ? "#16a34a" : "#251D1C")}
            maskColor="rgba(238,234,231,0.6)"
            className="border border-[#BEBAB7] rounded"
          />
        </ReactFlow>

        {/* Empty state */}
        {steps.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <p className="text-[#9A9590] text-sm">Нажмите «Добавить шаг», чтобы начать</p>
          </div>
        )}
      </div>

      {/* Right panel */}
      {panelOpen && (
        <div className="w-80 flex-shrink-0 overflow-hidden">
          <StepPanel
            selectedStep={selectedStep}
            selectedEdge={selectedEdge}
            steps={steps}
            edges={edges}
            onUpdateStep={handleUpdateStep}
            onDeleteStep={handleDeleteStep}
            onUpdateEdge={handleUpdateEdge}
            onDeleteEdge={handleDeleteEdge}
            onClose={() => {
              setSelectedStepId(null);
              setSelectedEdgeId(null);
            }}
          />
        </div>
      )}
    </div>
  );
}

// ── Public export (wraps in ReactFlowProvider) ─────────────────────────────────

export function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <div className="h-full w-full min-h-0">
      <ReactFlowProvider>
        <CanvasInner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
