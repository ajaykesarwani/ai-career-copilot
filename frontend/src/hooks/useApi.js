/**
 * API client — wraps all backend calls.
 * BASE_URL auto-detects: uses /api in prod (same origin),
 * falls back to localhost:8000 in dev.
 */

const BASE = import.meta.env.VITE_API_URL || '/api'

/**
 * Wraps a fetch Promise with an AbortController timeout.
 * @param {Promise} fetchPromise  - the in-flight fetch
 * @param {AbortController} controller - the controller for that fetch
 * @param {number} ms - timeout in milliseconds
 */
function withTimeout(fetchPromise, controller, ms) {
  const timer = setTimeout(() => controller.abort(), ms)
  return fetchPromise.finally(() => clearTimeout(timer))
}

async function request(path, options = {}, timeoutMs = 30_000) {
  const controller = new AbortController()
  const fetchPromise = fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    signal: controller.signal,
    ...options,
  })
  const res = await withTimeout(fetchPromise, controller, timeoutMs)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  // Profile
  parseResume: (file) => {
    const form = new FormData()
    form.append('file', file)
    const controller = new AbortController()
    const fetchPromise = fetch(`${BASE}/profile/parse`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    })
    return withTimeout(fetchPromise, controller, 30_000)
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail))))
  },

  // 45 second timeout — GitHub REST + GraphQL + LinkedIn + LLM structuring can be slow
  enrichSocials: (body) =>
    request('/profile/socials', { method: 'POST', body: JSON.stringify(body) }, 45_000),

  analyseProfile: (body) =>
    request('/profile/analyse', { method: 'POST', body: JSON.stringify(body) }, 60_000),

  // Jobs
  searchJobs: (body) =>
    request('/jobs/search', { method: 'POST', body: JSON.stringify(body) }, 45_000),

  // Tells the UI whether live job search (Adzuna) is configured, so it can
  // show an "Estimated" badge transparently when falling back to AI guesses.
  jobSourceStatus: () =>
    request('/jobs/source-status', { method: 'GET' }, 8_000).catch(() => ({ live_job_search_configured: false })),

  // Applications — 90s: Gemini generates full resume + cover letter + notes in one call
  generateDocs: (body) =>
    request('/applications/generate', { method: 'POST', body: JSON.stringify(body) }, 90_000),

  // Export a generated doc (resume or cover letter) as a real PDF/DOCX file.
  // Passes resume_layout so the server can reproduce the candidate's original style.
  exportDoc: async (body) => {
    const controller = new AbortController()
    const fetchPromise = fetch(`${BASE}/applications/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    const res = await withTimeout(fetchPromise, controller, 30_000)
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename="(.+?)"/)
    const filename = match ? match[1] : `document.${body.format}`
    return { blob, filename }
  },

  // Coach (non-streaming)
  coachChat: (body) =>
    request('/coach/chat', { method: 'POST', body: JSON.stringify(body) }, 30_000),

  // Coach streaming — returns an async generator of text chunks
  coachStream: async function* (body) {
    const res = await fetch(`${BASE}/coach/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            const { text } = JSON.parse(data)
            if (text) yield text
          } catch { /* skip malformed */ }
        }
      }
    }
  },
}
