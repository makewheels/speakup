import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { initAnalytics } from './lib/analytics.js'
import { initTheme } from './lib/theme.js'

// 自动主题跟随系统外观（index.html 先防闪，这里接管后续系统变化）
initTheme()
initAnalytics()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
