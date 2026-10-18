import { useCallback, useEffect, useState } from 'react'
import { BatteryMedium, CloudOff, RefreshCw, ScanLine, Wifi } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { Async, Badge, Button, Card, Field, Input, Modal, PageHeader, Select, SimBanner, Tabs, Textarea, useToast } from '../components/ui'
import { SUPPLY_LABEL, ago, fmt, fmtDateTime } from '../lib/format'

type QItem = { client_id: string; type: string; post_id?: string; route_id?: string; supply_class?: string; qty?: number; note?: string; condition?: string; base_version?: number | null; resolution?: string; created_at: string; status: 'pending' | 'conflict' | 'rejected'; message?: string; server?: any }
const KEY = 'hv.field.queue'
const load = (): QItem[] => { try { return JSON.parse(localStorage.getItem(KEY) ?? '[]') } catch { return [] } }
const save = (q: QItem[]) => { try { localStorage.setItem(KEY, JSON.stringify(q)) } catch { /* storage unavailable: queue is in-memory only */ } }
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`)

export default function FieldOps() {
  const s = useApi<any>('/api/field/overview'); const inv = useApi<any>('/api/inventory?page_size=100')
  const toast = useToast()
  const [online, setOnline] = useState(navigator.onLine); const [forceOffline, setForce] = useState(false)
  const [queue, setQueue] = useState<QItem[]>(load); const [lastSync, setLast] = useState<string | null>(() => { try { return localStorage.getItem('hv.field.sync') } catch { return null } })
  const [tab, setTab] = useState<'stock' | 'road' | 'sensors' | 'queue'>('stock'); const [busy, setBusy] = useState(false)
  const effOnline = online && !forceOffline
  useEffect(() => { const a = () => setOnline(true), b = () => setOnline(false); window.addEventListener('online', a); window.addEventListener('offline', b); return () => { window.removeEventListener('online', a); window.removeEventListener('offline', b) } }, [])
  const update = (q: QItem[]) => { setQueue(q); save(q) }
  const enqueue = (it: Omit<QItem, 'client_id' | 'created_at' | 'status'>) => { update([...queue, { ...it, client_id: uid(), created_at: new Date().toISOString(), status: 'pending' }]); toast('info', effOnline ? 'Saved to the sync queue. Press Sync now.' : 'Saved on this device. It will sync when you are back online.') }
  const sync = useCallback(async (items?: QItem[]) => {
    const list = (items ?? queue).filter((q) => q.status !== 'rejected')
    if (!list.length) return
    setBusy(true)
    try {
      const r = await api('/api/field/sync', { method: 'POST', body: { items: list.map(({ status, message, server, ...rest }) => rest) } })
      const by = Object.fromEntries(r.results.map((x: any) => [x.client_id, x]))
      const next = queue.flatMap((q): QItem[] => { const x = by[q.client_id]; if (!x) return [q]; if (x.status === 'applied' || x.status === 'duplicate') return []; return [{ ...q, status: x.status === 'conflict' ? 'conflict' : 'rejected', message: x.message, server: x.server }] })
      update(next); const t = new Date().toISOString(); setLast(t); try { localStorage.setItem('hv.field.sync', t) } catch { /* noop */ }
      const ok = r.results.filter((x: any) => x.status === 'applied').length
      toast(next.length ? 'info' : 'success', `${ok} change(s) synchronised${next.length ? `; ${next.length} need attention` : ''}.`); s.reload(); inv.reload()
    } catch (e) { toast('error', e instanceof ApiError && e.status !== 0 ? e.message : 'Cannot sync right now. Changes stay safely queued on this device.') } finally { setBusy(false) }
  }, [queue, s, inv, toast])
  useEffect(() => { if (effOnline && queue.some((q) => q.status === 'pending')) void sync(queue.filter((q) => q.status === 'pending')) /* auto-sync on reconnect */ }, [effOnline]) // eslint-disable-line
  const pending = queue.filter((q) => q.status === 'pending').length, conflicts = queue.filter((q) => q.status === 'conflict')
  const [resolve, setResolve] = useState<QItem | null>(null)
  return (
    <>
      <PageHeader title="IoT & Field Reports" sub="Quick entry, smart-bin readings and offline-ready sync" actions={<><Badge tone={effOnline ? 'ok' : 'warn'}>{effOnline ? <><Wifi className="h-3 w-3" aria-hidden />Online</> : <><CloudOff className="h-3 w-3" aria-hidden />Offline</>}</Badge><label className="flex items-center gap-1.5 text-xs text-gray"><input type="checkbox" className="accent-[#351A55]" checked={forceOffline} onChange={(e) => setForce(e.target.checked)} />Simulate offline</label></>} />
      <div className="mb-4"><SimBanner>Simulated sensors and readings. Offline entries are kept in this browser until synchronised; this is a prototype queue, not a guarantee against data loss.</SimBanner></div>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[['Pending sync', pending, pending ? 'warn' : 'ok'], ['Conflicts', conflicts.length, conflicts.length ? 'crit' : 'ok'], ['Last sync', lastSync ? ago(lastSync) : 'never', 'gray'], ['Connection', effOnline ? 'Online' : 'Offline', effOnline ? 'ok' : 'warn']].map(([k, v, t]: any) => <div key={k} className="rounded-xl border border-line bg-white p-3"><div className="text-xs text-muted">{k}</div><div className="num mt-0.5 text-xl font-bold">{v}</div></div>)}
      </div>
      <Async state={s}>{(d) => (
        <div className="space-y-4">
          <Tabs tabs={[{ id: 'stock', label: 'Stock entry' }, { id: 'road', label: 'Road & receipt' }, { id: 'sensors', label: 'Sensors' }, { id: 'queue', label: `Sync queue (${queue.length})` }]} value={tab} onChange={setTab} />
          {tab === 'stock' && <StockForms d={d} inv={inv.data?.items ?? []} enqueue={enqueue} />}
          {tab === 'road' && <RoadForms d={d} enqueue={enqueue} />}
          {tab === 'sensors' && <Sensors d={d} />}
          {tab === 'queue' && <Card title="Safe synchronisation queue" action={<Button size="sm" variant="primary" loading={busy} disabled={!effOnline || !queue.some((q) => q.status === 'pending')} onClick={() => sync()}><RefreshCw className="h-3.5 w-3.5" aria-hidden />Sync now</Button>} pad={false}>
            {queue.length === 0 ? <p className="p-4 text-sm text-muted">Nothing queued. Entries made offline appear here with a Pending Sync state.</p> : <ul className="divide-y divide-line">{queue.map((q) => <li key={q.client_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-[13px]"><div><b className="capitalize">{q.type.replace('_', ' ')}</b> {q.post_id ?? q.route_id} {q.supply_class && SUPPLY_LABEL[q.supply_class]} {q.qty != null && <span className="num">· {q.qty}</span>} {q.condition && `· ${q.condition}`}<div className="text-[11px] text-muted">{fmtDateTime(q.created_at)} {q.message && `· ${q.message}`}</div></div><div className="flex items-center gap-2"><Badge tone={q.status === 'pending' ? 'warn' : q.status === 'conflict' ? 'crit' : 'gray'}>{q.status === 'pending' ? 'Pending Sync' : q.status === 'conflict' ? 'Conflict' : 'Rejected'}</Badge>{q.status === 'conflict' && <Button size="sm" onClick={() => setResolve(q)}>Resolve</Button>}{q.status !== 'pending' && <Button size="sm" variant="ghost" onClick={() => update(queue.filter((x) => x.client_id !== q.client_id))}>Discard</Button>}</div></li>)}</ul>}
            <p className="border-t border-line p-3 text-[11px] text-muted"><b>Works offline:</b> this screen (once loaded), data entry and the queue. <b>Needs a connection:</b> sign-in, live data refresh and synchronisation. Entries carry a unique ID so a retry cannot apply twice.</p></Card>}
        </div>)}</Async>
      {resolve && <Modal open onClose={() => setResolve(null)} title="Resolve conflict" footer={<><Button onClick={() => { update(queue.map((q) => (q.client_id === resolve.client_id ? { ...q, resolution: 'keep_server', status: 'pending' } : q))); setResolve(null) }}>Keep server value</Button><Button variant="primary" onClick={() => { update(queue.map((q) => (q.client_id === resolve.client_id ? { ...q, resolution: 'apply_mine', status: 'pending' } : q))); setResolve(null) }}>Apply my entry</Button></>}>
        <div className="space-y-2 text-[13px]"><p>Stock at <b>{resolve.post_id} {SUPPLY_LABEL[resolve.supply_class ?? '']}</b> changed on the server while you were offline.</p><p>Server now: <b className="num">{fmt(resolve.server?.quantity, 1)} {resolve.server?.unit}</b> (updated {fmtDateTime(resolve.server?.updated_at)})</p><p>Your entry: <b>{resolve.type.replace('stock_', '')} {resolve.qty}</b></p><p className="text-xs text-muted">After choosing, press Sync now to apply your decision. It is recorded in the audit trail.</p></div></Modal>}
    </>
  )
}

function StockForms({ d, inv, enqueue }: { d: any; inv: any[]; enqueue: (i: any) => void }) {
  const [type, setType] = useState('stock_receipt'); const [post, setPost] = useState(d.scope_post ?? d.posts[0]?.id ?? ''); const [cls, setCls] = useState('rations'); const [qty, setQty] = useState(''); const [note, setNote] = useState(''); const [err, setErr] = useState<Record<string, string>>({})
  const rec = inv.find((i: any) => i.post_id === post && i.supply_class === cls)
  function go(e: React.FormEvent) {
    e.preventDefault(); const n: Record<string, string> = {}; const v = Number(qty)
    if (qty === '' || Number.isNaN(v) || v < 0) n.qty = 'Enter a valid quantity.'
    else if (type !== 'stock_count' && v === 0) n.qty = 'Quantity must be greater than zero.'
    if (!post) n.post = 'Choose a post.'
    setErr(n); if (Object.keys(n).length) return
    enqueue({ type, post_id: post, supply_class: cls, qty: v, note, base_version: rec?.version ?? null }); setQty(''); setNote('')
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Receipt, issue or manual count"><form onSubmit={go} noValidate className="space-y-3">
        <div className="grid grid-cols-2 gap-3"><Field label="Entry type">{(i) => <Select id={i} value={type} onChange={(e) => setType(e.target.value)}><option value="stock_receipt">Stock receipt</option><option value="stock_issue">Stock issue</option><option value="stock_count">Manual stock count</option></Select>}</Field><Field label="Post" error={err.post}>{(i) => <Select id={i} value={post} disabled={!!d.scope_post} onChange={(e) => setPost(e.target.value)}>{d.posts.map((p: any) => <option key={p.id} value={p.id}>{p.id} {p.name}</option>)}</Select>}</Field></div>
        <div className="grid grid-cols-2 gap-3"><Field label="Supply class">{(i) => <Select id={i} value={cls} onChange={(e) => setCls(e.target.value)}>{d.classes.map((c: any) => <option key={c.id} value={c.id}>{c.label} ({c.unit})</option>)}</Select>}</Field><Field label={type === 'stock_count' ? 'Counted total' : 'Quantity'} error={err.qty}>{(i) => <Input id={i} inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />}</Field></div>
        <Field label="Note (optional)" hint="Do not enter personal data.">{(i) => <Textarea id={i} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        {rec && <p className="text-[11px] text-muted">Last known: {fmt(rec.quantity, 1)} {rec.unit}</p>}
        <Button type="submit" variant="primary" className="w-full">Save entry</Button></form></Card>
      <Card title="RFID / BLE scan (placeholder)"><div className="flex flex-col items-center gap-3 py-6 text-center"><ScanLine className="h-12 w-12 text-lilac" aria-hidden /><p className="text-sm text-gray">Scanning is a placeholder interface. A device registry and a real RFID/BLE reader integration are not connected in this prototype.</p><Button onClick={() => { const code = `RF-SIM-${Math.floor(Math.random() * 9000 + 1000)}`; setNote(`Scanned ${code} (simulated)`) }}>Simulate a scan</Button>{note.startsWith('Scanned') && <Badge tone="purple" icon={false}>{note}</Badge>}</div></Card>
    </div>
  )
}

function RoadForms({ d, enqueue }: { d: any; enqueue: (i: any) => void }) {
  const [route, setRoute] = useState(d.routes[0]?.id ?? ''); const [cond, setCond] = useState('clear'); const [note, setNote] = useState(''); const [post, setPost] = useState(d.scope_post ?? d.posts[0]?.id ?? ''); const [rn, setRn] = useState('')
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Road-condition report"><form className="space-y-3" onSubmit={(e) => { e.preventDefault(); enqueue({ type: 'road_condition', route_id: route, condition: cond, note }); setNote('') }}>
        <Field label="Route">{(i) => <Select id={i} value={route} onChange={(e) => setRoute(e.target.value)}>{d.routes.map((r: any) => <option key={r.id} value={r.id}>{r.label}</option>)}</Select>}</Field>
        <Field label="Condition">{(i) => <Select id={i} value={cond} onChange={(e) => setCond(e.target.value)}><option value="clear">Clear</option><option value="slippery">Slippery</option><option value="debris">Debris</option><option value="blocked">Blocked</option></Select>}</Field>
        <Field label="Note" hint="Do not enter personal data.">{(i) => <Textarea id={i} value={note} onChange={(e) => setNote(e.target.value)} />}</Field><Button type="submit" variant="primary" className="w-full">Save report</Button></form></Card>
      <Card title="Receipt confirmation"><form className="space-y-3" onSubmit={(e) => { e.preventDefault(); enqueue({ type: 'receipt_confirmation', post_id: post, note: rn || 'Delivery received' }); setRn('') }}>
        <Field label="Post">{(i) => <Select id={i} value={post} disabled={!!d.scope_post} onChange={(e) => setPost(e.target.value)}>{d.posts.map((p: any) => <option key={p.id} value={p.id}>{p.id} {p.name}</option>)}</Select>}</Field>
        <Field label="Note">{(i) => <Input id={i} value={rn} onChange={(e) => setRn(e.target.value)} placeholder="Delivery received" />}</Field><Button type="submit" variant="primary" className="w-full">Confirm receipt</Button></form>
        {d.recent_reports.length > 0 && <div className="mt-4"><h3 className="mb-1 text-xs font-semibold text-muted">Recent reports</h3><ul className="space-y-1 text-xs text-gray">{d.recent_reports.slice(0, 5).map((r: any) => <li key={r.id}>{fmtDateTime(r.ts)} · {r.kind.replace('_', ' ')} {r.route_id ?? r.post_id}</li>)}</ul></div>}</Card>
    </div>
  )
}

function Sensors({ d }: { d: any }) {
  const bins = d.sensors.filter((s: any) => s.kind === 'smart-bin'), other = d.sensors.filter((s: any) => s.kind !== 'smart-bin')
  const tone = (h: string) => (h === 'ok' ? 'ok' : h === 'degraded' ? 'warn' : 'crit')
  return (
    <div className="space-y-4">
      <Card title="Smart-bin readings (simulated)" pad={false}><div className="overflow-x-auto"><table className="w-full text-left text-[13px]"><thead><tr className="border-b border-line text-[11px] uppercase text-muted"><th className="px-3 py-2">Sensor</th><th>Post</th><th>Class</th><th className="text-right">Reading</th><th>Battery</th><th>Last seen</th><th className="pr-3">Health</th></tr></thead><tbody>{bins.map((s: any) => <tr key={s.id} className="border-b border-line/70"><td className="px-3 py-2 font-medium">{s.id}</td><td>{s.post_id}</td><td>{SUPPLY_LABEL[s.supply_class]}</td><td className="num text-right">{fmt(s.reading, 1)} {s.unit}</td><td><span className="flex items-center gap-1"><BatteryMedium className="h-3.5 w-3.5" aria-hidden />{s.battery_pct}%</span></td><td>{ago(s.last_seen)}</td><td className="pr-3"><Badge tone={tone(s.health)}>{s.health}</Badge></td></tr>)}</tbody></table></div></Card>
      <Card title="RFID / BLE readers (placeholders)" pad={false}><ul className="divide-y divide-line">{other.slice(0, 12).map((s: any) => <li key={s.id} className="flex items-center justify-between px-4 py-2 text-[13px]"><span>{s.id} · {s.kind.toUpperCase()} · {s.post_id}</span><span className="flex items-center gap-2 text-muted">{ago(s.last_seen)}<Badge tone={tone(s.health)}>{s.health}</Badge></span></li>)}</ul></Card>
    </div>
  )
}
