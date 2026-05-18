import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable React strict mode for better development experience
  reactStrictMode: true,

  // Required for Docker multi-stage build (copies only necessary files)
  output: "standalone",

  // Transpile the shared workspace package (no separate build step needed)
  transpilePackages: ["@auto-at/shared"],

  // Required for Next standalone output in a monorepo: include root node_modules
  outputFileTracingRoot: require("path").join(__dirname, "../.."),

  // API proxy to avoid CORS issues in development
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
