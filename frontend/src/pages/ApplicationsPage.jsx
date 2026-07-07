import React, { useState } from 'react'
import { useStore } from '../hooks/useStore.jsx'
import { api } from '../hooks/useApi.js'
import { Card, Btn, Tabs } from '../components/UI.jsx'

const DOC_TABS = [
  { id: 'resume', label: 'Resume' },
  { id: 'cover',  label: 'Cover letter' },
  { id: 'notes',  label: 'Application notes' },
]

export default function ApplicationsPage() {
  const { state, dispatch } = useStore()
  const { queue, profile } = state

  const [activeDoc, setActiveDoc] = useState(null)  // { job, docs }
  const [docTab, setDocTab]       = useState('resume')
  const [exporting, setExporting] = useState(null)   // e.g. 'resume-pdf' while in-flight

  const loading = (msg) => dispatch({ type: 'LOADING', payload: msg })
  const loaded  = ()    => dispatch({ type: 'LOADED' })
  const toast   = (msg) => dispatch({ type: 'TOAST', payload: msg })

  const stats = {
    total:  queue.length,
    gen:    queue.filter(q => q.docs).length,
    ready:  queue.filter(q => q.status === 'ready').length,
    done:   queue.filter(q => q.status === 'done').length,
  }

  async function generateDocs(queueItem) {
    dispatch({ type: 'SET_QUEUE_STATUS', payload: { id: queueItem.job.id, update: { status: 'active' } } })
    loading(`Generating tailored documents for ${queueItem.job.title} at ${queueItem.job.company}…`)

    let docs = null
    let errorMsg = ''

    // Attempt 1 — primary backend call (90s timeout)
    try {
      const res = await api.generateDocs({ job: queueItem.job, profile })
      docs = res.docs
    } catch (err) {
      errorMsg = err.message || 'Unknown error'
      // Attempt 2 — single retry after 2s (handles transient Gemini timeouts)
      try {
        await new Promise(r => setTimeout(r, 2000))
        const res = await api.generateDocs({ job: queueItem.job, profile })
        docs = res.docs
        errorMsg = ''
      } catch (err2) {
        errorMsg = err2.message || errorMsg
      }
    }

    loaded()

    if (docs) {
      dispatch({ type: 'SET_QUEUE_STATUS', payload: { id: queueItem.job.id, update: { docs, status: 'ready' } } })
      setActiveDoc({ job: queueItem.job, docs })
      setDocTab('resume')
      toast(`✅ Documents ready for ${queueItem.job.company}!`)
    } else {
      // Last resort: build from profile data we actually have
      // Only fires if backend is truly unreachable or returned an error
      const fallback = makeFallbackDocs(queueItem.job, profile)
      dispatch({ type: 'SET_QUEUE_STATUS', payload: { id: queueItem.job.id, update: { docs: fallback, status: 'ready' } } })
      setActiveDoc({ job: queueItem.job, docs: fallback })
      setDocTab('resume')
      toast(
        errorMsg.includes('GEMINI_API_KEY') || errorMsg.includes('API key')
          ? '⚠️ No Gemini API key configured — showing profile-based template. Add GEMINI_API_KEY to .env to generate tailored documents.'
          : `⚠️ AI generation failed (${errorMsg.slice(0,60)}) — showing profile-based draft. Review and edit before downloading.`
      )
    }
  }

  function viewDocs(queueItem) {
    setActiveDoc({ job: queueItem.job, docs: queueItem.docs })
    setDocTab('resume')
  }

  function approveAndNext() {
    if (!activeDoc) return
    dispatch({ type: 'SET_QUEUE_STATUS', payload: { id: activeDoc.job.id, update: { status: 'done' } } })
    const nextPending = queue.find(q => q.job.id !== activeDoc.job.id && q.status !== 'done' && q.docs)
    if (nextPending) {
      setActiveDoc({ job: nextPending.job, docs: nextPending.docs })
      setDocTab('resume')
      toast('Moving to next application…')
    } else {
      setActiveDoc(null)
      toast('✅ All approved!')
    }
  }

  function copyDoc() {
    if (!activeDoc) return
    navigator.clipboard.writeText(activeDoc.docs[docTab] || '')
      .then(() => toast('Copied to clipboard!'))
  }

  /**
   * Download the current document as a properly formatted PDF or DOCX file,
   * rendered server-side from the SAME template shown in the formatted
   * preview — so what the user sees is exactly what they download.
   * Only applies to resume/cover tabs (notes stay plain-text-only).
   */
  async function downloadDoc(format) {
    if (!activeDoc || (docTab !== 'resume' && docTab !== 'cover')) return
    const key = `${docTab}-${format}`
    setExporting(key)
    try {
      const { blob, filename } = await api.exportDoc({
        doc_type: docTab,
        format,
        content: activeDoc.docs[docTab],
        profile,
        job: activeDoc.job,
        // Pass the detected layout so the backend reproduces the user's original style
        resume_layout: profile.resume_layout || null,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast(`✅ Downloaded ${filename}`)
    } catch (err) {
      toast(`⚠️ Could not generate ${format.toUpperCase()} — ${err.message || 'try again'}`)
    } finally {
      setExporting(null)
    }
  }

  return (
    <>
      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: '.75rem' }}>
        {[
          { num: stats.total, label: 'Jobs queued' },
          { num: stats.gen,   label: 'Docs generated' },
          { num: stats.ready, label: 'Ready to apply' },
          { num: stats.done,  label: 'Completed' },
        ].map(s => (
          <Card key={s.label}>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--brand)', lineHeight: 1 }}>{s.num}</div>
            <div style={{ fontSize: '.75rem', color: 'var(--text-3)', marginTop: '.25rem' }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {/* Queue */}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <div style={{ fontWeight: 600 }}>Application queue</div>
            <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>AI generates tailored documents for each role</div>
          </div>
          {queue.length > 0 && (
            <Btn variant="primary" size="sm" onClick={() => {
              const pending = queue.find(q => !q.docs && q.status !== 'done')
              if (pending) generateDocs(pending)
              else toast('All items already have documents')
            }}>⚡ Generate next</Btn>
          )}
        </div>

        {!queue.length ? (
          <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-3)' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '.75rem' }}>📋</div>
            <div style={{ marginBottom: '.75rem' }}>No applications queued yet</div>
            <Btn variant="primary" size="sm" onClick={() => dispatch({ type: 'SET_PAGE', payload: 'jobs' })}>
              Browse jobs →
            </Btn>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
            {queue.map(q => (
              <div key={q.job.id} style={{
                display: 'flex', alignItems: 'center', gap: '.75rem',
                padding: '.65rem .9rem', borderRadius: 'var(--radius-sm)',
                background: 'var(--surface-1)', border: '1px solid var(--border)',
              }}>
                {/* Status dot */}
                <div style={{
                  width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                  background: q.status === 'done' ? 'var(--success)' : q.status === 'active' ? 'var(--brand)' : 'var(--warning)',
                  animation: q.status === 'active' ? 'pulse 1.5s infinite' : 'none',
                }} />

                {/* Company logo */}
                <div style={{
                  width: 34, height: 34, borderRadius: 8, background: 'var(--surface-2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem',
                }}>{q.job.logo}</div>

                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '.85rem', fontWeight: 500 }}>{q.job.title}</div>
                  <div style={{ fontSize: '.78rem', color: 'var(--text-3)' }}>{q.job.company} · {q.job.match}% match</div>
                </div>

                <div style={{ fontSize: '.78rem', color: 'var(--text-3)', padding: '0 .5rem' }}>
                  {q.status === 'done' ? '✅ Approved' : q.status === 'ready' ? '📄 Ready' : q.status === 'active' ? '⚙️ Generating…' : '⏳ Pending'}
                </div>

                <Btn variant={q.docs ? 'secondary' : 'primary'} size="sm"
                  onClick={() => q.docs ? viewDocs(q) : generateDocs(q)}>
                  {q.docs ? '📄 View' : '✦ Generate'}
                </Btn>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Document preview */}
      {activeDoc && (
        <Card style={{ animation: 'fadeIn .3s ease' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '.5rem' }}>
            <div>
              <div style={{ fontWeight: 600 }}>
                {activeDoc.job.title} — {activeDoc.job.company}
              </div>
              <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>
                {activeDoc.job.match}% match · {activeDoc.job.location}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
              <Btn variant="secondary" size="sm" onClick={copyDoc}>📋 Copy text</Btn>
              <Btn variant="primary"   size="sm" onClick={approveAndNext}>✅ Approve & next</Btn>
              <Btn variant="ghost"     size="sm" onClick={() => setActiveDoc(null)}>✕</Btn>
            </div>
          </div>

          <Tabs tabs={DOC_TABS} active={docTab} onChange={setDocTab} />

          {/* Download row — only for resume/cover, since notes stay text-only */}
          {(docTab === 'resume' || docTab === 'cover') && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '.6rem', marginTop: '.85rem',
              padding: '.6rem .8rem', background: 'var(--surface-2)',
              border: '1px solid var(--border-2)', borderRadius: 'var(--radius-sm)',
            }}>
              <span style={{ fontSize: '.8rem', color: 'var(--text-2)', fontWeight: 500 }}>
                📥 Download formatted file:
              </span>
              <Btn
                variant="secondary" size="sm"
                disabled={exporting === `${docTab}-pdf`}
                onClick={() => downloadDoc('pdf')}
              >
                {exporting === `${docTab}-pdf` ? '⏳ Generating…' : '📄 PDF'}
              </Btn>
              <Btn
                variant="secondary" size="sm"
                disabled={exporting === `${docTab}-docx`}
                onClick={() => downloadDoc('docx')}
              >
                {exporting === `${docTab}-docx` ? '⏳ Generating…' : '📝 Word (.docx)'}
              </Btn>
              <span style={{ fontSize: '.72rem', color: 'var(--text-3)', marginLeft: 'auto' }}>
                Same content, professionally templated
              </span>
            </div>
          )}

          <div style={{
            background: 'var(--surface-1)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', padding: '1.25rem',
            fontSize: '.82rem', lineHeight: 1.7, whiteSpace: 'pre-wrap',
            maxHeight: 400, overflowY: 'auto', color: 'var(--text)',
            fontFamily: docTab === 'resume' ? 'var(--font-mono)' : 'var(--font)',
            marginTop: '1rem',
          }}>
            {activeDoc.docs[docTab] || ''}
          </div>

          {docTab !== 'notes' && (
            <div style={{ fontSize: '.72rem', color: 'var(--text-3)', marginTop: '.5rem' }}>
              This is the plain-text draft used to generate your downloadable PDF/Word file above —
              the downloaded file will have proper headings, spacing, and layout.
            </div>
          )}
        </Card>
      )}
    </>
  )
}

/* ── Fallback doc generator
   Runs ONLY when the backend is completely unreachable or returned an error
   after retrying. Uses every field actually present in the profile — no
   hollow placeholders for data we already have. Only uses brackets for
   genuinely unknown fields (e.g. past employer name if not in the resume). ── */
function makeFallbackDocs(job, profile) {
  const name     = profile.name     || '[Your Full Name]'
  const title    = profile.title    || '[Your Job Title]'
  const email    = profile.email    || '[Your Email Address]'
  const phone    = profile.phone    || '[Your Phone Number]'
  const location = profile.location || '[Your City, Country]'
  const linkedin = profile.linkedin_url || '[Your LinkedIn URL]'
  const github   = profile.github_url || ''
  const education = profile.education || '[Your Degree, Institution, Year]'
  const summary  = profile.summary  || `${title} with ${profile.years_exp || 0}+ years of professional experience.`
  const bio      = profile.bio      || ''

  const contactParts = [email, phone, location, linkedin]
  if (github) contactParts.push(github)
  const contactLine = contactParts.join(' | ')

  // Skills — use real data, group into categories
  const allSkills = profile.skills || []
  const coreSkills = allSkills.slice(0, 5).join(', ')
  const additionalSkills = allSkills.slice(5, 10).join(', ')
  const skillBlock = allSkills.length > 0
    ? `Core: ${coreSkills}${additionalSkills ? `\nAdditional: ${additionalSkills}` : ''}`
    : '[List your key technical skills here]'

  // Projects — use real repo data if available
  const projects = [
    ...(profile.top_projects || []).slice(0, 3),
    ...(profile.github_repos || []).slice(0, 2),
    ...(profile.github_pinned || []).slice(0, 2),
  ].filter(Boolean).slice(0, 4)

  const projectBlock = projects.length > 0
    ? projects.map(p => `• ${p}`).join('\n')
    : '• [Add your most relevant project with a one-line impact description]'

  // Experience — use real GitHub/LinkedIn data if available, otherwise indicate clearly
  const hasExperience = profile.years_exp > 0
  const expBlock = hasExperience
    ? `${title} — [Company Name] ([Start Year]–Present)\n• Delivered key results in ${(job.tags || []).slice(0, 2).join(' and ')} work\n• [Add quantified achievement — e.g. reduced X by Y%, improved Z by N%]\n• [Add a second quantified achievement]\n\n[Previous Role] — [Company Name] ([Start Year]–[End Year])\n• [Describe impact with specific metrics]\n• [Describe a second achievement]`
    : '[Add your work experience here — include company name, dates, and 2-3 bullet points per role with quantified impact]'

  const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })

  // Cover letter — use real summary and bio
  const para2Skills = (job.tags || []).slice(0, 2).join(' and ') || 'the required technical skills'
  const para3Context = bio || summary

  return {
    resume: `${name}
${title}
${contactLine}

SUMMARY
${summary} Applying for the ${job.title} role at ${job.company}, where I am eager to contribute my expertise to ${job.desc ? job.desc.split('.')[0].toLowerCase() : 'your team'}.

SKILLS
${skillBlock}

EXPERIENCE
${expBlock}

PROJECTS
${projectBlock}

EDUCATION
${education}${profile.certifications?.length ? '\n\nCERTIFICATIONS\n' + profile.certifications.map(c => `• ${c}`).join('\n') : ''}`,

    cover: `${name}
${email}
${phone}
${location}

${today}

${job.company}
[Company Address]

Dear ${job.company} Hiring Team,

I am writing to express my strong interest in the ${job.title} position at ${job.company}. ${job.desc ? job.desc.split('.')[0] + '.' : `Your work in this space is exactly the kind of challenge I am looking to take on.`} With ${profile.years_exp || 'several'} years of experience as a ${title}, I am confident in my ability to make a meaningful contribution to your team from day one.

My background in ${para2Skills} aligns closely with what you are looking for in this role. ${summary} I have consistently delivered results by combining technical rigour with a practical, outcome-driven approach — and I am excited by the opportunity to apply these skills in a new context at ${job.company}.

${para3Context ? para3Context + ' ' : ''}I am especially drawn to ${job.company}'s mission because it represents the kind of high-impact work I find most meaningful. I thrive in environments where I can take ownership of challenging problems, collaborate closely with cross-functional teams, and drive measurable outcomes. I am confident that my experience and work ethic make me a strong addition to your team.

I would very much welcome the opportunity to discuss my application further. Please feel free to reach out at ${email} or ${phone}. Thank you for considering my application — I look forward to the possibility of speaking with you.

Best regards,
${name}`,

    notes: `• Lead with experience in ${(job.tags || []).slice(0, 2).join(' and ') || 'the core requirements'} — direct match to job description
• Back every claim with a specific number: users, latency ms, cost %, team size
• Research ${job.company}: recent blog posts, product launches, engineering culture signals
• Questions to ask the interviewer: team structure, how success is measured in 90 days, growth path
• ATS keywords to include: ${(job.tags || []).join(', ') || '[check the job description for key terms]'}
• ⚠️ This is a profile-based draft — the AI-tailored version requires a working Gemini API key
• Edit the EXPERIENCE section above with your real employer names, dates, and quantified achievements`,
  }
}
