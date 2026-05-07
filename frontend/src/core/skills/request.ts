import type {
  SkillHubInstallCheckRequest,
  SkillHubInstallRequest,
  SkillInstallUpdateRequest,
  SkillForkPackageRequest,
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

export function buildSkillForkPackageRequest(
  baseUrl: string,
  skillName: string,
  request: SkillForkPackageRequest,
): [string, RequestInit] {
  return [
    buildSkillRoute(baseUrl, skillName, "fork-package"),
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
): [string, RequestInit] {
  return [
    buildSkillRoute(baseUrl, skillName, "update-install/preview"),
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

export function getSkillHubInstallCheckFallbackError(statusText: string) {
  return `Failed to check skill install: ${statusText}`;
}

export function getSkillHubInstallFallbackError(statusText: string) {
  return `Failed to install skill: ${statusText}`;
}
