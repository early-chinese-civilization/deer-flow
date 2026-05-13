import { getBackendBaseURL } from "@/core/config";

import {
  buildSkillHubInstallRequest,
  buildSkillInstallUpdateConfirmRequest,
  buildSkillInstallUpdatePreviewRequest,
  getSkillHubInstallFallbackError,
} from "./request";
import type { Skill } from "./type";

export interface SkillUploadCheckResponse {
  filename: string;
  skill_name: string;
  package_version?: string | null;
  source_package_version?: string | null;
  existing_package_version?: string | null;
  existing_source_package_version?: string | null;
  platform_version?: number | null;
  same_version: boolean;
  exists: boolean;
  message: string;
  recognized_as?: "fork" | "original";
  fork_source_name?: string | null;
  fork_source_owner_display_name?: string | null;
  fork_source_platform_version?: number | null;
  unchanged_from_source?: boolean;
}

export interface SkillUploadResult {
  filename: string;
  skill_name?: string | null;
  package_version?: string | null;
  source_package_version?: string | null;
  platform_version?: number | null;
  skill_id?: string | null;
  version_number?: number | null;
  action?: "created" | "updated" | "skipped" | null;
  success: boolean;
  message: string;
  recognized_as?: "fork" | "original" | null;
}

export interface SkillUploadResponse {
  results: SkillUploadResult[];
}

export interface SkillHubInstallRequest {
  skill_id: string;
  version_number: number;
}

export interface SkillPublishRequest {
  skill_definition_id?: number | null;
  release_notes?: string | null;
}

export interface SkillInstallUpdateRequest {
  skill_install_id: number;
  skill_id: string;
  version_number: number;
}

export interface SkillManagementIdentity {
  skill_definition_id?: number | null;
  skill_install_id?: number | null;
}

export interface SkillUpdateAffectedAgent {
  id: number;
  name: string;
}

export interface SkillInstallUpdatePreview {
  skill_name: string;
  skill_install_id: number;
  skill_id?: string | null;
  version_number?: number | null;
  current_platform_version: number;
  target_platform_version?: number | null;
  update_available: boolean;
  status: "available" | "up_to_date" | "unavailable";
  message: string;
  release_notes?: string | null;
  published_at?: string | null;
  publisher?: string | null;
  source: string;
  affected_agents: SkillUpdateAffectedAgent[];
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

export async function enableSkill(
  skillName: string,
  enabled: boolean,
  identity: SkillManagementIdentity = {},
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        enabled,
        skill_definition_id: identity.skill_definition_id ?? null,
        skill_install_id: identity.skill_install_id ?? null,
      }),
      credentials: "include",
    },
  );
  return response.json();
}

export async function deleteSkill(
  skillName: string,
  identity: SkillManagementIdentity = {},
): Promise<void> {
  const url = new URL(
    `${getBackendBaseURL()}/api/skills/${encodeURIComponent(skillName)}`,
    "http://placeholder.local",
  );
  if (identity.skill_definition_id != null) {
    url.searchParams.set(
      "skill_definition_id",
      String(identity.skill_definition_id),
    );
  }
  if (identity.skill_install_id != null) {
    url.searchParams.set("skill_install_id", String(identity.skill_install_id));
  }
  const requestUrl = getBackendBaseURL()
    ? url.toString().replace("http://placeholder.local", "")
    : `${url.pathname}${url.search}`;
  const response = await fetch(requestUrl, {
    method: "DELETE",
    credentials: "include",
  });
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

export async function installSkillHubSkill(
  request: SkillHubInstallRequest,
): Promise<Skill> {
  const response = await fetch(
    ...buildSkillHubInstallRequest(getBackendBaseURL(), request),
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

export async function previewSkillInstallUpdate(
  skillName: string,
  skillInstallId?: number | null,
): Promise<SkillInstallUpdatePreview> {
  const response = await fetch(
    ...buildSkillInstallUpdatePreviewRequest(
      getBackendBaseURL(),
      skillName,
      skillInstallId,
    ),
  );

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ??
        `Failed to preview Skill update: ${response.statusText}`,
    );
  }

  return response.json() as Promise<SkillInstallUpdatePreview>;
}

export async function confirmSkillInstallUpdate(
  skillName: string,
  request: SkillInstallUpdateRequest,
): Promise<SkillInstallUpdatePreview> {
  const response = await fetch(
    ...buildSkillInstallUpdateConfirmRequest(
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
        `Failed to update installed Skill: ${response.statusText}`,
    );
  }

  return response.json() as Promise<SkillInstallUpdatePreview>;
}

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
