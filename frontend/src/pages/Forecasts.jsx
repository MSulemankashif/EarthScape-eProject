/**
 * Forecasts - trend prediction charts. Pick a metric and horizon, the
 * trained linear+seasonal model projects future values.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, EmptyState } from '../components/ui.jsx'

const METRICS = ['temperature_c', 'co2_ppm', 'rainfall_mm']
const HORIZONS = [30, 90, 180, 365]

const FRIENDLY = {
  temperature_c: 'Temperature',
  co2_ppm: 'CO₂',
  rainfall_mm: 'Rainfall',
}

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

  useEffect(() => { load() }, [metric, days]) // eslint-disable-line react-hooks/exhaustive-deps

  const s = data?.summary

  return (
    <div>
      <PageHeader
        title="Trend Forecasts"
        subtitle="The trained models stretch history into the future — linear trend plus annual seasonality, for any horizon up to two years."
        actions={(
          <>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}
              aria-label="Forecast metric">
              {METRICS.map((m) => (
                <option key={m} value={m}>{FRIENDLY[m] || m}</option>
              ))}
            </select>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}
              aria-label="Forecast horizon">
              {HORIZONS.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </>
        )}
      />

      {error && (
        <div className="alert alert-info">
          {error} — train the models on the <Link to="/analytics">Analytics page</Link> first.
        </div>
      )}

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
        <div className="card-head">
          <h3 style={{ margin: 0 }}>
            {FRIENDLY[metric] || metric} — next {days} days
          </h3>
          {busy && <span className="time-chip">🔮 projecting…</span>}
        </div>
        {data?.forecast?.length > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={data.forecast}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
              <XAxis dataKey="date" stroke="#93a5bf" fontSize={11} />
              <YAxis stroke="#93a5bf" fontSize={12} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#1c2434', border: '1px solid #2b3850', borderRadius: 10 }} />
              <Line type="monotone" dataKey={metric} stroke="#ffb45c"
                strokeWidth={2.4} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : busy ? (
          <Spinner label="Projecting the future…" />
        ) : (
          <EmptyState emoji="🔮" title="No forecast yet">
            <p>Train the trend models on the <Link to="/analytics">Analytics page</Link> —
              once they are fresh, every metric here can look months ahead.</p>
          </EmptyState>
        )}
      </div>
    </div>
  )
}
