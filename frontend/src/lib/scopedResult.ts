export interface ScopedResult<T> {
  scopeKey: string;
  payload: T;
}

export function resultForScope<T>(
  result: ScopedResult<T> | null,
  scopeKey: string,
): T | null {
  return result?.scopeKey === scopeKey ? result.payload : null;
}

export function isLatestRequest(
  requestGeneration: number,
  latestGeneration: number,
): boolean {
  return requestGeneration === latestGeneration;
}
