/** Agent display utilities for consistent agent name formatting across the app. */

import type { Agent } from "@/lib/types/agent";

/**
 * Get display name for an agent.
 * Priority: agent_display_name > clinic_display_name > agent_id
 */
export function getAgentDisplayName(agent: Agent | null | undefined): string {
  if (!agent) {
    return "Unknown Agent";
  }

  const profileName = agent.config?.profile?.agent_display_name ?? agent.config?.profile?.doctor_display_name;
  if (profileName) {
    return profileName;
  }

  if (agent.config?.profile?.clinic_display_name) {
    return agent.config.profile.clinic_display_name;
  }

  return agent.agent_id;
}

/**
 * Get short display name for compact display (first 20 characters).
 */
export function getAgentShortName(agent: Agent | null | undefined): string {
  const fullName = getAgentDisplayName(agent);
  if (fullName.length <= 20) {
    return fullName;
  }
  return `${fullName.substring(0, 17)}...`;
}

/**
 * Get agent initials for avatar fallback.
 * Extracts first letter of each word (up to 2 letters).
 */
export function getAgentInitials(agent: Agent | null | undefined): string {
  const name = getAgentDisplayName(agent);
  const words = name.trim().split(/\s+/);
  
  if (words.length === 0) {
    return "?";
  }

  if (words.length === 1) {
    return words[0].charAt(0).toUpperCase();
  }

  // Take first letter of first two words
  return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
}

/**
 * Get agent specialty for display.
 */
export function getAgentSpecialty(agent: Agent | null | undefined): string | null {
  if (!agent?.config?.profile?.specialty) {
    return null;
  }
  return agent.config.profile.specialty;
}

/**
 * Get clinic display name.
 */
export function getClinicDisplayName(agent: Agent | null | undefined): string | null {
  if (!agent?.config?.profile?.clinic_display_name) {
    return null;
  }
  return agent.config.profile.clinic_display_name;
}

/**
 * Get agent profile display name.
 */
export function getAgentProfileDisplayName(agent: Agent | null | undefined): string | null {
  const name = agent?.config?.profile?.agent_display_name ?? agent?.config?.profile?.doctor_display_name;
  return name ?? null;
}
