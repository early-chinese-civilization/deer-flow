import type { SkillHubInstallRequest, SkillInstallUpdateRequest } from "./api";

function buildSkillRoute(baseUrl: string, skillName: string, suffix: string) {
  return `${baseUrl}/api/skills/${encodeURIComponent(skillName)}/${suffix}`;
}

export function buildSkillHubInstallRequest(
  baseUrl: string,
  request: SkillHubInstallRequest,
): [string, RequestInit] {
  return [
    `${baseUrl}/api/skills/install`,
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

export function buildSkillInstallUpdatePreviewRequest(
  baseUrl: string,
  skillName: string,
  skillInstallId?: number | null,
): [string, RequestInit] {
  const url = new URL(
    buildSkillRoute(baseUrl, skillName, "update-install/preview"),
    "http://placeholder.local",
  );
  if (skillInstallId != null) {
    url.searchParams.set("skill_install_id", String(skillInstallId));
  }
  const pathnameWithQuery = baseUrl
    ? url.toString().replace("http://placeholder.local", "")
    : `${url.pathname}${url.search}`;
  return [
    pathnameWithQuery,
    {
      method: "GET",
      credentials: "include",
    },
  ];
}

export function buildSkillInstallUpdateConfirmRequest(
  baseUrl: string,
  skillName: string,
  request: SkillInstallUpdateRequest,
): [string, RequestInit] {
  return [
    buildSkillRoute(baseUrl, skillName, "update-install"),
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

export function getSkillHubInstallFallbackError(statusText: string) {
  return `Failed to install skill: ${statusText}`;
}
