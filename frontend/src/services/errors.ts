export function getErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
