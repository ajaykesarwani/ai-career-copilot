import React from 'react'

export default function Loader({ message = 'Agents working…' }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(255,255,255,.88)',
      zIndex: 200, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: '1rem',
      backdropFilter: 'blur(4px)',
    }}>
      <div style={{
        width: 48, height: 48, border: '4px solid var(--border)',
        borderTopColor: 'var(--brand)', borderRadius: '50%',
        animation: 'spin 1s linear infinite',
      }} />
      <div style={{ fontSize: '.9rem', color: 'var(--text-2)', fontWeight: 500 }}>{message}</div>
    </div>
  )
}
