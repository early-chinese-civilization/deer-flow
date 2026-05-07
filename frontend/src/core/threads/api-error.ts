export class ThreadApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ThreadApiError";
    this.status = status;
  }
}

export function isThreadApiError(error: unknown): error is ThreadApiError {
  return error instanceof ThreadApiError;
}

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const error = await response.json().catch(() => ({ detail: fallback }));
  return error.detail ?? fallback;
}

export async function throwThreadApiError(
  response: Response,
  fallback: string,
): Promise<never> {
  throw new ThreadApiError(
    await readErrorDetail(response, fallback),
    response.status,
  );
}
