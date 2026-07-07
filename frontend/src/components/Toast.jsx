import React, { useEffect } from 'react'
import { useStore } from '../hooks/useStore.jsx'

export default function Toast() {
  const { state, dispatch } = useStore()

  useEffect(() => {
    const t = setTimeout(() => dispatch({ type: 'CLEAR_TOAST' }), 3500)
    return () => clearTimeout(t)
  }, [state.toast])

  if (!state.toast) return null

  return (
    <div style={{
      position: 'fixed', bottom: '1.5rem', right: '1.5rem',
      background: 'var(--text)', color: '#fff',
      padding: '.75rem 1.25rem', borderRadius: 'var(--radius)',
      fontSize: '.875rem', boxShadow: 'var(--shadow-lg)', zIndex: 999,
      animation: 'slideUp .3s ease both',
    }}>
      {state.toast}
    </div>
  )
}
