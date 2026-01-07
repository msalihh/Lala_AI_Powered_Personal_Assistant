"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Box, Text } from "@chakra-ui/react";
import { isAuthenticated, removeToken } from "@/lib/auth";
import { apiFetch } from "@/lib/api";

interface AuthGuardProps {
  children: React.ReactNode;
}

interface UserResponse {
  id: string;
  username: string;
  email: string | null;
  is_active: boolean;
  created_at: string;
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function verifyAuth() {
      if (!isAuthenticated()) {
        router.replace("/login");
        return;
      }

      // Verify token by calling /api/me
      try {
        await apiFetch<UserResponse>("/api/me");
        setIsLoading(false);

        // CRITICAL: Auto-sync Gmail in background immediately after successful login
        // This runs silently, no UI blocking
        // Check if we already triggered auto-sync for this session
        const autoSyncKey = 'gmail_auto_sync_triggered';
        if (!sessionStorage.getItem(autoSyncKey)) {
          sessionStorage.setItem(autoSyncKey, 'true');

          // Trigger auto-sync in background immediately (don't await, let it run silently)
          import("@/lib/api").then(({ getGmailStatus, syncGmail }) => {
            getGmailStatus().then((status) => {
              if (status.is_connected) {
                // Immediately sync on login (no delay check)
                // Sync in background (don't await, let it run silently)
                syncGmail().then((result) => {
                  const now = Date.now();
                  const lastSyncKey = `gmail_last_sync_${status.email || 'default'}`;
                  localStorage.setItem(lastSyncKey, now.toString());
                  console.log(`[AUTO-SYNC] Gmail synced on login: ${result.emails_indexed || 0} emails indexed`);
                }).catch((error) => {
                  // Silently fail - don't show error to user for background sync
                  console.warn("[AUTO-SYNC] Gmail sync failed on login (silent):", error);
                });
              } else {
                console.log("[AUTO-SYNC] Gmail not connected, skipping auto-sync");
              }
            }).catch((error) => {
              // Silently fail - don't show error to user for background sync
              console.warn("[AUTO-SYNC] Gmail status check failed on login (silent):", error);
            });
          });
        }
      } catch (error: any) {
        // Token is invalid or expired
        removeToken();
        router.replace("/login");
      }
    }

    verifyAuth();
  }, [router]);

  if (isLoading) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minH="100vh"
        bg="gray.900"
      >
        <Text>Yükleniyor...</Text>
      </Box>
    );
  }

  return <>{children}</>;
}

