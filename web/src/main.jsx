import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { initTheme } from './lib/theme.js'

// 主题跟随日出日落自动切换（index.html 里有首屏防闪脚本，这里接管后续刷新）
initTheme()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
