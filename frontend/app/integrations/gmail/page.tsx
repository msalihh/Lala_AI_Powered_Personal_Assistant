"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Box,
  VStack,
  Heading,
  Text,
  Spinner,
  Alert,
  AlertIcon,
  Button,
  useToast,
} from "@chakra-ui/react";
import { handleGmailCallback, getGmailStatus } from "@/lib/api";

export default function GmailCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    const processCallback = async () => {
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      const error = searchParams.get("error");

      if (error) {
        setStatus("error");
        setMessage(`Google OAuth hatası: ${error}`);
        return;
      }

      if (!code || !state) {
        setStatus("error");
        setMessage("Eksik parametreler: code veya state bulunamadı");
        return;
      }

      try {
        const result = await handleGmailCallback(code, state);
        setStatus("success");
        setMessage(`Gmail başarıyla bağlandı: ${result.email}`);
        
        // Redirect to app page after 2 seconds
        setTimeout(() => {
          router.push("/app");
        }, 2000);
      } catch (err: any) {
        console.error("Gmail callback error:", err);
        setStatus("error");
        
        // Handle specific error codes
        if (err.code === "GMAIL_NOT_CONFIGURED") {
          setMessage("Gmail entegrasyonu yapılandırılmamış. Lütfen yöneticiye başvurun.");
        } else if (err.code === "INVALID_STATE") {
          setMessage("Geçersiz veya süresi dolmuş bağlantı. Lütfen tekrar deneyin.");
        } else {
          setMessage(err.detail || "Gmail bağlantısı sırasında bir hata oluştu.");
        }
      }
    };

    processCallback();
  }, [searchParams, router, toast]);

  return (
    <Box
      minH="100vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      bg="gray.50"
      _dark={{ bg: "gray.900" }}
    >
      <VStack spacing={6} maxW="md" w="full" p={8}>
        <Heading size="lg">Gmail Bağlantısı</Heading>

        {status === "loading" && (
          <>
            <Spinner size="xl" color="green.500" />
            <Text>Gmail bağlantısı kuruluyor...</Text>
          </>
        )}

        {status === "success" && (
          <>
            <Alert status="success" borderRadius="md">
              <AlertIcon />
              {message}
            </Alert>
            <Text fontSize="sm" color="gray.600">
              Ana sayfaya yönlendiriliyorsunuz...
            </Text>
            <Button
              colorScheme="green"
              onClick={() => router.push("/app")}
            >
              Ana Sayfaya Dön
            </Button>
          </>
        )}

        {status === "error" && (
          <>
            <Alert status="error" borderRadius="md">
              <AlertIcon />
              {message}
            </Alert>
            <Button
              colorScheme="green"
              onClick={() => router.push("/app")}
            >
              Ana Sayfaya Dön
            </Button>
          </>
        )}
      </VStack>
    </Box>
  );
}

