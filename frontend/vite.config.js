import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发环境：将 /api 转发到本地 FastAPI。生产构建后请用 Nginx 等同源反代，见 deploy/nginx.ict-diagnosis.conf.example
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
