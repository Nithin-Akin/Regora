import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  experimental: { proxyTimeout: 900000, proxyClientMaxBodySize: "55mb" },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};
export default config;
