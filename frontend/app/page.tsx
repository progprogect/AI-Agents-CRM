/** Main page - Agent selection and chat entry point. */

"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { Badge } from "@/components/shared/Badge";
import { EmptyState } from "@/components/shared/EmptyState";
import { getAgentDisplayName, getAgentInitials, getAgentSpecialty } from "@/lib/utils/agentDisplay";
import type { Agent } from "@/lib/types/agent";

export default function Home() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadAgents = async () => {
      try {
        setIsLoading(true);
        const loadedAgents = await api.listAgents(true);
        setAgents(loadedAgents);
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

    loadAgents();
  }, []);

  const handleStartChat = (agentId: string) => {
    router.push(`/chat/${agentId}`);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white p-4">
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Error</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <Button variant="primary" onClick={() => window.location.reload()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-[#EEEAE7]/5 to-[#251D1C]/10">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <div className="flex justify-center mb-4">
            <Image src="/logo.svg" alt="CAworks" width={160} height={44} priority />
          </div>
          <p className="text-xl text-gray-600">
            Select an agent to start a consultation
          </p>
        </div>

        {agents.length === 0 ? (
          <EmptyState
            icon="👨‍⚕️"
            title="No agents available"
            description="Please contact the administrator to set up agents."
            action={
              <a
                href="/admin/agents"
                className="text-[#251D1C] hover:text-[#443C3C] underline transition-colors duration-200"
              >
                Go to Admin Panel
              </a>
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
            {agents.map((agent) => {
              const displayName = getAgentDisplayName(agent);
              const initials = getAgentInitials(agent);
              const specialty = getAgentSpecialty(agent);

              return (
                <div
                  key={agent.agent_id}
                  className="bg-white rounded-sm shadow-md border border-[#251D1C]/20 p-6 hover:shadow-lg hover:border-[#251D1C]/40 transition-all duration-200 cursor-pointer"
                  onClick={() => handleStartChat(agent.agent_id)}
                  role="button"
                  tabIndex={0}
                  onKeyPress={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      handleStartChat(agent.agent_id);
                    }
                  }}
                  aria-label={`Start chat with ${displayName}`}
                >
                  <div className="flex items-start gap-4 mb-4">
                    <div className="flex-shrink-0 w-12 h-12 rounded-full bg-[#EEEAE7]/20 flex items-center justify-center text-lg font-medium text-[#443C3C]">
                      {initials}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-xl font-semibold text-gray-900 mb-1 truncate">
                        {displayName}
                      </h3>
                      {specialty && (
                        <p className="text-sm text-gray-600 truncate">{specialty}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                    <Badge variant={agent.is_active ? "success" : "default"} size="sm">
                      {agent.is_active ? "Active" : "Inactive"}
                    </Badge>
                    <Button variant="primary" size="sm" onClick={(e) => {
                      e.stopPropagation();
                      handleStartChat(agent.agent_id);
                    }}>
                      Start Chat
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="text-center mt-12">
          <a
            href="/admin/agents"
            className="text-gray-600 hover:text-[#251D1C] underline text-sm transition-colors duration-200"
          >
            Admin Panel
          </a>
        </div>
      </div>
    </div>
  );
}
