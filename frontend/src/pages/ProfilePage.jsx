import React, { useState, useRef, useEffect } from 'react'
import { useStore } from '../hooks/useStore.jsx'
import { api } from '../hooks/useApi.js'
import { Card, Btn, Input, Textarea, Select, Stepper, AgentMsg } from '../components/UI.jsx'
import Pipeline from '../components/Pipeline.jsx'

const STEPS = ['Resume', 'Socials', 'Preferences', 'AI Analysis', 'Ready']

export default function ProfilePage() {
  const { state, dispatch } = useStore()
  const { step, profile, profileComplete } = state

  const [file,        setFile]        = useState(null)
  const [drag,        setDrag]        = useState(false)
  const [pipeStep,    setPipeStep]    = useState(-1)
  const [pipeDone,    setPipeDone]    = useState(-1)
  const [enriching,   setEnriching]   = useState(false)   // background enrichment spinner
  const [enrichDone,  setEnrichDone]  = useState(false)   // enrichment finished badge
  const [analysisMessages, setAnalysisMessages] = useState(
    profile.analysis ? [{ name: 'Profile Analyst', text: profile.analysis }] : []
  )
  const fileRef = useRef()

  // ── Local form state — initialise from persisted profile so returning fills fields ──
  const [github,   setGithub]   = useState(profile.github_url    || '')
  const [linkedin, setLinkedin] = useState(profile.linkedin_text || '')
  const [bio,      setBio]      = useState(profile.bio           || '')
  const [contactEmail,    setContactEmail]    = useState(profile.email        || '')
  const [contactPhone,    setContactPhone]    = useState(profile.phone        || '')
  const [contactLocation, setContactLocation] = useState(profile.location     || '')
  const [linkedinUrl,     setLinkedinUrl]     = useState(profile.linkedin_url || '')
  const [prefs,    setPrefs]    = useState(profile.preferences)
  const updPref = (k, v) => setPrefs(p => ({ ...p, [k]: v }))

  /* ── helpers ── */
  const loading = (msg) => dispatch({ type: 'LOADING', payload: msg })
  const loaded  = ()    => dispatch({ type: 'LOADED'  })
  const toast   = (msg) => dispatch({ type: 'TOAST',   payload: msg })
  const setProf = (p)   => dispatch({ type: 'SET_PROFILE', payload: p })

  /* ─────────────────────────────────────────────────────────────────────────
   * Step 0 — Resume
   * ───────────────────────────────────────────────────────────────────────── */
  function onFile(f) {
    if (!f) return
    setFile(f)
    const reader = new FileReader()
    reader.onload = e => setProf({ raw_resume: e.target.result.slice(0, 5000) })
    reader.readAsText(f)
  }

  async function processResume() {
    if (!file) return
    loading('Resume agent parsing your document…')
    try {
      const parsed = await api.parseResume(file)
      setProf(parsed)
      // Sync local contact-field inputs (step 1) with whatever was extracted,
      // so the user sees what was found and can correct/fill gaps directly.
      setContactEmail(parsed.email || '')
      setContactPhone(parsed.phone || '')
      setContactLocation(parsed.location || '')
      setLinkedinUrl(parsed.linkedin_url || '')
      dispatch({ type: 'SET_STEP', payload: 1 })
      toast(
        parsed.extraction_method === 'ocr_vision'
          ? '✅ Resume parsed via AI vision OCR (it looked like a scanned image)'
          : '✅ Resume parsed successfully!'
      )
    } catch {
      // Graceful fallback — never block the user
      setProf({
        name: 'Alex Johnson', title: 'ML Engineer',
        skills: ['Python','TensorFlow','PyTorch','NLP','AWS','Docker','FastAPI','TypeScript'],
        summary: 'Experienced ML engineer with 5+ years building production AI systems.',
        years_exp: 5,
        top_projects: ['Real-time NLP pipeline','RAG chatbot','OSS transformer toolkit'],
      })
      dispatch({ type: 'SET_STEP', payload: 1 })
      toast('Resume processed (demo mode — add GEMINI_API_KEY for full parsing)')
    }
    loaded()
  }

  /* ─────────────────────────────────────────────────────────────────────────
   * Step 1 — Socials (non-blocking background enrichment)
   *
   * Strategy:
   *  1. Immediately save the raw fields (github_url / linkedin_text / bio)
   *     to the store and advance to step 2 — user is never blocked.
   *  2. Fire the enrichment API call in the background (12 s timeout built
   *     into useApi.js).  Show a non-blocking "Enriching…" badge.
   *  3. When enrichment resolves, silently merge the extra fields (repos,
   *     languages) into the store.
   *  4. If enrichment times out or errors, show a small warning toast —
   *     the partial profile already saved is good enough to continue.
   * ───────────────────────────────────────────────────────────────────────── */
  async function processSocials() {
    // 1 — Save raw fields immediately and advance; never block on the API
    setProf({
      github_url: github || '',
      linkedin_text: linkedin || '',
      bio: bio || '',
      email: contactEmail || '',
      phone: contactPhone || '',
      location: contactLocation || '',
      linkedin_url: linkedinUrl || '',
    })
    dispatch({ type: 'SET_STEP', payload: 2 })
    toast('✅ Profiles saved! Continuing…')

    // 2 — Fire enrichment in the background only if there's a GitHub URL
    if (!github) return

    setEnriching(true)
    try {
      const enriched = await api.enrichSocials({
        github_url: github,
        linkedin_text: linkedin || null,
        bio: bio || null,
        current_profile: profile,
      })
      // Merge only the enrichment-specific fields — don't overwrite anything
      // the user typed themselves. In particular, the GitHub summary is only
      // used to FILL bio if the user left it blank, never to replace it.
      const { github_repos, github_languages, github_summary } = enriched
      setProf({
        ...(github_repos     ? { github_repos }     : {}),
        ...(github_languages ? { github_languages }  : {}),
        ...(github_summary && !bio ? { bio: github_summary } : {}),
      })
      setEnrichDone(true)
      toast('✅ GitHub data enriched!')
    } catch (err) {
      const isTimeout = err?.name === 'AbortError' || err?.message?.includes('abort')
      toast(isTimeout
        ? '⚠️ GitHub enrichment timed out — continuing with base profile'
        : '⚠️ GitHub enrichment unavailable — continuing with base profile'
      )
    } finally {
      setEnriching(false)
    }
  }

  /* ─────────────────────────────────────────────────────────────────────────
   * Step 2 — Preferences → full AI analysis
   * ───────────────────────────────────────────────────────────────────────── */
  async function runAnalysis() {
    dispatch({ type: 'SET_PREFS', payload: prefs })
    loading('Running 5-agent pipeline…')
    setAnalysisMessages([])
    dispatch({ type: 'SET_STEP', payload: 3 })

    // Animate pipeline steps in parallel with the real API call
    ;(async () => {
      for (let i = 0; i < 5; i++) {
        setPipeStep(i)
        await new Promise(r => setTimeout(r, 700))
        setPipeDone(i)
      }
      setPipeStep(-1)
    })()

    try {
      const result = await api.analyseProfile({
        profile: { ...profile, preferences: prefs },
        preferences: prefs,
      })
      setProf({
        ...result.updated_profile,
        strength_score: result.strength_score,
        analysis: result.analysis,
      })
      setAnalysisMessages([{ name: 'Profile Analyst', text: result.analysis }])
      dispatch({ type: 'PROFILE_DONE' })
      toast('✅ Analysis complete!')
    } catch (err) {
      const isTimeout = err?.name === 'AbortError' || err?.message?.includes('abort')
      const fallback = `1. PROFILE STRENGTH: 78/100 — Strong technical depth with proven production experience.\n\n2. SKILL GAPS:\n• MLOps / Kubeflow — critical for senior ML roles\n• LLM fine-tuning — in high demand at AI-first companies\n• System design at scale — expected at Staff+ level\n\n3. BEST-FIT ROLES:\n• Senior ML Engineer — core skills match strongly\n• AI Research Scientist — GitHub activity signals research credibility\n• ML Platform Engineer — infra + ML combo is rare and valuable\n\n4. UNIQUE VALUE PROPOSITION:\nYou combine deep ML research skills with production engineering experience — a rare pairing in the current market. Your open-source contributions signal initiative and technical credibility beyond the resume.\n\n5. KEYWORDS: transformer, LLM, RAG, MLOps, production ML, AI platform, fine-tuning, vector search\n\n6. QUICK WIN: Add quantified impact to each project (latency reduction %, users served, cost saved).`
      setProf({ strength_score: 78, analysis: fallback })
      setAnalysisMessages([{ name: 'Profile Analyst', text: fallback }])
      dispatch({ type: 'PROFILE_DONE' })
      toast(isTimeout ? 'Analysis timed out — using demo results' : 'Analysis complete (demo mode)')
    }
    loaded()
  }

  /* ─────────────────────────────────────────────────────────────────────────
   * Profile complete — summary view
   * ───────────────────────────────────────────────────────────────────────── */
  if (profileComplete && step >= 4) {
    return (
      <>
        {/* Completed banner */}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1.1rem', marginBottom: 4 }}>
                ✅ Profile complete
              </div>
              <div style={{ fontSize: '.85rem', color: 'var(--text-3)' }}>
                Your profile is set up and ready. Agents will use it to match and apply to jobs.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <Btn
                variant="secondary"
                size="sm"
                onClick={() => dispatch({ type: 'SET_STEP', payload: 0 })}
              >
                ✏️ Edit profile
              </Btn>
              <Btn
                variant="primary"
                size="sm"
                onClick={() => dispatch({ type: 'SET_PAGE', payload: 'jobs' })}
              >
                Find matching jobs →
              </Btn>
            </div>
          </div>
        </Card>

        {/* Profile summary */}
        <Card>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            <div>
              <SectionLabel>Identity</SectionLabel>
              <div style={{ fontWeight: 600, fontSize: '1rem' }}>{profile.name}</div>
              <div style={{ fontSize: '.85rem', color: 'var(--text-2)' }}>{profile.title}</div>
              {profile.years_exp > 0 && (
                <div style={{ fontSize: '.8rem', color: 'var(--text-3)', marginTop: 4 }}>
                  {profile.years_exp} years experience
                </div>
              )}
            </div>
            <div>
              <SectionLabel>Preferences</SectionLabel>
              {profile.preferences.roles     && <PrefRow icon="🎯">{profile.preferences.roles}</PrefRow>}
              {profile.preferences.locations && <PrefRow icon="📍">{profile.preferences.locations}</PrefRow>}
              {profile.preferences.salary    && <PrefRow icon="💰">{profile.preferences.salary}</PrefRow>}
              <div style={{ fontSize: '.82rem', color: 'var(--text-2)' }}>
                {[
                  profile.preferences.remote  && 'Remote',
                  profile.preferences.hybrid  && 'Hybrid',
                  profile.preferences.onsite  && 'On-site',
                ].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>

          {profile.skills.length > 0 && (
            <div style={{ marginTop: '1.25rem' }}>
              <SectionLabel>Skills</SectionLabel>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {profile.skills.map(s => (
                  <span key={s} style={{
                    fontSize: '.75rem', padding: '3px 10px', borderRadius: 20,
                    background: 'var(--surface-2)', color: 'var(--brand)',
                    border: '1px solid var(--border-2)', fontWeight: 500,
                  }}>{s.replace('*', '')}</span>
                ))}
              </div>
            </div>
          )}

          {profile.strength_score > 0 && (
            <div style={{ marginTop: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.8rem', color: 'var(--text-2)', marginBottom: 6 }}>
                <span style={{ fontWeight: 600 }}>Profile strength</span>
                <span style={{ fontWeight: 700, color: 'var(--brand)' }}>{profile.strength_score}/100</span>
              </div>
              <div style={{ background: 'var(--border)', borderRadius: 10, height: 8, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 10,
                  background: 'linear-gradient(90deg,var(--brand),var(--brand-light))',
                  width: `${profile.strength_score}%`, transition: 'width .6s ease',
                }} />
              </div>
            </div>
          )}
        </Card>

        {/* Analysis card */}
        {analysisMessages.length > 0 && (
          <Card>
            <div style={{ fontWeight: 600, marginBottom: '1rem' }}>AI Analysis</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: 420, overflowY: 'auto' }}>
              {analysisMessages.map((m, i) => <AgentMsg key={i} name={m.name} text={m.text} />)}
            </div>
          </Card>
        )}
      </>
    )
  }

  /* ─────────────────────────────────────────────────────────────────────────
   * Wizard flow (step < 4 or editing)
   * ───────────────────────────────────────────────────────────────────────── */
  return (
    <>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Stepper steps={STEPS} current={step} />
          {profileComplete && step < 4 && (
            <Btn variant="secondary" size="sm" onClick={() => dispatch({ type: 'PROFILE_DONE' })}>
              Cancel edit
            </Btn>
          )}
        </div>
      </Card>

      {/* ── Step 0 — Resume ─────────────────────────────────────────────────── */}
      {step >= 0 && (
        <Card>
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontWeight: 600, fontSize: '1rem' }}>Upload your resume</div>
            <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>PDF · DOCX · TXT — used by all agents</div>
          </div>

          {/* Already-parsed banner */}
          {profile.name && !file && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '.75rem 1rem', background: 'var(--success-bg)',
              border: '1px solid var(--success-border)', borderRadius: 'var(--radius-sm)',
              marginBottom: '.75rem',
            }}>
              <span style={{ fontSize: '1.2rem' }}>✅</span>
              <div>
                <div style={{ fontSize: '.875rem', fontWeight: 500, color: '#007a56' }}>
                  Resume already parsed
                </div>
                <div style={{ fontSize: '.75rem', color: 'var(--text-3)' }}>
                  Detected: {profile.name} · {profile.title}
                </div>
              </div>
              <Btn
                variant="secondary"
                size="sm"
                onClick={() => dispatch({ type: 'SET_STEP', payload: 1 })}
                style={{ marginLeft: 'auto' }}
              >
                Skip →
              </Btn>
            </div>
          )}

          <div
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files[0]) }}
            onClick={() => fileRef.current.click()}
            style={{
              border: `2px dashed ${drag ? 'var(--brand)' : 'var(--border-2)'}`,
              borderRadius: 'var(--radius)', padding: '2rem', textAlign: 'center',
              cursor: 'pointer', background: drag ? 'var(--surface-2)' : 'var(--surface-1)',
              transition: 'all .2s',
            }}
          >
            <div style={{ fontSize: '2.5rem', marginBottom: '.75rem', opacity: .5 }}>📄</div>
            <div style={{ fontWeight: 600, marginBottom: '.3rem' }}>
              {profile.name ? 'Replace resume' : 'Drop your resume here'}
            </div>
            <div style={{ fontSize: '.825rem', color: 'var(--text-3)' }}>
              or click to browse · PDF / DOCX / TXT
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              style={{ display: 'none' }}
              onChange={e => onFile(e.target.files[0])}
            />
          </div>

          {file && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '.75rem 1rem', background: 'var(--success-bg)',
              border: '1px solid var(--success-border)', borderRadius: 'var(--radius-sm)',
              marginTop: '.75rem',
            }}>
              <span style={{ fontSize: '1.3rem' }}>✅</span>
              <div>
                <div style={{ fontSize: '.875rem', fontWeight: 500, color: '#007a56' }}>{file.name}</div>
                <div style={{ fontSize: '.75rem', color: 'var(--text-3)' }}>
                  {(file.size / 1024).toFixed(0)} KB · Ready to parse
                </div>
              </div>
              <Btn variant="primary" size="sm" onClick={processResume} style={{ marginLeft: 'auto' }}>
                Analyse →
              </Btn>
            </div>
          )}
        </Card>
      )}

      {/* ── Step 1 — Socials ────────────────────────────────────────────────── */}
      {step >= 1 && (
        <Card style={{ animation: 'fadeIn .3s ease' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <div style={{ fontWeight: 600 }}>Connect your profiles</div>
              <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>
                Optional — enriches your profile in the background, won't block you
              </div>
            </div>
            {/* Background enrichment status badge */}
            {enriching && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                fontSize: '.75rem', color: 'var(--brand)',
                background: 'var(--surface-2)', border: '1px solid var(--border-2)',
                borderRadius: 20, padding: '4px 12px',
              }}>
                <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⟳</span>
                Enriching…
              </div>
            )}
            {enrichDone && (
              <div style={{
                fontSize: '.75rem', color: '#007a56',
                background: 'var(--success-bg)', border: '1px solid var(--success-border)',
                borderRadius: 20, padding: '4px 12px',
              }}>
                ✅ GitHub enriched
              </div>
            )}
          </div>

          {/* OCR transparency notice — only shown if the resume needed vision OCR */}
          {profile.extraction_method === 'ocr_vision' && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '.6rem .9rem', background: 'var(--surface-2)',
              border: '1px solid var(--border-2)', borderRadius: 'var(--radius-sm)',
              fontSize: '.78rem', color: 'var(--text-2)', marginBottom: '.85rem',
            }}>
              <span>🔍</span>
              Your resume looked like a scanned image, so it was read with AI vision OCR.
              Please double-check the details below for accuracy.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '.85rem' }}>
            {/* Contact details — pre-filled from resume parsing where available.
                Filling these in avoids placeholder brackets in generated documents. */}
            <div>
              <div style={{ fontSize: '.8rem', fontWeight: 500, color: 'var(--text-2)', marginBottom: '.4rem' }}>
                Contact details
                <span style={{ fontWeight: 400, color: 'var(--text-3)' }}> — fill in anything missing so your documents don't need placeholders</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.6rem' }}>
                <Input
                  label="Email"
                  value={contactEmail}
                  onChange={e => setContactEmail(e.target.value)}
                  placeholder="you@example.com"
                  type="email"
                />
                <Input
                  label="Phone"
                  value={contactPhone}
                  onChange={e => setContactPhone(e.target.value)}
                  placeholder="+1 555 123 4567"
                  type="tel"
                />
                <Input
                  label="City / Location"
                  value={contactLocation}
                  onChange={e => setContactLocation(e.target.value)}
                  placeholder="Berlin, Germany"
                />
                <Input
                  label="LinkedIn URL"
                  value={linkedinUrl}
                  onChange={e => setLinkedinUrl(e.target.value)}
                  placeholder="linkedin.com/in/yourname"
                />
              </div>
            </div>

            <Input
              label="GitHub profile URL"
              value={github}
              onChange={e => setGithub(e.target.value)}
              placeholder="https://github.com/yourusername"
              type="url"
            />
            <Textarea
              label="LinkedIn URL or paste profile text"
              value={linkedin}
              onChange={e => setLinkedin(e.target.value)}
              rows={3}
              placeholder="https://linkedin.com/in/yourname  or paste your About / experience…"
            />
            <Textarea
              label="Short bio (helps personalise cover letters)"
              value={bio}
              onChange={e => setBio(e.target.value)}
              rows={2}
              placeholder="e.g. Senior ML engineer with 5 yrs in NLP, passionate about real-world AI products…"
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '.78rem', color: 'var(--text-3)' }}>
                GitHub enrichment runs in the background — you can continue immediately
              </span>
              <Btn variant="primary" onClick={processSocials}>Continue →</Btn>
            </div>
          </div>
        </Card>
      )}

      {/* ── Step 2 — Preferences ────────────────────────────────────────────── */}
      {step >= 2 && (
        <Card style={{ animation: 'fadeIn .3s ease' }}>
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontWeight: 600 }}>Job preferences</div>
            <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>
              Agents use these to rank, filter, and search for real, recent job postings
            </div>
          </div>

          {/* Location — primary control, given its own prominent block */}
          <div style={{
            background: 'var(--surface-1)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', padding: '1rem', marginBottom: '1rem',
          }}>
            <Input
              label="📍 Preferred location"
              value={prefs.locations}
              onChange={e => updPref('locations', e.target.value)}
              placeholder="e.g. Berlin, London, New York…"
            />
            <div style={{ display: 'flex', gap: '.75rem', marginTop: '.75rem', flexWrap: 'wrap' }}>
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer',
                fontSize: '.82rem', flex: '1 1 220px', padding: '.6rem .75rem',
                borderRadius: 'var(--radius-sm)',
                border: `1px solid ${prefs.location_mode === 'strict' ? 'var(--brand)' : 'var(--border-2)'}`,
                background: prefs.location_mode === 'strict' ? 'var(--surface-2)' : 'var(--surface)',
              }}>
                <input
                  type="radio"
                  name="location_mode"
                  checked={prefs.location_mode === 'strict'}
                  onChange={() => updPref('location_mode', 'strict')}
                  style={{ marginTop: 2 }}
                />
                <span>
                  <strong>Only this location</strong>
                  <div style={{ color: 'var(--text-3)', fontSize: '.75rem', marginTop: 2 }}>
                    Search ONLY {prefs.locations || 'the location above'}{prefs.remote ? ' (+ remote roles)' : ''} — nothing else
                  </div>
                </span>
              </label>
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer',
                fontSize: '.82rem', flex: '1 1 220px', padding: '.6rem .75rem',
                borderRadius: 'var(--radius-sm)',
                border: `1px solid ${prefs.location_mode === 'any' ? 'var(--brand)' : 'var(--border-2)'}`,
                background: prefs.location_mode === 'any' ? 'var(--surface-2)' : 'var(--surface)',
              }}>
                <input
                  type="radio"
                  name="location_mode"
                  checked={prefs.location_mode === 'any'}
                  onChange={() => updPref('location_mode', 'any')}
                  style={{ marginTop: 2 }}
                />
                <span>
                  <strong>Prefer this, but search worldwide too</strong>
                  <div style={{ color: 'var(--text-3)', fontSize: '.75rem', marginTop: 2 }}>
                    Prioritise {prefs.locations || 'the location above'}, broaden globally if few matches
                  </div>
                </span>
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.85rem' }}>
            <Input
              label="Target roles (comma-separated)"
              value={prefs.roles}
              onChange={e => updPref('roles', e.target.value)}
              placeholder="ML Engineer, Data Scientist, AI Researcher"
            />
            <Input
              label="Salary expectation"
              value={prefs.salary}
              onChange={e => updPref('salary', e.target.value)}
              placeholder="€80,000 – €110,000"
            />
            <Select
              label="Seniority"
              value={prefs.seniority}
              onChange={e => updPref('seniority', e.target.value)}
            >
              <option>Junior (&lt;3 yrs)</option>
              <option>Mid-level (3-5 yrs)</option>
              <option>Senior (5-8 yrs)</option>
              <option>Staff / Principal</option>
            </Select>
            <Select
              label="🕐 How recent should postings be?"
              value={String(prefs.max_days_old)}
              onChange={e => updPref('max_days_old', parseInt(e.target.value, 10))}
            >
              <option value="3">Last 3 days</option>
              <option value="7">Last week</option>
              <option value="14">Last 2 weeks</option>
              <option value="21">Last 3 weeks</option>
              <option value="30">Last month</option>
            </Select>
            <div style={{ gridColumn: '1/-1' }}>
              <div style={{ fontSize: '.8rem', fontWeight: 500, color: 'var(--text-2)', marginBottom: '.4rem' }}>
                Work mode
              </div>
              <div style={{ display: 'flex', gap: '1rem' }}>
                {['remote','hybrid','onsite'].map(m => (
                  <label key={m} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '.875rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={prefs[m]}
                      onChange={e => updPref(m, e.target.checked)}
                    />
                    {m.charAt(0).toUpperCase() + m.slice(1)}
                  </label>
                ))}
              </div>
            </div>
            <Input
              label="Industries of interest"
              value={prefs.industries}
              onChange={e => updPref('industries', e.target.value)}
              placeholder="AI/ML, FinTech, HealthTech…"
              style={{ gridColumn: '1/-1' }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
            <Btn variant="primary" onClick={runAnalysis}>Run AI analysis ✦</Btn>
          </div>
        </Card>
      )}

      {/* ── Step 3 — Analysis ───────────────────────────────────────────────── */}
      {step >= 3 && (
        <Card style={{ animation: 'fadeIn .3s ease' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <div style={{ fontWeight: 600 }}>Agent analysis</div>
              <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>
                5-agent pipeline · Profile + GitHub + LinkedIn + Merger + Ranker
              </div>
            </div>
            {profileComplete && (
              <Btn
                variant="primary"
                size="sm"
                onClick={() => dispatch({ type: 'SET_PAGE', payload: 'jobs' })}
              >
                Find matching jobs →
              </Btn>
            )}
          </div>
          <Pipeline activeStep={pipeStep} doneUpTo={pipeDone} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: 420, overflowY: 'auto', paddingTop: '.5rem' }}>
            {analysisMessages.map((m, i) => <AgentMsg key={i} name={m.name} text={m.text} />)}
          </div>
        </Card>
      )}
    </>
  )
}

/* ── Small pure helpers ──────────────────────────────────────────────────────── */
function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: '.7rem', fontWeight: 600, textTransform: 'uppercase',
      letterSpacing: '.08em', color: 'var(--text-3)', marginBottom: '.5rem',
    }}>
      {children}
    </div>
  )
}

function PrefRow({ icon, children }) {
  return (
    <div style={{ fontSize: '.82rem', color: 'var(--text-2)', marginBottom: 2 }}>
      {icon} {children}
    </div>
  )
}
