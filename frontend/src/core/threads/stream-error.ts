type RunCallbackMeta = {
  run_id: string;
  thread_id: string;
};

type PassiveStreamErrorOptions = {
  sendInFlight: boolean;
};

export function shouldSuppressPassiveStreamError(
  run: RunCallbackMeta | undefined,
  options: PassiveStreamErrorOptions,
): boolean {
  return run !== undefined && !options.sendInFlight;
}
