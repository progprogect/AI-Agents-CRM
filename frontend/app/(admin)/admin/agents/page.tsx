/** Agents management page with improved UX and human-readable labels. */

"use client";

import { useEffect, useState, useMemo, memo, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { Input } from "@/components/shared/Input";
import { Badge } from "@/components/shared/Badge";
import { ConfirmModal } from "@/components/shared/ConfirmModal";
import { EmptyState } from "@/components/shared/EmptyState";
import { Tooltip } from "@/components/shared/Tooltip";
import { agentConfigToFormData } from "@/lib/utils/agentConfig";
import { getAgentDisplayName, getAgentInitials, getAgentSpecialty } from "@/lib/utils/agentDisplay";
import type { Agent } from "@/lib/types/agent";

const EditIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
    className="h-4 w-4"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
    />
  </svg>
);

const CloneIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
    className="h-4 w-4"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
    />
  </svg>
);

const DeleteIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
    className="h-4 w-4"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
    />
  </svg>
);

const AgentRow = memo(function AgentRow({
  agent,
  onClone,
  onEdit,
  onDelete,
}: {
  agent: Agent;
  onClone: (agent: Agent) => void;
  onEdit: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
}) {
  const [channelCount, setChannelCount] = useState<number | null>(null);
  const [isLoadingChannels, setIsLoadingChannels] = useState(true);

  useEffect(() => {
    loadChannelCount();
  }, [agent.agent_id]);

  const loadChannelCount = async () => {
    try {
      const bindings = await api.listChannelBindings(agent.agent_id, undefined, false);
      setChannelCount(bindings.length);
    } catch (err) {
      setChannelCount(0);
    } finally {
      setIsLoadingChannels(false);
    }
  };

  const agentName = useMemo(
    () => agent.config?.profile?.agent_display_name || agent.config?.profile?.doctor_display_name || agent.agent_id,
    [agent]
  );
  const companyName = useMemo(
    () => agent.config?.profile?.company_display_name || null,
    [agent]
  );
  const initials = useMemo(() => getAgentInitials(agent), [agent]);

  return (
    <tr className="hover:bg-[#EEEAE7]/5 transition-colors duration-150">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-[#EEEAE7]/20 flex items-center justify-center text-sm font-medium text-[#443C3C]">
            {initials}
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-medium text-gray-900">{agentName}</span>
            {companyName && (
              <span className="text-xs text-gray-500">{companyName}</span>
            )}
          </div>
        </div>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <Badge variant={agent.is_active ? "success" : "default"} size="sm">
          {agent.is_active ? "Active" : "Inactive"}
        </Badge>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
        {isLoadingChannels ? (
          <span className="text-gray-400">Loading...</span>
        ) : (
          <Link
            href={`/admin/agents/${agent.agent_id}/channels`}
            className="text-[#251D1C] hover:text-[#443C3C] transition-colors duration-200"
          >
            {channelCount ?? 0} channel{channelCount !== 1 ? "s" : ""}
          </Link>
        )}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
        <Link
          href={`/admin/agents/${agent.agent_id}/rag`}
          className="text-[#251D1C] hover:text-[#443C3C] transition-colors duration-200"
        >
          RAG
        </Link>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <Tooltip content="Edit agent">
            <button
              onClick={() => onEdit(agent)}
              className="inline-flex items-center justify-center w-8 h-8 text-[#251D1C] hover:text-[#443C3C] hover:bg-[#EEEAE7]/10 rounded-sm transition-all duration-200"
              aria-label="Edit agent"
            >
              <EditIcon />
            </button>
          </Tooltip>
          <Tooltip content="Clone agent">
            <button
              onClick={() => onClone(agent)}
              className="inline-flex items-center justify-center w-8 h-8 text-[#251D1C] hover:text-[#443C3C] hover:bg-[#EEEAE7]/10 rounded-sm transition-all duration-200"
              aria-label="Clone agent"
            >
              <CloneIcon />
            </button>
          </Tooltip>
          <Tooltip content="Delete agent">
            <button
              onClick={() => onDelete(agent)}
              className="inline-flex items-center justify-center w-8 h-8 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-sm transition-all duration-200"
              aria-label="Delete agent"
            >
              <DeleteIcon />
            </button>
          </Tooltip>
        </div>
      </td>
    </tr>
  );
});

AgentRow.displayName = "AgentRow";

export default function AgentsPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      setIsLoading(true);
      const agentsData = await api.listAgents();
      setAgents(agentsData);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load agents");
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Filter agents by search query
  const filteredAgents = useMemo(() => {
    if (!searchQuery.trim()) {
      return agents;
    }

    const query = searchQuery.toLowerCase();
    return agents.filter((agent) => {
      const displayName = getAgentDisplayName(agent).toLowerCase();
      const specialty = getAgentSpecialty(agent)?.toLowerCase() || "";
      const agentId = agent.agent_id.toLowerCase();
      return (
        displayName.includes(query) ||
        specialty.includes(query) ||
        agentId.includes(query)
      );
    });
  }, [agents, searchQuery]);

  const handleCreateAgent = () => {
    router.push("/admin/agents/create");
  };

  const handleCloneAgent = useCallback(async (agent: Agent) => {
    try {
      const formData = agentConfigToFormData(agent.config);
      const newAgentId = `${agent.agent_id}_clone_${Date.now()}`;
      formData.agent_id = newAgentId;

      const draft = {
        currentStep: 1,
        config: formData,
        timestamp: Date.now(),
        isClone: true,
        sourceAgentId: agent.agent_id,
      };
      localStorage.setItem("agent_wizard_draft", JSON.stringify(draft));

      router.push("/admin/agents/create");
    } catch (err) {
      console.error("Failed to clone agent:", err);
      setError("Failed to clone agent. Please try again.");
    }
  }, [router]);

  const handleEditAgent = useCallback(async (agent: Agent) => {
    try {
      const formData = agentConfigToFormData(agent.config);
      formData.agent_id = agent.agent_id;

      const draft = {
        currentStep: 1,
        config: formData,
        timestamp: Date.now(),
        isEdit: true,
        editingAgentId: agent.agent_id,
      };
      localStorage.setItem("agent_wizard_draft", JSON.stringify(draft));

      router.push("/admin/agents/create");
    } catch (err) {
      console.error("Failed to load agent for editing:", err);
      setError("Failed to load agent for editing. Please try again.");
    }
  }, [router]);

  const handleDeleteAgent = useCallback((agent: Agent) => {
    setAgentToDelete(agent);
    setIsDeleteModalOpen(true);
  }, []);

  const confirmDeleteAgent = async () => {
    if (!agentToDelete) return;

    try {
      setIsDeleting(true);
      setError(null);
      
      await api.deleteAgent(agentToDelete.agent_id);
      
      setAgents(agents.filter((a) => a.agent_id !== agentToDelete.agent_id));
      setIsDeleteModalOpen(false);
      setAgentToDelete(null);
    } catch (err) {
      console.error("Failed to delete agent:", err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to delete agent. Please try again.");
      }
    } finally {
      setIsDeleting(false);
    }
  };

  const closeDeleteModal = () => {
    if (!isDeleting) {
      setIsDeleteModalOpen(false);
      setAgentToDelete(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          {filteredAgents.length > 0 && (
            <p className="text-sm text-gray-600 mt-1">
              {filteredAgents.length} agent{filteredAgents.length !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        <Button variant="primary" onClick={handleCreateAgent}>
          Create Agent
        </Button>
      </div>

      {/* Search bar */}
      {agents.length > 0 && (
        <div className="mb-4">
          <Input
            type="text"
            placeholder="Search by name, specialty, or agent ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-md"
          />
        </div>
      )}

      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm" role="alert">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {filteredAgents.length === 0 ? (
        <EmptyState
          icon="👨‍⚕️"
          title={searchQuery ? "No agents found" : "No agents yet"}
          description={
            searchQuery
              ? "Try adjusting your search query."
              : "Create your first AI agent to start chatting with clients."
          }
          action={
            !searchQuery && (
              <Button variant="primary" onClick={handleCreateAgent}>
                Create Your First Agent
              </Button>
            )
          }
        />
      ) : (
        <div className="bg-white rounded-sm shadow border border-[#251D1C]/20 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-[#EEEAE7]/10">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Agent
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Channels
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  RAG
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#443C3C] uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredAgents.map((agent) => (
                <AgentRow
                  key={agent.agent_id}
                  agent={agent}
                  onClone={handleCloneAgent}
                  onEdit={handleEditAgent}
                  onDelete={handleDeleteAgent}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={isDeleteModalOpen}
        onClose={closeDeleteModal}
        onConfirm={confirmDeleteAgent}
        title="Delete Agent"
        message={
          agentToDelete
            ? `Are you sure you want to delete agent "${getAgentDisplayName(agentToDelete)}"?\n\nThis action will deactivate the agent. This action cannot be undone.`
            : ""
        }
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
}
