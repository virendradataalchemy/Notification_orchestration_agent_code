import type { NextConfig } from "next";
import path from "node:path";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },

  compress: true,
  productionBrowserSourceMaps: false,

  experimental: {
    optimizePackageImports: ["@supabase/supabase-js"],
  },

  async redirects() {
    return [
      { source: "/client/:id",                  destination: "/clients/:id",                    permanent: false },
      { source: "/client/:id/orchestration",    destination: "/clients/:id",                    permanent: false },
      { source: "/client/:id/templates",        destination: "/clients/:id/templates",          permanent: false },
      { source: "/client/:id/templates/create", destination: "/clients/:id/templates/new",      permanent: false },
      { source: "/client/:id/send-demo",        destination: "/clients/:id/notifications/demo", permanent: false },
      { source: "/client/:id/analytics",        destination: "/clients/:id/analytics",          permanent: false },
    ];
  },

  // Only set custom cache headers in production — dev mode handles its own caching
  ...(!isDev && {
    async headers() {
      return [
        {
          source: "/_next/static/:path*",
          headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
        },
      ];
    },
  }),

  async rewrites() {
    return [
      { source: "/api/:path*",       destination: "http://127.0.0.1:8000/api/:path*" },
      { source: "/admin/api/:path*", destination: "http://127.0.0.1:8000/admin/api/:path*" },
    ];
  },
};

export default nextConfig;
