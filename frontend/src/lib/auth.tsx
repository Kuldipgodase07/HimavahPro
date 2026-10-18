import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, tokenStore } from './api'

export interface Me { username: string; name: string; role: string; role_label: string; post_id: string | null; permissions: string[] }
interface AuthCtx { user: Me | null; ready: boolean; can: (p: string) => boolean; setSession: (token: string, user: Me, remember: boolean) => void; signOut: () => Promise<void> }
const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return }
    api<Me>('/api/auth/me').then(setUser).catch(() => tokenStore.clear()).finally(() => setReady(true))
  }, [])
  useEffect(() => { const h = () => setUser(null); window.addEventListener('hv:unauthorised', h); return () => window.removeEventListener('hv:unauthorised', h) }, [])
  const setSession = useCallback((token: string, u: Me, remember: boolean) => { tokenStore.set(token, remember); setUser(u) }, [])
  const signOut = useCallback(async () => { try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* ignore */ } tokenStore.clear(); setUser(null) }, [])
  const value = useMemo(() => ({ user, ready, setSession, signOut, can: (p: string) => !!user?.permissions.includes(p) }), [user, ready, setSession, signOut])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
