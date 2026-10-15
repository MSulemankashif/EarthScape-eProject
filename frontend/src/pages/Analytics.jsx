/**
 * Analytics - MapReduce job runner + ML model training + correlation matrix.
 */
import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

export default function Analytics() {
  const { isAdmin } = useAuth()
  const [jobs, setJobs] = useState([])
  const [jobResult, setJobResult] = useState(null)
  const [mlStatus, setMlStatus] = useState(null)
  const [mlResult, setMlResult] = useState(null)
  const [corr, setCorr] = useState(null)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    try {
      const [j, m] = await Promise.all([
        api.get('/analytics/jobs'),
        api.get('/analytics/ml/status'),
      ])
      setJobs(j.data.jobs)
      setMlStatus(m.data)
      const c = await api.get('/analytics/correlation')
      setCorr(c.data)
    } catch (err) {
      setNotice(errorMessage(err))
    }
  }

  useEffect(() => { load() }, [])

  const runJob = async (name) => {
    setBusy(name)
    setNotice('')
    try {
      const { data } = await api.post('/analytics/jobs/run', { job: name })
      setJobResult(data)
    } catch (err) {
      setNotice(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  const trainModels = async () => {
    setBusy('train')
    setNotice('')
    try {
      const { data } = await api.post('/analytics/ml/train')
      setMlResult(data)
      setNotice(data.message)
      const m = await api.get('/analytics/ml/status')
      setMlStatus(m.data)
    } catch (err) {
      setNotice(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  const relBars = (corr?.top_relationships || []).map((r) => ({
    name: `${short(r.variable_a)}×${short(r.variable_b)}`,
    r: Math.round(Math.abs(r.pearson_r) * 100),
  }))
  const short = (s) => s.replace(/_pct|_ppm|_mm|_kph|_c$/, '').slice(0, 8)

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Analytics & Machine Learning</h2>
          <p className="muted">Hadoop MapReduce jobs + predictive ML models.</p>
        </div>
        <button className="btn btn-primary" onClick={trainModels}
          disabled={busy === 'train'}>
          {busy === 'train' ? 'Training…' : '🧠 Train ML Models'}
        </button>
      </header>

      {notice && <div className="alert alert-info">{notice}</div>}

      <div className="grid-2">
        <div className="card">
          <h3>MapReduce Jobs</h3>
          {jobs.map((job) => (
            <div className="job-row" key={job.name}>
              <div>
                <strong>{job.name}</strong>
                <p className="muted">{job.description} · mapper {job.mapper} → reducer {job.reducer}</p>
              </div>
              <button className="btn btn-outline btn-sm"
                disabled={busy === job.name}
                onClick={() => runJob(job.name)}>
                {busy === job.name ? 'Running…' : 'Run'}
              </button>
            </div>
          ))}

          {jobResult && (
            <>
              <p className="muted">{jobResult.message}</p>
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
          <h3>ML Models</h3>
          <div className="model-status">
            <span className={mlStatus?.anomaly_model_trained ? 'tag tag-ok' : 'tag'}>
              Anomaly detector: {mlStatus?.anomaly_model_trained ? 'trained ✅' : 'not trained'}
            </span>
            {Object.entries(mlStatus?.trend_models || {}).map(([metric, s]) => (
              <span className="tag tag-ok" key={metric}>
                {metric}: {s.direction} {s.slope_per_year > 0 ? '↑' : '↓'} {Math.abs(s.slope_per_year)}/yr (R² {s.r2})
              </span>
            ))}
          </div>

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
                        <th>CO₂</th><th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mlResult.recent_anomalies.slice(0, 10).map((a, i) => (
                        <tr key={i}>
                          <td>{a.station_id}</td>
                          <td>{a.date?.slice(0, 10)}</td>
                          <td>{a.temperature_c}</td>
                          <td>{a.pm25}</td>
                          <td>{a.co2_ppm}</td>
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

      {relBars.length > 0 && (
        <div className="card">
          <h3>Strongest Climate Correlations (|Pearson r| ×100)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={relBars} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
              <XAxis type="number" stroke="#8aa0b8" fontSize={12} domain={[0, 100]} />
              <YAxis type="category" dataKey="name" stroke="#8aa0b8" fontSize={12} width={110} />
              <Tooltip contentStyle={{ background: '#16213a', border: '1px solid #2c3e57' }} />
              <Bar dataKey="r" fill="#4da3ff" radius={[0, 6, 6, 0]} />
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
