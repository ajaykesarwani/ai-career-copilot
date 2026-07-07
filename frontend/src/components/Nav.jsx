import React from 'react'
import { useStore } from '../hooks/useStore.jsx'

const navStyle = {
  background: 'var(--surface)', borderBottom: '1px solid var(--border)',
  padding: '0 2rem', display: 'flex', alignItems: 'center',
  justifyContent: 'space-between', height: 60, position: 'sticky',
  top: 0, zIndex: 100, boxShadow: '0 1px 8px rgba(108,92,231,.06)',
}

const tabs = [
  { id: 'profile', label: 'Profile' },
  { id: 'jobs', label: 'Jobs', badge: true },
  { id: 'applications', label: 'Applications' },
  { id: 'coach', label: 'AI Coach' },
]

export default function Nav() {
  const { state, dispatch } = useStore()

  return (
    <nav style={navStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 700, color: 'var(--brand)', fontSize: '1.1rem' }}>
        <div style={{
          width: 34, height: 34, background: 'linear-gradient(135deg,var(--brand),var(--brand-light))',
          borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: '1.1rem',
        }}>✦</div>
        AI Career Copilot
      </div>

      <div style={{ display: 'flex', gap: 4 }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => dispatch({ type: 'SET_PAGE', payload: t.id })}
            style={{
              padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none',
              background: state.page === t.id ? 'var(--surface-2)' : 'none',
              color: state.page === t.id ? 'var(--brand)' : 'var(--text-2)',
              cursor: 'pointer', fontSize: '.875rem', fontWeight: 500,
              transition: 'all var(--transition)', display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            {t.label}
            {t.badge && state.jobs.length > 0 && (
              <span style={{
                background: 'var(--brand)', color: '#fff', fontSize: '.7rem',
                padding: '2px 7px', borderRadius: 20,
              }}>{state.jobs.length}</span>
            )}
          </button>
        ))}
      </div>

      <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>
        {state.profileComplete ? '✅ Profile ready · Gemini 2.0 Flash' : 'Complete profile to begin'}
      </div>
    </nav>
  )
}
