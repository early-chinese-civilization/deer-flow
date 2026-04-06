type WorkspaceNavMenuTranslations = {
  common: {
    settings: string;
  };
  workspace: {
    logout: string;
  };
};

export type WorkspaceNavMenuItem = {
  id: "settings" | "logout";
  label: string;
};

export function getWorkspaceNavMenuItems(
  translations: WorkspaceNavMenuTranslations,
): readonly [
  WorkspaceNavMenuItem & { id: "settings" },
  WorkspaceNavMenuItem & { id: "logout" },
] {
  return [
    {
      id: "settings",
      label: translations.common.settings,
    },
    {
      id: "logout",
      label: translations.workspace.logout,
    },
  ] as const;
}
