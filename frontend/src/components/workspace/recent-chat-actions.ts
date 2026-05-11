export type RecentChatMenuAction = "rename" | "share" | "export" | "delete";

export const RECENT_CHAT_MENU_ACTIONS: readonly RecentChatMenuAction[] = [
  "rename",
  "export",
  "delete",
];

export function isRecentChatMenuActionVisible(
  action: RecentChatMenuAction,
): boolean {
  return RECENT_CHAT_MENU_ACTIONS.includes(action);
}
