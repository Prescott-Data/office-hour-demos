import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import OdinApp from './OdinApp.tsx'
import PresentationApp from './PresentationApp.tsx'

const app = window.location.pathname.startsWith('/demo') ? <OdinApp /> : <PresentationApp />

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {app}
  </StrictMode>,
)
