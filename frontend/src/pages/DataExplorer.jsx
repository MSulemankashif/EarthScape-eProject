/**
 * DataExplorer - browse the partitioned historical dataset with filters
 * (station, date range) and server-side pagination. Shows dataset catalog
 * from the ingestion pipeline.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errorMessage } from '../api/client.js'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner } from '../components/ui.jsx'

export default function DataExplorer() {
  const [datasets, setDatasets] = useState([])
  const [stations, setStations] = useState([])
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
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

  const loadRows = async (pageNr = page, f = filters) => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: pageNr, size: 50 })
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

  useEffect(() => { loadMeta(); loadRows(1, { station: '', start: '', end: '' }) }, [])

  const applyFilters = (e) => {
    e.preventDefault()
    setPage(1)
    loadRows(1, filters)
  }

  const goto = (p) => { setPage(p); loadRows(p) }

  return (
    <div>
      <PageHeader
        title="Data Explorer"
        subtitle="Browse the raw climate archive exactly as it sits in HDFS-style partitions — filter by station or date range and page through millions of rows."
      />

      {error && <div className="alert alert-error">{error}</div>}

      <div className="stat-grid">
        {datasets.length === 0 && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <p className="muted">No datasets yet — head to the{' '}
              <Link to="/">Dashboard</Link> and press “Load climate data” to fill the warehouse.</p>
          </div>
        )}
        {datasets.map((d) => (
          <div className="stat-card" key={d.name}>
            <span className="stat-icon">🗂️</span>
            <div>
              <p className="stat-label">{d.name}</p>
              <p className="stat-value">{d.rows?.toLocaleString()} rows</p>
              <p className="muted">{d.partition_count} partitions ·{' '}
                {(d.size_bytes / 1024).toFixed(0)} KB</p>
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
            Readings
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
                  <th>Temp °C</th><th>Humidity %</th><th>Rain mm</th>
                  <th>CO₂</th><th>PM2.5</th><th>Wind</th><th>Sea mm</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.date}</td>
                    <td>{r.station_id}</td>
                    <td>{r.city}</td>
                    <td><span className="tag">{r.region}</span></td>
                    <td>{r.temperature_c ?? '—'}</td>
                    <td>{r.humidity_pct ?? '—'}</td>
                    <td>{r.rainfall_mm ?? '—'}</td>
                    <td>{r.co2_ppm ?? '—'}</td>
                    <td className={r.pm25 > 150 ? 'danger-text' : ''}>{r.pm25 ?? '—'}</td>
                    <td>{r.wind_speed_kph ?? '—'}</td>
                    <td>{r.sea_level_mm ?? '—'}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={11} className="muted">
                    No rows match these filters — try widening the dates or picking
                    “All stations”.
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
