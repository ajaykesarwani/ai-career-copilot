import React, { useState, useEffect } from 'react'
import { useStore } from '../hooks/useStore.jsx'
import { api } from '../hooks/useApi.js'
import { Card, Btn, Chip } from '../components/UI.jsx'

export default function JobsPage() {
  const { state, dispatch } = useStore()
  const { jobs, profile, profileComplete } = state

  const [typeFilter, setTypeFilter] = useState('')
  const [matchFilter, setMatchFilter] = useState('')
  const [liveConfigured, setLiveConfigured] = useState(null) // null = unknown yet

  const loading = (msg) => dispatch({ type: 'LOADING', payload: msg })
  const loaded  = ()    => dispatch({ type: 'LOADED' })
  const toast   = (msg) => dispatch({ type: 'TOAST', payload: msg })

  useEffect(() => {
    api.jobSourceStatus().then(res => {
      setLiveConfigured(!!res.live_job_search_configured)
      // Warn if keys were set but look like placeholder values
      if (res.adzuna_app_id_set === false || res.adzuna_app_key_set === false) {
        console.warn('Adzuna keys appear to be placeholder values — check .env')
      }
    })
  }, [])

  async function searchJobs() {
    if (!profileComplete) { toast('Complete your profile first'); dispatch({ type: 'SET_PAGE', payload: 'profile' }); return }
    const loc = profile.preferences?.locations
    loading(loc ? `Searching for jobs in ${loc}…` : 'Job discovery agent searching and ranking…')
    try {
      const res = await api.searchJobs({ profile, filter_type: typeFilter || null, filter_match: matchFilter || null })
      dispatch({ type: 'SET_JOBS', payload: res.jobs })
      const realCount = res.jobs.filter(j => j.source === 'adzuna').length
      const estimatedCount = res.jobs.filter(j => j.source === 'ai_estimate').length
      if (realCount > 0) {
        toast(`✅ Found ${realCount} real live job${realCount !== 1 ? 's' : ''} from Adzuna${estimatedCount > 0 ? ` + ${estimatedCount} AI-estimated` : ''}!`)
      } else if (estimatedCount > 0) {
        toast(`⚠️ ${estimatedCount} AI-estimated jobs shown — Adzuna returned no results for this query/location. Try broader preferences.`)
      } else {
        toast('No jobs found — try changing your location or role preferences.')
      }
    } catch {
      // Network/backend totally unavailable — demo jobs fallback, clearly tagged
      dispatch({ type: 'SET_JOBS', payload: DEMO_JOBS })
      toast('Jobs loaded (offline demo mode — not live data)')
    }
    loaded()
  }

  function applySelected() {
    const sel = jobs.filter(j => j.selected)
    if (!sel.length) { toast('Select at least one job first'); return }
    dispatch({ type: 'ENQUEUE_JOBS', payload: sel })
    dispatch({ type: 'SET_PAGE', payload: 'applications' })
    toast(`${sel.length} job(s) added to application queue`)
  }

  const filtered = jobs.filter(j => {
    if (typeFilter && j.type !== typeFilter) return false
    if (matchFilter === 'high' && j.match < 85) return false
    if (matchFilter === 'med'  && j.match < 65) return false
    return true
  })

  const locLabel = profile.preferences?.locations
  const modeLabel = profile.preferences?.location_mode === 'strict' ? 'only' : 'preferred'
  const recencyLabel = profile.preferences?.max_days_old
    ? `last ${profile.preferences.max_days_old} days`
    : null

  return (
    <Card>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.5rem' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '1rem' }}>Job discovery</div>
          <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>
            AI-ranked matches based on your profile
            {locLabel && <> · 📍 {locLabel} ({modeLabel})</>}
            {recencyLabel && <> · 🕐 {recencyLabel}</>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <Btn variant="secondary" size="sm" onClick={searchJobs}>🔍 {jobs.length ? 'Refresh' : 'Search jobs'}</Btn>
          {jobs.some(j => j.selected) && (
            <Btn variant="primary" size="sm" onClick={applySelected}>
              Apply to selected ({jobs.filter(j => j.selected).length}) →
            </Btn>
          )}
        </div>
      </div>

      {/* Live-data transparency banner */}
      {liveConfigured === false && (
        <div style={{
          fontSize: '.8rem', color: '#5a3e00',
          background: '#fff8e1', border: '1px solid #ffe082',
          borderRadius: 'var(--radius-sm)', padding: '.75rem 1rem', marginBottom: '1rem',
        }}>
          <div style={{ fontWeight: 600, marginBottom: '.3rem' }}>⚠️ AI-estimated jobs only — no live job board connected</div>
          <div style={{ color: '#7a5600', lineHeight: 1.5 }}>
            Gemini AI is generating realistic job postings based on your profile.
            These are <b>not real listings</b> — they are AI estimates of what roles you might find.
            For <b>real, current job listings</b>: add a free{' '}
            <b>Adzuna API key</b> to your <code>.env</code> file
            (<a href="https://developer.adzuna.com/" target="_blank" rel="noreferrer" style={{ color: 'var(--brand)' }}>developer.adzuna.com</a> — 250 free calls/month, no credit card).
          </div>
        </div>
      )}
      {liveConfigured === true && (
        <div style={{
          fontSize: '.78rem', color: '#1a5c2a',
          background: 'var(--success-bg)', border: '1px solid var(--success-border)',
          borderRadius: 'var(--radius-sm)', padding: '.55rem .9rem', marginBottom: '1rem',
        }}>
          ✅ <b>Live job search active</b> — results are real, recent postings from Adzuna.
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '1rem' }}>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={selStyle}>
          <option value="">All types</option>
          <option value="remote">Remote</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">On-site</option>
        </select>
        <select value={matchFilter} onChange={e => setMatchFilter(e.target.value)} style={selStyle}>
          <option value="">All matches</option>
          <option value="high">High match (85%+)</option>
          <option value="med">Good match (65%+)</option>
        </select>
        {(typeFilter || matchFilter) && (
          <Chip active onClick={() => { setTypeFilter(''); setMatchFilter('') }}>✕ Clear filters</Chip>
        )}
        <div style={{ marginLeft: 'auto', fontSize: '.8rem', color: 'var(--text-3)' }}>
          {filtered.length} jobs
        </div>
      </div>

      {/* Empty state */}
      {!jobs.length && (
        <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-3)' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '.75rem' }}>🔍</div>
          {profileComplete ? (
            <>
              <div style={{ marginBottom: '.75rem', color: 'var(--text-2)' }}>
                Your profile is ready — click <strong>Search jobs</strong> to discover AI-ranked matches.
              </div>
              <Btn variant="primary" size="sm" onClick={searchJobs}>
                🔍 Search jobs
              </Btn>
            </>
          ) : (
            <>
              <div style={{ marginBottom: '.75rem' }}>Complete your profile to discover matching jobs</div>
              <Btn variant="primary" size="sm" onClick={() => dispatch({ type: 'SET_PAGE', payload: 'profile' })}>
                Set up profile →
              </Btn>
            </>
          )}
        </div>
      )}

      {/* Job cards */}
      <div style={{ display: 'grid', gap: '1rem' }}>
        {filtered.map(job => <JobCard key={job.id} job={job} dispatch={dispatch} />)}
      </div>
    </Card>
  )
}

function JobCard({ job, dispatch }) {
  function toggle() { dispatch({ type: 'TOGGLE_JOB', payload: job.id }) }

  function generate(e) {
    e.stopPropagation()
    dispatch({ type: 'ENQUEUE_JOBS', payload: [{ ...job, selected: true }] })
    dispatch({ type: 'SET_PAGE', payload: 'applications' })
  }

  return (
    <div
      onClick={toggle}
      style={{
        background: 'var(--surface)', border: `1px solid ${job.selected ? 'var(--brand)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)', padding: '1.1rem', cursor: 'pointer',
        transition: 'all .2s', position: 'relative',
        boxShadow: job.selected ? '0 0 0 2px rgba(108,92,231,.2)' : 'var(--shadow)',
      }}
      onMouseEnter={e => { if (!job.selected) e.currentTarget.style.borderColor = 'var(--brand-light)'; e.currentTarget.style.transform = 'translateY(-1px)' }}
      onMouseLeave={e => { if (!job.selected) e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'translateY(0)' }}
    >
      {/* Select circle */}
      <div style={{
        position: 'absolute', top: '.7rem', left: '.7rem',
        width: 20, height: 20, borderRadius: '50%',
        border: `2px solid ${job.selected ? 'var(--brand)' : 'var(--border-2)'}`,
        background: job.selected ? 'var(--brand)' : 'var(--surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '.7rem', color: '#fff', transition: 'all .2s',
      }}>{job.selected ? '✓' : ''}</div>

      {/* Match badge */}
      <div style={{
        position: 'absolute', top: '.9rem', right: '.9rem',
        fontSize: '.75rem', fontWeight: 600, padding: '3px 10px', borderRadius: 20,
        background: job.match >= 85 ? 'var(--success-bg)' : 'var(--warning-bg)',
        color: job.match >= 85 ? '#007a56' : '#7a5600',
        border: `1px solid ${job.match >= 85 ? 'var(--success-border)' : '#ffe09e'}`,
      }}>{job.match}% match</div>

      {/* Header */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginLeft: '1.5rem' }}>
        <div style={{
          width: 44, height: 44, borderRadius: 10, background: 'var(--surface-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.3rem', border: '1px solid var(--border)', flexShrink: 0,
        }}>{job.logo}</div>
        <div style={{ flex: 1, paddingRight: '5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <div style={{ fontWeight: 600, fontSize: '.95rem', lineHeight: 1.3, marginBottom: 2 }}>{job.title}</div>
            <SourceBadge source={job.source} />
          </div>
          <div style={{ fontSize: '.8rem', color: 'var(--text-2)', display: 'flex', gap: '.75rem', flexWrap: 'wrap' }}>
            <span>🏢 {job.company}</span>
            <span>📍 {job.location}</span>
            <span>💰 {job.salary}</span>
            <span>🕐 {job.posted}</span>
          </div>
          <div style={{ fontSize: '.8rem', color: 'var(--text-2)', marginTop: '.35rem' }}>{job.desc}</div>
        </div>
      </div>

      {/* Tags */}
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', margin: '.6rem 0 0 1.5rem' }}>
        {job.tags.map(t => (
          <span key={t} style={{
            fontSize: '.7rem', padding: '2px 8px', borderRadius: 20,
            background: 'var(--surface-2)', color: 'var(--brand)',
            border: '1px solid var(--border)', fontWeight: 500,
          }}>{t}</span>
        ))}
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '.75rem', paddingTop: '.75rem', borderTop: '1px solid var(--border)' }}>
        <span style={{ fontSize: '.78rem', color: 'var(--text-3)' }}>{job.type.charAt(0).toUpperCase() + job.type.slice(1)}</span>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          {job.source === 'adzuna' && job.url && job.url !== '#' && (
            <Btn variant="secondary" size="sm" onClick={e => { e.stopPropagation(); window.open(job.url, '_blank') }}>
              🔗 View posting
            </Btn>
          )}
          <Btn variant="secondary" size="sm" onClick={generate}>✦ Generate docs</Btn>
        </div>
      </div>
    </div>
  )
}

function SourceBadge({ source }) {
  if (source === 'adzuna') {
    return (
      <span style={{
        fontSize: '.65rem', fontWeight: 600, padding: '1px 7px', borderRadius: 20,
        background: 'var(--success-bg)', color: '#007a56', border: '1px solid var(--success-border)',
      }}>
        ✓ Live
      </span>
    )
  }
  return (
    <span style={{
      fontSize: '.65rem', fontWeight: 600, padding: '1px 7px', borderRadius: 20,
      background: 'var(--warning-bg)', color: '#7a5600', border: '1px solid #ffe09e',
    }} title="AI-estimated posting — verify details on the company's careers page">
      ~ Estimated
    </span>
  )
}

const selStyle = {
  padding: '.45rem .75rem', border: '1px solid var(--border-2)',
  borderRadius: 'var(--radius-sm)', fontSize: '.82rem',
  background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer', outline: 'none',
}

/* ── Demo jobs — used ONLY when the backend itself is unreachable.
   Explicitly tagged source: 'ai_estimate' so the UI never implies these
   are live, real postings even in this total-offline fallback case. ── */
const DEMO_JOBS = [
  { id:'j1', title:'Senior ML Engineer',     company:'DeepMind',     location:'London / Remote',     type:'hybrid',  salary:'£120k–£160k', match:94, tags:['PyTorch','Transformers','Research'],     logo:'🧠', desc:'Work on frontier AI systems with world-class researchers.',              posted:'2d ago',  url:'#', selected:false, source:'ai_estimate' },
  { id:'j2', title:'Staff AI Engineer',      company:'Hugging Face', location:'Remote',              type:'remote',  salary:'$140k–$180k', match:91, tags:['LLMs','Open source','Python'],           logo:'🤗', desc:'Build the tools that power the open-source ML ecosystem.',             posted:'1d ago',  url:'#', selected:false, source:'ai_estimate' },
  { id:'j3', title:'ML Platform Engineer',   company:'Mistral AI',   location:'Paris / Remote',      type:'hybrid',  salary:'€95k–€130k',  match:88, tags:['MLOps','Kubernetes','FastAPI'],          logo:'🌀', desc:'Scale model serving infrastructure to millions of users.',             posted:'3d ago',  url:'#', selected:false, source:'ai_estimate' },
  { id:'j4', title:'Applied AI Researcher',  company:'Cohere',       location:'Remote',              type:'remote',  salary:'$130k–$165k', match:85, tags:['NLP','RAG','Fine-tuning'],               logo:'⚡', desc:'Drive applied research bridging theory and production AI.',            posted:'Today',   url:'#', selected:false, source:'ai_estimate' },
  { id:'j5', title:'AI Infrastructure Lead', company:'Anthropic',    location:'San Francisco',       type:'hybrid',  salary:'$160k–$220k', match:82, tags:['ML Systems','Safety','Python'],          logo:'🔶', desc:'Build infrastructure behind responsible AI at scale.',                 posted:'Today',   url:'#', selected:false, source:'ai_estimate' },
  { id:'j6', title:'NLP Engineer',           company:'Aleph Alpha',  location:'Heidelberg / Remote', type:'hybrid',  salary:'€85k–€115k',  match:79, tags:['NLP','LLM','Multilingual'],             logo:'🔮', desc:'Develop multilingual LLMs for European enterprise.',                  posted:'5d ago',  url:'#', selected:false, source:'ai_estimate' },
  { id:'j7', title:'MLOps Engineer',         company:'Scale AI',     location:'Remote',              type:'remote',  salary:'$120k–$155k', match:76, tags:['MLOps','Kubeflow','Monitoring'],         logo:'⚖️', desc:'Build the pipelines that power large-scale AI training.',              posted:'3d ago',  url:'#', selected:false, source:'ai_estimate' },
  { id:'j8', title:'AI Product Engineer',    company:'Notion',       location:'Remote',              type:'remote',  salary:'$130k–$160k', match:71, tags:['LLMs','Product','TypeScript'],           logo:'📝', desc:'Embed AI features into the product used by millions.',                posted:'4d ago',  url:'#', selected:false, source:'ai_estimate' },
]
