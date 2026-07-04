import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    chunkSizeWarningLimit: 1024,
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心 —— 几乎每个页面都用
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // 图表库 —— 仪表盘页面使用，~600KB
          'vendor-charts': ['recharts'],
          // 代码高亮 —— 日志/配置页面使用，~800KB
          'vendor-syntax': ['react-syntax-highlighter'],
          // Markdown + 数学公式 —— README/文档页面
          'vendor-markdown': [
            'react-markdown',
            'remark-gfm',
            'remark-math',
            'rehype-katex',
            'katex',
          ],
          // UI 工具库 —— 多页面使用
          'vendor-ui': [
            'lucide-react',
            'react-virtuoso',
            'clsx',
          ],
        },
      },
    },
  },
})
