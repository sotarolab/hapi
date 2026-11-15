import { useState } from 'react'
import type { Cell, Index } from '../api'
import { pct, recordDay, skill } from '../lib/skill'

const products = (cells: Cell[]) => [...new Set(cells.map((c) => c.product))]

/** The verification: day N of the public record, then every product's CRPS by lead against persistence and
 *  climatology, and the same per point. Cells under the minimum number of forecast-days are shown dimmed. */
export function LabPane({ index, onPick }: { index: Index; onPick: (lid: string) => void }) {
  const { by_lead, by_point } = index.scores
  const prods = products(by_lead)
  const [product, setProduct] = useState<string | null>(null)
  const active = product && prods.includes(product) ? product : prods[0] ?? null
  const day = recordDay(index.record_start)
  const scoredDays = by_lead.filter((c) => c.lead === 1).reduce((s, c) => s + c.n, 0)
  const names = new Map(index.points.map((p) => [p.lid, p.name]))
  return (
    <>
      <section className="panel">
        <div className="panel-h"><h2>The record</h2><span className="stamp">built {index.built}</span></div>
        <p className="headline">
          {day ? `Day ${day} of a public forecast record. ` : 'The record has not started. '}
          {scoredDays ? `${scoredDays.toLocaleString('en-US')} lead-1 forecast-days scored so far.` : 'No forecast-day has an observation yet; scores appear once the first forecast days pass.'}
        </p>
        <div className="tiles">
          <div className="tile"><span className="eyebrow">Record since</span><b className="num">{index.record_start ? `${index.record_start.slice(0, 4)}-${index.record_start.slice(4, 6)}-${index.record_start.slice(6, 8)}` : '–'}</b><p className="note">UTC, first archived ensemble</p></div>
          <div className="tile"><span className="eyebrow">Archive days</span><b className="num">{index.archive_days}</b><p className="note">days with at least one capture</p></div>
          <div className="tile"><span className="eyebrow">Products</span><b className="num">{prods.length || '–'}</b><p className="note">{prods.join(', ') || 'HEFS and models once scored'}</p></div>
          <div className="tile"><span className="eyebrow">Points scored</span><b className="num">{index.points.filter((p) => p.scored).length}</b><p className="note">of {index.points.length} archived</p></div>
        </div>
        <p className="note">
          Every forecast is archived before its outcome exists and scored against the observation when it arrives:
          fair CRPS in cfs, against persistence (yesterday's observed inflow) and day-of-year climatology (all prior years).
          Skill is 1 minus the ratio of CRPS to the reference. Groups under {index.min_pairs} forecast-days are dimmed;
          no product is called best until the leads it leads on clear that count.
        </p>
      </section>
      <section className="panel">
        <div className="panel-h">
          <h2>Scorecard by lead</h2>
          {prods.length > 1 && (
            <div className="seg">{prods.map((p) => <button key={p} className={p === active ? 'on' : ''} onClick={() => setProduct(p)}>{p}</button>)}</div>
          )}
        </div>
        {active ? <ScoreTable cells={by_lead.filter((c) => c.product === active)} keyCol="lead" keyLabel="Lead (days)" /> : <p className="note">Nothing scored yet.</p>}
      </section>
      <section className="panel">
        <div className="panel-h"><h2>Scorecard by point</h2><span className="stamp">leads 1-14 pooled</span></div>
        {active ? (
          <ScoreTable cells={by_point.filter((c) => c.product === active)} keyCol="lid" keyLabel="Point"
            label={(k) => `${names.get(String(k)) ?? k} · ${k}`} onPick={(k) => onPick(String(k))} />
        ) : <p className="note">Nothing scored yet.</p>}
      </section>
    </>
  )
}

function ScoreTable({ cells, keyCol, keyLabel, label, onPick }: {
  cells: Cell[]; keyCol: 'lead' | 'lid'; keyLabel: string; label?: (k: string | number) => string; onPick?: (k: string | number) => void
}) {
  if (!cells.length) return <p className="note">Nothing scored yet for this product.</p>
  return (
    <div className="scroll">
      <table className="grid">
        <thead><tr><th>{keyLabel}</th><th className="r">n</th><th className="r">CRPS</th><th className="r">vs persistence</th><th className="r">vs climatology</th><th className="r">90% coverage</th></tr></thead>
        <tbody>
          {cells.map((c) => {
            const k = c[keyCol] as string | number
            return (
              <tr key={String(k)} className={c.thin ? 'thin' : ''}>
                <td className={onPick ? 'pick' : ''} onClick={onPick ? () => onPick(k) : undefined}>{label ? label(k) : k}</td>
                <td className="r num">{c.n}</td>
                <td className="r num">{c.crps.toLocaleString('en-US')}</td>
                <td className="r num">{pct(skill(c.crps, c.crps_persistence))}</td>
                <td className="r num">{pct(skill(c.crps, c.crps_climatology))}</td>
                <td className="r num">{pct(c.cov90)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
