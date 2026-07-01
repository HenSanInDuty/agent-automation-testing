import { defineConfig } from "vitest/config";

// Minimal vitest harness for @auto-at/shared component tests. esbuild's
// automatic JSX runtime renders React 19 components without an explicit React
// import (matching the apps' Next.js automatic-runtime setup).
export default defineConfig({
  esbuild: { jsx: "automatic", jsxImportSource: "react" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
