/** @type {import('next').NextConfig} */
const config = {
  async rewrites() {
    const upstream = process.env.CONTROL_PLANE_INTERNAL_URL ?? "http://127.0.0.1:7000";
    return [{ source: "/api/:path*", destination: `${upstream}/api/:path*` }];
  },
};

export default config;
