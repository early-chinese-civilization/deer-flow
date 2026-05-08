import { getBackendBaseURL } from "@/core/config";

import {
  buildSkillHubInstallCheckRequest,
  buildSkillHubInstallRequest,
  buildSkillForkPackageRequest,
  buildSkillInstallUpdateConfirmRequest,
  buildSkillInstallUpdatePreviewRequest,
  getSkillHubInstallCheckFallbackError,
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
  skill_version_id?: number | null;
  action?: "created" | "updated" | "skipped" | null;
  success: boolean;
  message: string;
  recognized_as?: "fork" | "original" | null;
}

export interface SkillUploadResponse {
  results: SkillUploadResult[];
}

export interface SkillHubInstallCheckRequest {
  owner_user_id?: number | null;
  skill_definition_id?: number | null;
}

export interface SkillHubInstallCheckResponse {
  skill_name: string;
  exists: boolean;
  message: string;
}

export interface SkillHubInstallRequest {
  owner_user_id?: number | null;
  skill_definition_id?: number | null;
  overwrite?: boolean;
}

export interface SkillForkPackageRequest {
  owner_user_id?: number | null;
  skill_definition_id?: number | null;
}

export interface SkillPublishRequest {
  release_notes?: string | null;
}

export interface SkillInstallUpdateRequest {
  skill_install_id?: number | null;
  skill_version_id?: number | null;
}

export interface SkillUpdateAffectedAgent {
  id: number;
  name: string;
}

export interface SkillInstallUpdatePreview {
  skill_name: string;
  skill_install_id: number;
  current_skill_version_id: number;
  target_skill_version_id?: number | null;
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

function filenameFromContentDisposition(disposition: string | null) {
  if (!disposition) {
    return null;
  }
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }
  const plainMatch = /filename="?([^";]+)"?/i.exec(disposition);
  return plainMatch?.[1] ?? null;
}

export async function downloadSkillForkPackage(
  skillName: string,
  request: SkillForkPackageRequest,
): Promise<void> {
  const response = await fetch(
    ...buildSkillForkPackageRequest(getBackendBaseURL(), skillName, request),
  );

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(
      errorData.detail ??
        `Failed to download editable Skill copy: ${response.statusText}`,
    );
  }

  const blob = await response.blob();
  const filename =
    filenameFromContentDisposition(
      response.headers.get("Content-Disposition"),
    ) ?? `${skillName}-editable-copy.zip`;
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(objectUrl);
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
  request: SkillInstallUpdateRequest = {},
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
