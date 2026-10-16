/**
 * Analytics - MapReduce job runner + ML model training + correlation matrix.
 * Friendly copy, live toasts, duration + model-freshness feedback.
 */
import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, EmptyState } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

function freshnessLabel(fresh) {
  if (!fresh?.trained_at) return null
  const mins = Math.max(0, Math.round((Date.now() - new Date(fresh.trained_at)) / 60000))
  const when = mins < 1 ? 'just now'
    : mins < 60 ? `${mins} min ago`
      : `${Math.round(mins / 60)} h ago`
  return `trained ${when} on ${fresh.rows_used.toLocaleString()} rows`
}

export default function Analytics() {
  const [jobs, setJobs] = useState(null)
  const [jobResult, setJobResult] = useState(null)
  const [zscore, setZscore] = useState(2)       // anomaly sensitivity
  const [mlStatus, setMlStatus] = useState(null)
  const [mlResult, setMlResult] = useState(null)
  const [corr, setCorr] = useState(null)
  const [busy, setBusy] = useState('')
  const toast = useToast()

  const load = async () => {
    try {
      const [j, m] = await Promise.all([
        api.get('/analytics/jobs'),
        api.get('/analytics/ml/status'),
      ])
      setJobs(j.data.jobs)
      setMlStatus(m.data)
      // Correlation needs live data — a friendly 400 must not blank the page.
      try {
        const c = await api.get('/analytics/correlation')
        setCorr(c.data)
      } catch {
        setCorr(null)
      }
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not load analytics' })
      setJobs([])
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const runJob = async (name) => {
    setBusy(name)
    try {
      const { data } = await api.post('/analytics/jobs/run',
        { job: name, zscore: Number(zscore) })
      setJobResult(data)
      toast.success(
        `${data.rows.toLocaleString()} rows in ${data.duration_seconds}s`,
        { title: `MapReduce · ${name}` },
      )
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Job failed' })
    } finally {
      setBusy('')
    }
  }

  const trainModels = async () => {
    setBusy('train')
    try {
      const { data } = await api.post('/analytics/ml/train')
      setMlResult(data)
      toast.success(
        `${data.anomalies_detected} anomalies found · trained in ${data.freshness.duration_seconds}s`,
        { title: 'Models are ready 🧠' },
      )
      if (data.metrics_without_enough_data?.length) {
        toast.info(
          `${data.metrics_without_enough_data.map((m) => m.metric).join(', ')} `
          + 'need ≥ 30 days of live history before a trend can be fitted — '
          + 'the real 5-day OpenWeather forecast covers near-term needs.',
          { title: 'Trend models: more history needed' },
        )
      }
      const m = await api.get('/analytics/ml/status')
      setMlStatus(m.data)
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Training failed' })
    } finally {
      setBusy('')
    }
  }

  const relBars = (corr?.top_relationships || []).map((r) => ({
    name: `${short(r.variable_a)}×${short(r.variable_b)}`,
    r: Math.round(Math.abs(r.pearson_r) * 100),
  }))
  const short = (s) => s.replace(/_pct|_ppm|_mm|_kph|_c$/, '').slice(0, 8)
  const fresh = freshnessLabel(mlStatus?.freshness)

  return (
    <div>
      <PageHeader
        title="Analytics & Machine Learning"
        subtitle="Run Hadoop MapReduce jobs over your live OpenWeather export, train the ML models on real readings, and discover how climate variables move together."
        actions={(
          <button className="btn btn-primary" onClick={trainModels}
            disabled={busy === 'train'}>
            {busy === 'train'
              ? <><span className="spinner spinner-sm" aria-hidden="true" /> Training…</>
              : '🧠 Train ML Models'}
          </button>
        )}
      />

      {jobs === null && <Spinner label="Fetching jobs & model status…" />}

      {jobs !== null && (
        <div className="grid-2">
          <div className="card">
            <h3>MapReduce jobs</h3>
            <p className="muted" style={{ marginTop: -4 }}>
              Jobs read your live export <code>data/processed/openweather_current.csv</code>{' '}
              automatically — or pass any CSV via the API.
            </p>
            {jobs.length === 0 && (
              <p className="muted">No jobs registered — they ship with the platform, try a refresh.</p>
            )}
            <div className="live-meta" style={{ marginBottom: 8 }}>
              <label className="muted" style={{ margin: 0 }}>
                Anomaly sensitivity (z-score)
                <select value={zscore} onChange={(e) => setZscore(e.target.value)}
                  aria-label="Anomaly z-score threshold"
                  style={{ width: 'auto', marginLeft: 8, marginTop: 0 }}>
                  <option value={1.5}>1.5 · sensitive</option>
                  <option value={2}>2.0 · balanced</option>
                  <option value={2.5}>2.5 · strict</option>
                  <option value={3}>3.0 · conservative</option>
                </select>
              </label>
              <span className="muted">lower = more anomalies flagged</span>
            </div>
            {jobs.map((job) => (
              <div className="job-row" key={job.name}>
                <div>
                  <strong>{job.name}</strong>
                  <p className="muted">{job.description} · mapper {job.mapper} → reducer {job.reducer}</p>
                </div>
                <button className="btn btn-outline btn-sm"
                  disabled={busy === job.name}
                  onClick={() => runJob(job.name)}>
                  {busy === job.name
                    ? <><span className="spinner spinner-sm" aria-hidden="true" /> Running…</>
                    : '▶ Run'}
                </button>
              </div>
            ))}

            {jobResult && (
              <>
                <p className="muted">
                  {jobResult.message}{' '}
                  <span className="time-chip">⏱ {jobResult.duration_seconds}s</span>
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {Object.keys(jobResult.preview[0] || {}).map((k) => (
                          <th key={k}>{k}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {jobResult.preview.slice(0, 15).map((row, i) => (
                        <tr key={i}>
                          {Object.values(row).map((v, j) => (
                            <td key={j}>{typeof v === 'number' ? v.toFixed(2) : String(v)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>ML models</h3>
              {fresh && <span className="time-chip">🌱 {fresh}</span>}
            </div>
            <div className="model-status">
              <span className={mlStatus?.anomaly_model_trained ? 'tag tag-ok' : 'tag'}>
                Anomaly detector: {mlStatus?.anomaly_model_trained ? 'trained ✅' : 'not trained yet'}
              </span>
              {Object.entries(mlStatus?.trend_models || {}).map(([metric, s]) => (
                <span className="tag tag-ok" key={metric}>
                  {metric}: {s.direction} {s.slope_per_year > 0 ? '↑' : '↓'} {Math.abs(s.slope_per_year)}/yr (R² {s.r2})
                </span>
              ))}
            </div>

            {!mlStatus?.anomaly_model_trained && Object.keys(mlStatus?.trend_models || {}).length === 0 && (
              <p className="muted">
                No models trained yet. Press <strong>Train ML Models</strong> above — it
                only takes a few seconds.
              </p>
            )}

            {mlResult && (
              <div className="ml-result">
                <p><strong>Anomalies detected:</strong> {mlResult.anomalies_detected}
                  {' '}({(mlResult.anomaly_rate * 100).toFixed(2)}%)</p>
                {mlResult.recent_anomalies?.length > 0 && (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Station</th><th>Date</th><th>Temp</th><th>PM2.5</th>
                          <th>Wind</th><th>Score</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mlResult.recent_anomalies.slice(0, 10).map((a, i) => (
                          <tr key={i}>
                            <td>{a.station_id}</td>
                            <td>{a.date?.slice(0, 10)}</td>
                            <td>{a.temperature_c}</td>
                            <td>{a.pm25}</td>
                            <td>{a.wind_speed_kph ?? '—'}</td>
                            <td><span className="tag tag-warn">{a.anomaly_score}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {jobs !== null && relBars.length === 0 && (
        <EmptyState emoji="🔬" title="Correlations appear with data">
          <p>Once live weather syncs in, this card ranks every variable pair by
            Pearson correlation so you can spot relationships at a glance —
            metrics without live values (like outdoor CO₂) are skipped honestly.</p>
        </EmptyState>
      )}

      {relBars.length > 0 && (
        <div className="card">
          <h3>Strongest climate correlations (|Pearson r| ×100)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={relBars} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
              <XAxis type="number" stroke="#93a5bf" fontSize={12} domain={[0, 100]} />
              <YAxis type="category" dataKey="name" stroke="#93a5bf" fontSize={12} width={110} />
              <Tooltip contentStyle={{ background: '#1c2434', border: '1px solid #2b3850', borderRadius: 10 }} />
              <Bar dataKey="r" fill="#5aabff" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Variable A</th><th>Variable B</th><th>r</th>
                  <th>Strength</th><th>Direction</th></tr>
              </thead>
              <tbody>
                {(corr?.top_relationships || []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.variable_a}</td>
                    <td>{r.variable_b}</td>
                    <td>{r.pearson_r}</td>
                    <td><span className="tag">{r.strength}</span></td>
                    <td>{r.direction}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
