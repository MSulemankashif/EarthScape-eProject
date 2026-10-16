/**
 * Dashboard - the friendly "how is our planet doing?" home screen.
 * KPI cards, a customizable trend chart (pick any metric), the latest
 * reading per station, and a guided 3-step first run.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import StatCard from '../components/StatCard.jsx'
import { PageHeader, greetingFor } from '../components/Layout.jsx'
import { Spinner, EmptyState } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const CHART_METRICS = [
  { key: 'temperature_c', label: 'Temperature', unit: '°C', color: '#5aabff' },
  { key: 'co2_ppm', label: 'CO₂', unit: 'ppm', color: '#ffb45c' },
  { key: 'pm25', label: 'PM2.5', unit: 'µg/m³', color: '#ff6b7a' },
  { key: 'rainfall_mm', label: 'Rainfall', unit: 'mm', color: '#4fd1c5' },
  { key: 'humidity_pct', label: 'Humidity', unit: '%', color: '#46d9a3' },
  { key: 'sea_level_mm', label: 'Sea level', unit: 'mm', color: '#c084fc' },
]

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [trend, setTrend] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [metric, setMetric] = useState('temperature_c')
  const toast = useToast()

  const greeting = useMemo(() => greetingFor(new Date().getHours()), [])
  const activeMetric = CHART_METRICS.find((m) => m.key === metric) || CHART_METRICS[0]

  const load = async () => {
    try {
      const [s, h] = await Promise.all([
        api.get('/analytics/summary'),
        api.get('/health'),
      ])
      setSummary(s.data)
      setHealth(h.data)
      if (s.data.available) {
        const t = await api.get(`/analytics/timeseries?metric=${metric}&months=36`)
        setTrend(t.data)
      } else {
        setTrend(null)
      }
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not reach the backend' })
    } finally {
      setLoading(false)
    }
  }

  /* Reload just the chart when the metric changes */
  useEffect(() => {
    if (!summary?.available) return
    api.get(`/analytics/timeseries?metric=${metric}&months=36`)
      .then(({ data }) => setTrend(data))
      .catch((err) => toast.error(errorMessage(err)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric])

  const ingest = async () => {
    setBusy(true)
    const started = Date.now()
    try {
      const { data } = await api.post('/data/ingest')
      const rows = data.results.reduce((a, r) => a + (r.rows_ingested || 0), 0)
      const secs = ((Date.now() - started) / 1000).toFixed(1)
      toast.success(
        `${rows.toLocaleString()} rows loaded across ${data.results.length} datasets in ${secs}s`,
        { title: 'Ingestion complete' },
      )
      await load()
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Ingestion failed' })
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const avg = summary?.averages || {}

  if (loading) {
    return <Spinner label="Waking up the dashboard…" />
  }

  return (
    <div>
      <PageHeader
        title={`${greeting.text}, ${greeting.icon}`}
        wave
        subtitle={summary?.available
          ? `Here's how our planet is doing today — ${summary.stations} stations reporting `
            + `· ${summary.total_readings.toLocaleString()} readings · `
            + `${summary.date_range.start} → ${summary.date_range.end}`
          : 'Your climate warehouse is warmed up and waiting for its first dataset.'}
        actions={(
          <>
            <span className="status-chip" title="API backend">
              <span className="dot" aria-hidden="true" />
              {health?.storage_backend || '…'} · {health?.database_backend || '…'}
            </span>
            <button className="btn btn-warm" onClick={ingest} disabled={busy}>
              {busy
                ? <><span className="spinner spinner-sm" aria-hidden="true" /> Loading data…</>
                : '⚙️ Load climate data'}
            </button>
          </>
        )}
      />

      {!summary?.available && (
        <EmptyState
          emoji="🌱"
          title="Let's fill your warehouse"
        >
          <p>
            Three quick steps and every chart, model and alert on this platform comes alive.
            It takes about ten seconds.
          </p>
          <div className="steps">
            <div className="step">
              <span className="step-num">1</span>
              <strong>Load the data</strong>
              <span>Press “Load climate data” above — raw CSVs get cleaned and stored in HDFS-style partitions.</span>
            </div>
            <div className="step">
              <span className="step-num">2</span>
              <strong>Train the models</strong>
              <span>Head to Analytics &amp; ML and train the anomaly + trend detectors.</span>
            </div>
            <div className="step">
              <span className="step-num">3</span>
              <strong>Watch it live</strong>
              <span>Start the Live Stream simulator and see readings turn into alerts in real time.</span>
            </div>
          </div>
        </EmptyState>
      )}

      {summary?.available && (
        <>
          <div className="stat-grid">
            <StatCard label="Avg Temperature" value={`${avg.temperature_c} °C`} icon="🌡️" />
            <StatCard label="Avg CO₂" value={`${avg.co2_ppm} ppm`} icon="🌫️" />
            <StatCard label="Avg PM2.5" value={`${avg.pm25} µg/m³`} icon="🍃" />
            <StatCard label="Avg Rainfall" value={`${avg.rainfall_mm} mm`} icon="🌧️" />
            <StatCard label="Missing Values" value={summary.missing_values} icon="⚠️" />
            <StatCard label="Storage" value={health?.storage_backend || '—'} icon="💾" />
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>
                {activeMetric.label} trend
                <span className="muted" style={{ fontWeight: 400 }}> · monthly average, last 3 years</span>
              </h3>
              <label className="muted" style={{ margin: 0 }}>
                Metric
                <select value={metric} onChange={(e) => setMetric(e.target.value)}
                  aria-label="Choose chart metric"
                  style={{ width: 'auto', marginLeft: 8, marginTop: 0 }}>
                  {CHART_METRICS.map((m) => (
                    <option key={m.key} value={m.key}>{m.label} ({m.unit})</option>
                  ))}
                </select>
              </label>
            </div>
            {trend?.points?.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trend.points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
                  <XAxis dataKey="date" stroke="#93a5bf" fontSize={12} />
                  <YAxis stroke="#93a5bf" fontSize={12} />
                  <Tooltip contentStyle={{
                    background: '#1c2434', border: '1px solid #2b3850',
                    borderRadius: 10,
                  }} />
                  <Line type="monotone" dataKey="value" stroke={activeMetric.color}
                    strokeWidth={2.4} dot={false} name={activeMetric.unit} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="muted">No monthly data for this metric yet.</p>
            )}
          </div>

          <div className="card">
            <h3>Latest reading per station</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Station</th><th>City</th><th>Temp °C</th>
                    <th>CO₂ ppm</th><th>PM2.5</th><th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.latest_by_station.map((r) => (
                    <tr key={r.station_id}>
                      <td>{r.station_id}</td>
                      <td>{r.city}</td>
                      <td>{r.temperature_c ?? '—'}</td>
                      <td>{r.co2_ppm ?? '—'}</td>
                      <td className={r.pm25 > 150 ? 'danger-text' : ''}>
                        {r.pm25 ?? '—'}
                      </td>
                      <td>{r.date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
