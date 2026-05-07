export function shouldNotifyThreadStartBeforeEnsureThread(
  hasCurrentThreadId: boolean,
): boolean {
  return hasCurrentThreadId;
}

export function shouldShowOptimisticMessageBeforeEnsureThread(
  hasCurrentThreadId: boolean,
): boolean {
  return hasCurrentThreadId;
}
