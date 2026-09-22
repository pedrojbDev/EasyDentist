import type { NextConfig } from 'next';

const apiInternalBaseUrl = process.env.API_INTERNAL_BASE_URL ?? 'http://localhost:8000';

const nextConfig: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  typedRoutes: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiInternalBaseUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
