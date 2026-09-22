import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type Part,
  type ShopInfo,
  type Thread,
  type ThreadSummary,
} from './api'

function stars(n: number) {
  const full = Math.round(n)
  return '★'.repeat(Math.max(0, Math.min(5, full))) + '☆'.repeat(Math.max(0, 5 - full))
}

function fmtWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || '')
    .join('')
}

type Props = {
  onExit: () => void
}

export function Inbox({ onExit }: Props) {
  const [folder, setFolder] = useState('inbox')
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [shop, setShop] = useState<ShopInfo | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [thread, setThread] = useState<Thread | null>(null)
  const [error, setError] = useState('')
  const [pcppUrl, setPcppUrl] = useState('')
  const [partsText, setPartsText] = useState('')
  const [notes, setNotes] = useState('')
  const [previewParts, setPreviewParts] = useState<Part[] | null>(null)
  const [sending, setSending] = useState(false)
  const [gameOver, setGameOver] = useState(false)
  const [gameOverReason, setGameOverReason] = useState('')

  const refreshInbox = useCallback(async () => {
    const data = await api.inbox(folder)
    setThreads(data.threads)
    setShop(data.shop)
    if (data.shop.status === 'game_over') {
      setGameOver(true)
      setGameOverReason(data.shop.game_over_reason)
    }
  }, [folder])

  useEffect(() => {
    let alive = true
    const tick = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const hb = await api.heartbeat()
        if (!alive) return
        if (hb.game_over) {
          setGameOver(true)
          setGameOverReason(hb.reason || '')
        }
        await refreshInbox()
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      }
    }
    tick()
    const id = window.setInterval(tick, 5000)
    const onVis = () => {
      if (document.visibilityState === 'visible') tick()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      alive = false
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [refreshInbox])

  async function openThread(id: string) {
    setSelectedId(id)
    setError('')
    setPcppUrl('')
    setPartsText('')
    setNotes('')
    setPreviewParts(null)
    try {
      const t = await api.thread(id)
      setThread(t)
      await refreshInbox()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function previewList() {
    setError('')
    if (!pcppUrl.trim()) {
      setError('Paste a PCPartPicker list URL first')
      return
    }
    try {
      const r = await api.resolvePcpp(pcppUrl.trim())
      setPreviewParts(r.parts)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setPreviewParts(null)
    }
  }

  async function sendMessage() {
    if (!thread) return
    if (!notes.trim()) {
      setError('Write a message or question for the customer first')
      return
    }
    setSending(true)
    setError('')
    try {
      const result = await api.reply(thread.id, {
        notes: notes.trim(),
        mode: 'message',
      })
      setThread(result.thread)
      setShop(result.shop)
      setNotes('')
      await refreshInbox()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  async function sendReply() {
    if (!thread) return
    if (!pcppUrl.trim() && !partsText.trim()) {
      setError('Add a PCPartPicker link or pasted parts to send a final proposal')
      return
    }
    setSending(true)
    setError('')
    try {
      const result = await api.reply(thread.id, {
        pcpp_url: pcppUrl.trim() || undefined,
        parts_text: partsText.trim() || undefined,
        notes: notes.trim(),
        mode: 'proposal',
      })
      setThread(result.thread)
      setShop(result.shop)
      if (result.game_over) {
        setGameOver(true)
        setGameOverReason(result.shop.game_over_reason)
      }
      setPcppUrl('')
      setPartsText('')
      setNotes('')
      setPreviewParts(null)
      await refreshInbox()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  async function exit() {
    try {
      await api.unload()
    } catch {
      /* ignore */
    }
    onExit()
  }

  const readOnly = shop?.status === 'game_over' || gameOver

  return (
    <div className="mail-app">
      <header className="mail-top">
        <div className="logo">Mail</div>
        {shop && (
          <div className="shop-badge">
            <div>
              <div className="name">{shop.shop_name}</div>
              <div>
                <span className="stars">{stars(shop.shop_rating)}</span>
                <span className="rating-num">{shop.shop_rating.toFixed(1)}</span>
                <span className="breakdown">
                  {' '}
                  · Perf {shop.avg_performance.toFixed(1)} · Speed{' '}
                  {shop.avg_response_time.toFixed(1)} · Service {shop.avg_service.toFixed(1)} ·{' '}
                  {shop.jobs_completed} jobs · Rep {shop.reputation}
                </span>
              </div>
            </div>
          </div>
        )}
        <button className="btn btn-ghost" onClick={exit}>
          Exit to saves
        </button>
      </header>

      <nav className="sidebar">
        {(['inbox', 'sent', 'archive'] as const).map((f) => (
          <button
            key={f}
            className={`folder-btn ${folder === f ? 'active' : ''}`}
            onClick={() => {
              setFolder(f)
              setSelectedId(null)
              setThread(null)
            }}
          >
            {f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </nav>

      <div className="thread-list">
        {threads.length === 0 && (
          <div className="waiting">
            {folder === 'inbox'
              ? 'Inbox empty — customers will email while you are playing…'
              : 'No messages here.'}
          </div>
        )}
        {threads.map((t) => (
          <button
            key={t.id}
            className={`thread-row ${selectedId === t.id ? 'selected' : ''} ${t.unread ? 'unread' : ''} sla-${t.sla_stage}`}
            onClick={() => openThread(t.id)}
          >
            <div className="from">
              {initials(t.from_name)} · {t.from_name}
            </div>
            <div className="subject">{t.subject}</div>
            <div className="preview">{t.preview}</div>
            {t.sla_stage !== 'ok' && t.status === 'open' && (
              <span className={`sla-tag ${t.sla_stage}`}>
                {t.sla_stage === 'warning'
                  ? 'Customer waiting…'
                  : t.sla_stage === 'impatient'
                    ? 'Impatient'
                    : 'Expired'}
              </span>
            )}
          </button>
        ))}
      </div>

      <main className="reading-pane">
        {error && <div className="error-banner">{error}</div>}
        {!thread && <div className="empty-pane">Select a message</div>}
        {thread && (
          <>
            <h2 style={{ marginTop: 0, fontWeight: 400, fontSize: 22 }}>{thread.subject}</h2>
            {thread.messages.map((m) => (
              <div key={m.id} className="message-block">
                <div className="message-header">
                  <div>
                    <span className="who">{m.from_name}</span>
                    <span className="email">&lt;{m.from_email}&gt;</span>
                  </div>
                  <div className="when">{fmtWhen(m.created_at)}</div>
                </div>
                <div className="message-subject">{m.subject}</div>
                <div className="message-body">{m.body}</div>
                {m.parts?.length > 0 && (
                  <table className="parts-table">
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Name</th>
                        <th>Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.parts.map((p, i) => (
                        <tr key={i}>
                          <td>{p.type}</td>
                          <td>{p.name}</td>
                          <td>{p.price}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {m.score_summary && (
                  <div className="score-card">
                    <strong>Customer review · {m.score_summary.overall.toFixed(1)}/5</strong>
                    <div>
                      Performance {m.score_summary.performance.toFixed(1)} · Speed{' '}
                      {m.score_summary.response_time.toFixed(1)} · Service{' '}
                      {m.score_summary.service.toFixed(1)}
                    </div>
                    {m.score_summary.pros?.length > 0 && (
                      <div>Pros: {m.score_summary.pros.join('; ')}</div>
                    )}
                    {m.score_summary.cons?.length > 0 && (
                      <div>Cons: {m.score_summary.cons.join('; ')}</div>
                    )}
                    {m.score_summary.suggested_swaps?.length > 0 && (
                      <div>Suggested swaps: {m.score_summary.suggested_swaps.join('; ')}</div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {thread.status === 'open' && !readOnly && (
              <div className="compose">
                <h3>Reply</h3>
                <div className="hint">
                  To: {thread.customer_name} &lt;{thread.customer_email}&gt;
                  {thread.budget_aud != null ? ` · Budget ~$${thread.budget_aud} AUD` : ''}
                  <br />
                  Ask questions first if you need clarity — SLA pauses while you wait on their reply.
                  Send a parts proposal when you are ready to close the job.
                </div>
                <label>Message to customer</label>
                <textarea
                  rows={4}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Questions, options, caveats… (Send message) or notes with your final list (Send parts proposal)"
                />
                <label>PCPartPicker list URL (final proposal)</label>
                <input
                  value={pcppUrl}
                  onChange={(e) => setPcppUrl(e.target.value)}
                  placeholder="https://au.pcpartpicker.com/list/…"
                />
                <label>Or paste parts list (fallback)</label>
                <textarea
                  rows={4}
                  value={partsText}
                  onChange={(e) => setPartsText(e.target.value)}
                  placeholder={'CPU: AMD Ryzen 5 7600\nGPU: …'}
                />
                {previewParts && (
                  <table className="parts-table">
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Name</th>
                        <th>Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewParts.map((p, i) => (
                        <tr key={i}>
                          <td>{p.type}</td>
                          <td>{p.name}</td>
                          <td>{p.price}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="compose-actions">
                  <button
                    className="btn btn-primary"
                    disabled={sending || !notes.trim()}
                    onClick={sendMessage}
                  >
                    {sending ? 'Sending…' : 'Send message'}
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={sending || (!pcppUrl.trim() && !partsText.trim())}
                    onClick={sendReply}
                    style={{ background: '#188038' }}
                  >
                    {sending ? 'Sending…' : 'Send parts proposal'}
                  </button>
                  <button className="btn btn-ghost" disabled={sending} onClick={previewList}>
                    Preview list
                  </button>
                  <button
                    className="btn btn-ghost"
                    disabled={sending}
                    onClick={() => {
                      setPcppUrl('')
                      setPartsText('')
                      setNotes('')
                      setPreviewParts(null)
                    }}
                  >
                    Discard
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {gameOver && (
        <div className="overlay">
          <div className="overlay-card">
            <h2>Shop Closed</h2>
            <p>
              {shop?.shop_name} shut down after too many bad reviews.
              <br />
              {gameOverReason}
              <br />
              Final rating {shop?.shop_rating.toFixed(1)} · {shop?.jobs_completed} jobs completed
            </p>
            <button className="btn btn-primary" onClick={exit}>
              Back to saves
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
