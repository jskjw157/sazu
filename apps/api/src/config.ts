/** Secrets never appear in configuration errors or logs. */
export interface Config {
  publicToken: string; internalToken: string; pythonBaseUrl: string;
  databaseUrl: string; timeoutMs: number; maxInFlight: number; rateLimit: number;
  host: string; port: number;
}
function integer(value: string | undefined, fallback: number, lo: number, hi: number): number {
  if (value === undefined) return fallback;
  if (!/^[0-9]+$/.test(value)) throw new Error('Invalid service configuration');
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < lo || n > hi) throw new Error('Invalid service configuration');
  return n;
}
export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  try {
    const publicToken = env.RESEARCH_API_TOKEN ?? '';
    const internalToken = env.CALCULATOR_TOKEN ?? '';
    if (env.SAZU_MODE !== 'research' || !/^[a-f0-9]{64}$/.test(publicToken)
        || !/^[a-f0-9]{64}$/.test(internalToken) || publicToken === internalToken) throw Error();
    const upstream = new URL(env.PYTHON_BASE_URL ?? '');
    if (!['http:', 'https:'].includes(upstream.protocol)
        || !['calculator', '127.0.0.1', 'localhost', '[::1]'].includes(upstream.hostname)
        || upstream.username || upstream.password || upstream.search || upstream.hash
        || upstream.pathname !== '/') throw Error();
    const databaseUrl = env.DATABASE_URL ?? '';
    const db = new URL(databaseUrl);
    if (!['postgres:', 'postgresql:'].includes(db.protocol) || !db.hostname) throw Error();
    const host = env.HOST ?? '127.0.0.1';
    if (!['127.0.0.1', '0.0.0.0', '::1'].includes(host)) throw Error();
    return Object.freeze({publicToken, internalToken, pythonBaseUrl:upstream.origin, databaseUrl,
      timeoutMs:integer(env.PYTHON_TIMEOUT_MS,3000,25,30000),
      maxInFlight:integer(env.MAX_IN_FLIGHT,32,1,64),
      rateLimit:integer(env.RATE_LIMIT_PER_MINUTE,120,1,10000),
      host,port:integer(env.PORT,3000,1,65535)});
  } catch { throw new Error('Invalid service configuration'); }
}
