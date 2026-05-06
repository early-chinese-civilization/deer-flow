import type {
  SkillHubInstallCheckRequest,
  SkillHubInstallRequest,
} from "./api";

function buildSkillRoute(baseUrl: string, skillName: string, suffix: string) {
  return `${baseUrl}/api/skills/${encodeURIComponent(skillName)}/${suffix}`;
}

export function buildSkillHubInstallCheckRequest(
  baseUrl: string,
  skillName: string,
  request: SkillHubInstallCheckRequest,
): [string, RequestInit] {
  return [
    buildSkillRoute(baseUrl, skillName, "check-download"),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      credentials: "include",
    },
  ];
}

export function buildSkillHubInstallRequest(
  baseUrl: string,
  skillName: string,
  request: SkillHubInstallRequest,
): [string, RequestInit] {
  return [
    buildSkillRoute(baseUrl, skillName, "download"),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      credentials: "include",
    },
  ];
}

export function getSkillHubInstallCheckFallbackError(statusText: string) {
  return `Failed to check skill install: ${statusText}`;
}

export function getSkillHubInstallFallbackError(statusText: string) {
  return `Failed to install skill: ${statusText}`;
}
