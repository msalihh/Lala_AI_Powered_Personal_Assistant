import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";

// Force Node.js runtime (not Edge) to support fs module
export const runtime = 'nodejs';

/**
 * NextAuth Configuration with Google OAuth
 * 
 * SECURITY NOTES:
 * - All secrets are read from environment variables (never hardcoded)
 * - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env.local
 * - NEXTAUTH_URL must match the Authorized JS Origin in Google Console
 * - NEXTAUTH_SECRET is used to encrypt JWT tokens
 * 
 * Callback URL: /api/auth/callback/google
 * This must match exactly with the Authorized Redirect URI in Google Console
 */
const authOptions = {
  providers: [
    GoogleProvider({
      // SECURITY: Read from environment variables only - never hardcode
      // NextAuth v5 supports both AUTH_GOOGLE_ID and GOOGLE_CLIENT_ID formats
      // Using AUTH_GOOGLE_ID is preferred for NextAuth v5 auto-inference
      clientId: process.env.AUTH_GOOGLE_ID || process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.AUTH_GOOGLE_SECRET || process.env.GOOGLE_CLIENT_SECRET!,
      // Explicitly set the provider ID to ensure NextAuth v5 recognizes it
      id: "google",
      // Callback URL is automatically set to: /api/auth/callback/google
      // This must match the Authorized Redirect URI in Google Console
    }),
  ],
  pages: {
    signIn: "/login",
    error: "/login",
    // Callback page will handle the Google OAuth callback and exchange token
  },
  callbacks: {
    // This callback runs after successful Google sign-in
    // NextAuth v5: account is only available on the first call (during OAuth flow)
    async jwt({ token, account, trigger }: any) {
      // Store the Google ID token in the JWT callback
      // account is only available during the OAuth callback, not on subsequent calls
      if (account?.id_token) {
        token.id_token = account.id_token;
      }
      return token;
    },
    async session({ session, token }: any) {
      // Pass the ID token to the session
      (session as any).id_token = token.id_token;
      return session;
    },
  },
  // We don't need database session storage since we use JWT
  session: {
    strategy: "jwt" as const,
  },
  // SECURITY: NEXTAUTH_URL environment variable is automatically used by NextAuth
  // This ensures the callback URL matches Google Console configuration
  // Callback URL will be: ${NEXTAUTH_URL}/api/auth/callback/google
};

// NextAuth v5: Create handler instance
// NextAuth v5 beta.30: NextAuth() returns an object with handlers, auth, signIn, signOut
const nextAuthResult: any = NextAuth(authOptions);
const { handlers } = nextAuthResult || {};

// NextAuth v5: Export route handlers for App Router
const originalGet = handlers?.GET;
const originalPost = handlers?.POST;

// CRITICAL: If handlers are undefined, Next.js won't recognize this as a route
// Export a fallback error handler so we can at least see the route is being called
export const GET = originalGet || (async (req: Request) => {
  return new Response(JSON.stringify({error:'NextAuth handlers not initialized'}),{status:500,headers:{'Content-Type':'application/json'}});
});

export const POST = originalPost || (async (req: Request) => {
  return new Response(JSON.stringify({error:'NextAuth handlers not initialized'}),{status:500,headers:{'Content-Type':'application/json'}});
});
