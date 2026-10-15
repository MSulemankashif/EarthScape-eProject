/**
 * Dashboard - KPI cards, national averages, station snapshot and the
 * monthly temperature trend chart. Also triggers data ingestion when the
 * storage is still empty.
 */
import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import StatCard from '../components/StatCard.jsx'

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [trend, setTrend] = useState(null)
  const [health, setHealth] = useState(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const [s, h] = await Promise.all([
        api.get('/analytics/summary'),
        api.get('/health'),
      ])
      setSummary(s.data)
      setHealth(h.data)
      if (s.data.available) {
        const t = await api.get('/analytics/timeseries?metric=temperature_c&months=36')
        setTrend(t.data)
      }
    } catch (err) {
      setNotice(errorMessage(err))
    }
  }

  const ingest = async () => {
    setBusy(true)
    setNotice('')
    try {
      const { data } = await api.post('/data/ingest')
      const rows = data.results.reduce((a, r) => a + (r.rows_ingested || 0), 0)
      setNotice(`Ingested ${rows} rows across ${data.results.length} datasets ✅`)
      await load()
    } catch (err) {
      setNotice(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { load() }, [])

  const avg = summary?.averages || {}

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Climate Overview</h2>
          <p className="muted">
            {summary?.available
              ? `${summary.stations} stations · ${summary.total_readings.toLocaleString()} readings · ${summary.date_range.start} → ${summary.date_range.end}`
              : 'No dataset loaded yet'}
          </p>
        </div>
        <button className="btn btn-primary" onClick={ingest} disabled={busy}>
          {busy ? 'Ingesting…' : '⚙ Run Ingestion Pipeline'}
        </button>
      </header>

      {notice && <div className="alert alert-info">{notice}</div>}

      {!summary?.available && (
        <div className="card empty-state">
          <h3>Welcome to EarthScape 👋</h3>
          <p>Click <strong>Run Ingestion Pipeline</strong> to load the climate
            datasets from the raw CSVs into HDFS-partitioned storage, then train
            the ML models from the Analytics page.</p>
        </div>
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

          {trend?.points?.length > 0 && (
            <div className="card">
              <h3>National Average Temperature (monthly)</h3>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trend.points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
                  <XAxis dataKey="date" stroke="#8aa0b8" fontSize={12} />
                  <YAxis stroke="#8aa0b8" fontSize={12} />
                  <Tooltip contentStyle={{ background: '#16213a', border: '1px solid #2c3e57' }} />
                  <Line type="monotone" dataKey="value" stroke="#4da3ff"
                    strokeWidth={2} dot={false} name="°C" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="card">
            <h3>Latest Reading per Station</h3>
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
