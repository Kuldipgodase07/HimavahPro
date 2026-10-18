import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff, Loader2, ShieldCheck, UserCog } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth, type Me } from '../lib/auth'
import { Logo } from '../components/Logo'
import { Button, Field, Input, SimBanner } from '../components/ui'

export default function SignIn() {
  const { user, setSession } = useAuth(); const nav = useNavigate(); const loc = useLocation()
  const [username, setU] = useState(''); const [password, setP] = useState(''); const [show, setShow] = useState(false); const [remember, setR] = useState(false)
  const [errs, setErrs] = useState<{ u?: string; p?: string; form?: string }>({}); const [busy, setBusy] = useState(false)
  const [challenge, setChallenge] = useState<string | null>(null); const [code, setCode] = useState(''); const [ok, setOk] = useState(false)
  const [roles, setRoles] = useState<{ role: string; label: string; description: string }[]>([])
  const [demoNotice, setDemoNotice] = useState('')
  useEffect(() => {
    api('/api/auth/demo-roles')
      .then((d) => {
        if (d && Array.isArray(d.roles)) {
          setRoles(d.roles)
          setDemoNotice(typeof d.notice === 'string' ? d.notice : '')
        } else {
          setRoles([])
        }
      })
      .catch(() => { setRoles([]) })
  }, [])
  const dest = (loc.state as any)?.from ?? '/app'
  if (user && !ok) return <Navigate to={dest} replace />
  const finish = (r: { token: string; user: Me }) => { setOk(true); setSession(r.token, r.user, remember); setTimeout(() => nav(dest, { replace: true }), 600) }
  async function submit(e: FormEvent) {
    e.preventDefault()
    const n: typeof errs = {}
    if (!username.trim()) n.u = 'Enter your email or username.'
    if (password.length < 1) n.p = 'Enter your password.'
    setErrs(n); if (n.u || n.p) return
    setBusy(true)
    try { const r = await api('/api/auth/login', { method: 'POST', body: { username, password } }); r.mfa_required ? setChallenge(r.challenge) : finish(r) }
    catch (err) { setErrs({ form: err instanceof ApiError ? err.message : 'Sign-in failed.' }) } finally { setBusy(false) }
  }
  async function verify(e: FormEvent) {
    e.preventDefault(); if (!/^\d{6}$/.test(code)) { setErrs({ form: 'Enter the 6-digit verification code.' }); return }
    setBusy(true); setErrs({})
    try { finish(await api('/api/auth/mfa', { method: 'POST', body: { challenge, code } })) } catch (err) { setErrs({ form: err instanceof ApiError ? err.message : 'Verification failed.' }); if (err instanceof ApiError && err.message.includes('expired')) setChallenge(null) } finally { setBusy(false) }
  }
  async function demo(role: string) {
    setBusy(true); setErrs({})
    try { finish(await api('/api/auth/demo-login', { method: 'POST', body: { role } })) } catch (err) { setErrs({ form: err instanceof ApiError ? err.message : 'Demo sign-in failed.' }) } finally { setBusy(false) }
  }
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col justify-between bg-deep p-8 text-white max-lg:hidden">
        <Logo light />
        <div><h1 className="text-3xl font-bold leading-tight">Predictive Logistics.<br />Strengthen Readiness.</h1>
          <p className="mt-3 max-w-md text-[#D8D4EC]">AI-driven intelligence for resilient supply chains and uninterrupted operations. Every recommendation is reviewed and decided by authorised people.</p>
          <p className="mt-6 text-sm font-semibold tracking-wide text-[#B9B5DB]">Predict | Prepare | Optimise | Assure</p></div>
        <p className="text-xs text-[#CFCBE6]">Hackathon prototype · synthetic data · not an operational system.</p>
      </div>
      <main className="flex items-center justify-center bg-white p-6">
        <div className="w-full max-w-md">
          <div className="mb-6 lg:hidden"><Logo /></div>
          <h2 className="text-2xl font-bold">Secure sign in</h2>
          <p className="mt-1 text-sm text-muted">Predictive Logistics Intelligence Platform</p>
          <div className="mt-4"><SimBanner>Demonstration authentication: no real identity infrastructure is used.</SimBanner></div>
          {errs.form && <div role="alert" className="mt-4 rounded-lg border border-[#f0c4c4] bg-[#fbe3e3] px-3 py-2 text-sm text-crit-ink">{errs.form}</div>}
          {ok ? <p role="status" className="mt-8 flex items-center gap-2 text-ok-ink"><ShieldCheck className="h-5 w-5" aria-hidden />Signed in. Opening the Command Centre…</p> : !challenge ? (
            <form onSubmit={submit} noValidate className="mt-5 space-y-4">
              <Field label="Email or username" error={errs.u}>{(id) => <Input id={id} autoComplete="username" value={username} onChange={(e) => setU(e.target.value)} aria-invalid={!!errs.u} placeholder="e.g. planner" />}</Field>
              <Field label="Password" error={errs.p}>{(id) => (
                <div className="relative"><Input id={id} type={show ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(e) => setP(e.target.value)} aria-invalid={!!errs.p} className="pr-10" />
                  <button type="button" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(!show)} className="absolute right-2 top-2 rounded p-1 text-muted hover:text-deep">{show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div>)}</Field>
              <label className="flex items-center gap-2 text-[13px] text-gray"><input type="checkbox" checked={remember} onChange={(e) => setR(e.target.checked)} className="h-4 w-4 accent-[#351A55]" />Remember this device (demo only)</label>
              <Button type="submit" variant="primary" className="w-full" loading={busy}>Continue</Button>
            </form>
          ) : (
            <form onSubmit={verify} noValidate className="mt-5 space-y-4">
              <p className="text-sm text-gray">Step 2 of 2: enter the 6-digit demonstration verification code (see README).</p>
              <Field label="Verification code">{(id) => <Input id={id} inputMode="numeric" maxLength={6} autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} data-autofocus placeholder="••••••" className="text-center text-lg tracking-[0.4em]" />}</Field>
              <div className="flex gap-2"><Button type="button" onClick={() => { setChallenge(null); setCode(''); setErrs({}) }}>Back</Button><Button type="submit" variant="primary" className="flex-1" loading={busy}>Verify and sign in</Button></div>
            </form>
          )}
          {!ok && !challenge && Array.isArray(roles) && roles.length > 0 && (
            <div className="mt-7">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted"><UserCog className="h-3.5 w-3.5" aria-hidden />Demo sign-in by role</div>
              <p className="mb-2 text-xs text-muted">{demoNotice} Skips the password and verification steps.</p>
              <ul className="space-y-1.5">{roles.map((r) => <li key={r.role}><button disabled={busy} onClick={() => demo(r.role)} className="group flex w-full items-center justify-between rounded-lg border border-line px-3 py-2 text-left hover:border-lilac hover:bg-lilac-soft disabled:opacity-50"><span><span className="block text-[13px] font-semibold">{r.label}</span><span className="block text-[11px] text-muted">{r.description}</span></span>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4 text-lilac group-hover:translate-x-0.5" aria-hidden />}</button></li>)}</ul>
            </div>)}
          <p className="mt-6 flex items-start gap-2 text-[11px] text-muted"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />Sessions are signed, time-limited and audited. Production deployments use an approved identity provider.</p>
          <Link to="/" className="mt-3 inline-block text-xs font-medium text-deep hover:underline">← Back to overview</Link>
        </div>
      </main>
    </div>
  )
}
