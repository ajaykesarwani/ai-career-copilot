import React, { useState, useRef, useEffect } from 'react'
import { useStore } from '../hooks/useStore.jsx'
import { api } from '../hooks/useApi.js'
import { Card, Tabs, Btn, Chip, AgentMsg, ThinkingDots } from '../components/UI.jsx'

const MODES = [
  { id: 'general',    label: 'General prep' },
  { id: 'technical',  label: 'Technical' },
  { id: 'behavioral', label: 'Behavioral' },
  { id: 'salary',     label: 'Salary negotiation' },
]

const QUICK_PROMPTS = {
  general:    ['"Tell me about yourself" — craft a great answer', 'How do I stand out in a competitive market?', 'What makes a great follow-up email?'],
  technical:  ['Walk me through how you would design a recommendation system', 'Common ML interview questions and how to answer them', 'How to explain transformers to a non-technical interviewer'],
  behavioral: ['STAR method — help me structure a strong answer', 'How do I answer "tell me about a time you failed"?', 'Best examples of leadership impact from my background'],
  salary:     ['How do I counter a lowball offer professionally?', 'Give me a salary negotiation script for a senior ML role', 'What benefits should I negotiate beyond base salary?'],
}

export default function CoachPage() {
  const { state } = useStore()
  const { profile } = state

  const [mode, setMode]           = useState('general')
  const [messages, setMessages]   = useState([
    { role: 'assistant', name: 'Career Agent', content: 'Hi! I\'m your AI Career Coach. I can help you prepare for interviews, craft compelling answers, negotiate salary, and tailor your approach for specific companies.\n\nWhat would you like to work on today?' }
  ])
  const [input, setInput]         = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const containerRef = useRef()

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages, streamText])

  async function send(text) {
    const msg = (text || input).trim()
    if (!msg || streaming) return
    setInput('')

    const userMsg = { role: 'user', content: msg }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setStreaming(true)
    setStreamText('')

    // Build history for API (exclude display-only name field)
    const history = newMessages.map(m => ({ role: m.role, content: m.content }))

    try {
      let full = ''
      for await (const chunk of api.coachStream({ messages: history, mode, profile })) {
        full += chunk
        setStreamText(full)
      }
      setMessages(prev => [...prev, { role: 'assistant', name: 'Career Agent', content: full }])
    } catch {
      // Fallback to non-streaming
      try {
        const res = await api.coachChat({ messages: history, mode, profile })
        setMessages(prev => [...prev, { role: 'assistant', name: 'Career Agent', content: res.reply }])
      } catch {
        setMessages(prev => [...prev, {
          role: 'assistant', name: 'Career Agent',
          content: 'I\'m here to help! As your career coach, my advice would be to focus on specific, quantified examples from your experience. Would you like me to help you craft a particular answer or work through a specific aspect of your job search?'
        }])
      }
    }

    setStreaming(false)
    setStreamText('')
  }

  function clear() {
    setMessages([{
      role: 'assistant', name: 'Career Agent',
      content: `Conversation cleared. I'm in ${mode} mode. What would you like to work on?`
    }])
  }

  return (
    <Card style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '1rem' }}>AI Interview Coach</div>
          <div style={{ fontSize: '.8rem', color: 'var(--text-3)' }}>Powered by Gemini — context-aware career guidance</div>
        </div>
        <Btn variant="secondary" size="sm" onClick={clear}>Clear</Btn>
      </div>

      {/* Mode tabs */}
      <Tabs tabs={MODES} active={mode} onChange={m => { setMode(m); clear() }} />

      {/* Messages */}
      <div ref={containerRef} style={{
        display: 'flex', flexDirection: 'column', gap: '1rem',
        maxHeight: 420, overflowY: 'auto', padding: '.25rem 0',
      }}>
        {messages.map((m, i) => (
          <AgentMsg key={i} name={m.name} text={m.content} isUser={m.role === 'user'} />
        ))}
        {streaming && streamText && (
          <AgentMsg name="Career Agent" text={streamText} isUser={false} />
        )}
        {streaming && !streamText && <ThinkingDots />}
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: '.5rem' }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="Ask anything about interviews, career moves, or your applications… (Enter to send)"
          rows={2}
          style={{
            flex: 1, padding: '.6rem .9rem', border: '1px solid var(--border-2)',
            borderRadius: 'var(--radius-sm)', fontSize: '.875rem', fontFamily: 'inherit',
            background: 'var(--surface)', color: 'var(--text)', resize: 'none', outline: 'none',
          }}
          onFocus={e => { e.target.style.borderColor = 'var(--brand)'; e.target.style.boxShadow = 'var(--shadow-focus)' }}
          onBlur={e  => { e.target.style.borderColor = 'var(--border-2)'; e.target.style.boxShadow = 'none' }}
        />
        <Btn variant="primary" onClick={() => send()} disabled={streaming}>
          {streaming ? '…' : 'Send ↗'}
        </Btn>
      </div>

      {/* Quick prompts */}
      <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
        {(QUICK_PROMPTS[mode] || []).map(p => (
          <Chip key={p} onClick={() => send(p)}>{p}</Chip>
        ))}
      </div>
    </Card>
  )
}
