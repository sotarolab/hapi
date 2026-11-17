import { useEffect, useState } from 'react'
import { api, type Point, type PointData } from './api'
import { LabPane } from './components/LabPane'
import { MODEL_VARS, PointChart, category, latest } from './components/PointChart'
import { PointMap } from './components/PointMap'
import { SkyCard } from './components/SatellitePane'
import { WeatherCard, WeatherTiles } from './components/WeatherPane'
import { useFetch } from './hooks/useFetch'
import { dayLabel, fmtFlow, recordDay } from './lib/skill'

const TABS = [{ id: 'forecast', label: 'Forecast' }, { id: 'lab', label: 'Lab' }] as const
type Tab = (typeof TABS)[number]['id']
type View = { tab: Tab; lid: string | null; stage: boolean }
const REFRESH_MS = 10 * 60_000

/** The URL hash carries the pane, the point and the chart's view: #lab, #forecast?p=GUEC1, #forecast?p=GUEC1&v=stage. */
function readHash(): View {
  const [raw, query] = location.hash.slice(1).split('?')
  const q = new URLSearchParams(query ?? '')
  return { tab: raw === 'lab' ? 'lab' : 'forecast', lid: q.get('p'), stage: q.get('v') === 'stage' }
}

export default function App() {
  const [{ tab, lid, stage }, setView] = useState(readHash)
  useEffect(() => {
    const q = new URLSearchParams({ ...(lid ? { p: lid } : {}), ...(stage ? { v: 'stage' } : {}) }).toString()
    const h = `#${tab}${q ? `?${q}` : ''}`
    if (location.hash !== h) history.replaceState(null, '', h)
  }, [tab, lid, stage])
  const [tick, setTick] = useState(0)
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), REFRESH_MS); return () => clearInterval(t) }, [])
  const index = useFetch((s) => api.index(s), [], tick)
  const points = index.data?.points ?? []
  const current = lid ?? points.find((p) => p.scored)?.lid ?? null
  const point = useFetch((s) => (current ? api.point(current, s) : Promise.resolve(null)), [current], tick)
  const here = points.find((p) => p.lid === current)
  const pick = (p: string) => setView({ tab: 'forecast', lid: p, stage })
  const day = recordDay(index.data?.record_start ?? null)
  return (
    <div className="wrap">
      <header className="top">
        <div className="brand"><h1>hapi</h1><span className="sub">California reservoir inflow and river flood forecasts, scored in public</span></div>
        <nav className="tabs">{TABS.map((t) => <button key={t.id} className={`tab${t.id === tab ? ' active' : ''}`} onClick={() => setView({ tab: t.id, lid, stage })}>{t.label}</button>)}</nav>
        <span className="stamp"><i className={`live${index.error ? ' stale' : ''}`} />{index.data ? `day ${day} · built ${index.data.built.slice(0, 16)}Z` : index.error ? `data: ${index.error}` : 'loading'}</span>
      </header>
      {tab === 'forecast' && (
        <div className="shell">
          <aside className="rail">
            <label className="picker">
              <select value={current ?? ''} onChange={(e) => pick(e.target.value)}>
                <optgroup label="Reservoir inflow">{points.filter((p) => p.kind === 'reservoir').map((p) => <option key={p.lid} value={p.lid}>{p.name} · {p.lid}{p.scored ? '' : ' (not scored)'}</option>)}</optgroup>
                <optgroup label="Flood gauges">{points.filter((p) => p.kind === 'gauge').map((p) => <option key={p.lid} value={p.lid}>{p.name} · {p.lid}</option>)}</optgroup>
              </select>
            </label>
            <PointMap points={points} selected={current} onSelect={pick} tick={tick} />
          </aside>
          <main className="detail">
            {point.data && here
              ? <PointDetail point={point.data} here={here} stage={stage} onStage={(v) => setView({ tab, lid, stage: v })} />
              : <p className="note card">{point.error ?? 'Loading…'}</p>}
          </main>
        </div>
      )}
      {tab === 'lab' && <div className="lab">{index.data ? <LabPane index={index.data} onPick={pick} /> : <section className="panel"><p className="note">{index.error ?? 'Loading…'}</p></section>}</div>}
      <footer>
        Archive, observations, forecasts and scores: the <a href="https://github.com/sotarolab/hapi/tree/data">data branch</a> of
        <a href="https://github.com/sotarolab/hapi"> hapi</a>. Official products from CNRFC (HEFS) and NWS (NWPS); observed inflow from CDEC.
        Models are issued before the outcome exists and never revised. Weather forecasts from <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0);
        satellite loops from NOAA STAR, radar from the NWS and the Iowa Environmental Mesonet.
      </footer>
    </div>
  )
}

/** The detail column for one point: its header and toggles, a strip of flow tiles and one of weather tiles, the
 *  chart card, and the weather and sky cards side by side. A gauge can switch its chart to stage. */
function PointDetail({ point, here, stage: wantStage, onStage }: { point: PointData; here: Point; stage: boolean; onStage: (v: boolean) => void }) {
  const [log, setLog] = useState(true)
  const models = Object.entries(point.models)
  const last = point.obs.at(-1)
  const alerts = point.alerts ?? []
  const hasStage = point.kind === 'gauge' && (point.live?.stage_ft?.some((v) => v != null) ?? false)
  const stage = hasStage && wantStage
  const now = point.live ? latest(point.live) : null
  const peak = point.official ? Math.max(...point.official.flow_cfs.filter((v): v is number => v != null), 0) : null
  const where = (cfs: number | null) => { const c = category(cfs, alerts); return c ? ` · ${c}` : '' }
  return (
    <>
      <div className="head">
        <div>
          <div className="row">
            <span className="headline" style={{ margin: 0 }}>{point.name}</span>
            <span className="pill">{point.kind === 'reservoir' ? 'reservoir inflow' : 'flood gauge'}</span>
            {!point.scored && <span className="pill warn">not scored</span>}
          </div>
          <span className="stamp">{point.lid}{point.cdec ? ` · CDEC ${point.cdec}` : ''}{point.usgs ? ` · USGS ${point.usgs}` : ''}</span>
        </div>
        <div className="row">
          {hasStage && <div className="seg"><button className={!stage ? 'on' : ''} onClick={() => onStage(false)}>flow</button><button className={stage ? 'on' : ''} onClick={() => onStage(true)}>stage</button></div>}
          {!stage && <div className="seg"><button className={log ? 'on' : ''} onClick={() => setLog(true)}>log</button><button className={!log ? 'on' : ''} onClick={() => setLog(false)}>linear</button></div>}
        </div>
      </div>
      <div className="tiles">
        {last && <div className="tile"><span className="eyebrow">Observed {dayLabel(last[0])}</span><b className="num">{fmtFlow(last[1])} cfs</b><p className="note">CDEC daily mean inflow</p></div>}
        {now && <div className="tile"><span className="eyebrow">Hourly, {now.when}</span><b className="num">{fmtFlow(now.cfs)} cfs</b><p className="note">{point.live!.source}{where(now.cfs)}</p></div>}
        {point.hefs && <div className="tile"><span className="eyebrow">HEFS median, day 1</span><b className="num">{fmtFlow(point.hefs.p50[1])} cfs</b><p className="note">5-95%: {fmtFlow(point.hefs.p05[1])} to {fmtFlow(point.hefs.p95[1])} · issued {point.hefs.issued.slice(0, 8)}</p></div>}
        {models.map(([name, m], i) => <div key={name} className="tile"><span className="eyebrow" style={{ color: `var(${MODEL_VARS[i % MODEL_VARS.length]})` }}>{name}, day 1</span><b className="num">{fmtFlow(m.q50[0])} cfs</b><p className="note">5-95%: {fmtFlow(m.q05[0])} to {fmtFlow(m.q95[0])} · issued {m.issued}</p></div>)}
        {point.official && <div className="tile"><span className="eyebrow">NWS official peak</span><b className="num">{fmtFlow(peak)} cfs</b><p className="note">issued {point.official.issued?.slice(0, 16)}Z{where(peak)}</p></div>}
      </div>
      {point.weather && <div className="tiles"><WeatherTiles weather={point.weather} /></div>}
      <section className="card">
        <div className="card-h"><h2>{stage ? 'Stage, ft' : 'Flow, cfs'}</h2></div>
        <PointChart point={point} log={log} view={stage ? 'stage' : 'flow'} />
        <div className="legend">
          <span><i style={{ background: 'var(--obs)' }} />{stage ? 'Observed stage, hourly' : `Observed${point.live ? ', daily and hourly' : ''}`}</span>
          {!stage && point.hefs && <span><i className="band" style={{ background: 'var(--cool)' }} />HEFS 5-95% / 25-75%, median</span>}
          {!stage && models.map(([name], i) => <span key={name}><i className="band" style={{ background: `var(${MODEL_VARS[i % MODEL_VARS.length]})` }} />{name} 5-95% / 25-75%, median</span>)}
          {point.official && <span><i style={{ background: 'var(--official)' }} />NWS official (hourly)</span>}
          {alerts.length > 0 && <span><i style={{ background: 'var(--warn)' }} />NWS flood categories: {alerts.map((a) => `${a.label.toLowerCase()} ${a.ft} ft`).join(', ')}{stage ? '' : ' (drawn in the stage view)'}</span>}
        </div>
        {point.note && <p className="note">{point.note}</p>}
      </section>
      <div className="cards2">
        {point.weather && <WeatherCard weather={point.weather} />}
        <SkyCard point={here} />
      </div>
    </>
  )
}
