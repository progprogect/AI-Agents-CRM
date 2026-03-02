/** CRM Kanban board — drag conversations between pipeline stages. */

"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useDroppable } from "@dnd-kit/core";
import { api } from "@/lib/api";
import type { Conversation, CRMStage } from "@/lib/types/conversation";
import type { Agent } from "@/lib/types/agent";
import { formatRelativeTime, getWaitingTime } from "@/lib/utils/timeFormat";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Plus, Pencil, Trash2, Check, X, ExternalLink, RefreshCw } from "lucide-react";

// ── Status dot ───────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    AI_ACTIVE: "bg-green-500",
    NEEDS_HUMAN: "bg-amber-500",
    HUMAN_ACTIVE: "bg-blue-500",
    CLOSED: "bg-gray-400",
  };
  const labels: Record<string, string> = {
    AI_ACTIVE: "AI Active",
    NEEDS_HUMAN: "Needs Human",
    HUMAN_ACTIVE: "Human Active",
    CLOSED: "Closed",
  };
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 ${colors[status] ?? "bg-gray-400"}`}
      title={labels[status] ?? status}
    />
  );
}

// ── Channel badge ─────────────────────────────────────────────────────────────

function ChannelBadge({ channel }: { channel?: string | null }) {
  if (channel === "instagram") return <span className="text-xs text-pink-600 font-medium">IG</span>;
  if (channel === "telegram") return <span className="text-xs text-blue-500 font-medium">TG</span>;
  return <span className="text-xs text-[#9A9590] font-medium">Web</span>;
}

// ── Conversation card ─────────────────────────────────────────────────────────

interface CardProps {
  conversation: Conversation;
  isDragging?: boolean;
}

function ConversationCard({ conversation: c, isDragging }: CardProps) {
  const contactName =
    c.external_user_name ||
    (c.external_user_username ? `@${c.external_user_username}` : null) ||
    `Visitor #${c.conversation_id.slice(-6)}`;

  return (
    <div
      className={`bg-white rounded-md border border-[#BEBAB7] p-3 space-y-2 select-none transition-shadow ${
        isDragging ? "shadow-lg opacity-80 rotate-1 border-[#251D1C]" : "shadow-sm hover:shadow-md"
      }`}
    >
      {/* Top row: status + channel + id + time */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <StatusDot status={c.status} />
          <ChannelBadge channel={c.channel} />
          <span className="text-xs text-[#9A9590] font-mono">
            #{c.conversation_id.slice(-6)}
          </span>
        </div>
        <span className="text-xs text-[#9A9590] flex-shrink-0">
          {formatRelativeTime(c.updated_at)}
        </span>
      </div>

      {/* Contact name */}
      <div className="font-medium text-sm text-[#251D1C] truncate">{contactName}</div>

      {/* Request type / handoff reason as context */}
      {(c.request_type || c.handoff_reason) && (
        <div className="text-xs text-[#9A9590] truncate">
          {c.request_type
            ? `Type: ${c.request_type}`
            : `Reason: ${c.handoff_reason}`}
        </div>
      )}

      {/* Waiting time (only for NEEDS_HUMAN) + open link */}
      <div className="flex items-center justify-between pt-0.5">
        {c.status === "NEEDS_HUMAN" ? (
          <span className="text-xs text-amber-600 font-medium">
            Waiting {getWaitingTime(c.updated_at)}
          </span>
        ) : (
          <span />
        )}
        <Link
          href={`/admin/conversations/${c.conversation_id}`}
          className="flex items-center gap-1 text-xs text-[#443C3C] hover:text-[#251D1C] font-medium"
          onClick={(e) => e.stopPropagation()}
        >
          Open <ExternalLink size={10} />
        </Link>
      </div>
    </div>
  );
}

// ── Sortable card wrapper ─────────────────────────────────────────────────────

function SortableCard({ conversation }: { conversation: Conversation }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: conversation.conversation_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <ConversationCard conversation={conversation} />
    </div>
  );
}

// ── Kanban column ─────────────────────────────────────────────────────────────

interface ColumnProps {
  stage: CRMStage;
  conversations: Conversation[];
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onColorChange: (id: string, color: string) => void;
}

function KanbanColumn({ stage, conversations, onRename, onDelete, onColorChange }: ColumnProps) {
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(stage.name);
  const inputRef = useRef<HTMLInputElement>(null);

  const { setNodeRef, isOver } = useDroppable({ id: stage.id });

  const handleRenameSubmit = () => {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== stage.name) {
      onRename(stage.id, trimmed);
    }
    setEditing(false);
    setEditName(stage.name);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleRenameSubmit();
    if (e.key === "Escape") {
      setEditing(false);
      setEditName(stage.name);
    }
  };

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  return (
    <div className="flex-shrink-0 w-72 flex flex-col gap-3">
      {/* Column header */}
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {/* Color swatch (click to change color) */}
          <label className="cursor-pointer flex-shrink-0" title="Change color">
            <span
              className="block w-3 h-3 rounded-full"
              style={{ backgroundColor: stage.color }}
            />
            <input
              type="color"
              value={stage.color}
              onChange={(e) => onColorChange(stage.id, e.target.value)}
              className="sr-only"
            />
          </label>

          {editing ? (
            <div className="flex items-center gap-1 flex-1">
              <input
                ref={inputRef}
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={handleKeyDown}
                className="flex-1 text-sm font-semibold text-[#251D1C] bg-[#EEEAE7] px-1.5 py-0.5 rounded border border-[#BEBAB7] outline-none min-w-0"
              />
              <button onClick={handleRenameSubmit} className="text-green-600 hover:text-green-800">
                <Check size={14} />
              </button>
              <button
                onClick={() => { setEditing(false); setEditName(stage.name); }}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <button
              className="text-sm font-semibold text-[#251D1C] truncate hover:text-[#443C3C] text-left"
              onClick={() => setEditing(true)}
              title="Click to rename"
            >
              {stage.name}
            </button>
          )}

          <span className="text-xs text-[#9A9590] flex-shrink-0">
            ({conversations.length})
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setEditing(true)}
            className="text-[#9A9590] hover:text-[#443C3C] p-0.5"
            title="Rename"
          >
            <Pencil size={12} />
          </button>
          {!stage.is_default && (
            <button
              onClick={() => onDelete(stage.id)}
              className="text-[#9A9590] hover:text-red-500 p-0.5"
              title="Delete stage"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Color bar */}
      <div
        className="h-1 rounded-full w-full"
        style={{ backgroundColor: stage.color }}
      />

      {/* Cards drop zone */}
      <div
        ref={setNodeRef}
        className={`flex flex-col gap-2 min-h-[120px] rounded-md p-2 transition-colors ${
          isOver ? "bg-[#EEEAE7]/70 ring-2 ring-[#251D1C]/20" : "bg-[#F7F5F3]"
        }`}
      >
        <SortableContext
          items={conversations.map((c) => c.conversation_id)}
          strategy={verticalListSortingStrategy}
        >
          {conversations.map((conv) => (
            <SortableCard key={conv.conversation_id} conversation={conv} />
          ))}
        </SortableContext>

        {conversations.length === 0 && (
          <div className="flex items-center justify-center h-16 text-xs text-[#BEBAB7]">
            Drop cards here
          </div>
        )}
      </div>
    </div>
  );
}

// ── Add Stage form ────────────────────────────────────────────────────────────

function AddStageButton({ onAdd }: { onAdd: (name: string, color: string) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState("#9A9590");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const handleSubmit = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd(trimmed, color);
    setName("");
    setColor("#9A9590");
    setOpen(false);
  };

  if (!open) {
    return (
      <div className="flex-shrink-0 w-72">
        <button
          onClick={() => setOpen(true)}
          className="w-full flex items-center gap-2 px-4 py-3 rounded-md border-2 border-dashed border-[#BEBAB7] text-[#9A9590] hover:border-[#443C3C] hover:text-[#443C3C] transition-colors text-sm font-medium"
        >
          <Plus size={16} />
          Add Stage
        </button>
      </div>
    );
  }

  return (
    <div className="flex-shrink-0 w-72 bg-white rounded-md border border-[#BEBAB7] p-3 space-y-3">
      <div className="text-sm font-semibold text-[#251D1C]">New Stage</div>
      <input
        ref={inputRef}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") handleSubmit();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Stage name..."
        className="w-full text-sm px-2.5 py-1.5 border border-[#BEBAB7] rounded outline-none focus:border-[#251D1C]"
      />
      <div className="flex items-center gap-2">
        <label className="text-xs text-[#9A9590]">Color:</label>
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          className="w-8 h-8 cursor-pointer rounded border border-[#BEBAB7]"
        />
        <div className="flex gap-2 ml-auto">
          <button
            onClick={() => setOpen(false)}
            className="text-xs text-[#9A9590] hover:text-[#443C3C]"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="text-xs font-medium text-white bg-[#251D1C] px-3 py-1 rounded hover:bg-[#443C3C]"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CRMPage() {
  const [stages, setStages] = useState<CRMStage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const load = useCallback(async () => {
    try {
      setError(null);
      const [stagesData, convsData, agentsData] = await Promise.all([
        api.listCrmStages(),
        api.listConversations({ agent_id: selectedAgentId || undefined, limit: 500 }),
        api.listAgents().catch(() => []),
      ]);
      setStages(stagesData);
      setConversations(convsData);
      setAgents(agentsData);
    } catch (e) {
      setError("Failed to load CRM data");
    } finally {
      setLoading(false);
    }
  }, [selectedAgentId]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  // Auto-refresh every 30s
  useEffect(() => {
    const timer = setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, [load]);

  // Group conversations by crm_stage_id
  const byStage = useCallback(
    (stageId: string) =>
      conversations.filter((c) => c.crm_stage_id === stageId),
    [conversations]
  );

  // ── Drag handlers ────────────────────────────────────────────────────────────

  const handleDragStart = (event: DragStartEvent) => {
    const conv = conversations.find((c) => c.conversation_id === event.active.id);
    setActiveConversation(conv ?? null);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveConversation(null);
    const { active, over } = event;
    if (!over) return;

    const conv = conversations.find((c) => c.conversation_id === active.id);
    if (!conv) return;

    // Determine target stage: over.id can be a stage UUID or a conversation UUID
    const targetStageId =
      stages.find((s) => s.id === over.id)?.id ??
      conversations.find((c) => c.conversation_id === over.id)?.crm_stage_id;

    if (!targetStageId || targetStageId === conv.crm_stage_id) return;

    // Optimistic update
    setConversations((prev) =>
      prev.map((c) =>
        c.conversation_id === conv.conversation_id
          ? { ...c, crm_stage_id: targetStageId }
          : c
      )
    );

    try {
      await api.updateConversationCrmStage(conv.conversation_id, targetStageId);
    } catch {
      // Revert on failure
      setConversations((prev) =>
        prev.map((c) =>
          c.conversation_id === conv.conversation_id
            ? { ...c, crm_stage_id: conv.crm_stage_id }
            : c
        )
      );
    }
  };

  // ── Stage CRUD ───────────────────────────────────────────────────────────────

  const handleRename = async (id: string, name: string) => {
    const updated = await api.updateCrmStage(id, { name }).catch(() => null);
    if (updated) setStages((prev) => prev.map((s) => (s.id === id ? updated : s)));
  };

  const handleColorChange = async (id: string, color: string) => {
    setStages((prev) => prev.map((s) => (s.id === id ? { ...s, color } : s)));
    await api.updateCrmStage(id, { color }).catch(() => null);
  };

  const handleDelete = async (id: string) => {
    if (deleteConfirm !== id) {
      setDeleteConfirm(id);
      return;
    }
    try {
      await api.deleteCrmStage(id);
      setStages((prev) => prev.filter((s) => s.id !== id));
    } catch (e: any) {
      alert(e?.message ?? "Cannot delete: stage has conversations assigned.");
    } finally {
      setDeleteConfirm(null);
    }
  };

  const handleAddStage = async (name: string, color: string) => {
    const created = await api.createCrmStage(name, color).catch(() => null);
    if (created) setStages((prev) => [...prev, created]);
  };

  // ── Render ────────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-600 text-sm">{error}</div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#BEBAB7] bg-white flex-shrink-0">
        <div>
          <h1 className="text-xl font-bold text-[#251D1C]">CRM Pipeline</h1>
          <p className="text-sm text-[#9A9590]">Drag conversations between stages</p>
        </div>

        <div className="flex items-center gap-3">
          {/* Agent filter */}
          <select
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
            className="text-sm border border-[#BEBAB7] rounded px-3 py-1.5 text-[#443C3C] bg-white outline-none focus:border-[#251D1C]"
          >
            <option value="">All Agents</option>
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.config?.profile?.agent_display_name ?? a.agent_id}
              </option>
            ))}
          </select>

          <button
            onClick={load}
            className="flex items-center gap-1.5 text-sm text-[#9A9590] hover:text-[#251D1C] border border-[#BEBAB7] px-3 py-1.5 rounded hover:border-[#443C3C] transition-colors"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {/* Delete confirmation banner */}
      {deleteConfirm && (
        <div className="px-6 py-2 bg-red-50 border-b border-red-200 flex items-center justify-between text-sm">
          <span className="text-red-700">
            Click Delete again to confirm removing &quot;{stages.find((s) => s.id === deleteConfirm)?.name}&quot;
          </span>
          <button
            onClick={() => setDeleteConfirm(null)}
            className="text-red-400 hover:text-red-600"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Board */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden">
        <DndContext
          sensors={sensors}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <div className="flex gap-4 p-6 h-full min-w-max items-start">
            {stages.map((stage) => (
              <KanbanColumn
                key={stage.id}
                stage={stage}
                conversations={byStage(stage.id)}
                onRename={handleRename}
                onDelete={handleDelete}
                onColorChange={handleColorChange}
              />
            ))}

            <AddStageButton onAdd={handleAddStage} />
          </div>

          <DragOverlay>
            {activeConversation ? (
              <ConversationCard conversation={activeConversation} isDragging />
            ) : null}
          </DragOverlay>
        </DndContext>
      </div>
    </div>
  );
}
