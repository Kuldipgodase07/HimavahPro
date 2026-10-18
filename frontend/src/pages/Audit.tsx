import { useState } from 'react'
import { ShieldCheck, ShieldAlert, Search } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { Async, Badge, Button, Card, DataTable, Drawer, Input, Kv, PageHeader, Pager, Select, useToast, type Col } from '../components/ui'
import { fmtDateTime } from '../lib/format'

export default function Audit() {
  const [q, setQ] = useState(''); const [action, setAction] = useState(''); const [outcome, setOutcome] = useState(''); const [page, setPage] = useState(1)
  const s = useApi<any>(`/api/audit?${new URLSearchParams({ q, action, outcome, page: String(page), page_size: '20' })}`)
  const [ver, setVer] = useState<any>(null); const [busy, setBusy] = useState(false); const [sel, setSel] = useState<any>(null); const toast = useToast()
  async function verify(tamper: boolean) { setBusy(true); try { setVer(await api(`/api/audit/verify?tamper_demo=${tamper}`, { method: 'POST' })); s.reload() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Failed') } finally { setBusy(false) } }
  const cols: Col<any>[] = [
    { key: 'ts', label: 'Timestamp', render: (r) => fmtDateTime(r.ts) }, { key: 'actor', label: 'Actor', render: (r) => <>{r.actor}<div className="text-[11px] text-muted">{r.role}</div></> },
    { key: 'action', label: 'Action', render: (r) => <code className="text-xs">{r.action}</code> }, { key: 'resource', label: 'Resource' },
    { key: 'outcome', label: 'Outcome', render: (r) => <Badge tone={r.outcome === 'success' ? 'ok' : r.outcome === 'denied' ? 'orange' : 'crit'}>{r.outcome}</Badge> },
  ]
  return (
    <>
      <PageHeader title="Audit & Governance" sub="Hash-chained record of consequential actions in this prototype" />
      <Async state={s}>{(d) => (
        <div className="space-y-4">
          <Card title="Integrity verification" action={d.can_verify ? <div className="flex gap-2"><Button size="sm" variant="primary" loading={busy} onClick={() => verify(false)}>Verify chain</Button><Button size="sm" loading={busy} onClick={() => verify(true)}>Demonstrate tamper detection</Button></div> : <Badge tone="gray" icon={false}>Verification requires the Auditor role</Badge>}>
            {ver ? <div role="status" className={`flex items-start gap-3 rounded-lg p-3 ${ver.status === 'intact' ? 'bg-[#e9f6e3] text-ok-ink' : 'bg-[#fbe3e3] text-crit-ink'}`}>{ver.status === 'intact' ? <ShieldCheck className="h-5 w-5" aria-hidden /> : <ShieldAlert className="h-5 w-5" aria-hidden />}<div><b>{ver.status === 'intact' ? 'Chain intact' : 'Tampering detected'}{ver.simulated && ' (simulated edit on an in-memory copy; stored data unchanged)'}</b><p className="text-sm">{ver.events_checked} events checked{ver.broken_at && ` · first break at event #${ver.broken_at}: ${ver.reason}`}.</p><p className="font-mono text-[11px] break-all">head {ver.head_hash}</p></div></div> : <p className="text-sm text-muted">Status: not verified in this session. Each event’s SHA-256 hash covers the previous hash plus its own content.</p>}
            <p className="mt-2 text-[11px] text-muted"><b>Limitations:</b> a hash chain alone is not a complete tamper-proof system. Production deployments need protected append-only storage, access controls, key management, monitoring and independent verification.</p></Card>
          <Card pad={false}>
            <div className="flex flex-wrap gap-2 border-b border-line p-3"><label className="relative min-w-[200px] flex-1"><span className="sr-only">Search audit</span><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden /><Input className="pl-9" placeholder="Search actor, action, resource or detail" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></label>
              <Select aria-label="Action" className="w-auto" value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }}><option value="">All actions</option>{d.actions.map((a: string) => <option key={a}>{a}</option>)}</Select>
              <Select aria-label="Outcome" className="w-auto" value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1) }}><option value="">All outcomes</option><option>success</option><option>denied</option><option>failure</option></Select></div>
            <DataTable rowKey={(r) => r.id} cols={cols} rows={d.items} onRow={setSel} empty={<p className="py-10 text-center text-sm text-muted">No audit events match.</p>} />
            <Pager page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} />
          </Card>
        </div>)}</Async>
      <Drawer open={!!sel} onClose={() => setSel(null)} title={sel ? `Event #${sel.id}` : ''}>{sel && <div className="space-y-3 text-[13px]"><Kv k="Time" v={fmtDateTime(sel.ts)} /><Kv k="Actor" v={sel.actor} /><Kv k="Role" v={sel.role} /><Kv k="Action" v={sel.action} /><Kv k="Resource" v={sel.resource} /><Kv k="Outcome" v={sel.outcome} /><div><h3 className="font-semibold">Detail</h3><pre className="mt-1 overflow-auto rounded-lg bg-bg p-3 text-xs">{JSON.stringify(sel.detail, null, 2)}</pre></div><div><h3 className="font-semibold">Hash chain</h3><p className="break-all font-mono text-[11px] text-muted">prev {sel.prev_hash}<br />hash {sel.hash}</p></div></div>}</Drawer>
    </>
  )
}
