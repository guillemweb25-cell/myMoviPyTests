import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(() => {
  const frontendPort = Number(process.env.FRONTEND_PORT ?? '5173')
  const backendHost = process.env.BACKEND_HOST ?? 'backend'
  const backendPort = Number(process.env.BACKEND_PORT ?? '8000')

  return {
    plugins: [react()],
    server: {
      host: true,
      port: frontendPort,
      proxy: {
        '/api': {
          target: `http://${backendHost}:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
