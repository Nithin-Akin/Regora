import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  experimental: { proxyTimeout: 900000, proxyClientMaxBodySize: "55mb" },
};
export default config;
