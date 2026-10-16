/**
 * DataExplorer - browse the live OpenWeather data exactly as it sits in
 * HDFS-style partitions (station, date range, dataset, pagination).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errorMessage } from '../api/client.js'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, weatherEmoji } from '../components/ui.jsx'

const DATASETS = [
  { key: 'openweather_current', label: 'Current observations (live)' },
  { key: 'openweather_forecast', label: '5-day forecast (live)' },
]

export default function DataExplorer() {
  const [datasets, setDatasets] = useState([])
  const [stations, setStations] = useState([])
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [dataset, setDataset] = useState('openweather_current')
  const [filters, setFilters] = useState({ station: '', start: '', end: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const loadMeta = async () => {
    try {
      const [d, s] = await Promise.all([
        api.get('/data/datasets'),
        api.get('/data/stations'),
      ])
      setDatasets(d.data.datasets)
      setStations(s.data.stations)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const loadRows = async (pageNr = page, f = filters, ds = dataset) => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: pageNr, size: 50, dataset: ds })
      if (f.station) params.set('station', f.station)
      if (f.start) params.set('start', f.start)
      if (f.end) params.set('end', f.end)
      const { data } = await api.get(`/data/readings?${params}`)
      setRows(data.readings)
      setTotal(data.total)
      setPages(data.pages || 1)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadMeta(); loadRows(1, { station: '', start: '', end: '' }, dataset) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const applyFilters = (e) => {
    e.preventDefault()
    setPage(1)
    loadRows(1, filters, dataset)
  }

  const switchDataset = (ds) => {
    setDataset(ds)
    setPage(1)
    loadRows(1, filters, ds)
  }

  const goto = (p) => { setPage(p); loadRows(p, filters, dataset) }

  const isForecast = dataset === 'openweather_forecast'

  return (
    <div>
      <PageHeader
        title="Data Explorer"
        subtitle="Live OpenWeather data, exactly as it sits in HDFS-style year=/month= partitions — filter by station or date range and page through every reading."
        actions={(
          <select value={dataset} onChange={(e) => switchDataset(e.target.value)}
            aria-label="Choose dataset">
            {DATASETS.map((d) => (
              <option key={d.key} value={d.key}>{d.label}</option>
            ))}
          </select>
        )}
      />

      {error && <div className="alert alert-error">{error}</div>}

      <div className="stat-grid">
        {datasets.length === 0 && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <p className="muted">No live datasets yet — head to the{' '}
              <Link to="/">Dashboard</Link> and press “☁ Sync live weather” to fill the warehouse.</p>
          </div>
        )}
        {datasets.map((d) => (
          <div className="stat-card" key={d.name}>
            <span className="stat-icon">🗂️</span>
            <div>
              <p className="stat-label">{d.name}</p>
              <p className="stat-value">{d.rows?.toLocaleString()} rows</p>
              <p className="muted">{d.partition_count} partitions ·{' '}
                {(d.size_bytes / 1024).toFixed(0)} KB ·{' '}
                <span className="tag tag-info">Live · OpenWeather</span></p>
            </div>
          </div>
        ))}
      </div>

      <form className="filter-bar" onSubmit={applyFilters}>
        <select value={filters.station}
          onChange={(e) => setFilters({ ...filters, station: e.target.value })}>
          <option value="">All stations</option>
          {stations.map((s) => (
            <option key={s.station_id} value={s.station_id}>
              {s.station_id} — {s.city}
            </option>
          ))}
        </select>
        <input type="date" value={filters.start}
          onChange={(e) => setFilters({ ...filters, start: e.target.value })} />
        <input type="date" value={filters.end}
          onChange={(e) => setFilters({ ...filters, end: e.target.value })} />
        <button className="btn btn-primary">Apply</button>
      </form>

      <div className="card">
        <div className="card-head">
          <h3 style={{ margin: 0 }}>
            {isForecast ? 'Forecast readings' : 'Current readings'}
            {loading && <span className="muted"> · fetching…</span>}
          </h3>
          <span className="muted">{total.toLocaleString()} matching rows</span>
        </div>
        {loading ? (
          <Spinner label="Paging through the warehouse…" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th><th>Station</th><th>City</th><th>Region</th>
                  <th>Now</th><th>Temp °C</th><th>Humidity %</th><th>Rain mm</th>
                  {isForecast ? <th>Rain %</th> : <th>PM2.5</th>}
                  <th>Wind</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.date}</td>
                    <td>{r.station_id}</td>
                    <td>{r.city}</td>
                    <td><span className="tag">{r.region ?? '—'}</span></td>
                    <td>{weatherEmoji(r.weather_main)}</td>
                    <td>{r.temperature_c ?? '—'}</td>
                    <td>{r.humidity_pct ?? '—'}</td>
                    <td>{r.rainfall_mm ?? '—'}</td>
                    {isForecast ? (
                      <td>{Math.round((r.precipitation_prob ?? 0) * 100)}%</td>
                    ) : (
                      <td className={r.pm25 > 150 ? 'danger-text' : ''}>
                        {r.pm25 ?? '—'}
                      </td>
                    )}
                    <td>{r.wind_speed_kph ?? '—'}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={10} className="muted">
                    No rows match these filters — try widening the dates, picking
                    “All stations”, or syncing live weather first.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <div className="pager">
          <button className="btn btn-outline btn-sm" disabled={page <= 1}
            onClick={() => goto(page - 1)}>‹ Prev</button>
          <span className="muted">Page {page} of {pages || 1}</span>
          <button className="btn btn-outline btn-sm" disabled={page >= pages}
            onClick={() => goto(page + 1)}>Next ›</button>
        </div>
      </div>
    </div>
  )
}
