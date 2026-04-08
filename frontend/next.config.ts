import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  async redirects() {
    return [
      {
        source: "/client/:id",
        destination: "/clients/:id",
        permanent: false,
      },
      {
        source: "/client/:id/orchestration",
        destination: "/clients/:id",
        permanent: false,
      },
      {
        source: "/client/:id/templates",
        destination: "/clients/:id/templates",
        permanent: false,
      },
      {
        source: "/client/:id/templates/create",
        destination: "/clients/:id/templates/new",
        permanent: false,
      },
      {
        source: "/client/:id/send-demo",
        destination: "/clients/:id/notifications/demo",
        permanent: false,
      },
      {
        source: "/client/:id/analytics",
        destination: "/clients/:id/analytics",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8000/api/:path*',
      },
      {
        source: '/admin/api/:path*',
        destination: 'http://127.0.0.1:8000/admin/api/:path*',
      }
    ];
  },
};

export default nextConfig;
