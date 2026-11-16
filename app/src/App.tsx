import { useEffect, useState } from 'react'
import { api, type PointData } from './api'
import { LabPane } from './components/LabPane'
import { MODEL_VARS, PointChart, category, latest } from './components/PointChart'
import { PointMap } from './components/PointMap'
import { SatellitePane } from './components/SatellitePane'
import { WeatherPane } from './components/WeatherPane'
import { useFetch } from './hooks/useFetch'
import { dayLabel, fmtFlow, recordDay } from './lib/skill'

const TABS = [{ id: 'forecast', label: 'Forecast' }, { id: 'lab', label: 'Lab' }] as const
type Tab = (typeof TABS)[number]['id']
const REFRESH_MS = 10 * 60_000

/** The URL hash carries the pane and the point: #lab, or #forecast?p=GUEC1. */
function readHash(): { tab: Tab; lid: string | null } {
  const [raw, query] = location.hash.slice(1).split('?')
  const q = new URLSearchParams(query ?? '')
  return { tab: raw === 'lab' ? 'lab' : 'forecast', lid: q.get('p') }
}

export default function App() {
  const [{ tab, lid }, setView] = useState(readHash)
  useEffect(() => {
    const h = `#${tab}${lid ? `?p=${lid}` : ''}`
    if (location.hash !== h) history.replaceState(null, '', h)
  }, [tab, lid])
  const [tick, setTick] = useState(0)
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), REFRESH_MS); return () => clearInterval(t) }, [])
  const index = useFetch((s) => api.index(s), [], tick)
  const points = index.data?.points ?? []
  const current = lid ?? points.find((p) => p.scored)?.lid ?? null
  const point = useFetch((s) => (current ? api.point(current, s) : Promise.resolve(null)), [current], tick)
  const here = points.find((p) => p.lid === current)
  const pick = (p: string) => setView({ tab: 'forecast', lid: p })
  const day = recordDay(index.data?.record_start ?? null)
  return (
    <div className="wrap">
      <header className="top">
        <div className="brand"><h1>hapi</h1><span className="sub">California reservoir inflow and river flood forecasts, scored in public</span></div>
        <span className="stamp"><i className={`live${index.error ? ' stale' : ''}`} />{index.data ? `day ${day} · built ${index.data.built.slice(0, 16)}Z` : index.error ? `data: ${index.error}` : 'loading'}</span>
      </header>
      <nav className="tabs">{TABS.map((t) => <button key={t.id} className={`tab${t.id === tab ? ' active' : ''}`} onClick={() => setView({ tab: t.id, lid })}>{t.label}</button>)}</nav>
      {tab === 'forecast' && (<>
        <section className="panel">
          <div className="panel-h">
            <h2>Points</h2>
            <label className="picker">
              <select value={current ?? ''} onChange={(e) => pick(e.target.value)}>
                <optgroup label="Reservoir inflow">{points.filter((p) => p.kind === 'reservoir').map((p) => <option key={p.lid} value={p.lid}>{p.name} · {p.lid}{p.scored ? '' : ' (not scored)'}</option>)}</optgroup>
                <optgroup label="Flood gauges">{points.filter((p) => p.kind === 'gauge').map((p) => <option key={p.lid} value={p.lid}>{p.name} · {p.lid}</option>)}</optgroup>
              </select>
            </label>
          </div>
          <div className="pgrid">
            <PointMap points={points} selected={current} onSelect={pick} tick={tick} />
            {point.data ? <PointCard point={point.data} /> : <p className="note">{point.error ?? 'Loading…'}</p>}
          </div>
        </section>
        {point.data && <WeatherPane point={point.data} />}
        {here && <SatellitePane point={here} />}
      </>)}
      {tab === 'lab' && (index.data ? <LabPane index={index.data} onPick={pick} /> : <section className="panel"><p className="note">{index.error ?? 'Loading…'}</p></section>)}
      <footer>
        Archive, observations, forecasts and scores: the <a href="https://github.com/sotarolab/hapi/tree/data">data branch</a> of
        <a href="https://github.com/sotarolab/hapi"> hapi</a>. Official products from CNRFC (HEFS) and NWS (NWPS); observed inflow from CDEC.
        Models are issued before the outcome exists and never revised. Weather forecasts from <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0);
        satellite loops from NOAA STAR, radar from the NWS and the Iowa Environmental Mesonet.
      </footer>
    </div>
  )
}

function PointCard({ point }: { point: PointData }) {
  const [log, setLog] = useState(true)
  const models = Object.entries(point.models)
  const last = point.obs.at(-1)
  const alerts = point.alerts ?? []
  const now = point.live ? latest(point.live) : null
  const peak = point.official ? Math.max(...point.official.flow_cfs.filter((v): v is number => v != null), 0) : null
  const where = (cfs: number | null) => { const c = category(cfs, alerts); return c ? ` · ${c}` : '' }
  return (
    <div>
      <div className="panel-h">
        <div>
          <div className="row">
            <span className="headline" style={{ margin: 0 }}>{point.name}</span>
            <span className="pill">{point.kind === 'reservoir' ? 'reservoir inflow' : 'flood gauge'}</span>
            {!point.scored && <span className="pill warn">not scored</span>}
          </div>
          <span className="stamp">{point.lid}{point.cdec ? ` · CDEC ${point.cdec}` : ''}{point.usgs ? ` · USGS ${point.usgs}` : ''}</span>
        </div>
        <div className="seg"><button className={log ? 'on' : ''} onClick={() => setLog(true)}>log</button><button className={!log ? 'on' : ''} onClick={() => setLog(false)}>linear</button></div>
      </div>
      <div className="tiles">
        {last && <div className="tile"><span className="eyebrow">Observed {dayLabel(last[0])}</span><b className="num">{fmtFlow(last[1])} cfs</b><p className="note">CDEC daily mean inflow</p></div>}
        {now && <div className="tile"><span className="eyebrow">Hourly, {now.when}</span><b className="num">{fmtFlow(now.cfs)} cfs</b><p className="note">{point.live!.source}{where(now.cfs)}</p></div>}
        {point.hefs && <div className="tile"><span className="eyebrow">HEFS median, day 1</span><b className="num">{fmtFlow(point.hefs.p50[1])} cfs</b><p className="note">5-95%: {fmtFlow(point.hefs.p05[1])} to {fmtFlow(point.hefs.p95[1])} · issued {point.hefs.issued.slice(0, 8)}</p></div>}
        {models.map(([name, m], i) => <div key={name} className="tile"><span className="eyebrow" style={{ color: `var(${MODEL_VARS[i % MODEL_VARS.length]})` }}>{name}, day 1</span><b className="num">{fmtFlow(m.q50[0])} cfs</b><p className="note">5-95%: {fmtFlow(m.q05[0])} to {fmtFlow(m.q95[0])} · issued {m.issued}</p></div>)}
        {point.official && <div className="tile"><span className="eyebrow">NWS official peak</span><b className="num">{fmtFlow(peak)} cfs</b><p className="note">issued {point.official.issued?.slice(0, 16)}Z{where(peak)}</p></div>}
      </div>
      <PointChart point={point} log={log} />
      <div className="legend">
        <span><i style={{ background: 'var(--obs)' }} />Observed{point.live ? ', daily and hourly' : ''}</span>
        {alerts.some((a) => a.cfs != null) && <span><i style={{ background: 'var(--warn)' }} />NWS flood categories: {alerts.map((a) => `${a.label.toLowerCase()} ${a.ft} ft`).join(', ')}</span>}
        {point.hefs && <span><i className="band" style={{ background: 'var(--cool)' }} />HEFS 5-95% / 25-75%, median</span>}
        {models.map(([name], i) => <span key={name}><i className="band" style={{ background: `var(${MODEL_VARS[i % MODEL_VARS.length]})` }} />{name} 5-95% / 25-75%, median</span>)}
        {point.official && <span><i style={{ background: 'var(--official)' }} />NWS official (hourly)</span>}
      </div>
      {point.note && <p className="note">{point.note}</p>}
    </div>
  )
}
