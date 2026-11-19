import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api 로 시작하는 요청은 Render 백엔드로 넘긴다.
// 브라우저는 같은 주소로 요청하는 것처럼 보이므로 CORS 설정을 바꿀 필요가 없다.
// 배포(Vercel)에서는 vercel.json 의 rewrites 가 같은 일을 한다.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "https://baf60081-team9.onrender.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  // npm run build:html → 그림·CSS·JS를 모두 품은 HTML 파일 하나 (scripts/single-html.mjs 가 마무리)
  build:
    mode === "html"
      ? { outDir: "dist-html", assetsInlineLimit: 100_000_000, cssCodeSplit: false, modulePreload: false }
      : undefined,
}));
