import React from 'react'
import { useStore } from '../hooks/useStore.jsx'

export default function Sidebar() {
  const { state, dispatch } = useStore()
  const { profile, profileComplete } = state
  const initials = profile.name
    ? profile.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : '?'

  return (
    <aside style={{
      background: 'var(--surface)', borderRight: '1px solid var(--border)',
      padding: '1.5rem 1rem', display: 'flex', flexDirection: 'column', gap: '1rem',
    }}>
      {/* Profile card */}
      <div style={{
        background: 'linear-gradient(135deg,var(--surface-2),#fff)',
        border: '1px solid var(--border)', borderRadius: 'var(--radius)',
        padding: '1.25rem', textAlign: 'center',
      }}>
        <div style={{
          width: 60, height: 60, borderRadius: '50%',
          background: 'linear-gradient(135deg,var(--brand),var(--brand-light))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.5rem', color: '#fff', margin: '0 auto 10px',
          fontWeight: 700, boxShadow: '0 4px 12px rgba(108,92,231,.3)',
        }}>{initials}</div>
        <div style={{ fontWeight: 600, fontSize: '.95rem', marginBottom: 3 }}>
          {profile.name || 'Your Profile'}
        </div>
        <div style={{ fontSize: '.78rem', color: 'var(--text-3)' }}>
          {profile.title || 'Upload resume to begin'}
        </div>
        {profile.extraction_method === 'ocr_vision' && (
          <div style={{ fontSize: '.7rem', color: 'var(--brand)', marginTop: 4 }}>
            🔍 Parsed via AI vision OCR
          </div>
        )}
        {/* Contact completeness indicator */}
        {profileComplete && (() => {
          const fields = [profile.email, profile.phone, profile.location]
          const filled = fields.filter(Boolean).length
          return filled < 3 ? (
            <div style={{ fontSize: '.7rem', color: 'var(--warning)', marginTop: 4 }}>
              ⚠️ {3 - filled} contact field{3 - filled > 1 ? 's' : ''} missing — docs will use placeholders
            </div>
          ) : (
            <div style={{ fontSize: '.7rem', color: 'var(--success)', marginTop: 4 }}>
              ✅ Contact details complete
            </div>
          )
        })()}

        {profileComplete && (
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.75rem', color: 'var(--text-2)', marginBottom: 5 }}>
              <span>Profile strength</span>
              <span>{profile.strength_score}%</span>
            </div>
            <div style={{ background: 'var(--border)', borderRadius: 10, height: 6, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 10,
                background: 'linear-gradient(90deg,var(--brand),var(--brand-light))',
                width: `${profile.strength_score}%`, transition: 'width .6s ease',
              }} />
            </div>
          </div>
        )}

        <button
          onClick={() => dispatch({ type: 'SET_PAGE', payload: 'profile' })}
          style={{
            marginTop: 12, width: '100%', padding: '.45rem', borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-2)', background: 'var(--surface-2)',
            color: 'var(--brand)', fontSize: '.78rem', fontWeight: 600, cursor: 'pointer',
            transition: 'all var(--transition)',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--brand)'; e.currentTarget.style.color = '#fff' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--brand)' }}
        >
          {profileComplete ? '✏️ Edit profile' : '🚀 Set up profile'}
        </button>
      </div>

      {/* GitHub enrichment details */}
      {(profile.github_pinned?.length > 0 || profile.github_contributions) && (
        <div>
          <div style={{ fontSize: '.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--text-3)', padding: '0 .5rem', marginBottom: '.4rem' }}>
            GitHub activity
          </div>
          <div style={{ padding: '0 .5rem' }}>
            {profile.github_contributions && (
              <div style={{ fontSize: '.72rem', color: 'var(--text-2)', marginBottom: '.3rem' }}>
                📊 {profile.github_contributions}
              </div>
            )}
            {profile.github_pinned?.slice(0,2).map((repo, i) => (
              <div key={i} style={{ fontSize: '.72rem', color: 'var(--text-2)', marginBottom: '.2rem' }}>
                📌 {repo.split(' — ')[0]}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* LinkedIn enrichment status */}
      {(profile.linkedin_url || profile.linkedin_structured?.name) && (
        <div style={{ padding: '0 .5rem' }}>
          <div style={{ fontSize: '.72rem', color: profile.linkedin_structured?.name ? 'var(--success)' : 'var(--text-3)' }}>
            {profile.linkedin_structured?.name
              ? `✅ LinkedIn data enriched`
              : `🔗 LinkedIn URL saved`}
          </div>
        </div>
      )}

      {/* Resume layout detected */}
      {profile.resume_layout?.raw_description && (
        <div style={{ padding: '0 .5rem' }}>
          <div style={{ fontSize: '.72rem', color: 'var(--brand)' }}>
            🎨 Layout: {profile.resume_layout.columns === 2 ? 'Two-column' : 'Single-column'} · {profile.resume_layout.font_style}
          </div>
        </div>
      )}

      {/* Skills */}
      {profile.skills.length > 0 && (
        <div>
          <div style={{ fontSize: '.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--text-3)', padding: '0 .5rem', marginBottom: '.4rem' }}>
            Skills detected
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '.5rem' }}>
            {profile.skills.slice(0, 14).map(s => (
              <span key={s} style={{
                fontSize: '.7rem', padding: '3px 9px', borderRadius: 20,
                background: s.endsWith('*') ? 'var(--success-bg)' : 'var(--surface-2)',
                color: s.endsWith('*') ? 'var(--success)' : 'var(--brand)',
                border: `1px solid ${s.endsWith('*') ? 'var(--success-border)' : 'var(--border-2)'}`,
                fontWeight: 500,
              }}>{s.replace('*', '')}</span>
            ))}
          </div>
        </div>
      )}

      <div style={{ height: 1, background: 'var(--border)', margin: '.25rem 0' }} />

      {/* Quick actions */}
      <div>
        <div style={{ fontSize: '.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--text-3)', padding: '0 .5rem', marginBottom: '.4rem' }}>
          Quick actions
        </div>
        {[
          { icon: '🔍', label: 'Find jobs now',      page: 'jobs' },
          { icon: '📄', label: 'My applications',    page: 'applications' },
          { icon: '🤖', label: 'Interview prep',     page: 'coach' },
        ].map(item => (
          <button key={item.label} onClick={() => dispatch({ type: 'SET_PAGE', payload: item.page })} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '.55rem .75rem',
            borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '.875rem',
            color: 'var(--text-2)', transition: 'all var(--transition)', border: 'none',
            background: 'none', width: '100%', textAlign: 'left',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--brand)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-2)' }}
          >
            <span style={{ width: 20, textAlign: 'center' }}>{item.icon}</span> {item.label}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 'auto', fontSize: '.72rem', color: 'var(--text-3)', textAlign: 'center', padding: '.5rem' }}>
        Powered by Gemini 2.0 Flash<br />6-agent pipeline
      </div>
    </aside>
  )
}
