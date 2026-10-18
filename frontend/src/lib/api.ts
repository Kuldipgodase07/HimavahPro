// Thin typed-ish API client. Permission errors surface as ApiError(403); the server is the source of truth.
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
const TOKEN_KEY = 'hv.token'
export const tokenStore = {
  get: () => { try { return sessionStorage.getItem(TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t: string, remember: boolean) => { try { sessionStorage.setItem(TOKEN_KEY, t); remember ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ } },
  clear: () => { try { sessionStorage.removeItem(TOKEN_KEY); localStorage.removeItem(TOKEN_KEY) } catch { /* noop */ } },
}
function detailText(d: unknown): string {
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => (x?.msg ? `${(x.loc ?? []).slice(1).join('.')}: ${x.msg}` : String(x))).join('; ')
  return 'Request failed'
}
export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = tokenStore.get()
  let res: Response
  try {
    res = await fetch(path, { method: opts.method ?? 'GET', headers: { ...(opts.body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: opts.body ? JSON.stringify(opts.body) : undefined })
  } catch { throw new ApiError(0, 'Cannot reach the HimavahPro API. Check your connection or that the backend is running.') }
  if (res.status === 401 && token && !path.startsWith('/api/auth/')) { tokenStore.clear(); window.dispatchEvent(new Event('hv:unauthorised')) }
  if (!res.ok) { let d: unknown; try { d = (await res.json()).detail } catch { d = res.statusText } throw new ApiError(res.status, detailText(d)) }
  return (res.headers.get('content-type')?.includes('json') ? res.json() : res.text()) as Promise<T>
}
export async function download(path: string, filename: string) {
  const token = tokenStore.get()
  const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, 'Export failed')
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
}
