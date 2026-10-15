/**
 * Forecasts - trend prediction charts. Pick a metric and horizon, the
 * trained linear+seasonal model projects future values.
 */
import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'

const METRICS = ['temperature_c', 'co2_ppm', 'rainfall_mm']
const HORIZONS = [30, 90, 180, 365]

export default function Forecasts() {
  const [metric, setMetric] = useState('temperature_c')
  const [days, setDays] = useState(90)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await api.get(`/analytics/ml/forecast?metric=${metric}&days=${days}`)
      setData(data)
    } catch (err) {
      setData(null)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { load() }, [metric, days])

  const s = data?.summary

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Trend Forecasts</h2>
          <p className="muted">ML trend models project climate metrics into the
            future (linear trend + annual seasonality).</p>
        </div>
        <div className="header-actions">
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {HORIZONS.map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}

      {s && (
        <div className="stat-grid">
          <div className="stat-card">
            <span className="stat-icon">📈</span>
            <div>
              <p className="stat-label">Trend direction</p>
              <p className="stat-value">{s.direction}</p>
            </div>
          </div>
          <div className="stat-card">
            <span className="stat-icon">📐</span>
            <div>
              <p className="stat-label">Slope per year</p>
              <p className="stat-value">{s.slope_per_year}</p>
            </div>
          </div>
          <div className="stat-card">
            <span className="stat-icon">🎯</span>
            <div>
              <p className="stat-label">Model fit (R²)</p>
              <p className="stat-value">{s.r2}</p>
            </div>
          </div>
          <div className="stat-card">
            <span className="stat-icon">🗓️</span>
            <div>
              <p className="stat-label">Trained until</p>
              <p className="stat-value">{s.trained_until}</p>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h3>{metric} — next {days} days {busy && <span className="muted">loading…</span>}</h3>
        {data?.forecast?.length > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={data.forecast}>
              <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
              <XAxis dataKey="date" stroke="#8aa0b8" fontSize={11} />
              <YAxis stroke="#8aa0b8" fontSize={12} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#16213a', border: '1px solid #2c3e57' }} />
              <Line type="monotone" dataKey={metric} stroke="#ff9f43"
                strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="muted">Train the ML models on the Analytics page first.</p>
        )}
      </div>
    </div>
  )
}
