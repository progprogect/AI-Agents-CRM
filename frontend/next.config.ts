import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  
  // Enable standalone output for Docker
  output: 'standalone',
  
  // Code splitting optimization
  experimental: {
    optimizePackageImports: ['@/components', '@/lib'],
  },

  // Image optimization
  images: {
    domains: [],
  },

  // Headers для правильной работы кэширования и безопасности
  async headers() {
    return [
      {
        // Применяем заголовки безопасности ко всем страницам
        source: '/:path*',
        headers: [
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains; preload'
          },
          {
            key: 'Content-Security-Policy',
            value: 'upgrade-insecure-requests'
          },
        ],
      },
      {
        // Статические файлы с хешами можно кэшировать долго
        source: '/_next/static/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ];
  },
};

export default withNextIntl(nextConfig);
