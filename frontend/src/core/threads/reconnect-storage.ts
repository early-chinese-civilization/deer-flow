const LEGACY_STREAM_SUFFIX = "/stream";

type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

type RunReconnectStorage = {
  getItem(key: `lg:stream:${string}`): string | null;
  setItem(key: `lg:stream:${string}`, value: string): void;
  removeItem(key: `lg:stream:${string}`): void;
};

export function normalizeStoredRunId(
  runId: string | null | undefined,
): string | null {
  if (!runId) {
    return null;
  }

  const trimmed = runId.trim();
  if (!trimmed) {
    return null;
  }

  if (!trimmed.includes("/")) {
    return trimmed;
  }

  if (!trimmed.endsWith(LEGACY_STREAM_SUFFIX)) {
    return null;
  }

  const normalized = trimmed.slice(0, -LEGACY_STREAM_SUFFIX.length);
  return normalized && !normalized.includes("/") ? normalized : null;
}

export function createRunReconnectStorage(
  storage: StorageLike,
): RunReconnectStorage {
  const repairStoredValue = (key: `lg:stream:${string}`): string | null => {
    const rawValue = storage.getItem(key);
    const normalizedValue = normalizeStoredRunId(rawValue);

    if (rawValue === normalizedValue) {
      return normalizedValue;
    }

    if (normalizedValue === null) {
      storage.removeItem(key);
      return null;
    }

    storage.setItem(key, normalizedValue);
    return normalizedValue;
  };

  return {
    getItem(key) {
      return repairStoredValue(key);
    },
    setItem(key, value) {
      const normalizedValue = normalizeStoredRunId(value);
      if (normalizedValue === null) {
        storage.removeItem(key);
        return;
      }
      storage.setItem(key, normalizedValue);
    },
    removeItem(key) {
      storage.removeItem(key);
    },
  };
}

let sessionRunReconnectStorage: RunReconnectStorage | null = null;

export function getRunReconnectStorage(): RunReconnectStorage {
  // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing
  if (sessionRunReconnectStorage === null) {
    sessionRunReconnectStorage = createRunReconnectStorage(
      window.sessionStorage,
    );
  }
  return sessionRunReconnectStorage;
}
