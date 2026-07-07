import React, { useEffect } from 'react'
import { StoreProvider, useStore } from './hooks/useStore.jsx'
import Nav from './components/Nav.jsx'
import Sidebar from './components/Sidebar.jsx'
import ProfilePage from './pages/ProfilePage.jsx'
import JobsPage from './pages/JobsPage.jsx'
import ApplicationsPage from './pages/ApplicationsPage.jsx'
import CoachPage from './pages/CoachPage.jsx'
import Loader from './components/Loader.jsx'
import Toast from './components/Toast.jsx'

function Layout() {
  const { state } = useStore()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Nav />
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', flex: 1 }}>
        <Sidebar />
        <main style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', minWidth: 0 }}>
          {state.page === 'profile'      && <ProfilePage />}
          {state.page === 'jobs'         && <JobsPage />}
          {state.page === 'applications' && <ApplicationsPage />}
          {state.page === 'coach'        && <CoachPage />}
        </main>
      </div>
      {state.loading && <Loader message={state.loadingMsg} />}
      {state.toast   && <Toast />}
    </div>
  )
}

export default function App() {
  return (
    <StoreProvider>
      <Layout />
    </StoreProvider>
  )
}
