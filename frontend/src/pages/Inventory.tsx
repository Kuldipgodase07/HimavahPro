import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, Search } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { Async, Badge, Button, Card, ConfBadge, Confirm, DataTable, Drawer, Field, HealthBadge, Input, Kv, PageHeader, Pager, Select, Textarea, useToast, type Col } from '../components/ui'
import { SUPPLY_LABEL, fmt, fmtDateTime, fmtHours } from '../lib/format'

export default function Inventory() {
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState(''); const [health, setHealth] = useState(''); const [cls, setCls] = useState(sp.get('cls') ?? ''); const [source, setSource] = useState(''); const [validation, setValidation] = useState('')
  const post = sp.get('post') ?? ''
  const [sort, setSort] = useState({ key: 'dos', order: 'asc' as 'asc' | 'desc' }); const [page, setPage] = useState(1); const [open, setOpen] = useState<number | null>(null)
  const qs = new URLSearchParams({ q, post, cls, health, source, validation, sort: sort.key, order: sort.order, page: String(page), page_size: '15' })
  const s = useApi<any>(`/api/inventory?${qs}`)
  const onSort = (k: string) => setSort((p) => ({ key: k, order: p.key === k && p.order === 'asc' ? 'desc' : 'asc' }))
  const cols: Col<any>[] = [
    { key: 'post_id', label: 'Post', sortable: true, render: (r) => <><b>{r.post_id}</b><div className="text-[11px] text-muted">{r.post_name}</div></> },
    { key: 'supply_class', label: 'Class', sortable: true, render: (r) => SUPPLY_LABEL[r.supply_class] },
    { key: 'usable', label: 'Usable', sortable: true, align: 'right', render: (r) => <>{fmt(r.usable)} <span className="text-[11px] text-muted">{r.unit}</span><div className="text-[11px] text-muted">reserved {fmt(r.reserved)}</div></> },
    { key: 'avg_daily', label: 'Avg daily', sortable: true, align: 'right', render: (r) => fmt(r.avg_daily, 1) },
    { key: 'dos', label: 'Days of supply', sortable: true, align: 'right', render: (r) => <b>{r.dos}</b> },
    { key: 'tts_p50_h', label: 'Time-to-stockout', sortable: true, align: 'right', render: (r) => fmtHours(r.tts_p50_h) },
    { key: 'reorder_threshold', label: 'Reorder at', sortable: true, align: 'right', render: (r) => <span className={r.below_reorder ? 'font-semibold text-crit-ink' : ''}>{fmt(r.reorder_threshold)}</span> },
    { key: 'health', label: 'Health', sortable: true, render: (r) => <HealthBadge h={r.health} /> },
    { key: 'source', label: 'Source · freshness', render: (r) => <><Badge tone="gray" icon={false}>{r.source}</Badge><div className={`mt-0.5 text-[11px] ${r.validation !== 'valid' || r.age_h > 24 ? 'font-semibold text-orange-ink' : 'text-muted'}`}>{r.validation !== 'valid' ? `${r.validation} · ` : ''}{r.age_h} h old</div></> },
    { key: 'confidence', label: 'Confidence', sortable: true, render: (r) => <ConfBadge c={r.confidence} /> },
  ]
  return (
    <>
      <PageHeader title="Inventory & Stock Health" sub="Stock, consumption and Days of Supply per post and supply class" />
      <Async state={s}>{(d) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{(['healthy', 'attention', 'elevated', 'critical'] as const).map((h) => <button key={h} onClick={() => { setHealth(health === h ? '' : h); setPage(1) }} aria-pressed={health === h} className={`rounded-xl border bg-white p-3.5 text-left ${health === h ? 'border-deep ring-1 ring-deep' : 'border-line'}`}><HealthBadge h={h} /><div className="num mt-1 text-2xl font-bold">{d.summary[h]}</div><div className="text-[11px] text-muted">records</div></button>)}</div>
          {d.discrepancies.length > 0 && <div role="alert" className="flex items-start gap-2 rounded-xl border border-[#f7d9b9] bg-[#fde8d6] p-3 text-sm text-orange-ink"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><div><b>Stock discrepancy alert:</b> {d.discrepancies.map((x: any) => `${x.post_id} ${SUPPLY_LABEL[x.supply_class]}`).join(', ')}. Recorded stock disagrees with an independent source; verify with a physical count.</div></div>}
          <Card pad={false}>
            <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
              <label className="relative min-w-[200px] flex-1"><span className="sr-only">Search inventory</span><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden /><Input className="pl-9" placeholder="Search post, name or class" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></label>
              {post && <Badge tone="purple" icon={false}>Post {post} <button aria-label="Clear post filter" className="ml-1" onClick={() => setSp({})}>×</button></Badge>}
              <Select aria-label="Supply class" className="w-auto" value={cls} onChange={(e) => { setCls(e.target.value); setPage(1) }}><option value="">All classes</option>{Object.entries(SUPPLY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
              <Select aria-label="Source" className="w-auto" value={source} onChange={(e) => { setSource(e.target.value); setPage(1) }}><option value="">All sources</option><option value="sensor">Sensor</option><option value="manual">Manual</option><option value="simulated">Simulated</option></Select>
              <Select aria-label="Validation" className="w-auto" value={validation} onChange={(e) => { setValidation(e.target.value); setPage(1) }}><option value="">All validation</option><option value="valid">Valid</option><option value="stale">Stale</option><option value="discrepancy">Discrepancy</option></Select>
            </div>
            <DataTable rowKey={(r) => r.id} cols={cols} rows={d.items} sort={sort} onSort={onSort} onRow={(r) => setOpen(r.id)} empty={<div className="py-10 text-center text-sm text-muted">No inventory records match these filters.</div>} />
            <Pager page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} />
          </Card>
          <p className="text-[11px] text-muted">Days of Supply uses the simulated forecaster's P50 demand over 7 days. Select a row for stock history and adjustments.</p>
        </div>)}</Async>
      <Detail id={open} onClose={() => setOpen(null)} onChanged={() => s.reload()} />
    </>
  )
}

function Detail({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged: () => void }) {
  const d = useApi<any>(id ? `/api/inventory/${id}` : null, [id])
  const toast = useToast()
  const [kind, setKind] = useState('receipt'); const [qty, setQty] = useState(''); const [reason, setReason] = useState('')
  const [errs, setErrs] = useState<Record<string, string>>({}); const [confirm, setConfirm] = useState(false); const [busy, setBusy] = useState(false)
  const item = d.data?.item
  function validate(e: FormEvent) {
    e.preventDefault(); const n: Record<string, string> = {}
    const v = Number(qty)
    if (qty === '' || Number.isNaN(v)) n.qty = 'Enter a number.'
    else if (kind !== 'adjustment' && kind !== 'count' && v <= 0) n.qty = 'Quantity must be greater than zero.'
    else if (kind === 'count' && v < 0) n.qty = 'Counted quantity cannot be negative.'
    else if (kind === 'adjustment' && v === 0) n.qty = 'Adjustment cannot be zero (use a negative number to reduce).'
    else if (kind === 'issue' && item && v > item.usable) n.qty = `Cannot issue more than usable stock (${item.usable} ${item.unit}).`
    if (reason.trim().length < 5) n.reason = 'Give a reason of at least 5 characters (recorded in the audit trail).'
    setErrs(n); if (!Object.keys(n).length) setConfirm(true)
  }
  async function submit() {
    setBusy(true)
    try { const r = await api(`/api/inventory/${id}/adjust`, { method: 'POST', body: { kind, qty: Number(qty), reason, expected_version: item.version } }); toast('success', `Stock updated (${r.delta > 0 ? '+' : ''}${r.delta} ${item.unit}) and recorded in the audit trail.`); setConfirm(false); setQty(''); setReason(''); d.reload(); onChanged() }
    catch (e) { toast('error', e instanceof ApiError ? e.message : 'Update failed'); setConfirm(false); if (e instanceof ApiError && e.status === 409) d.reload() } finally { setBusy(false) }
  }
  return (
    <Drawer open={id !== null} onClose={onClose} title={item ? `${item.post_id} · ${SUPPLY_LABEL[item.supply_class]}` : 'Inventory record'}>
      <Async state={d}>{(x) => (
        <div className="space-y-5 text-[13px]">
          <div><Kv k="Usable / reserved" v={`${fmt(x.item.usable)} / ${fmt(x.item.reserved)} ${x.item.unit}`} /><Kv k="Days of supply" v={`${x.item.dos} d`} /><Kv k="Time-to-stockout (P50 / earliest)" v={`${fmtHours(x.item.tts_p50_h)} / ${fmtHours(x.item.tts_earliest_h)}`} /><Kv k="Reorder threshold" v={`${fmt(x.item.reorder_threshold)} ${x.item.unit}`} /><Kv k="Source" v={`${x.item.source}${x.item.sensor_id ? ` (${x.item.sensor_id}, ${x.item.sensor_health})` : ''}`} /><Kv k="Validation" v={x.item.validation} /><Kv k="Last update" v={fmtDateTime(x.item.updated_at)} /></div>
          {x.flags.length > 0 && <div role="alert" className="rounded-lg border border-[#f7d9b9] bg-[#fde8d6] p-3 text-orange-ink"><b>Discrepancy / data alerts</b><ul className="mt-1 list-disc pl-4">{x.flags.map((f: string) => <li key={f}>{f}</li>)}</ul></div>}
          <div><h3 className="mb-2 font-semibold">Receipt, issue and adjustment</h3>
            {x.can_adjust ? (
              <form onSubmit={validate} noValidate className="space-y-3">
                <div className="grid grid-cols-2 gap-3"><Field label="Type">{(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}><option value="receipt">Receipt (add)</option><option value="issue">Issue (remove)</option><option value="adjustment">Adjustment (±)</option><option value="count">Manual count (set)</option></Select>}</Field>
                  <Field label={`Quantity (${x.item.unit})`} error={errs.qty} hint={kind === 'count' ? 'Enter the total counted' : undefined}>{(id) => <Input id={id} inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!errs.qty} />}</Field></div>
                <Field label="Reason" error={errs.reason} hint="Do not enter personal data.">{(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} aria-invalid={!!errs.reason} />}</Field>
                <Button type="submit" variant="primary">Review change</Button>
              </form>) : <p className="rounded-lg bg-[#eceef3] p-3 text-muted">Your role cannot change stock{x.item && ' at this post'}. This is enforced by the server.</p>}
          </div>
          <div><h3 className="mb-2 font-semibold">Stock movement history</h3>
            {x.movements.length === 0 ? <p className="text-muted">No movements recorded.</p> : <ul className="divide-y divide-line rounded-lg border border-line">{x.movements.map((m: any) => <li key={m.id} className="flex items-center justify-between px-3 py-2"><span><span className="font-medium capitalize">{m.kind}</span> <span className="text-muted">· {m.actor}</span><span className="block text-[11px] text-muted">{fmtDateTime(m.ts)} {m.note && `· ${m.note}`}</span></span><span className={`num font-semibold ${m.qty < 0 ? 'text-crit-ink' : 'text-ok-ink'}`}>{m.qty > 0 ? '+' : ''}{fmt(m.qty, 1)} {x.item.unit}</span></li>)}</ul>}</div>
          <Confirm open={confirm} onClose={() => setConfirm(false)} title="Confirm stock change" confirmLabel="Apply and record" loading={busy} onConfirm={submit} body={<><p>You are about to record a <b>{kind}</b> of <b>{qty} {x.item.unit}</b> for {x.item.post_id} {SUPPLY_LABEL[x.item.supply_class]}.</p><p className="mt-2">Reason: “{reason}”</p><p className="mt-2 text-xs text-muted">This writes a stock movement and an audit event, and may update recommendations.</p></>} />
        </div>)}</Async>
    </Drawer>
  )
}
