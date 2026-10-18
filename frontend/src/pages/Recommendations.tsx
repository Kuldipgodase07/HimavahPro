import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Search } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { Async, Badge, Button, Card, ConfBadge, DataTable, Drawer, Empty, Field, Input, Kv, Modal, PageHeader, Select, Skeleton, Stepper, StatusBadge, Tabs, Textarea, UrgBadge, useToast, type Col } from '../components/ui'
import { CHART, SUPPLY_LABEL, fmt, fmtDateTime, fmtHours } from '../lib/format'

export default function Recommendations() {
  const [sp, setSp] = useSearchParams()
  const [f, setF] = useState({ status: '', urgency: '', cls: '', confidence: '', q: sp.get('q') ?? '', post: '' })
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const s = useApi<any>(`/api/recommendations?${qs}`)
  const open = sp.get('open')
  const cols: Col<any>[] = [
    { key: 'id', label: 'ID', render: (r) => <b>{r.id}</b> },
    { key: 'post_id', label: 'Post', render: (r) => <>{r.post_id}<div className="text-[11px] text-muted">{r.post_name}</div></> },
    { key: 'qty', label: 'Supply & quantity', render: (r) => <>{SUPPLY_LABEL[r.supply_class]}<div className="num text-[11px] text-muted">{fmt(r.qty)} {r.unit} · {r.transport_mode}</div></> },
    { key: 'urgency', label: 'Urgency', render: (r) => <UrgBadge u={r.urgency} /> },
    { key: 'confidence', label: 'Confidence', render: (r) => <div className="flex flex-col items-start gap-1"><ConfBadge c={r.confidence} />{r.mandatory_review && <Badge tone="crit">Mandatory review</Badge>}</div> },
    { key: 'eta_h', label: 'Est. timing', align: 'right', render: (r) => (r.eta_h ? fmtHours(r.eta_h) : '—') },
    { key: 'status', label: 'Status', render: (r) => <StatusBadge s={r.status} /> },
  ]
  return (
    <>
      <PageHeader title="Supply Recommendations" sub="The AI recommends; authorised people decide. Dispatch is simulated." />
      <Async state={s}>{(d) => (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">{['Pending Review', 'Info Requested', 'Approved', 'Simulated Dispatch', 'Completed', 'Rejected', 'Draft'].map((k) => d.counts[k] ? <button key={k} onClick={() => setF({ ...f, status: f.status === k ? '' : k })} aria-pressed={f.status === k} className={`rounded-full border px-3 py-1 text-xs font-medium ${f.status === k ? 'border-deep bg-deep text-white' : 'border-line bg-white'}`}>{k} · {d.counts[k]}</button> : null)}</div>
          <Card pad={false}>
            <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
              <label className="relative min-w-[200px] flex-1"><span className="sr-only">Search</span><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden /><Input className="pl-9" placeholder="Search ID, post or reason" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></label>
              <Select aria-label="Urgency" className="w-auto" value={f.urgency} onChange={(e) => setF({ ...f, urgency: e.target.value })}><option value="">All urgency</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option></Select>
              <Select aria-label="Supply class" className="w-auto" value={f.cls} onChange={(e) => setF({ ...f, cls: e.target.value })}><option value="">All classes</option>{Object.entries(SUPPLY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
              <Select aria-label="Confidence" className="w-auto" value={f.confidence} onChange={(e) => setF({ ...f, confidence: e.target.value })}><option value="">All confidence</option><option>High</option><option>Medium</option><option>Low</option></Select>
              <Input aria-label="Affected post" className="w-36" placeholder="Post e.g. POST-K04" value={f.post} onChange={(e) => setF({ ...f, post: e.target.value.toUpperCase() })} />
            </div>
            <DataTable rowKey={(r) => r.id} cols={cols} rows={d.items} onRow={(r) => setSp({ open: r.id })} empty={<Empty title="No recommendations match" hint="Adjust the filters, or run a what-if scenario to create drafts." />} />
          </Card>
        </div>)}</Async>
      <DetailDrawer id={open} onClose={() => setSp({})} onChanged={() => s.reload()} perms={s.data?.perms} />
    </>
  )
}

function DetailDrawer({ id, onClose, onChanged, perms }: { id: string | null; onClose: () => void; onChanged: () => void; perms: any }) {
  const d = useApi<any>(id ? `/api/recommendations/${id}` : null, [id]); const ex = useApi<any>(id ? `/api/recommendations/${id}/explanation` : null, [id])
  const [tab, setTab] = useState<'overview' | 'why' | 'history'>('overview'); const [dlg, setDlg] = useState<null | 'approve' | 'edit' | 'reject' | 'info'>(null)
  useEffect(() => setTab('overview'), [id])
  const toast = useToast(); const [busy, setBusy] = useState(false)
  const reload = () => { d.reload(); ex.reload(); onChanged() }
  async function post(path: string, ok: string) { setBusy(true); try { await api(path, { method: 'POST' }); toast('success', ok); reload() } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Failed') } finally { setBusy(false) } }
  const r = d.data?.item
  return (
    <Drawer open={!!id} onClose={onClose} width="max-w-2xl" title={r ? `${r.id} · ${r.post_id} ${r.post_name}` : 'Recommendation'}>
      <Async state={d}>{(x) => { const r = x.item; const ev = r.evidence ?? {}; const plan = r.plan ?? {}; const open = ['Pending Review', 'Info Requested'].includes(r.status); return (
        <div className="space-y-4 text-[13px]">
          <Stepper flow={x.flow} current={r.status} />
          <div className="flex flex-wrap items-center gap-2"><StatusBadge s={r.status} /><UrgBadge u={r.urgency} /><ConfBadge c={r.confidence} />{r.mandatory_review && <Badge tone="crit">Mandatory human review</Badge>}</div>
          {r.mandatory_review && open && <div role="alert" className="flex gap-2 rounded-lg border border-[#f0c4c4] bg-[#fbe3e3] p-2.5 text-crit-ink"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><span>Low confidence or no feasible route. You must acknowledge the limitations before approving.</span></div>}
          <Tabs tabs={[{ id: 'overview', label: 'Overview' }, { id: 'why', label: 'Why this recommendation?' }, { id: 'history', label: 'Decision history' }]} value={tab} onChange={setTab} />
          {tab === 'overview' && <div className="space-y-4">
            <div className="rounded-lg bg-lilac-soft p-3"><div className="text-xs text-muted">Proposed</div><div className="num text-xl font-bold text-deep">{fmt(r.qty)} {r.unit} {SUPPLY_LABEL[r.supply_class]}</div>{r.original_qty && <div className="text-xs text-muted">Originally proposed {fmt(r.original_qty)} {r.unit} (edited by a human)</div>}<p className="mt-2 text-gray">{r.reason}</p></div>
            <div><h3 className="mb-1 font-semibold">Forecast & stock-risk evidence</h3><div className="grid grid-cols-2 gap-x-4"><Kv k="Days of supply" v={ev.dos != null ? `${ev.dos} d` : '—'} /><Kv k="Stockout (P50 / P90)" v={`${fmtHours(ev.tts_p50_h)} / ${fmtHours(ev.tts_earliest_h)}`} /><Kv k="Usable stock" v={ev.usable != null ? `${fmt(ev.usable)} ${ev.unit}` : '—'} /><Kv k="Inbound counted" v={`${fmt(ev.inbound_qty ?? 0)} ${r.unit}`} /><Kv k="Time margin" v={ev.margin_h != null ? `${ev.margin_h > 0 ? '+' : ''}${ev.margin_h} h` : '—'} /><Kv k="Forecast confidence" v={ev.forecast_confidence ?? '—'} /></div></div>
            <div><h3 className="mb-1 font-semibold">Route reliability & transport</h3>{plan.mode ? <div className="rounded-lg border border-line p-3"><div className="flex items-center justify-between"><b className="capitalize">{plan.label ?? plan.mode}</b><Badge tone="purple" icon={false}>{r.transport_mode}</Badge></div><p className="mt-1 text-xs text-muted">{plan.nodes?.join(' → ')}</p><div className="mt-1 grid grid-cols-3 gap-2 text-center"><div><div className="num font-bold">{plan.time_h} h</div><div className="text-[11px] text-muted">travel</div></div><div><div className="num font-bold">{(plan.reliability * 100).toFixed(0)}%</div><div className="text-[11px] text-muted">reliability</div></div><div><div className="num font-bold">{fmtHours(ev.eta_h)}</div><div className="text-[11px] text-muted">est. total</div></div></div>{ev.closed_routes?.length > 0 && <p className="mt-2 text-xs text-orange-ink">Closed segments excluded: {ev.closed_routes.join(', ')}</p>}</div> : <p className="rounded-lg bg-[#fbe3e3] p-3 text-crit-ink">No feasible road or air route in the current network state.</p>}</div>
            {r.alternatives.length > 0 && <div><h3 className="mb-1 font-semibold">Alternative plans</h3><ul className="space-y-1.5">{r.alternatives.map((a: any, i: number) => <li key={i} className="rounded-lg border border-line p-2.5"><div className="flex justify-between"><b>{a.label}</b><span className="num text-xs">{a.time_h} h · {(a.reliability * 100).toFixed(0)}%</span></div><p className="text-xs text-muted">{a.tradeoff}</p></li>)}</ul></div>}
            <div><h3 className="mb-1 font-semibold">Confidence & limitations</h3><ul className="list-disc space-y-0.5 pl-4 text-gray">{r.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul></div>
            <div className="grid grid-cols-2 gap-x-4"><Kv k="Model" v={r.model_version.split(' (')[0]} /><Kv k="Data as of" v={fmtDateTime(r.data_as_of)} /><Kv k="Origin" v={r.origin} />{r.convoy_id && <Kv k="Simulated convoy" v={r.convoy_id} />}{r.decided_by && <Kv k="Decided by" v={r.decided_by} />}{r.decision_reason && <Kv k="Reason" v={r.decision_reason} />}</div>
          </div>}
          {tab === 'why' && <Why ex={ex} />}
          {tab === 'history' && <ol className="space-y-2">{x.history.map((h: any, i: number) => <li key={i} className="rounded-lg border border-line p-2.5"><div className="flex justify-between"><b>{h.action}</b><span className="text-xs text-muted">{fmtDateTime(h.ts)}</span></div><div className="text-xs text-muted">{h.actor} · {h.from} → {h.to}</div>{h.reason && <p className="mt-1 text-gray">“{h.reason}”</p>}{h.detail?.qty_to && <p className="text-xs text-gray">Quantity {h.detail.qty_from} → {h.detail.qty_to}</p>}</li>)}</ol>}
          <div className="sticky bottom-0 -mx-5 -mb-5 flex flex-wrap gap-2 border-t border-line bg-white px-5 py-3">
            {r.status === 'Draft' && perms?.submit && <Button variant="primary" loading={busy} onClick={() => post(`/api/recommendations/${r.id}/submit`, 'Submitted for review.')}>Submit for review</Button>}
            {open && perms?.decide && <><Button variant="primary" onClick={() => setDlg('approve')}>Approve</Button><Button onClick={() => setDlg('edit')}>Edit and Approve</Button><Button onClick={() => setDlg('info')}>Request More Information</Button><Button variant="danger" onClick={() => setDlg('reject')}>Reject</Button></>}
            {r.status === 'Info Requested' && perms?.submit && <Button onClick={() => setDlg('info')}>Provide information</Button>}
            {r.status === 'Approved' && perms?.dispatch && <Button variant="primary" loading={busy} onClick={() => post(`/api/recommendations/${r.id}/dispatch`, 'Simulated dispatch started (fictional convoy; no real system).')}>Start simulated dispatch</Button>}
            {r.status === 'Simulated Dispatch' && perms?.dispatch && <Button variant="primary" loading={busy} onClick={() => post(`/api/recommendations/${r.id}/complete`, 'Delivery recorded; inventory updated.')}>Mark simulated delivery complete</Button>}
            {open && !perms?.decide && <p className="text-xs text-muted">Your role cannot decide on recommendations.</p>}
          </div>
          <DecisionDialog kind={dlg} r={r} onClose={() => setDlg(null)} onDone={reload} />
        </div>) }}</Async>
    </Drawer>
  )
}

function Why({ ex }: { ex: any }) {
  if (!ex.data) return <Skeleton className="h-60" />
  const e = ex.data
  return (
    <div className="space-y-4">
      <p className="rounded-lg bg-[#eceef3] p-2 text-[11px] text-gray">{e.method}</p>
      <div><h3 className="mb-1 font-semibold">Reasons</h3><ul className="list-disc space-y-1 pl-4">{e.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>
      {e.forecast_drivers.length > 0 && <div><h3 className="mb-1 font-semibold">Forecast driver breakdown</h3><div className="h-40"><ResponsiveContainer><BarChart data={e.forecast_change?.available ? e.forecast_change.components.map((c: any) => ({ k: c.driver, v: c.pct_of_prior })) : []} layout="vertical" margin={{ left: 40 }}><CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" fontSize={10} unit="%" /><YAxis type="category" dataKey="k" fontSize={11} width={130} /><Tooltip formatter={(v: any) => `${Number(v).toFixed(1)}%`} /><Bar dataKey="v" name="Change vs 3 days ago" fill={CHART.teal} radius={[0, 3, 3, 0]} /></BarChart></ResponsiveContainer></div><p className="text-[11px] text-muted">{e.forecast_change?.method}</p></div>}
      {e.route_drivers.length > 0 && <div><h3 className="mb-1 font-semibold">Route-risk drivers</h3>{e.route_drivers.map((r: any) => <div key={r.route_id} className="mb-1 rounded-lg border border-line p-2"><b>{r.route_id}</b> · RRI {r.rri ?? '—'} <span className="text-muted">{r.explanation}</span></div>)}</div>}
      <div><h3 className="mb-1 font-semibold">Counterfactuals (calculated)</h3>{e.counterfactuals.length === 0 ? <p className="text-muted">None available.</p> : e.counterfactuals.map((c: any, i: number) => <div key={i} className="mb-1.5 rounded-lg border border-line p-2.5"><b>{c.question}</b><p>{c.result}</p><p className="text-[11px] text-muted">{c.method}</p></div>)}</div>
      <div><h3 className="mb-1 font-semibold">Assumptions</h3><ul className="list-disc space-y-0.5 pl-4 text-gray">{e.assumptions.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul></div>
    </div>
  )
}

function DecisionDialog({ kind, r, onClose, onDone }: { kind: null | 'approve' | 'edit' | 'reject' | 'info'; r: any; onClose: () => void; onDone: () => void }) {
  const toast = useToast(); const [reason, setReason] = useState(''); const [qty, setQty] = useState(''); const [mode, setMode] = useState(''); const [ack, setAck] = useState(false); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { setReason(''); setQty(r ? String(r.qty) : ''); setMode(r?.transport_mode ?? ''); setAck(false); setErr('') }, [kind, r?.id])
  if (!kind || !r) return null
  const titles = { approve: 'Approve recommendation', edit: 'Edit and approve', reject: 'Reject recommendation', info: r.status === 'Info Requested' ? 'Provide information' : 'Request more information' }
  const needReason = kind !== 'approve'
  async function go() {
    setErr('')
    if (needReason && reason.trim().length < 10) { setErr('A reason of at least 10 characters is required.'); return }
    if (kind === 'edit' && Number(qty) === r.qty && mode === r.transport_mode) { setErr('Change the quantity or transport mode to override.'); return }
    if ((kind === 'approve' || kind === 'edit') && r.mandatory_review && !ack) { setErr('Acknowledge the low-confidence limitations to continue.'); return }
    setBusy(true)
    try {
      if (kind === 'info' && r.status === 'Info Requested') await api(`/api/recommendations/${r.id}/respond`, { method: 'POST', body: { message: reason } })
      else await api(`/api/recommendations/${r.id}/decision`, { method: 'POST', body: { action: { approve: 'approve', edit: 'edit_approve', reject: 'reject', info: 'request_info' }[kind as 'approve'], reason: reason || null, qty: kind === 'edit' ? Number(qty) : null, transport_mode: kind === 'edit' && mode !== r.transport_mode ? mode : null, acknowledged_low_confidence: ack } })
      toast('success', 'Decision recorded in the audit trail.'); onClose(); onDone()
    } catch (e) { setErr(e instanceof ApiError ? e.message : 'Failed') } finally { setBusy(false) }
  }
  const modes = ['road', 'air'].filter((m) => m === r.transport_mode || r.alternatives.some((a: any) => a.mode === m))
  return (
    <Modal open onClose={onClose} title={`${titles[kind]} · ${r.id}`} footer={<><Button onClick={onClose}>Cancel</Button><Button variant={kind === 'reject' ? 'danger' : 'primary'} loading={busy} onClick={go}>{kind === 'reject' ? 'Reject' : kind === 'info' ? 'Send' : 'Confirm'}</Button></>}>
      <div className="space-y-3 text-[13px]">
        <p className="text-gray">{fmt(r.qty)} {r.unit} {SUPPLY_LABEL[r.supply_class]} to {r.post_id} via {r.transport_mode}.</p>
        {kind === 'edit' && <div className="grid grid-cols-2 gap-3"><Field label={`Quantity (${r.unit})`}>{(i) => <Input id={i} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field><Field label="Transport mode">{(i) => <Select id={i} value={mode} onChange={(e) => setMode(e.target.value)}>{modes.map((m) => <option key={m}>{m}</option>)}</Select>}</Field></div>}
        <Field label={kind === 'approve' ? 'Note (optional)' : kind === 'info' ? (r.status === 'Info Requested' ? 'Information provided' : 'What information is needed?') : 'Reason (required)'}>{(i) => <Textarea id={i} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        {(kind === 'approve' || kind === 'edit') && r.mandatory_review && <label className="flex items-start gap-2 rounded-lg bg-[#fbe3e3] p-2.5 text-crit-ink"><input type="checkbox" className="mt-0.5 accent-[#D64545]" checked={ack} onChange={(e) => setAck(e.target.checked)} />I have reviewed the limitations and low-confidence warnings and accept responsibility for this decision.</label>}
        {kind === 'approve' && <p className="text-[11px] text-muted">Approval does not dispatch anything. It enables a <b>simulated</b> dispatch inside this prototype.</p>}
        {err && <p role="alert" className="font-medium text-crit-ink">{err}</p>}
      </div>
    </Modal>
  )
}
