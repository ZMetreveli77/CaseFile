import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { readSavedTheme } from './theme'
import './styles.css'

// Apply a saved theme before the first paint, so a dark-mode visitor never sees a white flash.
const savedTheme = readSavedTheme()
if (savedTheme) {
  document.documentElement.dataset.theme = savedTheme
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
