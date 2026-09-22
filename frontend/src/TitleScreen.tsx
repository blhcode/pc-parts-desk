import { useEffect, useState } from 'react'
import { api, type SaveSummary } from './api'

function stars(n: number) {
  const full = Math.round(n)
  return '★'.repeat(Math.max(0, Math.min(5, full))) + '☆'.repeat(Math.max(0, 5 - full))
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

type Props = {
  onLoad: (saveId: string) => void
}

export function TitleScreen({ onLoad }: Props) {
  const [saves, setSaves] = useState<SaveSummary[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function refresh() {
    const data = await api.listSaves()
    setSaves(data.saves)
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e.message || e)))
  }, [])

  async function create() {
    setBusy(true)
    setError('')
    try {
      const save = (await api.createSave(name.trim())) as { id: string }
      await api.loadSave(save.id)
      onLoad(save.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function load(id: string) {
    setBusy(true)
    setError('')
    try {
      await api.loadSave(id)
      onLoad(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: string) {
    if (!confirm('Delete this save?')) return
    setBusy(true)
    try {
      await api.deleteSave(id)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="title-screen">
      <div className="title-card">
        <h1>PC Parts Desk</h1>
        <p className="subtitle">Run your PC building shop from an email inbox.</p>
        {error && <div className="error-banner">{error}</div>}

        <div className="save-list">
          {saves.length === 0 && (
            <p className="hint">No saves yet — name your shop to open for business.</p>
          )}
          {saves.map((s) => (
            <div key={s.id} className={`save-row ${s.status === 'game_over' ? 'closed' : ''}`}>
              <div className="save-meta">
                <strong>
                  {s.shop_name}
                  {s.status === 'game_over' ? ' — Closed' : ''}
                </strong>
                <span>
                  <span className="stars">{stars(s.shop_rating)}</span> {s.shop_rating.toFixed(1)} ·{' '}
                  {s.jobs_completed} jobs · rep {s.reputation}
                  <br />
                  Last played {fmtDate(s.last_played)}
                  {s.game_over_reason ? ` · ${s.game_over_reason}` : ''}
                </span>
              </div>
              <div className="save-actions">
                <button className="btn btn-primary" disabled={busy} onClick={() => load(s.id)}>
                  {s.status === 'game_over' ? 'Review' : 'Continue'}
                </button>
                <button className="btn btn-danger" disabled={busy} onClick={() => remove(s.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>

        {saves.length < 5 && (
          <div className="new-save">
            <input
              placeholder="New shop name…"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && name.trim() && create()}
              maxLength={64}
            />
            <button className="btn btn-primary" disabled={busy || !name.trim()} onClick={create}>
              New Save
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
