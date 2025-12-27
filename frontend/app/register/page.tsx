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

interface RegisterResponse {
  message: string;
  user_id: string;
}

export default function RegisterPage() {
  const router = useRouter();
  const toast = useToast();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);
  
  // Uygulama renk paleti
  const bgColor = useColorModeValue("#FFFFFF", "#0D1117");
  const cardBg = useColorModeValue("#F6F8FA", "#161B22");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  const textPrimary = useColorModeValue("#1F2328", "#E6EDF3");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const accentColor = useColorModeValue("#1A7F37", "#3FB950");
  const accentHover = useColorModeValue("#2EA043", "#2EA043");
  const inputBg = useColorModeValue("#FFFFFF", "#1C2128");
  const inputBorder = useColorModeValue("#D1D9E0", "#30363D");
  const hoverBg = useColorModeValue("#E7ECF0", "#22272E");

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
          
          console.log("[Google Callback] Session data:", {
            hasSession: !!currentSession,
            hasIdToken: !!currentSession?.id_token,
            sessionKeys: currentSession ? Object.keys(currentSession) : []
          });

          if (currentSession?.id_token) {
            // Exchange Google ID token for our JWT
            const jwtResponse = await exchangeGoogleToken(currentSession.id_token);
            
            // Store our JWT token
            setToken(jwtResponse.access_token);

            // Redirect to chat
            router.push("/chat");
          } else {
            console.error("[Google Callback] No id_token in session:", currentSession);
            setError("Google token alınamadı. Session: " + JSON.stringify(currentSession));
            setIsGoogleLoading(false);
          }
        } catch (err: any) {
          console.error("Google callback error:", err);
          const errorMessage = err.detail || err.message || "Google giriş başarısız";
          setError(errorMessage);
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
      callbackInput.value = "/register?callback=google";
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
      await apiFetch<RegisterResponse>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim() || undefined,
          password,
        }),
      });

      router.push("/login");
    } catch (err: any) {
      setError(err.detail || "Kayıt başarısız");
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
            "radial-gradient(circle at 20% 50%, rgba(26, 127, 55, 0.05) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(26, 127, 55, 0.05) 0%, transparent 50%)",
            "radial-gradient(circle at 20% 50%, rgba(63, 185, 80, 0.08) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(63, 185, 80, 0.08) 0%, transparent 50%)"
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
            <HStack spacing={3} justify="center">
              <Box
                as="img"
                src="/hace-logo.svg"
                alt="HACE Logo"
                w="40px"
                h="40px"
              />
              <Heading
                size="xl"
                fontWeight="700"
                color={textPrimary}
                letterSpacing="tight"
              >
                HACE
              </Heading>
            </HStack>
            <Text
              fontSize="md"
              color={textSecondary}
              textAlign="center"
              fontWeight="400"
            >
              Yeni hesap oluşturun ve AI destekli sohbetin keyfini çıkarın
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
            Google ile kaydol
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
                  Kullanıcı Adı *
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

              <FormControl>
                <FormLabel
                  fontSize="sm"
                  fontWeight="500"
                  color={textPrimary}
                  mb={2}
                >
                  E-posta (isteğe bağlı)
                </FormLabel>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError(null);
                  }}
                  placeholder="E-posta adresiniz"
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
                  Şifre *
                </FormLabel>
                <InputGroup>
                  <Input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setError(null);
                    }}
                    placeholder="Şifrenizi girin (min 6 karakter)"
                    required
                    minLength={6}
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
                  boxShadow: "0 4px 12px rgba(63, 185, 80, 0.3)",
                }}
                _active={{
                  transform: "translateY(0)",
                  bg: accentHover,
                }}
                isLoading={isLoading}
                loadingText="Kayıt olunuyor..."
                transition="all 0.2s ease"
                borderRadius="lg"
                mt={2}
              >
                Kayıt Ol
              </Button>
            </VStack>
          </form>

          <Text textAlign="center" fontSize="sm" color={textSecondary}>
            Zaten hesabınız var mı?{" "}
            <Link
              href="/login"
              color={accentColor}
              fontWeight="600"
              _hover={{
                textDecoration: "underline",
                color: accentHover,
              }}
              transition="color 0.2s ease"
            >
              Giriş yapın
            </Link>
          </Text>
        </VStack>
      </Box>
    </Box>
  );
}
