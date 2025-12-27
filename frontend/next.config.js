/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      // Rewrite backend API routes to FastAPI server
      // CRITICAL: /api/auth/* routes are EXCLUDED - they are handled by NextAuth route handler
      {
        source: "/api/me",
        destination: "http://127.0.0.1:8000/me",
      },
      {
        source: "/api/auth/login",
        destination: "http://127.0.0.1:8000/auth/login",
      },
      {
        source: "/api/auth/register",
        destination: "http://127.0.0.1:8000/auth/register",
      },
      {
        source: "/api/documents",
        destination: "http://127.0.0.1:8000/documents",
      },
      {
        source: "/api/documents/:path*",
        destination: "http://127.0.0.1:8000/documents/:path*",
      },
      {
        source: "/api/chats",
        destination: "http://127.0.0.1:8000/chats",
      },
      {
        source: "/api/chats/:path*",
        destination: "http://127.0.0.1:8000/chats/:path*",
      },
      {
        source: "/api/chat",
        destination: "http://127.0.0.1:8000/chat",
      },
      {
        source: "/api/chat/runs/:path*",
        destination: "http://127.0.0.1:8000/chat/runs/:path*",
      },
      // Backend Google token exchange endpoint
      // Using /api/google-auth to avoid conflict with NextAuth /api/auth/* routes
      // Backend endpoint is /auth/google (not /api/auth/google)
      {
        source: "/api/google-auth",
        destination: "http://127.0.0.1:8000/auth/google",
      },
      // DO NOT add /api/auth/* routes - they are handled by NextAuth in app/api/auth/[...nextauth]/route.ts
    ];
  },
};

module.exports = nextConfig;

