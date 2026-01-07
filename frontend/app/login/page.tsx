"use client";

import { useState, FormEvent, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Box,
  VStack,
  Input,
  Button,
  Text,
  FormControl,
  FormLabel,
  FormErrorMessage,
  useColorModeValue,
  Heading,
  Link,
  Divider,
  useToast,
  HStack,
  InputGroup,
  InputRightElement,
  IconButton,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon } from "@chakra-ui/icons";
import { apiFetch, exchangeGoogleToken } from "@/lib/api";
import { setToken } from "@/lib/auth";
import LalaAILogo from "@/components/icons/LalaAILogo";

interface LoginResponse {
  access_token: string;
  token_type: string;
}

export default function LoginPage() {
  const router = useRouter();
  const toast = useToast();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);

  // Premium dark theme color palette
  const bgColor = useColorModeValue("#F9FAFB", "#0B0F14");
  const cardBg = useColorModeValue("#FFFFFF", "#111827");
  const borderColor = useColorModeValue("#E5E7EB", "#1F2937");
  const textPrimary = useColorModeValue("#111827", "#E5E7EB");
  const textSecondary = useColorModeValue("#6B7280", "#9CA3AF");
  const accentColor = useColorModeValue("#10B981", "#10B981");
  const accentHover = useColorModeValue("#34D399", "#34D399");
  const inputBg = useColorModeValue("#F9FAFB", "#1F2937");
  const inputBorder = useColorModeValue("#E5E7EB", "#1F2937");
  const hoverBg = useColorModeValue("#F3F4F6", "#1F2937");

  // Handle Google OAuth callback - check for session after redirect
  useEffect(() => {
    const handleGoogleCallback = async () => {
      // Check if we're returning from Google OAuth
      const callback = searchParams.get("callback");
      if (callback === "google") {
        setIsGoogleLoading(true);
        try {
          // Wait a moment for NextAuth to process the callback
          await new Promise(resolve => setTimeout(resolve, 1000));

          // Get the current session to access the ID token
          const response = await fetch("/api/auth/session");
          const currentSession: any = await response.json();

          if (currentSession?.id_token) {
            // Exchange Google ID token for our JWT
            const jwtResponse = await exchangeGoogleToken(currentSession.id_token);

            // Store our JWT token
            setToken(jwtResponse.access_token);

            // Redirect to chat
            router.push("/chat");
          } else {
            setError("Google token alınamadı");
            setIsGoogleLoading(false);
          }
        } catch (err: any) {
          console.error("Google callback error:", err);
          setError(err.detail || "Google giriş başarısız");
          setIsGoogleLoading(false);
        }
      }
    };

    handleGoogleCallback();
  }, [searchParams, router, toast]);

  // Handle Google sign-in button click
  // NextAuth v5: Provider sign-in requires POST request to /api/auth/signin/google
  const handleGoogleSignIn = async () => {
    setIsGoogleLoading(true);
    setError(null);

    try {
      // NextAuth v5: Provider sign-in requires POST request
      // First, get CSRF token from /api/auth/csrf
      const csrfResponse = await fetch("/api/auth/csrf");
      const { csrfToken } = await csrfResponse.json();

      // Create a form and submit it via POST
      const form = document.createElement("form");
      form.method = "POST";
      form.action = "/api/auth/signin/google";

      const csrfInput = document.createElement("input");
      csrfInput.type = "hidden";
      csrfInput.name = "csrfToken";
      csrfInput.value = csrfToken;
      form.appendChild(csrfInput);

      const callbackInput = document.createElement("input");
      callbackInput.type = "hidden";
      callbackInput.name = "callbackUrl";
      callbackInput.value = "/login?callback=google";
      form.appendChild(callbackInput);

      document.body.appendChild(form);
      form.submit();
    } catch (err: any) {
      console.error("Google sign-in error:", err);
      setError("Google giriş başlatılamadı");
      setIsGoogleLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const response = await apiFetch<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: username.trim(),
          password,
        }),
      });

      setToken(response.access_token);
      router.push("/chat");
    } catch (err: any) {
      setError(err.detail || "Giriş başarısız");
      setIsLoading(false);
    }
  };

  return (
    <Box
      minH="100vh"
      bg={bgColor}
      display="flex"
      alignItems="center"
      justifyContent="center"
      p={4}
      position="relative"
      sx={{
        "&::before": {
          content: '""',
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: useColorModeValue(
            "radial-gradient(circle at 20% 50%, rgba(16, 185, 129, 0.05) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(16, 185, 129, 0.05) 0%, transparent 50%)",
            "radial-gradient(circle at 20% 50%, rgba(16, 185, 129, 0.08) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(16, 185, 129, 0.08) 0%, transparent 50%)"
          ),
          pointerEvents: "none",
          zIndex: 0,
        },
      }}
    >
      <Box
        w="100%"
        maxW="440px"
        p={10}
        bg={cardBg}
        borderRadius="xl"
        border="1px solid"
        borderColor={borderColor}
        boxShadow="0 8px 32px rgba(0, 0, 0, 0.12)"
        position="relative"
        zIndex={1}
        sx={{
          animation: "fadeInUp 0.5s ease-out",
        }}
      >
        <VStack spacing={8} align="stretch">
          {/* Logo ve Başlık */}
          <VStack spacing={4}>
            <VStack spacing={3} align="center">
              <Box
                display="flex"
                alignItems="center"
                justifyContent="center"
                sx={{
                  "@keyframes float": {
                    "0%": { transform: "translateY(0px)" },
                    "50%": { transform: "translateY(-10px)" },
                    "100%": { transform: "translateY(0px)" },
                  },
                }}
              >
                <LalaAILogo
                  size={32}
                  sx={{
                    animation: "float 4s ease-in-out infinite",
                    filter: "drop-shadow(0 0 8px rgba(16, 185, 129, 0.3))",
                  }}
                />
              </Box>
              <Heading
                size="xl"
                fontWeight="700"
                color={textPrimary}
                letterSpacing="tight"
                textAlign="center"
              >
                Lala
              </Heading>
            </VStack>
            <Text
              fontSize="md"
              color={textSecondary}
              textAlign="center"
              fontWeight="400"
            >
              AI destekli sohbet uygulamasına hoş geldiniz
            </Text>
          </VStack>

          {/* Google Sign In Button */}
          <Button
            onClick={handleGoogleSignIn}
            isLoading={isGoogleLoading}
            w="100%"
            h="48px"
            bg={inputBg}
            border="1px solid"
            borderColor={inputBorder}
            color={textPrimary}
            fontSize="sm"
            fontWeight="500"
            _hover={{
              bg: hoverBg,
              borderColor: accentColor,
            }}
            _active={{
              bg: hoverBg,
              transform: "scale(0.98)",
            }}
            transition="all 0.2s ease"
            borderRadius="lg"
            display="flex"
            alignItems="center"
            justifyContent="center"
            gap={2}
          >
            <Box
              as="svg"
              w={5}
              h={5}
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </Box>
            Google ile giriş yap
          </Button>

          <HStack>
            <Divider borderColor={borderColor} />
            <Text fontSize="xs" color={textSecondary} px={2} fontWeight="500">
              VEYA
            </Text>
            <Divider borderColor={borderColor} />
          </HStack>

          <form onSubmit={handleSubmit}>
            <VStack spacing={5}>
              <FormControl isInvalid={!!error}>
                <FormLabel
                  fontSize="sm"
                  fontWeight="500"
                  color={textPrimary}
                  mb={2}
                >
                  Kullanıcı Adı
                </FormLabel>
                <Input
                  value={username}
                  onChange={(e) => {
                    setUsername(e.target.value);
                    setError(null);
                  }}
                  placeholder="Kullanıcı adınızı girin"
                  required
                  h="48px"
                  bg={inputBg}
                  border="1px solid"
                  borderColor={inputBorder}
                  color={textPrimary}
                  _placeholder={{ color: textSecondary }}
                  _hover={{
                    borderColor: accentColor,
                  }}
                  _focus={{
                    borderColor: accentColor,
                    boxShadow: `0 0 0 1px ${accentColor}`,
                  }}
                  transition="all 0.2s ease"
                  borderRadius="lg"
                />
              </FormControl>

              <FormControl isInvalid={!!error}>
                <FormLabel
                  fontSize="sm"
                  fontWeight="500"
                  color={textPrimary}
                  mb={2}
                >
                  Şifre
                </FormLabel>
                <InputGroup>
                  <Input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setError(null);
                    }}
                    placeholder="Şifrenizi girin"
                    required
                    h="48px"
                    bg={inputBg}
                    border="1px solid"
                    borderColor={inputBorder}
                    color={textPrimary}
                    _placeholder={{ color: textSecondary }}
                    _hover={{
                      borderColor: accentColor,
                    }}
                    _focus={{
                      borderColor: accentColor,
                      boxShadow: `0 0 0 1px ${accentColor}`,
                    }}
                    transition="all 0.2s ease"
                    borderRadius="lg"
                    pr="48px"
                  />
                  <InputRightElement h="48px" w="48px">
                    <IconButton
                      aria-label={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
                      icon={showPassword ? <ViewOffIcon /> : <ViewIcon />}
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowPassword(!showPassword)}
                      color={textSecondary}
                      _hover={{
                        color: textPrimary,
                        bg: hoverBg,
                      }}
                    />
                  </InputRightElement>
                </InputGroup>
                {error && (
                  <FormErrorMessage mt={2} fontSize="sm">
                    {error}
                  </FormErrorMessage>
                )}
              </FormControl>

              <Button
                type="submit"
                w="100%"
                h="48px"
                bg={accentColor}
                color="white"
                fontSize="sm"
                fontWeight="600"
                _hover={{
                  bg: accentHover,
                  transform: "translateY(-1px)",
                  boxShadow: "0 4px 12px rgba(59, 130, 246, 0.3)",
                }}
                _active={{
                  transform: "translateY(0)",
                  bg: accentHover,
                }}
                isLoading={isLoading}
                loadingText="Giriş yapılıyor..."
                transition="all 0.2s ease"
                borderRadius="lg"
                mt={2}
              >
                Giriş Yap
              </Button>
            </VStack>
          </form>

          <Text textAlign="center" fontSize="sm" color={textSecondary}>
            Hesabınız yok mu?{" "}
            <Link
              href="/register"
              color={accentColor}
              fontWeight="600"
              _hover={{
                textDecoration: "underline",
                color: accentHover,
              }}
              transition="color 0.2s ease"
            >
              Kayıt olun
            </Link>
          </Text>
        </VStack>
      </Box>
    </Box>
  );
}
