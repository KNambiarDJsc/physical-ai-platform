import type { NextConfig } from "next";

const api = process.env.PAP_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The browser talks to the web origin only; the API is proxied server-side.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default config;
