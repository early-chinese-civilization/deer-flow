export function resolveNextStreamThreadId(
  currentThreadId: string | null | undefined,
  nextThreadId: string | null | undefined,
): string | null {
  const normalizedCurrentThreadId = currentThreadId ?? null;
  const normalizedNextThreadId = nextThreadId ?? null;

  if (normalizedCurrentThreadId === normalizedNextThreadId) {
    return normalizedCurrentThreadId;
  }

  return normalizedNextThreadId;
}
