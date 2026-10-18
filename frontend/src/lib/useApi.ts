import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'

export function useApi<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(!!path)
  const seq = useRef(0)
  const load = useCallback(async (silent = false) => {
    if (!path) return
    const my = ++seq.current
    if (!silent) setLoading(true)
    try { const d = await api<T>(path); if (my === seq.current) { setData(d); setError(null) } }
    catch (e) { if (my === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, String(e))) }
    finally { if (my === seq.current) setLoading(false) }
  }, [path])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [load, ...deps])
  return { data, error, loading, reload: () => load(true), setData }
}
