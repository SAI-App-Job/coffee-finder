import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { LanguageProvider } from './i18n'
import { runMigrations } from './utils/storage'

// 利用者のデータの保存形式の版を確かめる(形式を変える版が出たときの移行。docs/user-data-storage.md)
runMigrations()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LanguageProvider>
      <App />
    </LanguageProvider>
  </StrictMode>,
)
