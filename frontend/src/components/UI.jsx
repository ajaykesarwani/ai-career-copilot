import React from 'react'

/* ── Card ─────────────────────────────────────────────────────────────────── */
export function Card({ children, style = {} }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '1.25rem',
      boxShadow: 'var(--shadow)', ...style,
    }}>
      {children}
    </div>
  )
}

/* ── Button ───────────────────────────────────────────────────────────────── */
export function Btn({ children, variant = 'primary', size = 'md', onClick, disabled, style = {} }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: '.5rem',
    border: '1px solid', borderRadius: 'var(--radius-sm)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? .5 : 1,
    fontFamily: 'inherit', fontWeight: 500, transition: 'all var(--transition)',
    padding: size === 'sm' ? '.4rem .9rem' : '.6rem 1.25rem',
    fontSize: size === 'sm' ? '.8rem' : '.875rem',
  }
  const variants = {
    primary:   { background: 'var(--brand)',   color: '#fff', borderColor: 'var(--brand)' },
    secondary: { background: 'var(--surface)', color: 'var(--text-2)', borderColor: 'var(--border-2)' },
    ghost:     { background: 'none',           color: 'var(--text-2)', borderColor: 'transparent' },
    danger:    { background: 'var(--danger)',  color: '#fff', borderColor: 'var(--danger)' },
  }
  return (
    <button onClick={onClick} disabled={disabled} style={{ ...base, ...variants[variant], ...style }}>
      {children}
    </button>
  )
}

/* ── Input ────────────────────────────────────────────────────────────────── */
export function Input({ label, style = {}, ...props }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem' }}>
      {label && <label style={{ fontSize: '.8rem', fontWeight: 500, color: 'var(--text-2)' }}>{label}</label>}
      <input
        style={{
          padding: '.6rem .9rem', border: '1px solid var(--border-2)',
          borderRadius: 'var(--radius-sm)', fontSize: '.875rem',
          fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text)',
          outline: 'none', transition: 'border var(--transition)', ...style,
        }}
        onFocus={e => { e.target.style.borderColor = 'var(--brand)'; e.target.style.boxShadow = 'var(--shadow-focus)' }}
        onBlur={e  => { e.target.style.borderColor = 'var(--border-2)'; e.target.style.boxShadow = 'none' }}
        {...props}
      />
    </div>
  )
}

/* ── Textarea ─────────────────────────────────────────────────────────────── */
export function Textarea({ label, style = {}, ...props }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem' }}>
      {label && <label style={{ fontSize: '.8rem', fontWeight: 500, color: 'var(--text-2)' }}>{label}</label>}
      <textarea
        style={{
          padding: '.6rem .9rem', border: '1px solid var(--border-2)',
          borderRadius: 'var(--radius-sm)', fontSize: '.875rem',
          fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text)',
          outline: 'none', resize: 'vertical', transition: 'border var(--transition)', ...style,
        }}
        onFocus={e => { e.target.style.borderColor = 'var(--brand)'; e.target.style.boxShadow = 'var(--shadow-focus)' }}
        onBlur={e  => { e.target.style.borderColor = 'var(--border-2)'; e.target.style.boxShadow = 'none' }}
        {...props}
      />
    </div>
  )
}

/* ── Select ───────────────────────────────────────────────────────────────── */
export function Select({ label, children, style = {}, ...props }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem' }}>
      {label && <label style={{ fontSize: '.8rem', fontWeight: 500, color: 'var(--text-2)' }}>{label}</label>}
      <select
        style={{
          padding: '.6rem .9rem', border: '1px solid var(--border-2)',
          borderRadius: 'var(--radius-sm)', fontSize: '.875rem',
          fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text)',
          outline: 'none', cursor: 'pointer', ...style,
        }}
        {...props}
      >
        {children}
      </select>
    </div>
  )
}

/* ── Chip ─────────────────────────────────────────────────────────────────── */
export function Chip({ children, active, onClick, style = {} }) {
  return (
    <button onClick={onClick} style={{
      padding: '.35rem .75rem', borderRadius: 20,
      border: `1px solid ${active ? 'var(--brand)' : 'var(--border-2)'}`,
      background: active ? 'var(--surface-2)' : 'var(--surface)',
      color: active ? 'var(--brand)' : 'var(--text-2)',
      fontSize: '.78rem', cursor: 'pointer', fontFamily: 'inherit',
      transition: 'all var(--transition)', ...style,
    }}>
      {children}
    </button>
  )
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{
      display: 'flex', gap: 2, background: 'var(--surface-1)',
      borderRadius: 'var(--radius-sm)', padding: 3,
    }}>
      {tabs.map(tab => (
        <button key={tab.id} onClick={() => onChange(tab.id)} style={{
          flex: 1, padding: '.4rem', border: 'none', borderRadius: 6,
          fontSize: '.8rem', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500,
          background: active === tab.id ? 'var(--surface)' : 'none',
          color: active === tab.id ? 'var(--brand)' : 'var(--text-2)',
          boxShadow: active === tab.id ? 'var(--shadow)' : 'none',
          transition: 'all var(--transition)',
        }}>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

/* ── Stepper ──────────────────────────────────────────────────────────────── */
export function Stepper({ steps, current }) {
  return (
    <div style={{ display: 'flex' }}>
      {steps.map((label, i) => {
        const done   = i < current
        const active = i === current
        return (
          <div key={i} style={{ flex: 1, textAlign: 'center', position: 'relative' }}>
            {i < steps.length - 1 && (
              <div style={{
                position: 'absolute', top: 14, left: '60%', right: '-40%',
                height: 2, background: done ? 'var(--brand-light)' : 'var(--border)', zIndex: 0,
              }} />
            )}
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              border: `2px solid ${done ? 'var(--brand)' : active ? 'var(--brand)' : 'var(--border)'}`,
              background: done ? 'var(--brand)' : 'var(--surface)',
              color: done ? '#fff' : active ? 'var(--brand)' : 'var(--text-3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '.75rem', fontWeight: 600, margin: '0 auto .3rem',
              position: 'relative', zIndex: 1, transition: 'all .3s',
              boxShadow: active ? '0 0 0 3px rgba(108,92,231,.2)' : 'none',
            }}>
              {done ? '✓' : i === steps.length - 1 ? '✦' : i + 1}
            </div>
            <div style={{
              fontSize: '.7rem', fontWeight: 500,
              color: (done || active) ? 'var(--text-2)' : 'var(--text-3)',
            }}>{label}</div>
          </div>
        )
      })}
    </div>
  )
}

/* ── Agent bubble ─────────────────────────────────────────────────────────── */
export function AgentMsg({ name, text, isUser = false }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexDirection: isUser ? 'row-reverse' : 'row' }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
        background: isUser ? 'var(--surface-2)' : 'linear-gradient(135deg,var(--brand),var(--brand-light))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '.8rem', color: isUser ? 'var(--text-2)' : '#fff', fontWeight: 700,
      }}>{isUser ? 'You' : '✦'}</div>
      <div style={{
        background: isUser ? 'var(--surface-2)' : 'var(--surface-1)',
        border: '1px solid var(--border)',
        borderRadius: isUser ? 'var(--radius) 0 var(--radius) var(--radius)' : '0 var(--radius) var(--radius) var(--radius)',
        padding: '.75rem 1rem', flex: 1, maxWidth: '85%',
        borderColor: isUser ? 'var(--border-2)' : 'var(--border)',
      }}>
        {!isUser && <div style={{ fontSize: '.75rem', fontWeight: 600, color: 'var(--brand)', marginBottom: '.3rem' }}>{name}</div>}
        <div style={{ fontSize: '.875rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{text}</div>
      </div>
    </div>
  )
}

/* ── Thinking dots ────────────────────────────────────────────────────────── */
export function ThinkingDots() {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%',
        background: 'linear-gradient(135deg,var(--brand),var(--brand-light))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#fff', fontSize: '.8rem', fontWeight: 700, flexShrink: 0,
      }}>✦</div>
      <div style={{
        background: 'var(--surface-1)', border: '1px solid var(--border)',
        borderRadius: '0 var(--radius) var(--radius) var(--radius)',
        padding: '.75rem 1rem',
      }}>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', height: 20 }}>
          {[0, 0.15, 0.3].map((delay, i) => (
            <div key={i} style={{
              width: 7, height: 7, borderRadius: '50%', background: 'var(--brand-light)',
              animation: `bounce .9s ${delay}s infinite`,
            }} />
          ))}
        </div>
      </div>
    </div>
  )
}
