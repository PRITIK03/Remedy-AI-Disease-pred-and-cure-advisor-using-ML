import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Phase 9: emit a self-contained server bundle so the production Docker
  // runtime stage only needs node_modules for the traced dependencies.
  output: "standalone",
  // Never leak secrets to the browser bundle.
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;

