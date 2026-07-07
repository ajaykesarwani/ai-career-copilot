import React from 'react'

const STEPS = [
  { icon: '📄', name: 'Parser',   desc: 'Resume extraction' },
  { icon: '🐙', name: 'GitHub',   desc: 'Repo analysis' },
  { icon: '🔗', name: 'LinkedIn', desc: 'Profile merge' },
  { icon: '🧠', name: 'Merger',   desc: 'Profile unification' },
  { icon: '✦',  name: 'Ranker',  desc: 'Skill scoring' },
]

export default function Pipeline({ activeStep = -1, doneUpTo = -1 }) {
  return (
    <div style={{ display: 'flex', gap: 0, alignItems: 'stretch', margin: '1rem 0' }}>
      {STEPS.map((step, i) => {
        const done   = i <= doneUpTo
        const active = i === activeStep
        return (
          <div key={i} style={{ flex: 1, position: 'relative' }}>
            {i < STEPS.length - 1 && (
              <div style={{
                position: 'absolute', right: -10, top: '50%', transform: 'translateY(-50%)',
                color: 'var(--brand-light)', fontSize: '1.1rem', zIndex: 1,
              }}>→</div>
            )}
            <div style={{
              background: done ? 'var(--success-bg)' : active ? 'var(--surface-2)' : 'var(--surface-1)',
              border: `1px solid ${done ? 'var(--success-border)' : active ? 'var(--brand)' : 'var(--border)'}`,
              borderRadius: 'var(--radius-sm)', padding: '.75rem .6rem',
              textAlign: 'center', height: '100%', transition: 'all .3s',
              boxShadow: active ? '0 0 0 2px rgba(108,92,231,.15)' : 'none',
              opacity: (!done && !active) ? .5 : 1,
            }}>
              <div style={{ fontSize: '1.3rem', marginBottom: '.25rem' }}>{step.icon}</div>
              <div style={{ fontSize: '.7rem', fontWeight: 600, color: 'var(--text-2)' }}>{step.name}</div>
              <div style={{ fontSize: '.65rem', color: 'var(--text-3)', marginTop: '.15rem' }}>
                {done ? '✅ Done' : active ? 'Running…' : step.desc}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
