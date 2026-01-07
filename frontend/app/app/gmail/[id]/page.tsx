"use client";

import { useState, useEffect } from "react";
import {
  Box,
  VStack,
  HStack,
  Button,
  Text,
  Heading,
  useColorModeValue,
  Card,
  CardBody,
  Spinner,
  useToast,
  Badge,
  IconButton,
  Tooltip,
  Divider,
  Skeleton,
  SkeletonText,
} from "@chakra-ui/react";
import { useRouter, useParams } from "next/navigation";
import { ArrowBackIcon } from "@chakra-ui/icons";
import AuthGuard from "@/components/AuthGuard";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { getGmailMessage } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import GmailIcon from "@/components/icons/GmailIcon";

interface GmailMessageDetail {
  id: string;
  thread_id?: string;
  threadId?: string;
  subject: string;
  sender: string;
  date: string;
  snippet: string;
  body: string;
}

export default function GmailDetailPage() {
  const router = useRouter();
  const params = useParams();
  const toast = useToast();
  const { isOpen, toggle } = useSidebar();
  const messageId = params.id as string;
  const [message, setMessage] = useState<GmailMessageDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cache utilities for message details
  const getCachedMessage = (msgId: string): GmailMessageDetail | null => {
    try {
      const cached = localStorage.getItem(`gmail-message-${msgId}`);
      if (!cached) return null;

      const { data, timestamp } = JSON.parse(cached);
      const now = Date.now();
      const CACHE_DURATION = 30 * 60 * 1000; // 30 dakika (daha uzun cache)

      if (now - timestamp > CACHE_DURATION) {
        localStorage.removeItem(`gmail-message-${msgId}`);
        return null;
      }

      return data;
    } catch {
      return null;
    }
  };

  const setCachedMessage = (msgId: string, message: GmailMessageDetail) => {
    try {
      localStorage.setItem(`gmail-message-${msgId}`, JSON.stringify({
        data: message,
        timestamp: Date.now()
      }));
    } catch (error) {
      console.warn("Failed to cache message:", error);
    }
  };

  // Consistent theme colors matching app design - ALL hooks must be at top level
  // Aligned with app's emerald green accent palette
  const bgColor = useColorModeValue("#F9FAFB", "#0B0F14");
  const cardBg = useColorModeValue("#FFFFFF", "#111827");
  const borderColor = useColorModeValue("#E7ECF0", "#1F2937");
  const textPrimary = useColorModeValue("#1F2328", "#E5E7EB");
  const textSecondary = useColorModeValue("#656D76", "#9CA3AF");
  const textMuted = useColorModeValue("#8B949E", "#6B7280");
  const accentPrimary = useColorModeValue("#059669", "#10B981");
  const scrollbarTrack = useColorModeValue("#f1f1f1", "#1F2937");
  const scrollbarThumb = useColorModeValue("#888", "#4A5568");
  const scrollbarThumbHover = useColorModeValue("#555", "#718096");
  // Additional color values used in JSX - must be at top level
  const sidebarToggleColor = useColorModeValue("gray.700", "gray.200");
  const sidebarToggleBg = useColorModeValue("white", "gray.800");
  const sidebarToggleBorder = useColorModeValue("gray.200", "gray.700");
  const sidebarToggleHoverBg = useColorModeValue("gray.50", "gray.700");
  const sidebarToggleHoverColor = useColorModeValue("gray.900", "white");
  const sidebarToggleHoverBorder = useColorModeValue("gray.300", "gray.600");
  const backButtonHoverBg = useColorModeValue("#F0F3F6", "#1F2937");
  const mailBodyBg = useColorModeValue("white", "gray.900");
  const mailBodyFontFamily = useColorModeValue("system-ui", "system-ui");
  const codeBg = useColorModeValue("gray.100", "gray.700");

  useEffect(() => {
    if (messageId) {
      // Try to load from cache first - INSTANT display
      const cached = getCachedMessage(messageId);
      if (cached) {
        setMessage(cached);
        setIsLoading(false);
        setIsRefreshing(false);
        // Load fresh data in background silently
        loadMessage(true).catch(() => {
          // Silent fail - we already have cached data
        });
      } else {
        loadMessage(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messageId]);

  const loadMessage = async (isBackgroundRefresh: boolean = false): Promise<void> => {
    try {
      if (!isBackgroundRefresh) {
        setIsLoading(true);
        setError(null);
      }
      const msg = await getGmailMessage(messageId);
      if (!msg) {
        throw new Error("Mail verisi alınamadı");
      }
      setMessage(msg);
      // Cache the message
      setCachedMessage(messageId, msg);
    } catch (error: any) {
      console.error("Gmail message load error:", error);
      const errorMessage = error.detail || error.message || "Mail yüklenemedi";

      // Only show error and set error state if not a background refresh
      if (!isBackgroundRefresh) {
        setError(errorMessage);
        toast({
          title: "Hata",
          description: errorMessage,
          status: "error",
          duration: 5000,
        });
      }
    } finally {
      if (!isBackgroundRefresh) {
        setIsLoading(false);
      }
      setIsRefreshing(false);
    }
  };

  const handleRetry = () => {
    loadMessage(false);
  };

  const handleBack = () => {
    router.back();
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleString("tr-TR");
    } catch {
      return dateString;
    }
  };

  // Custom Sidebar Toggle Icon Component
  const SidebarToggleIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
    </svg>
  );

  return (
    <AuthGuard>
      <Box display="flex" h="100vh" bg={bgColor} position="relative">
        {/* Sidebar Toggle Button */}
        {!isOpen && (
          <Tooltip label="Kenar çubuğunu aç" placement="right" hasArrow>
            <IconButton
              icon={<SidebarToggleIcon />}
              aria-label="Kenar çubuğunu aç"
              onClick={toggle}
              position="fixed"
              left={4}
              top="50%"
              transform="translateY(-50%)"
              size="md"
              variant="ghost"
              color={sidebarToggleColor}
              bg={sidebarToggleBg}
              border="1px"
              borderColor={sidebarToggleBorder}
              _hover={{
                bg: sidebarToggleHoverBg,
                color: sidebarToggleHoverColor,
                borderColor: sidebarToggleHoverBorder
              }}
              transition="all 0.2s ease"
              zIndex={1000}
              borderRadius="lg"
              boxShadow="sm"
              minW="44px"
              h="44px"
            />
          </Tooltip>
        )}
        <Sidebar />
        <Box
          flex={1}
          ml={isOpen ? "260px" : "0"}
          display="flex"
          flexDirection="column"
          transition="margin-left 0.3s ease"
        >
          <Topbar />
          <Box flex={1} mt="60px" overflowY="auto" p={6}>
            <VStack spacing={6} align="stretch" maxW="6xl" mx="auto">
              <HStack>
                <Button
                  leftIcon={<ArrowBackIcon />}
                  variant="ghost"
                  onClick={handleBack}
                  color={textPrimary}
                  _hover={{ bg: backButtonHoverBg }}
                >
                  Geri
                </Button>
              </HStack>

              {isLoading && !message ? (
                <>
                  {/* Skeleton Loader for Mail Detail - Only show if no cached message */}
                  <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                    <CardBody>
                      <VStack align="stretch" spacing={4}>
                        <HStack justify="space-between">
                          <Skeleton height="24px" width="60%" />
                          <Skeleton height="20px" width="80px" />
                        </HStack>
                        <Divider borderColor={borderColor} />
                        <VStack align="stretch" spacing={2}>
                          <HStack justify="space-between">
                            <Skeleton height="16px" width="80px" />
                            <Skeleton height="16px" width="200px" />
                          </HStack>
                          <HStack justify="space-between">
                            <Skeleton height="16px" width="60px" />
                            <Skeleton height="16px" width="250px" />
                          </HStack>
                        </VStack>
                      </VStack>
                    </CardBody>
                  </Card>
                  <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                    <CardBody>
                      <VStack align="stretch" spacing={4}>
                        <Skeleton height="20px" width="120px" />
                        <SkeletonText noOfLines={10} spacing="4" />
                      </VStack>
                    </CardBody>
                  </Card>
                </>
              ) : error && !message ? (
                <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                  <CardBody textAlign="center" py={12}>
                    <VStack spacing={4}>
                      <Text fontSize="4xl">⚠️</Text>
                      <Heading size="md" color={textPrimary}>
                        Mail Yüklenemedi
                      </Heading>
                      <Text fontSize="lg" color={textSecondary} maxW="500px">
                        {error}
                      </Text>
                      <HStack spacing={3}>
                        <Button colorScheme="green" onClick={handleRetry}>
                          Tekrar Dene
                        </Button>
                        <Button variant="ghost" onClick={handleBack} color={textPrimary} _hover={{ bg: backButtonHoverBg }}>
                          Geri Dön
                        </Button>
                      </HStack>
                    </VStack>
                  </CardBody>
                </Card>
              ) : !message ? (
                <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                  <CardBody textAlign="center" py={12}>
                    <VStack spacing={4}>
                      <Box>
                        <img src="/email.png" alt="Email" style={{ width: '48px', height: '48px', objectFit: 'contain' }} />
                      </Box>
                      <Text fontSize="lg" color={textSecondary}>
                        Mail bulunamadı
                      </Text>
                      <Button variant="ghost" onClick={handleBack}>
                        Geri Dön
                      </Button>
                    </VStack>
                  </CardBody>
                </Card>
              ) : (
                <>
                  {/* Mail Header */}
                  <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                    <CardBody>
                      <VStack align="stretch" spacing={4}>
                        <HStack justify="space-between" align="start">
                          <Heading size="md" color={textPrimary} fontWeight="600" letterSpacing="-0.02em" flex={1} lineHeight="1.3">
                            {message.subject || "Konu yok"}
                          </Heading>
                          <Badge colorScheme="green" fontSize="xs" px={2.5} py={1} borderRadius="md" fontWeight="500" letterSpacing="0.05em">
                            E-POSTA
                          </Badge>
                        </HStack>
                        <Divider borderColor={borderColor} />
                        <VStack align="stretch" spacing={2.5}>
                          <HStack justify="space-between" fontSize="sm">
                            <Text color={textMuted} fontWeight="500" letterSpacing="0.01em">Gönderen</Text>
                            <Text fontWeight="600" color={textPrimary} textAlign="right" letterSpacing="-0.01em">
                              {message.sender}
                            </Text>
                          </HStack>
                          <HStack justify="space-between" fontSize="sm">
                            <Text color={textMuted} fontWeight="500" letterSpacing="0.01em">Tarih</Text>
                            <Text fontWeight="400" color={textSecondary} textAlign="right" fontSize="xs">
                              {formatDate(message.date)}
                            </Text>
                          </HStack>
                          {(message.thread_id || message.threadId) && (
                            <HStack justify="space-between" fontSize="sm">
                              <Text color={textMuted} fontWeight="500" letterSpacing="0.01em">Thread ID</Text>
                              <Text fontWeight="400" color={textMuted} fontSize="xs" fontFamily="mono" textAlign="right">
                                {message.thread_id || message.threadId}
                              </Text>
                            </HStack>
                          )}
                        </VStack>
                      </VStack>
                    </CardBody>
                  </Card>

                  {/* Mail Body - PDF Viewer Style */}
                  <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                    <CardBody>
                      <VStack align="stretch" spacing={4}>
                        <Heading size="sm" color={textPrimary} fontWeight="600" letterSpacing="-0.01em" mb={1}>Mail İçeriği</Heading>
                        <Box
                          w="100%"
                          minH="60vh"
                          maxH="80vh"
                          border="1px solid"
                          borderColor={borderColor}
                          borderRadius="md"
                          overflowY="auto"
                          bg={mailBodyBg}
                          p={6}
                          css={{
                            "&::-webkit-scrollbar": {
                              width: "8px",
                            },
                            "&::-webkit-scrollbar-track": {
                              background: scrollbarTrack,
                            },
                            "&::-webkit-scrollbar-thumb": {
                              background: scrollbarThumb,
                              borderRadius: "4px",
                            },
                            "&::-webkit-scrollbar-thumb:hover": {
                              background: scrollbarThumbHover,
                            },
                          }}
                        >
                          {message.body ? (
                            <Box
                              fontSize="md"
                              lineHeight="1.8"
                              color={textPrimary}
                              whiteSpace="pre-wrap"
                              wordBreak="break-word"
                              fontFamily={mailBodyFontFamily}
                            >
                              <ReactMarkdown
                                remarkPlugins={[remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={{
                                  p: ({ children }) => <Text mb={4}>{children}</Text>,
                                  h1: ({ children }) => <Heading size="lg" mb={4} mt={6}>{children}</Heading>,
                                  h2: ({ children }) => <Heading size="md" mb={3} mt={5}>{children}</Heading>,
                                  h3: ({ children }) => <Heading size="sm" mb={2} mt={4}>{children}</Heading>,
                                  ul: ({ children }) => <Box as="ul" pl={6} mb={4}>{children}</Box>,
                                  ol: ({ children }) => <Box as="ol" pl={6} mb={4}>{children}</Box>,
                                  li: ({ children }) => <Box as="li" mb={2}>{children}</Box>,
                                  code: ({ children, className }) => {
                                    const isInline = !className;
                                    return isInline ? (
                                      <Text
                                        as="code"
                                        bg={codeBg}
                                        px={1}
                                        py={0.5}
                                        borderRadius="sm"
                                        fontSize="0.9em"
                                        fontFamily="mono"
                                      >
                                        {children}
                                      </Text>
                                    ) : (
                                      <Box
                                        as="pre"
                                        bg={codeBg}
                                        p={4}
                                        borderRadius="md"
                                        overflowX="auto"
                                        mb={4}
                                      >
                                        <Text as="code" fontFamily="mono" fontSize="sm">
                                          {children}
                                        </Text>
                                      </Box>
                                    );
                                  },
                                  blockquote: ({ children }) => (
                                    <Box
                                      borderLeft="4px solid"
                                      borderColor="green.500"
                                      pl={4}
                                      my={4}
                                      fontStyle="italic"
                                      color={textSecondary}
                                    >
                                      {children}
                                    </Box>
                                  ),
                                }}
                              >
                                {message.body}
                              </ReactMarkdown>
                            </Box>
                          ) : (
                            <Text color={textSecondary} fontStyle="italic">
                              Mail içeriği bulunamadı
                            </Text>
                          )}
                        </Box>
                      </VStack>
                    </CardBody>
                  </Card>

                  {/* Snippet (Preview) */}
                  {message.snippet && message.snippet !== message.body && (
                    <Card bg={cardBg} border="1px solid" borderColor={borderColor} borderRadius="xl">
                      <CardBody>
                        <VStack align="stretch" spacing={4}>
                          <Heading size="sm" color={textPrimary}>Önizleme</Heading>
                          <Text fontSize="sm" color={textSecondary} fontStyle="italic">
                            {message.snippet}
                          </Text>
                        </VStack>
                      </CardBody>
                    </Card>
                  )}
                </>
              )}
            </VStack>
          </Box>
        </Box>
      </Box>
    </AuthGuard>
  );
}

