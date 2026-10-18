import { useState } from 'react'
import { Plane, Truck } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { Async, Badge, Button, Card, DataTable, Drawer, Field, Kv, Modal, PageHeader, RiskBadge, Select, SimBanner, StatusBadge, Textarea, useToast, type Col } from '../components/ui'
import { SUPPLY_LABEL, fmt, fmtDateTime } from '../lib/format'

export default function Convoys() {
  const [status, setStatus] = useState(''); const s = useApi<any>(`/api/convoys?status=${status}`)
  const [open, setOpen] = useState<string | null>(null); const [inc, setInc] = useState<any>(null)
  const cols: Col<any>[] = [
    { key: 'id', label: 'Movement', render: (r) => <span className="flex items-center gap-1.5 font-semibold">{r.mode === 'air' ? <Plane className="h-4 w-4 text-lilac" aria-hidden /> : <Truck className="h-4 w-4 text-lilac" aria-hidden />}{r.id}</span> },
    { key: 'dest', label: 'Destination', render: (r) => <>{r.dest_post}<div className="text-[11px] text-muted">from {r.origin}</div></> },
    { key: 'cargo', label: 'Cargo', render: (r) => <>{SUPPLY_LABEL[r.supply_class]}<div className="num text-[11px] text-muted">{fmt(r.qty)} {r.unit}</div></> },
    { key: 'status', label: 'Status', render: (r) => <StatusBadge s={r.status} /> },
    { key: 'planned', label: 'Planned ETA', render: (r) => fmtDateTime(r.planned_eta) },
    { key: 'est', label: 'Estimated ETA', render: (r) => <span className={r.delay_h > 0.5 ? 'font-semibold text-orange-ink' : ''}>{fmtDateTime(r.est_eta)}{r.delay_h > 0.5 && <div className="text-[11px]">+{r.delay_h} h</div>}</span> },
    { key: 'route', label: 'Route status', render: (r) => <RiskBadge r={r.route_status} /> },
  ]
  return (
    <>
      <PageHeader title="Convoy & Movement Status" sub="Fictional movement records for demonstration" />
      <div className="mb-4"><SimBanner>{s.data?.simulation_label ?? 'Simulated movements: fictional identifiers; no real GPS/NavIC tracking.'}</SimBanner></div>
      <Async state={s}>{(d) => (
        <Card pad={false}>
          <div className="flex items-center gap-2 border-b border-line p-3"><Select aria-label="Status" className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{['Planned', 'In Transit', 'Delayed', 'Incident', 'Arrived'].map((x) => <option key={x}>{x}</option>)}</Select></div>
          <DataTable rowKey={(r) => r.id} cols={cols} rows={d.items} onRow={(r) => setOpen(r.id)} />
        </Card>)}</Async>
      <Drawer open={!!open} onClose={() => setOpen(null)} title={`Movement ${open}`}>
        {(() => { const c = s.data?.items.find((x: any) => x.id === open); if (!c) return null; return (
          <div className="space-y-4 text-[13px]">
            <div className="flex gap-2"><StatusBadge s={c.status} /><RiskBadge r={c.route_status} /><Badge tone="purple" icon={false}>Simulated</Badge></div>
            <div><Kv k="Cargo" v={`${fmt(c.qty)} ${c.unit} ${SUPPLY_LABEL[c.supply_class]}`} /><Kv k="Mode" v={c.mode} /><Kv k="Dispatched" v={fmtDateTime(c.dispatched_at)} /><Kv k="Planned ETA" v={fmtDateTime(c.planned_eta)} /><Kv k="Estimated ETA" v={fmtDateTime(c.est_eta)} />{c.rec_id && <Kv k="Recommendation" v={c.rec_id} />}</div>
            <div><h3 className="mb-1 font-semibold">Path</h3><p className="text-gray">{c.path.join(' → ')}</p><ul className="mt-1 flex flex-wrap gap-1">{c.segments.map((x: any) => <li key={x.route_id}><Badge tone={x.closed ? 'gray' : x.risk === 'low' ? 'ok' : x.risk === 'moderate' ? 'warn' : x.risk === 'elevated' ? 'orange' : 'crit'}>{x.route_id}</Badge></li>)}</ul></div>
            <div><h3 className="mb-1 font-semibold">Incidents (simulated)</h3>{c.incidents.length === 0 ? <p className="text-muted">None reported.</p> : <ul className="space-y-1.5">{c.incidents.map((i: any, k: number) => <li key={k} className="rounded-lg border border-line p-2"><b>{i.type}</b> <span className="text-xs text-muted">{fmtDateTime(i.ts)} · {i.actor}</span><p className="text-gray">{i.note}</p></li>)}</ul>}</div>
            {d(s) && c.status !== 'Arrived' && <Button onClick={() => setInc(c)}>Report simulated incident</Button>}
          </div>) })()}
      </Drawer>
      <Incident c={inc} onClose={() => setInc(null)} onDone={() => s.reload()} />
    </>
  )
  function d(st: typeof s) { return st.data?.can_report }
}

function Incident({ c, onClose, onDone }: { c: any; onClose: () => void; onDone: () => void }) {
  const [type, setType] = useState('Rockfall delay'); const [note, setNote] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false); const toast = useToast()
  if (!c) return null
  async function go() {
    if (note.trim().length < 5) { setErr('Describe the incident (at least 5 characters). Do not include personal data.'); return }
    setBusy(true)
    try { await api(`/api/convoys/${c.id}/incident`, { method: 'POST', body: { type, note } }); toast('success', 'Incident recorded (simulated) and audited.'); setNote(''); setErr(''); onClose(); onDone() } catch (e) { setErr(e instanceof ApiError ? e.message : 'Failed') } finally { setBusy(false) }
  }
  return <Modal open onClose={onClose} title={`Report incident · ${c.id}`} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={go}>Submit report</Button></>}>
    <div className="space-y-3"><Field label="Type">{(i) => <Select id={i} value={type} onChange={(e) => setType(e.target.value)}>{['Vehicle breakdown', 'Rockfall delay', 'Weather hold', 'Road blocked', 'Other'].map((x) => <option key={x}>{x}</option>)}</Select>}</Field><Field label="Details" error={err}>{(i) => <Textarea id={i} value={note} onChange={(e) => setNote(e.target.value)} />}</Field><p className="text-[11px] text-muted">Adds a simulated 3 h delay to the estimated arrival.</p></div></Modal>
}
