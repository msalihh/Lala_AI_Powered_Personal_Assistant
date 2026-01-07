/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backendUrl = 'http://127.0.0.1:8000';

    return [
      // Health check
      {
        source: '/api/health',
        destination: `${backendUrl}/health`,
      },
      // Auth routes
      {
        source: '/api/auth/login',
        destination: `${backendUrl}/auth/login`,
      },
      {
        source: '/api/auth/register',
        destination: `${backendUrl}/auth/register`,
      },
      {
        source: '/api/google-auth',
        destination: `${backendUrl}/auth/google`,
      },
      // User routes
      {
        source: '/api/me',
        destination: `${backendUrl}/me`,
      },
      {
        source: '/api/me/:path*',
        destination: `${backendUrl}/me/:path*`,
      },
      {
        source: '/api/user/settings',
        destination: `${backendUrl}/user/settings`,
      },
      // Chat routes
      {
        source: '/api/chat',
        destination: `${backendUrl}/chat`,
      },
      {
        source: '/api/chat/runs/:path*',
        destination: `${backendUrl}/chat/runs/:path*`,
      },
      {
        source: '/api/chats',
        destination: `${backendUrl}/chats`,
      },
      {
        source: '/api/chats/:path*',
        destination: `${backendUrl}/chats/:path*`,
      },
      // Documents
      {
        source: '/api/documents',
        destination: `${backendUrl}/documents`,
      },
      {
        source: '/api/documents/:path*',
        destination: `${backendUrl}/documents/:path*`,
      },
      // Integrations
      {
        source: '/api/integrations/:path*',
        destination: `${backendUrl}/integrations/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
