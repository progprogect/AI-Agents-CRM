/**
 * Visual workflow canvas editor.
 *
 * Architecture:
 *  - ReactFlow renders step nodes, auto-step nodes and transition/timed edges
 *  - Right-side panel shows step / edge / auto-step settings when something is selected
 *  - All mutations flow back into the parent via onUpdate
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

import { Plus, Zap } from "lucide-react";

import type {
  AgentConfigFormData,
  WorkflowFormAutoStep,
  WorkflowFormStep,
} from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";

import { nodeTypes } from "./nodeTypes";
import { StepPanel } from "./StepPanel";
import { AutoStepPanel } from "./AutoStepPanel";
import {
  START_NODE_ID,
  configToFlow,
  deriveStartStepId,
  flowToAutoSteps,
  flowToSteps,
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

function makeAutoStepId(): string {
  return `auto_${Date.now()}`;
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
    quick_replies: [],
  };
}

function makeDefaultAutoStep(id: string, sourceId: string): WorkflowFormAutoStep {
  return {
    id,
    name: "Авто-шаг",
    source_id: sourceId,
    schedule_anchor: "on_step_enter",
    cancel_on_workflow_step_change: true,
    delay_seconds: 86400, // 1 day default
    action_type: "static",
    message_template: "",
    prompt: "",
    condition: null,
    telegram_attachment_type: "none",
    telegram_video_url: null,
    telegram_video_note_file_id: null,
    _delay_unit: "days",
  };
}

// ── Inner canvas (has access to useReactFlow) ──────────────────────────────────

function CanvasInner({ config, onUpdate }: WorkflowCanvasProps) {
  const { fitView } = useReactFlow();

  const steps: WorkflowFormStep[] = config.workflow_steps ?? [];
  const autoSteps: WorkflowFormAutoStep[] = config.workflow_auto_steps ?? [];
  const startStepId = config.workflow_start_step_id ?? steps[0]?.id ?? "";

  // ── React Flow state ───────────────────────────────────────────────────────

  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => configToFlow(steps, autoSteps, startStepId),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [] // initialise once; subsequent updates come through onNodesChange/onEdgesChange
  );

  const [nodes, setNodes] = useState<Node[]>(initNodes);
  const [edges, setEdges] = useState<Edge[]>(initEdges);

  // Track whether the canvas was updated from parent (e.g. undo / external change)
  const lastStepsRef = useRef(steps);
  const lastAutoStepsRef = useRef(autoSteps);
  useEffect(() => {
    const stepsChanged = JSON.stringify(lastStepsRef.current) !== JSON.stringify(steps);
    const autoChanged = JSON.stringify(lastAutoStepsRef.current) !== JSON.stringify(autoSteps);
    if (stepsChanged || autoChanged) {
      const { nodes: n, edges: e } = configToFlow(steps, autoSteps, startStepId);
      setNodes(n);
      setEdges(e);
      lastStepsRef.current = steps;
      lastAutoStepsRef.current = autoSteps;
    }
  }, [steps, autoSteps, startStepId]);

  // ── Selection state ────────────────────────────────────────────────────────

  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectedAutoStepId, setSelectedAutoStepId] = useState<string | null>(null);

  const selectedStep = useMemo(
    () => steps.find((s) => s.id === selectedStepId) ?? null,
    [steps, selectedStepId]
  );
  const selectedEdge = useMemo(
    () => edges.find((e) => e.id === selectedEdgeId) ?? null,
    [edges, selectedEdgeId]
  );
  const selectedAutoStep = useMemo(
    () => autoSteps.find((a) => a.id === selectedAutoStepId) ?? null,
    [autoSteps, selectedAutoStepId]
  );

  // ── Flush canvas state → form data ────────────────────────────────────────

  const flush = useCallback(
    (nextNodes: Node[], nextEdges: Edge[]) => {
      const nextSteps = flowToSteps(nextNodes, nextEdges, steps);
      const nextAutoSteps = flowToAutoSteps(nextNodes, nextEdges, autoSteps);
      const newStartId = deriveStartStepId(nextEdges) || nextSteps[0]?.id || "";
      // Mark as canvas-originated so the sync useEffect doesn't rebuild nodes/edges.
      lastStepsRef.current = nextSteps;
      lastAutoStepsRef.current = nextAutoSteps;
      onUpdate({
        workflow_steps: nextSteps,
        workflow_auto_steps: nextAutoSteps,
        workflow_start_step_id: newStartId,
      });
    },
    [steps, autoSteps, onUpdate]
  );

  // ── React Flow change handlers ─────────────────────────────────────────────

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      const next = applyNodeChanges(changes, nodes);
      setNodes(next);
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
      // Detect if the target is an auto-step node — create a timed edge.
      const targetNode = nodes.find((n) => n.id === connection.target);
      const isTimedEdge = targetNode?.type === "autoStepNode";

      const newEdge: Edge = isTimedEdge
        ? {
            ...connection,
            id: `timed:${connection.source}→${connection.target}__${Date.now()}`,
            type: "smoothstep",
            animated: true,
            label: "⏱",
            labelStyle: { fontSize: 11, fill: "#7C3AED", fontWeight: 600 },
            labelBgStyle: { fill: "#F5F3FF", fillOpacity: 0.9, stroke: "#C4B5FD" },
            style: { stroke: "#7C3AED", strokeWidth: 1.5, strokeDasharray: "6 3" },
            data: {
              isTimed: true,
              autoStepId: connection.target,
              sourceId: connection.source,
            },
          }
        : {
            ...connection,
            id: `${connection.source}→${connection.target}__${Date.now()}`,
            type: "smoothstep",
            label: "",
            style: { stroke: "#251D1C", strokeWidth: 1.5 },
            data: {
              condition: "",
              is_forced: false,
              is_fallback: false,
              next_step_id: connection.target,
            },
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
    if (node.type === "autoStepNode") {
      setSelectedAutoStepId(node.id);
      setSelectedStepId(null);
      setSelectedEdgeId(null);
    } else {
      setSelectedStepId(node.id);
      setSelectedAutoStepId(null);
      setSelectedEdgeId(null);
    }
  }, []);

  const onEdgeClick: EdgeMouseHandler = useCallback((_, edge) => {
    if (edge.source === START_NODE_ID) return;
    if ((edge.data as { isTimed?: boolean })?.isTimed) return; // timed edges not editable via click
    setSelectedEdgeId(edge.id);
    setSelectedStepId(null);
    setSelectedAutoStepId(null);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedStepId(null);
    setSelectedEdgeId(null);
    setSelectedAutoStepId(null);
  }, []);

  // ── Step mutations ─────────────────────────────────────────────────────────

  const handleAddStep = useCallback(() => {
    const id = makeStepId();
    const idx = nodes.filter((n) => n.type === "stepNode").length;
    const newStep = makeDefaultStep(id, idx);

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
    lastStepsRef.current = nextSteps;
    lastAutoStepsRef.current = autoSteps;
    onUpdate({
      workflow_steps: nextSteps,
      workflow_auto_steps: autoSteps,
      workflow_start_step_id: config.workflow_start_step_id || id,
    });
  }, [nodes, steps, autoSteps, onUpdate, config.workflow_start_step_id]);

  const handleUpdateStep = useCallback(
    (stepId: string, patch: Partial<WorkflowFormStep>) => {
      const nextSteps = steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s));
      const updatedStep = nextSteps.find((s) => s.id === stepId);
      setNodes((prev) =>
        prev.map((n) => (n.id === stepId ? { ...n, data: { step: updatedStep } } : n))
      );
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

  // ── Auto-step mutations ────────────────────────────────────────────────────

  const handleAddAutoStep = useCallback(() => {
    const id = makeAutoStepId();
    // Attach to the first step by default, or empty string if no steps yet.
    const sourceId = steps[0]?.id ?? "";
    const newAutoStep = makeDefaultAutoStep(id, sourceId);

    // Position to the right of the last step node (or auto-step node).
    const allStepNodes = nodes.filter(
      (n) => n.type === "stepNode" || n.type === "autoStepNode"
    );
    const lastX = allStepNodes.reduce((max, n) => Math.max(max, n.position.x), 160);
    const position = { x: lastX + 340, y: 280 };
    const newAutoStepWithPos = { ...newAutoStep, _position: position };

    const newNode: Node = {
      id,
      type: "autoStepNode",
      position,
      data: { autoStep: newAutoStepWithPos },
    };

    const nextNodes = [...nodes, newNode];
    const nextAutoSteps = [...autoSteps, newAutoStepWithPos];
    setNodes(nextNodes);
    lastStepsRef.current = steps;
    lastAutoStepsRef.current = nextAutoSteps;
    onUpdate({
      workflow_auto_steps: nextAutoSteps,
    });
    setSelectedAutoStepId(id);
    setSelectedStepId(null);
    setSelectedEdgeId(null);
  }, [nodes, steps, autoSteps, onUpdate]);

  const handleUpdateAutoStep = useCallback(
    (autoStepId: string, patch: Partial<WorkflowFormAutoStep>) => {
      const nextAutoSteps = autoSteps.map((a) =>
        a.id === autoStepId ? { ...a, ...patch } : a
      );
      const updated = nextAutoSteps.find((a) => a.id === autoStepId);
      setNodes((prev) =>
        prev.map((n) =>
          n.id === autoStepId ? { ...n, data: { autoStep: updated } } : n
        )
      );
      lastAutoStepsRef.current = nextAutoSteps;
      onUpdate({ workflow_auto_steps: nextAutoSteps });
    },
    [autoSteps, onUpdate]
  );

  const handleDeleteAutoStep = useCallback(
    (autoStepId: string) => {
      const nextNodes = nodes.filter((n) => n.id !== autoStepId);
      const nextEdges = edges.filter(
        (e) => e.source !== autoStepId && e.target !== autoStepId
      );
      setNodes(nextNodes);
      setEdges(nextEdges);
      setSelectedAutoStepId(null);
      flush(nextNodes, nextEdges);
    },
    [nodes, edges, flush]
  );

  // ── Fit view on mount ──────────────────────────────────────────────────────

  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 80);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const panelOpen = !!(selectedStep || selectedEdge || selectedAutoStep);

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

          <button
            type="button"
            onClick={handleAddAutoStep}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[#7C3AED] text-white rounded-md hover:bg-[#6D28D9] transition-colors shadow"
          >
            <Zap size={13} />
            Авто-шаг
          </button>

          {(steps.length > 0 || autoSteps.length > 0) && (
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
            nodeColor={(n) => {
              if (n.type === "startNode") return "#16a34a";
              if (n.type === "autoStepNode") return "#7C3AED";
              return "#251D1C";
            }}
            maskColor="rgba(238,234,231,0.6)"
            className="border border-[#BEBAB7] rounded"
          />
        </ReactFlow>

        {/* Empty state */}
        {steps.length === 0 && autoSteps.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <p className="text-[#9A9590] text-sm">Нажмите «Добавить шаг», чтобы начать</p>
          </div>
        )}
      </div>

      {/* Right panel */}
      {panelOpen && (
        <div className="w-80 flex-shrink-0 overflow-hidden border-l border-[#EEEAE7]">
          {selectedAutoStep ? (
            <AutoStepPanel
              autoStep={selectedAutoStep}
              onUpdate={(patch) => handleUpdateAutoStep(selectedAutoStep.id, patch)}
              onDelete={() => handleDeleteAutoStep(selectedAutoStep.id)}
              onClose={() => setSelectedAutoStepId(null)}
            />
          ) : (
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
          )}
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
