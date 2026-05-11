export const NEW_THREAD_PATHNAME = "/workspace/chats/new";
export const CHAT_DRAFT_QUERY_KEY = "draft";

export function isNewThreadPathname(pathname: string | null | undefined) {
  return pathname === NEW_THREAD_PATHNAME;
}

export function shouldResetNewThreadDraftKey(
  previousPathname: string | null,
  nextPathname: string | null,
) {
  if (previousPathname === null) {
    return false;
  }

  return (
    !isNewThreadPathname(previousPathname) && isNewThreadPathname(nextPathname)
  );
}

export function getLegacyDraftQueryValue(search: string | null | undefined) {
  const normalizedSearch =
    typeof search === "string"
      ? search.startsWith("?")
        ? search.slice(1)
        : search
      : undefined;
  const params = new URLSearchParams(normalizedSearch);
  const draft = params.get(CHAT_DRAFT_QUERY_KEY)?.trim() ?? null;
  return draft === "" ? null : draft;
}
