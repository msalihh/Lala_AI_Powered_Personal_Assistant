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

