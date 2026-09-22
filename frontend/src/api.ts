const BASE = ''

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = j.detail || JSON.stringify(j)
    } catch {
      /* ignore */
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json() as Promise<T>
}

export type SaveSummary = {
  id: string
  shop_name: string
  created_at: string
  last_played: string
  status: string
  shop_rating: number
  jobs_completed: number
  reputation: number
  game_over_reason: string
}

export type ThreadSummary = {
  id: string
  unread: boolean
  status: string
  sla_stage: string
  play_seconds_open: number
  from_name: string
  from_email: string
  subject: string
  preview: string
  updated_at: string
  created_at: string
}

export type Part = { type: string; name: string; price: string; url: string }

export type Message = {
  id: string
  role: string
  from_name: string
  from_email: string
  subject: string
  body: string
  created_at: string
  parts: Part[]
  score_summary?: {
    overall: number
    performance: number
    response_time: number
    service: number
    pros: string[]
    cons: string[]
    suggested_swaps: string[]
  } | null
}

export type Thread = {
  id: string
  folder: string
  unread: boolean
  status: string
  sla_stage: string
  play_seconds_open: number
  customer_name: string
  customer_email: string
  subject: string
  preview: string
  budget_aud?: number | null
  use_case: string
  must_haves: string[]
  constraints: string[]
  messages: Message[]
  created_at: string
  updated_at: string
  job_result?: Record<string, unknown> | null
}

export type ShopInfo = {
  shop_name: string
  shop_rating: number
  jobs_completed: number
  status: string
  game_over_reason: string
  reputation: number
  avg_performance: number
  avg_response_time: number
  avg_service: number
}

export const api = {
  listSaves: () => req<{ saves: SaveSummary[] }>('/api/saves'),
  createSave: (shop_name: string) =>
    req('/api/saves', { method: 'POST', body: JSON.stringify({ shop_name }) }),
  loadSave: (id: string) => req(`/api/saves/${id}/load`, { method: 'POST' }),
  deleteSave: (id: string) => req(`/api/saves/${id}`, { method: 'DELETE' }),
  unload: () => req('/api/unload', { method: 'POST' }),
  heartbeat: () =>
    req<{ ok: boolean; playing?: boolean; game_over?: boolean; reason?: string }>(
      '/api/heartbeat',
      { method: 'POST' },
    ),
  inbox: (folder = 'inbox') =>
    req<{ threads: ThreadSummary[]; shop: ShopInfo }>(`/api/inbox?folder=${folder}`),
  thread: (id: string) => req<Thread>(`/api/threads/${id}`),
  archive: (id: string) => req(`/api/threads/${id}/archive`, { method: 'POST' }),
  reply: (
    id: string,
    body: {
      pcpp_url?: string
      parts_text?: string
      notes?: string
      mode?: 'message' | 'proposal'
    },
  ) =>
    req<{ thread: Thread; shop: ShopInfo; game_over: boolean; kind?: string }>(
      `/api/threads/${id}/reply`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
  resolvePcpp: (url: string) =>
    req<{ url: string; parts: Part[]; method: string }>('/api/pcpp/resolve', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  shop: () => req<ShopInfo & { id: string; playing: boolean }>('/api/shop'),
}
