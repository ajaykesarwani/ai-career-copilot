import React, { createContext, useContext, useReducer, useEffect } from 'react'

const STORAGE_KEY = 'ai_career_copilot_state'

const initialState = {
  // current page
  page: 'profile', // profile | jobs | applications | coach

  // candidate profile (mirrors backend CandidateProfile)
  profile: {
    name: '', title: '', summary: '', skills: [],
    years_exp: 0, top_projects: [], github_repos: [], github_repos_rich: [],
    github_languages: [], github_pinned: [], github_readme_summary: '',
    github_contributions: '', linkedin_text: '', linkedin_structured: {},
    bio: '', raw_resume: '', github_url: '',
    email: '', phone: '', location: '', address: '',
    linkedin_url: '', education: '', certifications: [],
    resume_layout: {
      columns: 1, has_sidebar: false, section_order: [],
      accent_color: '', font_style: 'modern', header_style: 'centered',
      uses_icons: false, uses_dividers: true, raw_description: '',
    },
    preferences: {
      roles: '', locations: '', location_mode: 'any', salary: '',
      seniority: 'Mid-level', remote: true, hybrid: true,
      onsite: false, industries: '', max_days_old: 21,
    },
    strength_score: 0,
    analysis: '',
    extraction_method: '',
  },

  // onboarding step 0-4
  step: 0,
  profileComplete: false,

  // jobs
  jobs: [],
  jobsLoaded: false,

  // application queue
  queue: [],   // [{job, status, docs}]

  // ui — ephemeral, never persisted
  loading: false,
  loadingMsg: '',
  toast: null,
}

/** Keys that are ephemeral and should NOT be saved to localStorage */
const EPHEMERAL_KEYS = new Set(['loading', 'loadingMsg', 'toast'])

function loadPersistedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return initialState
    const saved = JSON.parse(raw)
    // Deep-merge saved state over initialState so any newly-added fields get defaults
    return {
      ...initialState,
      ...saved,
      profile: {
        ...initialState.profile,
        ...saved.profile,
        preferences: {
          ...initialState.profile.preferences,
          ...(saved.profile?.preferences ?? {}),
        },
      },
      // Always reset ephemeral UI state on load
      loading: false,
      loadingMsg: '',
      toast: null,
    }
  } catch {
    return initialState
  }
}

function persistState(state) {
  try {
    const toSave = Object.fromEntries(
      Object.entries(state).filter(([k]) => !EPHEMERAL_KEYS.has(k))
    )
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  } catch {
    // Quota exceeded or private mode — ignore silently
  }
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_PAGE':     return { ...state, page: action.payload }
    case 'SET_STEP':     return { ...state, step: action.payload }
    case 'SET_PROFILE':  return { ...state, profile: { ...state.profile, ...action.payload } }
    case 'SET_PREFS':    return {
      ...state,
      profile: {
        ...state.profile,
        preferences: { ...state.profile.preferences, ...action.payload },
      },
    }
    case 'PROFILE_DONE': return { ...state, profileComplete: true, step: 4 }
    case 'SET_JOBS':     return { ...state, jobs: action.payload, jobsLoaded: true }
    case 'TOGGLE_JOB':   return {
      ...state,
      jobs: state.jobs.map(j => j.id === action.payload ? { ...j, selected: !j.selected } : j),
    }
    case 'ENQUEUE_JOBS': {
      const existing = new Set(state.queue.map(q => q.job.id))
      const newItems = action.payload
        .filter(j => j.selected && !existing.has(j.id))
        .map(j => ({ job: j, status: 'pending', docs: null }))
      return { ...state, queue: [...state.queue, ...newItems] }
    }
    case 'SET_QUEUE_STATUS': return {
      ...state,
      queue: state.queue.map(q =>
        q.job.id === action.payload.id ? { ...q, ...action.payload.update } : q
      ),
    }
    case 'LOADING':     return { ...state, loading: true,  loadingMsg: action.payload || 'Agents working…' }
    case 'LOADED':      return { ...state, loading: false, loadingMsg: '' }
    case 'TOAST':       return { ...state, toast: action.payload }
    case 'CLEAR_TOAST': return { ...state, toast: null }
    case 'RESET_PROFILE': return {
      ...initialState,
      page: 'profile',
      loading: false,
      loadingMsg: '',
      toast: null,
    }
    default: return state
  }
}

const StoreContext = createContext(null)

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, undefined, loadPersistedState)

  // Persist to localStorage after every state change
  useEffect(() => {
    persistState(state)
  }, [state])

  return (
    <StoreContext.Provider value={{ state, dispatch }}>
      {children}
    </StoreContext.Provider>
  )
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used within StoreProvider')
  return ctx
}
