"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Box,
  VStack,
  Text,
  Button,
  Heading,
  useColorModeValue,
  Card,
  CardBody,
} from "@chakra-ui/react";
import AuthGuard from "@/components/AuthGuard";
import { apiFetch } from "@/lib/api";
import { removeToken } from "@/lib/auth";

interface UserResponse {
  id: string;
  username: string;
  email: string | null;
  is_active: boolean;
  created_at: string;
}

export default function AppPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bgColor = useColorModeValue("gray.50", "gray.900");
  const cardBg = useColorModeValue("white", "gray.800");

  useEffect(() => {
    async function fetchUser() {
      try {
        const response = await apiFetch<UserResponse>("/api/me");
        setUser(response);
      } catch (err: any) {
        setError(err.detail || "Kullanıcı bilgileri alınamadı");
      }
    }

    fetchUser();
  }, []);

  const handleLogout = () => {
    removeToken();
    router.push("/login");
  };

  return (
    <AuthGuard>
      <Box minH="100vh" bg={bgColor} p={8}>
        <VStack spacing={6} maxW="600px" mx="auto">
          <Heading>Dashboard</Heading>

          {error && (
            <Box p={4} bg="red.100" color="red.800" borderRadius="md" w="100%">
              {error}
            </Box>
          )}

          {user && (
            <Card w="100%" bg={cardBg}>
              <CardBody>
                <VStack align="stretch" spacing={4}>
                  <Text>
                    <strong>ID:</strong> {user.id}
                  </Text>
                  <Text>
                    <strong>Kullanıcı Adı:</strong> {user.username}
                  </Text>
                  <Text>
                    <strong>E-posta:</strong> {user.email || "N/A"}
                  </Text>
                  <Text>
                    <strong>Aktif:</strong> {user.is_active ? "Evet" : "Hayır"}
                  </Text>
                  <Text>
                    <strong>Oluşturulma:</strong>{" "}
                    {new Date(user.created_at).toLocaleString("tr-TR")}
                  </Text>
                </VStack>
              </CardBody>
            </Card>
          )}

          <Button
            colorScheme="brand"
            onClick={() => router.push("/chat")}
            w="100%"
          >
            Chat'e Git
          </Button>

          <Button
            colorScheme="blue"
            variant="outline"
            onClick={() => router.push("/app/documents")}
            w="100%"
          >
            Dokümanlarım
          </Button>

          <Button
            colorScheme="red"
            variant="outline"
            onClick={handleLogout}
            w="100%"
            size="lg"
          >
            Çıkış Yap
          </Button>
        </VStack>
      </Box>
    </AuthGuard>
  );
}
