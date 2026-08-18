import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fortawesome/fontawesome-free/css/all.min.css'
import './index.css'
import App from './App.jsx'

// ── 主题初始化（在渲染前设置，避免闪色）──
// 优先级：URL ?theme=light|dark（DSH 内嵌 iframe 传入，与 dsh web 的
// data-ds-dark-theme 联动）> 默认 dark（独立打开保持深色专业风）
function applyTheme() {
  const params = new URLSearchParams(window.location.search);
  const explicit = params.get('theme');
  const theme = explicit === 'light' || explicit === 'dark' ? explicit : 'dark';
  document.documentElement.setAttribute('data-theme', theme);
}
applyTheme();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
