import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { Minus, Plus, Maximize2 } from 'lucide-react'
import { HEALTH_COLOR, RISK_COLOR } from '../lib/format'
import { cx } from './ui'

export interface MapLayers { routes: boolean; air: boolean; weather: boolean; terrain: boolean; labels: boolean }
interface Props { nodes: any[]; routes: any[]; selected?: string | null; onSelect?: (id: string) => void; layers: MapLayers; className?: string; focusRoute?: string | null }

const hasWebGL = () => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')) } catch { return false } }
const STYLE: maplibregl.StyleSpecification = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#eef0f6' } }] }

function geo(nodes: any[], routes: any[], layers: MapLayers) {
  const by = Object.fromEntries(nodes.map((n) => [n.id, n]))
  const lines = routes.filter((r) => by[r.a] && by[r.b] && (r.mode === 'road' ? layers.routes : layers.air)).map((r) => ({ type: 'Feature' as const, properties: { id: r.id, mode: r.mode, risk: r.risk, color: RISK_COLOR[r.risk] ?? '#999', closed: r.closed ? 1 : 0 }, geometry: { type: 'LineString' as const, coordinates: [[by[r.a].lon, by[r.a].lat], [by[r.b].lon, by[r.b].lat]] } }))
  const pts = nodes.map((n) => ({ type: 'Feature' as const, properties: { id: n.id, name: n.name, kind: n.kind, color: n.kind === 'post' ? HEALTH_COLOR[n.health ?? 'healthy'] : '#355493', label: n.kind === 'post' ? n.id.replace('POST-', '') : n.id }, geometry: { type: 'Point' as const, coordinates: [n.lon, n.lat] } }))
  const wx = layers.weather ? nodes.filter((n) => n.weather && n.weather.snow_cm > 8).map((n) => ({ type: 'Feature' as const, properties: { r: n.weather.snow_cm }, geometry: { type: 'Point' as const, coordinates: [n.lon, n.lat] } })) : []
  const terr = layers.terrain ? nodes.filter((n) => n.kind === 'post').map((n) => ({ type: 'Feature' as const, properties: { alt: n.alt_m }, geometry: { type: 'Point' as const, coordinates: [n.lon, n.lat] } })) : []
  return { lines: { type: 'FeatureCollection' as const, features: lines }, pts: { type: 'FeatureCollection' as const, features: pts }, wx: { type: 'FeatureCollection' as const, features: wx }, terr: { type: 'FeatureCollection' as const, features: terr } }
}

export function SynthMap(props: Props) {
  const [gl] = useState(hasWebGL)
  const [failed, setFailed] = useState(false)
  return gl && !failed ? <GLMap {...props} onFail={() => setFailed(true)} /> : <SvgMap {...props} />
}

function GLMap({ nodes, routes, selected, onSelect, layers, className, onFail }: Props & { onFail: () => void }) {
  const el = useRef<HTMLDivElement>(null); const map = useRef<maplibregl.Map | null>(null); const ready = useRef(false); const markers = useRef<maplibregl.Marker[]>([])
  const data = useMemo(() => geo(nodes, routes, layers), [nodes, routes, layers])
  const cb = useRef(onSelect); cb.current = onSelect
  const bounds = useMemo(() => { const b = new maplibregl.LngLatBounds(); nodes.forEach((n) => b.extend([n.lon, n.lat])); return b }, [nodes])
  useEffect(() => {
    if (!el.current || !nodes.length) return
    let m: maplibregl.Map
    try { m = new maplibregl.Map({ container: el.current, style: STYLE, bounds, fitBoundsOptions: { padding: 40 }, attributionControl: false, dragRotate: false }) } catch { onFail(); return }
    map.current = m
    m.on('error', () => { if (!ready.current) onFail() })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => {
      ready.current = true
      for (const s of ['lines', 'pts', 'wx', 'terr']) m.addSource(s, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({ id: 'terr', type: 'circle', source: 'terr', paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'alt'], 2500, 22, 4200, 46], 'circle-color': '#746FA7', 'circle-opacity': 0.12 } })
      m.addLayer({ id: 'wx', type: 'circle', source: 'wx', paint: { 'circle-radius': 36, 'circle-color': '#3498B3', 'circle-opacity': 0.22, 'circle-blur': 0.6 } })
      m.addLayer({ id: 'lines-case', type: 'line', source: 'lines', paint: { 'line-color': '#fff', 'line-width': 6 } })
      m.addLayer({ id: 'lines', type: 'line', source: 'lines', paint: { 'line-color': ['get', 'color'], 'line-width': 3.2, 'line-dasharray': ['case', ['==', ['get', 'closed'], 1], ['literal', [1.5, 1.5]], ['==', ['get', 'mode'], 'air'] as any, ['literal', [4, 3]], ['literal', [1, 0]]] as any } })
      m.addLayer({ id: 'pts-halo', type: 'circle', source: 'pts', paint: { 'circle-radius': ['case', ['==', ['get', 'kind'], 'post'], 11, 9], 'circle-color': '#fff' } })
      m.addLayer({ id: 'pts', type: 'circle', source: 'pts', paint: { 'circle-radius': ['case', ['==', ['get', 'kind'], 'post'], 8, 6], 'circle-color': ['get', 'color'], 'circle-stroke-color': '#351A55', 'circle-stroke-width': ['case', ['==', ['get', 'kind'], 'post'], 0, 2] } })
      m.addLayer({ id: 'sel', type: 'circle', source: 'pts', filter: ['==', ['get', 'id'], ''], paint: { 'circle-radius': 15, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#351A55', 'circle-stroke-width': 3 } })
      m.on('click', 'pts', (e) => { const id = e.features?.[0]?.properties?.id; if (id) cb.current?.(id) })
      m.on('mouseenter', 'pts', () => (m.getCanvas().style.cursor = 'pointer')); m.on('mouseleave', 'pts', () => (m.getCanvas().style.cursor = ''))
      m.fire('hv-ready' as any)
    })
    return () => { ready.current = false; m.remove(); map.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length > 0])
  useEffect(() => {
    const m = map.current; if (!m) return
    const apply = () => { for (const k of ['lines', 'pts', 'wx', 'terr'] as const) (m.getSource(k) as maplibregl.GeoJSONSource | undefined)?.setData(data[k]); m.getLayer('sel') && m.setFilter('sel', ['==', ['get', 'id'], selected ?? '']) }
    ready.current ? apply() : m.once('load', apply)
  }, [data, selected])
  // Labels are DOM markers: the offline style has no glyph server, so symbol layers cannot be used.
  useEffect(() => {
    const m = map.current; if (!m) return
    markers.current.forEach((k) => k.remove()); markers.current = []
    if (!layers.labels) return
    nodes.forEach((n) => { const d = document.createElement('div'); d.textContent = n.kind === 'post' ? n.id.replace('POST-', '') : n.id; d.style.cssText = 'font:600 10.5px Inter,sans-serif;color:#351A55;text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;pointer-events:none;margin-top:22px'; markers.current.push(new maplibregl.Marker({ element: d }).setLngLat([n.lon, n.lat]).addTo(m)) })
  }, [nodes, layers.labels])
  return (
    <div className={cx('relative overflow-hidden rounded-xl border border-line', className)}>
      <div ref={el} className="h-full w-full" role="application" aria-label="Interactive synthetic logistics map. Use the post list for keyboard access." />
      <button aria-label="Reset map view" onClick={() => map.current?.fitBounds(bounds, { padding: 40 })} className="absolute left-2 top-2 rounded-lg border border-line bg-white p-1.5 shadow hover:bg-lilac-soft"><Maximize2 className="h-4 w-4" /></button>
    </div>
  )
}

// Functional fallback when WebGL / the map engine is unavailable: same data, plain SVG with pan-free zoom buttons.
function SvgMap({ nodes, routes, selected, onSelect, layers, className }: Props) {
  const [z, setZ] = useState(1)
  const W = 800, H = 520, pad = 40
  const xs = nodes.map((n) => n.lon), ys = nodes.map((n) => n.lat)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const p = (n: any) => [pad + ((n.lon - minX) / (maxX - minX || 1)) * (W - 2 * pad), H - pad - ((n.lat - minY) / (maxY - minY || 1)) * (H - 2 * pad)]
  const by = Object.fromEntries(nodes.map((n) => [n.id, n]))
  return (
    <div className={cx('relative overflow-auto rounded-xl border border-line bg-[#eef0f6]', className)}>
      <div className="absolute right-2 top-2 z-10 flex flex-col overflow-hidden rounded-lg border border-line bg-white shadow"><button aria-label="Zoom in" className="p-1.5 hover:bg-lilac-soft" onClick={() => setZ(Math.min(2.5, z + 0.3))}><Plus className="h-4 w-4" /></button><button aria-label="Zoom out" className="border-t border-line p-1.5 hover:bg-lilac-soft" onClick={() => setZ(Math.max(1, z - 0.3))}><Minus className="h-4 w-4" /></button><button aria-label="Reset map view" className="border-t border-line p-1.5 hover:bg-lilac-soft" onClick={() => setZ(1)}><Maximize2 className="h-4 w-4" /></button></div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: `${z * 100}%`, minWidth: '100%' }} role="img" aria-label="Synthetic logistics map (fallback renderer)">
        {routes.filter((r) => by[r.a] && by[r.b] && (r.mode === 'road' ? layers.routes : layers.air)).map((r) => { const [x1, y1] = p(by[r.a]), [x2, y2] = p(by[r.b]); return <line key={r.id} x1={x1} y1={y1} x2={x2} y2={y2} stroke={RISK_COLOR[r.risk]} strokeWidth={3} strokeDasharray={r.closed ? '3 4' : r.mode === 'air' ? '8 5' : undefined} /> })}
        {nodes.map((n) => { const [x, y] = p(n); const post = n.kind === 'post'; return (
          <g key={n.id} onClick={() => onSelect?.(n.id)} className="cursor-pointer" tabIndex={0} role="button" aria-label={`${n.id} ${n.name}`} onKeyDown={(e) => e.key === 'Enter' && onSelect?.(n.id)}>
            <circle cx={x} cy={y} r={post ? 9 : 7} fill={post ? HEALTH_COLOR[n.health ?? 'healthy'] : '#355493'} stroke={selected === n.id ? '#351A55' : '#fff'} strokeWidth={selected === n.id ? 4 : 2} />
            {layers.labels && <text x={x} y={y + 22} textAnchor="middle" fontSize="11" fill="#351A55">{post ? n.id.replace('POST-', '') : n.id}</text>}</g>) })}
      </svg>
      <p className="absolute bottom-1 left-2 text-[10px] text-muted">Fallback renderer (WebGL unavailable)</p>
    </div>
  )
}

export function MapLegend() {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-gray" aria-label="Map legend">
      <span className="font-semibold text-ink">Post stock health:</span>{Object.entries(HEALTH_COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />{k[0].toUpperCase() + k.slice(1)}</span>)}
      <span className="font-semibold text-ink">Route risk:</span>{Object.entries(RISK_COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1"><i className="inline-block h-0.5 w-4" style={{ background: c }} />{k === 'closed' ? 'Closed (dotted)' : k[0].toUpperCase() + k.slice(1)}</span>)}
      <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-full border-2 border-deep bg-blue" />Depot / airfield / junction</span>
    </div>
  )
}
