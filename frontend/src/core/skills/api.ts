import { getBackendBaseURL } from "@/core/config";

import {
  buildSkillHubInstallCheckRequest,
  buildSkillHubInstallRequest,
  getSkillHubInstallCheckFallbackError,
  getSkillHubInstallFallbackError,
} from "./request";
import type { Skill } from "./type";

export interface SkillUploadCheckResponse {
  filename: string;
  skill_name: string;
  package_version?: string | null;
  existing_package_version?: string | null;
  same_version: boolean;
  exists: boolean;
  message: string;
}

export interface SkillUploadResult {
  filename: string;
  skill_name?: string | null;
  package_version?: string | null;
  action?: "created" | "updated" | "skipped" | null;
  success: boolean;
  message: string;
}

export interface SkillUploadResponse {
  results: SkillUploadResult[];
}

export interface SkillHubInstallCheckRequest {
  owner_user_id?: number | null;
}

export interface SkillHubInstallCheckResponse {
  skill_name: string;
  exists: boolean;
  message: string;
}

export interface SkillHubInstallRequest {
  owner_user_id?: number | null;
  overwrite?: boolean;
}

export interface SkillPublishRequest {
  release_notes?: string | null;
}

export async function loadSkills() {
  const response = await fetch(`${getBackendBaseURL()}/api/skills`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load skills: ${response.statusText}`);
  }
  const json = (await response.json()) as { skills: Skill[] };
  return json.skills;
}

export async function enableSkill(skillName: string, enabled: boolean) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        enabled,
      }),
      credentials: "include",
    },
  );
  return response.json();
}

export async function deleteSkill(skillName: string): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}`,
    {
      method: "DELETE",
      credentials: "include",
    },
  );
  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ?? `Failed to delete skill: ${response.statusText}`,
    );
  }
}

export async function checkSkillUpload(
  file: File,
): Promise<SkillUploadCheckResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/check-upload`,
    {
      method: "POST",
      body: formData,
      credentials: "include",
    },
  );

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ??
        `Failed to check skill upload: ${response.statusText}`,
    );
  }

  return response.json() as Promise<SkillUploadCheckResponse>;
}

export async function uploadSkills(
  files: File[],
  overwriteNames: string[],
): Promise<SkillUploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  for (const overwriteName of overwriteNames) {
    formData.append("overwrite_names", overwriteName);
  }

  const response = await fetch(`${getBackendBaseURL()}/api/skills/uploads`, {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ?? `Failed to upload skills: ${response.statusText}`,
    );
  }

  return response.json() as Promise<SkillUploadResponse>;
}

export async function checkSkillHubInstall(
  skillName: string,
  request: SkillHubInstallCheckRequest,
): Promise<SkillHubInstallCheckResponse> {
  const response = await fetch(
    ...buildSkillHubInstallCheckRequest(
      getBackendBaseURL(),
      skillName,
      request,
    ),
  );

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ??
        getSkillHubInstallCheckFallbackError(response.statusText),
    );
  }

  return response.json() as Promise<SkillHubInstallCheckResponse>;
}

export async function installSkillHubSkill(
  skillName: string,
  request: SkillHubInstallRequest,
): Promise<Skill> {
  const response = await fetch(
    ...buildSkillHubInstallRequest(getBackendBaseURL(), skillName, request),
  );

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ?? getSkillHubInstallFallbackError(response.statusText),
    );
  }

  return response.json() as Promise<Skill>;
}

export const checkSkillDownload = checkSkillHubInstall;
export const downloadSkill = installSkillHubSkill;

export async function publishSkill(
  skillName: string,
  request: SkillPublishRequest = {},
): Promise<Skill> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}/publish`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      credentials: "include",
    },
  );

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ?? `Failed to publish skill: ${response.statusText}`,
    );
  }

  return response.json() as Promise<Skill>;
}

export interface InstallSkillRequest {
  thread_id: string;
  path: string;
}

export interface InstallSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
}

export async function installSkill(
  request: InstallSkillRequest,
): Promise<InstallSkillResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/install`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    credentials: "include",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const errorMessage =
      errorData.detail ?? `HTTP ${response.status}: ${response.statusText}`;
    return {
      success: false,
      skill_name: "",
      message: errorMessage,
    };
  }

  return response.json();
}
