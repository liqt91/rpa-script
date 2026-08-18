import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, '../../runtime/static/workflow-editor'),
    emptyOutDir: true,
  },
  // 相对 base：页面可由多位置托管（后端 /workflow-editor/、dsh web /rpa-editor/），
  // 资源路径随页面 URL 解析，两处都能用
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/admin': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
