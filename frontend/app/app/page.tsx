"use client";

import { useEffect, useState, useRef } from "react";
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
  HStack,
  IconButton,
  useToast,
  Divider,
  Avatar,
  Badge,
  Flex,
  Spinner,
  Icon,
  Grid,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Tooltip,
  Progress,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  useDisclosure,
} from "@chakra-ui/react";
import { DeleteIcon, RepeatIcon, ArrowBackIcon, ChatIcon, ViewIcon } from "@chakra-ui/icons";
import {
  FaFileAlt,
  FaSignOutAlt,
  FaArchive,
  FaTrash,
  FaUndo,
  FaUser,
  FaCalendarAlt,
  FaComments,
  FaRocket,
  FaChartLine,
  FaCog,
} from "react-icons/fa";
import AuthGuard from "@/components/AuthGuard";
import { apiFetch, listArchivedChats, archiveChat, deleteChat, listChats } from "@/lib/api";
import { removeToken } from "@/lib/auth";

interface UserResponse {
  id: string;
  username: string;
  email: string | null;
  is_active: boolean;
  created_at: string;
  avatar_url?: string | null;
}

interface ChatListItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

const GmailIntegrationStatus = ({ isConnected }: { isConnected: boolean }) => (
  <Badge colorScheme={isConnected ? "green" : "gray"} borderRadius="full" px={2}>
    {isConnected ? "Bağlı" : "Bağlı Değil"}
  </Badge>
);

export default function AppPage() {
  const router = useRouter();
  const toast = useToast();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [archivedChats, setArchivedChats] = useState<ChatListItem[]>([]);
  const [activeChats, setActiveChats] = useState<ChatListItem[]>([]);
  const [gmailStatus, setGmailStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [statsLoading, setStatsLoading] = useState(true);
  const [chatToDelete, setChatToDelete] = useState<{ id: string; title: string } | null>(null);
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const deleteButtonRef = useRef<HTMLButtonElement>(null);

  // Tema-aware renkler - Premium Dark UI
  const bgColor = useColorModeValue("#F9FAFB", "#0B0F14");
  const cardBg = useColorModeValue("#FFFFFF", "#111827");
  const borderColor = useColorModeValue("#E5E7EB", "#1F2937");
  const textPrimary = useColorModeValue("#111827", "#E5E7EB");
  const textSecondary = useColorModeValue("#6B7280", "#9CA3AF");
  const accentPrimary = useColorModeValue("#10B981", "#10B981");
  const accentHover = useColorModeValue("#34D399", "#34D399");
  const errorColor = useColorModeValue("#EF4444", "#EF4444");
  const buttonHoverBg = useColorModeValue("#F3F4F6", "#1F2937");
  const avatarBg = useColorModeValue("#FFFFFF", "#0B0F14");
  const toastBg = useColorModeValue("white", "#111827"); // Toast background
  const toastBorder = useColorModeValue("#E5E7EB", "#1F2937"); // Toast border

  // Define functions before useEffect to maintain hook order
  const loadGmailStatus = async () => {
    try {
      const { getGmailStatus } = await import("@/lib/api");
      const status = await getGmailStatus();
      setGmailStatus(status);
    } catch (err) {
      console.error("Failed to load Gmail status:", err);
    }
  };

  const loadActiveChats = async () => {
    try {
      const chats = await listChats();
      setActiveChats(chats);
    } catch (err: any) {
      console.error("Failed to load active chats:", err);
    }
  };

  const loadArchivedChats = async () => {
    try {
      setLoading(true);
      const chats = await listArchivedChats();
      setArchivedChats(chats);
    } catch (err: any) {
      console.error("Failed to load archived chats:", err);
    } finally {
      setLoading(false);
    }
  };

  // CRITICAL: Auto-sync Gmail in background when user logs in
  // This runs silently in background, no UI blocking
  const autoSyncGmail = async () => {
    try {
      const { getGmailStatus, syncGmail } = await import("@/lib/api");

      // Check if Gmail is connected
      const status = await getGmailStatus();

      if (status.is_connected) {
        // Immediately sync on page load if Gmail is connected
        // Sync in background (don't await, let it run silently)
        syncGmail().then((result) => {
          const now = Date.now();
          const lastSyncKey = `gmail_last_sync_${status.email || 'default'}`;
          localStorage.setItem(lastSyncKey, now.toString());
          console.log(`[AUTO-SYNC] Gmail synced on page load: ${result.emails_indexed || 0} emails indexed`);
        }).catch((error) => {
          // Silently fail - don't show error to user for background sync
          console.warn("[AUTO-SYNC] Gmail sync failed (silent):", error);
        });
      } else {
        console.log("[AUTO-SYNC] Gmail not connected, skipping auto-sync");
      }
    } catch (error) {
      // Silently fail - don't show error to user for background sync
      console.warn("[AUTO-SYNC] Gmail auto-sync check failed (silent):", error);
    }
  };

  const loadData = async () => {
    setStatsLoading(true);
    try {
      await Promise.all([
        loadArchivedChats(),
        loadActiveChats(),
        loadGmailStatus(),
      ]);

      // CRITICAL: After loading Gmail status, trigger auto-sync in background
      // This runs after initial load, so it doesn't block UI
      autoSyncGmail();
    } finally {
      setStatsLoading(false);
    }
  };

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
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSync = async () => {
    try {
      setSyncing(true);
      const { syncGmail } = await import("@/lib/api");
      const result = await syncGmail();
      toast({
        title: "Senkronizasyon Tamamlandı",
        description: `${result.emails_indexed} yeni e-posta eklendi.`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      await loadGmailStatus();
    } catch (err: any) {
      console.error("Gmail sync error:", err);
      let description = err.detail || "Senkronizasyon başarısız oldu";

      if (err.code === "GMAIL_NOT_CONNECTED") {
        description = "Gmail hesabınız bağlı değil. Lütfen önce bağlantı kurun.";
      } else if (err.code === "GMAIL_REAUTH_REQUIRED") {
        description = "Gmail bağlantısı süresi doldu. Lütfen tekrar bağlanın.";
      }

      toast({
        title: "Hata",
        description,
        status: "error",
        duration: 5000,
      });

      // Refresh status to update UI
      await loadGmailStatus();
    } finally {
      setSyncing(false);
    }
  };

  const handleUnarchive = async (chatId: string) => {
    try {
      await archiveChat(chatId, false);
      const chat = archivedChats.find(c => c.id === chatId);
      toast({
        title: "Sohbet arşivden çıkarıldı",
        description: chat?.title ? `${chat.title} sohbeti arşivden çıkarıldı` : undefined,
        status: "success",
        duration: 3000,
        isClosable: true,
        position: "top-right",
      });
      await loadData();
    } catch (err: any) {
      toast({
        title: "Hata",
        description: err.detail || "Sohbet arşivden çıkarılamadı",
        status: "error",
        duration: 3000,
        isClosable: true,
        position: "top-right",
      });
    }
  };

  const handleDeleteClick = (chatId: string) => {
    const chat = archivedChats.find(c => c.id === chatId);
    setChatToDelete({ id: chatId, title: chat?.title || "Bu sohbet" });
    onDeleteOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!chatToDelete) return;

    onDeleteClose();

    try {
      await deleteChat(chatToDelete.id);

      // Show professional toast notification
      toast({
        title: "Sohbet silindi",
        description: `${chatToDelete.title} sohbeti kalıcı olarak silindi`,
        status: "success",
        duration: 2500,
        isClosable: true,
        position: "top-right",
        icon: <FaTrash />,
        containerStyle: {
          bg: toastBg,
          border: `1px solid ${toastBorder}`,
          borderRadius: "8px",
        },
      });

      setChatToDelete(null);
      await loadData();

      // Navigate to new chat screen
      router.push("/chat");
    } catch (err: any) {
      toast({
        title: "Hata",
        description: err.detail || "Sohbet silinemedi",
        status: "error",
        duration: 3000,
        isClosable: true,
        position: "top-right",
      });
    }
  };

  const handleLogout = () => {
    removeToken();
    router.push("/login");
  };

  // Calculate account age
  const accountAge = user
    ? Math.floor((new Date().getTime() - new Date(user.created_at).getTime()) / (1000 * 60 * 60 * 24))
    : 0;

  return (
    <AuthGuard>
      <Box
        minH="100vh"
        bg={bgColor}
        position="relative"
        _before={{
          content: '""',
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "300px",
          background: useColorModeValue(
            "linear-gradient(180deg, rgba(16, 185, 129, 0.05) 0%, transparent 100%)",
            "linear-gradient(180deg, rgba(16, 185, 129, 0.08) 0%, transparent 100%)"
          ),
          pointerEvents: "none",
        }}
      >
        <Box maxW="1200px" mx="auto" p={{ base: 4, md: 8 }} position="relative" zIndex={1}>
          {/* Header with gradient effect */}
          <HStack mb={8} spacing={4} align="center">
            <IconButton
              aria-label="Geri dön"
              icon={<ArrowBackIcon />}
              variant="ghost"
              onClick={() => router.push("/chat")}
              color={textPrimary}
              _hover={{
                bg: buttonHoverBg,
                transform: "translateX(-2px)",
              }}
              transition="all 0.2s"
              size="md"
            />
            <VStack align="start" spacing={0} flex={1}>
              <Heading
                size="xl"
                color={textPrimary}
                fontWeight="700"
                letterSpacing="-0.5px"
              >
                Profil
              </Heading>
              <Text fontSize="sm" color={textSecondary} mt={1}>
                Hesap bilgileriniz ve istatistikleriniz
              </Text>
            </VStack>
          </HStack>

          {error && (
            <Card mb={6} bg={cardBg} borderColor={errorColor} borderWidth="1px">
              <CardBody>
                <Text color={errorColor}>{error}</Text>
              </CardBody>
            </Card>
          )}

          <VStack spacing={6} align="stretch">
            {/* İstatistik Kartları */}
            {!statsLoading && (
              <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
                <Card
                  bg={cardBg}
                  borderColor={borderColor}
                  borderWidth="1px"
                  _hover={{
                    borderColor: accentPrimary,
                    transform: "translateY(-2px)",
                    boxShadow: `0 8px 24px ${useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}`,
                  }}
                  transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                  position="relative"
                  overflow="hidden"
                  _before={{
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "3px",
                    bg: accentPrimary,
                  }}
                >
                  <CardBody>
                    <Stat>
                      <HStack justify="space-between" align="start">
                        <VStack align="start" spacing={1}>
                          <StatLabel color={textSecondary} fontSize="xs" fontWeight="600" textTransform="uppercase" letterSpacing="0.5px">
                            Aktif Sohbetler
                          </StatLabel>
                          <StatNumber color={textPrimary} fontSize="2xl" fontWeight="700">
                            {activeChats.length}
                          </StatNumber>
                        </VStack>
                        <Box
                          p={3}
                          borderRadius="lg"
                          bg={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                          color={accentPrimary}
                        >
                          <Icon as={FaComments} boxSize={5} />
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>

                <Card
                  bg={cardBg}
                  borderColor={borderColor}
                  borderWidth="1px"
                  _hover={{
                    borderColor: accentPrimary,
                    transform: "translateY(-2px)",
                    boxShadow: `0 8px 24px ${useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}`,
                  }}
                  transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                  position="relative"
                  overflow="hidden"
                  _before={{
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "3px",
                    bg: accentPrimary,
                  }}
                >
                  <CardBody>
                    <Stat>
                      <HStack justify="space-between" align="start">
                        <VStack align="start" spacing={1}>
                          <StatLabel color={textSecondary} fontSize="xs" fontWeight="600" textTransform="uppercase" letterSpacing="0.5px">
                            Arşivlenen
                          </StatLabel>
                          <StatNumber color={textPrimary} fontSize="2xl" fontWeight="700">
                            {archivedChats.length}
                          </StatNumber>
                        </VStack>
                        <Box
                          p={3}
                          borderRadius="lg"
                          bg={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                          color={accentPrimary}
                        >
                          <Icon as={FaArchive} boxSize={5} />
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>

                <Card
                  bg={cardBg}
                  borderColor={borderColor}
                  borderWidth="1px"
                  _hover={{
                    borderColor: accentPrimary,
                    transform: "translateY(-2px)",
                    boxShadow: `0 8px 24px ${useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}`,
                  }}
                  transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                  position="relative"
                  overflow="hidden"
                  _before={{
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "3px",
                    bg: accentPrimary,
                  }}
                >
                  <CardBody>
                    <Stat>
                      <HStack justify="space-between" align="start">
                        <VStack align="start" spacing={1}>
                          <StatLabel color={textSecondary} fontSize="xs" fontWeight="600" textTransform="uppercase" letterSpacing="0.5px">
                            Toplam Sohbet
                          </StatLabel>
                          <StatNumber color={textPrimary} fontSize="2xl" fontWeight="700">
                            {activeChats.length + archivedChats.length}
                          </StatNumber>
                        </VStack>
                        <Box
                          p={3}
                          borderRadius="lg"
                          bg={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                          color={accentPrimary}
                        >
                          <Icon as={FaChartLine} boxSize={5} />
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>

                <Card
                  bg={cardBg}
                  borderColor={borderColor}
                  borderWidth="1px"
                  _hover={{
                    borderColor: accentPrimary,
                    transform: "translateY(-2px)",
                    boxShadow: `0 8px 24px ${useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}`,
                  }}
                  transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                  position="relative"
                  overflow="hidden"
                  _before={{
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "3px",
                    bg: accentPrimary,
                  }}
                >
                  <CardBody>
                    <Stat>
                      <HStack justify="space-between" align="start">
                        <VStack align="start" spacing={1}>
                          <StatLabel color={textSecondary} fontSize="xs" fontWeight="600" textTransform="uppercase" letterSpacing="0.5px">
                            Hesap Yaşı
                          </StatLabel>
                          <StatNumber color={textPrimary} fontSize="2xl" fontWeight="700">
                            {accountAge}
                          </StatNumber>
                          <StatHelpText color={textSecondary} fontSize="xs" m={0}>
                            gün
                          </StatHelpText>
                        </VStack>
                        <Box
                          p={3}
                          borderRadius="lg"
                          bg={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                          color={accentPrimary}
                        >
                          <Icon as={FaCalendarAlt} boxSize={5} />
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>
              </SimpleGrid>
            )}

            {statsLoading && (
              <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
                {[1, 2, 3, 4].map((i) => (
                  <Card key={i} bg={cardBg} borderColor={borderColor} borderWidth="1px">
                    <CardBody>
                      <Flex justify="center" py={8}>
                        <Spinner color={accentPrimary} size="lg" />
                      </Flex>
                    </CardBody>
                  </Card>
                ))}
              </SimpleGrid>
            )}

            {/* Kullanıcı Bilgileri - Enhanced Design */}
            {user && (
              <Card
                bg={cardBg}
                borderColor={borderColor}
                borderWidth="1px"
                _hover={{
                  borderColor: accentPrimary,
                  boxShadow: `0 4px 16px ${useColorModeValue("rgba(26, 127, 55, 0.08)", "rgba(63, 185, 80, 0.12)")}`,
                }}
                transition="all 0.3s"
                position="relative"
                overflow="hidden"
              >
                <Box
                  position="absolute"
                  top={0}
                  left={0}
                  right={0}
                  height="4px"
                  bgGradient={`linear(to-r, ${accentPrimary}, ${accentHover})`}
                />
                <CardBody p={6}>
                  <VStack spacing={6} align="stretch">
                    {/* Avatar ve Temel Bilgiler - Enhanced */}
                    <Flex align="center" gap={5}>
                      <Box position="relative">
                        <Avatar
                          size="2xl"
                          name={user.username}
                          src={user.avatar_url || undefined}
                          bg={accentPrimary}
                          color={avatarBg}
                          fontWeight="700"
                          fontSize="xl"
                          borderWidth="3px"
                          borderColor={useColorModeValue("rgba(26, 127, 55, 0.2)", "rgba(63, 185, 80, 0.3)")}
                          boxShadow={`0 4px 16px ${useColorModeValue("rgba(26, 127, 55, 0.2)", "rgba(63, 185, 80, 0.3)")}`}
                        />
                      </Box>
                      <VStack align="start" spacing={2} flex={1}>
                        <HStack spacing={3} flexWrap="wrap">
                          <Heading size="lg" color={textPrimary} fontWeight="700">
                            {user.username}
                          </Heading>
                          {user.is_active && (
                            <Badge
                              borderRadius="full"
                              px={3}
                              py={1}
                              bg={accentPrimary}
                              color={avatarBg}
                              fontSize="xs"
                              fontWeight="700"
                              textTransform="uppercase"
                              letterSpacing="0.5px"
                              boxShadow={`0 2px 8px ${useColorModeValue("rgba(26, 127, 55, 0.2)", "rgba(63, 185, 80, 0.3)")}`}
                            >
                              Aktif
                            </Badge>
                          )}
                        </HStack>
                        <HStack spacing={2} color={textSecondary}>
                          <Icon as={FaUser} boxSize={3} />
                          <Text fontSize="sm" fontWeight="500">
                            {user.email || "E-posta eklenmemiş"}
                          </Text>
                        </HStack>
                      </VStack>
                    </Flex>

                    <Divider borderColor={borderColor} />

                    {/* Detaylı Bilgiler - Enhanced */}
                    <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                      <Box
                        p={4}
                        borderRadius="lg"
                        bg={useColorModeValue("rgba(26, 127, 55, 0.03)", "rgba(63, 185, 80, 0.05)")}
                        borderWidth="1px"
                        borderColor={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                      >
                        <HStack spacing={2} mb={2}>
                          <Icon as={FaUser} color={accentPrimary} boxSize={4} />
                          <Text fontSize="xs" fontWeight="700" color={textSecondary} textTransform="uppercase" letterSpacing="0.5px">
                            Kullanıcı ID
                          </Text>
                        </HStack>
                        <Text
                          fontSize="sm"
                          color={textPrimary}
                          fontFamily="mono"
                          fontWeight="600"
                          wordBreak="break-all"
                        >
                          {user.id}
                        </Text>
                      </Box>
                      <Box
                        p={4}
                        borderRadius="lg"
                        bg={useColorModeValue("rgba(26, 127, 55, 0.03)", "rgba(63, 185, 80, 0.05)")}
                        borderWidth="1px"
                        borderColor={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                      >
                        <HStack spacing={2} mb={2}>
                          <Icon as={FaCalendarAlt} color={accentPrimary} boxSize={4} />
                          <Text fontSize="xs" fontWeight="700" color={textSecondary} textTransform="uppercase" letterSpacing="0.5px">
                            Hesap Oluşturulma
                          </Text>
                        </HStack>
                        <Text fontSize="sm" color={textPrimary} fontWeight="600">
                          {new Date(user.created_at).toLocaleDateString("tr-TR", {
                            year: "numeric",
                            month: "long",
                            day: "numeric",
                          })}
                        </Text>
                      </Box>
                    </SimpleGrid>
                  </VStack>
                </CardBody>
              </Card>
            )}

            {/* Gmail Entegrasyonu */}
            <Card
              bg={cardBg}
              borderColor={borderColor}
              borderWidth="1px"
              _hover={{
                borderColor: "green.400",
                boxShadow: `0 4px 16px rgba(16, 185, 129, 0.1)`,
              }}
              transition="all 0.3s"
              position="relative"
              overflow="hidden"
            >
              <Box
                position="absolute"
                top={0}
                left={0}
                right={0}
                height="4px"
                bgGradient="linear(to-r, green.400, green.600)"
              />
              <CardBody p={6}>
                <VStack align="stretch" spacing={4}>
                  <HStack justify="space-between">
                    <HStack spacing={3}>
                      <Box p={2} borderRadius="lg" bg="green.50" color="green.500">
                        <Text fontSize="xl">📧</Text>
                      </Box>
                      <VStack align="start" spacing={0}>
                        <Heading size="sm" color={textPrimary} fontWeight="700">
                          Gmail Entegrasyonu
                        </Heading>
                        <Text fontSize="xs" color={textSecondary}>
                          E-postalarınızı bilgi kaynağı olarak kullanın
                        </Text>
                      </VStack>
                    </HStack>
                    <GmailIntegrationStatus isConnected={gmailStatus?.is_connected || false} />
                  </HStack>

                  <Text fontSize="sm" color={textSecondary}>
                    Gmail hesabınızı bağlayarak e-postalarınızı Lala AI'ye aktarabilir ve sohbetlerinizde bu bilgileri kullanabilirsiniz.
                    {gmailStatus?.is_connected && (
                      <Text as="span" fontWeight="600" color="green.500" ml={1}>
                        ({gmailStatus.email})
                      </Text>
                    )}
                    {!gmailStatus?.is_connected && " Sadece okuma (readonly) izni istenir."}
                  </Text>

                  {gmailStatus?.last_sync_at && (
                    <Text fontSize="xs" color={textSecondary}>
                      Son Senkronizasyon: {new Date(gmailStatus.last_sync_at).toLocaleString("tr-TR")}
                    </Text>
                  )}

                  <Divider borderColor={borderColor} />

                  <HStack spacing={4}>
                    {!gmailStatus?.is_connected ? (
                      <Button
                        leftIcon={<Text fontSize="lg">🔐</Text>}
                        colorScheme="green"
                        onClick={async () => {
                          try {
                            const { getGmailConnectUrl } = await import("@/lib/api");
                            const { auth_url } = await getGmailConnectUrl();
                            window.location.href = auth_url;
                          } catch (err: any) {
                            console.error("Gmail connect error:", err);
                            toast({
                              title: "Bağlantı Hatası",
                              description: err.code === "GMAIL_NOT_CONFIGURED"
                                ? "Gmail entegrasyonu yapılandırılmamış. Lütfen yöneticiye başvurun."
                                : err.detail || "Gmail bağlantısı başlatılamadı.",
                              status: "error",
                              duration: 5000,
                            });
                          }
                        }}
                        fontWeight="600"
                        flex={1}
                      >
                        Google ile Bağlan
                      </Button>
                    ) : (
                      <>
                        <Button
                          leftIcon={<RepeatIcon />}
                          colorScheme="green"
                          variant="outline"
                          onClick={handleSync}
                          isLoading={syncing}
                          loadingText="Senkronize ediliyor..."
                          flex={1}
                        >
                          Şimdi Senkronize Et
                        </Button>
                        <Button
                          variant="ghost"
                          colorScheme="red"
                          size="sm"
                          onClick={async () => {
                            try {
                              const { disconnectGmail } = await import("@/lib/api");
                              await disconnectGmail();
                              toast({
                                title: "Başarılı",
                                description: "Gmail bağlantısı kesildi.",
                                status: "success",
                              });
                              // Refresh status
                              const { getGmailStatus } = await import("@/lib/api");
                              const status = await getGmailStatus();
                              setGmailStatus(status);
                            } catch (err: any) {
                              console.error("Gmail disconnect error:", err);
                              toast({
                                title: "Hata",
                                description: err.detail || "Gmail bağlantısı kesilemedi.",
                                status: "error",
                              });
                            }
                          }}
                        >
                          Bağlantıyı Kes
                        </Button>
                      </>
                    )}
                  </HStack>
                </VStack>
              </CardBody>
            </Card>

            {/* Hızlı Erişim Butonları - Enhanced */}
            <Card
              bg={cardBg}
              borderColor={borderColor}
              borderWidth="1px"
              _hover={{
                borderColor: accentPrimary,
                boxShadow: `0 4px 16px ${useColorModeValue("rgba(26, 127, 55, 0.08)", "rgba(63, 185, 80, 0.12)")}`,
              }}
              transition="all 0.3s"
            >
              <CardBody p={6}>
                <VStack align="stretch" spacing={4}>
                  <HStack spacing={2} mb={2}>
                    <Icon as={FaRocket} color={accentPrimary} boxSize={5} />
                    <Heading size="sm" color={textPrimary} fontWeight="700">
                      Hızlı Erişim
                    </Heading>
                  </HStack>
                  <SimpleGrid columns={{ base: 1, md: 3 }} spacing={3}>
                    <Button
                      leftIcon={<ChatIcon />}
                      bg={accentPrimary}
                      color={avatarBg}
                      _hover={{
                        bg: accentHover,
                        transform: "translateY(-2px)",
                        boxShadow: `0 6px 20px ${useColorModeValue("rgba(26, 127, 55, 0.25)", "rgba(63, 185, 80, 0.3)")}`,
                      }}
                      onClick={() => router.push("/chat")}
                      w="100%"
                      justifyContent="flex-start"
                      fontWeight="600"
                      transition="all 0.2s"
                      size="lg"
                    >
                      Yeni Sohbet
                    </Button>
                    <Button
                      leftIcon={<Icon as={FaFileAlt} />}
                      variant="outline"
                      borderColor={borderColor}
                      borderWidth="2px"
                      color={textPrimary}
                      _hover={{
                        bg: buttonHoverBg,
                        borderColor: accentPrimary,
                        transform: "translateY(-2px)",
                        boxShadow: `0 4px 12px ${useColorModeValue("rgba(26, 127, 55, 0.15)", "rgba(63, 185, 80, 0.2)")}`,
                      }}
                      onClick={() => router.push("/app/documents")}
                      w="100%"
                      justifyContent="flex-start"
                      fontWeight="600"
                      transition="all 0.2s"
                      size="lg"
                    >
                      Dokümanlarım
                    </Button>
                    <Button
                      leftIcon={<Icon as={FaSignOutAlt} />}
                      variant="outline"
                      borderColor={errorColor}
                      borderWidth="2px"
                      color={errorColor}
                      _hover={{
                        bg: buttonHoverBg,
                        borderColor: errorColor,
                        transform: "translateY(-2px)",
                        boxShadow: `0 4px 12px ${useColorModeValue("rgba(207, 34, 46, 0.15)", "rgba(248, 81, 73, 0.2)")}`,
                      }}
                      onClick={handleLogout}
                      w="100%"
                      justifyContent="flex-start"
                      fontWeight="600"
                      transition="all 0.2s"
                      size="lg"
                    >
                      Çıkış Yap
                    </Button>
                  </SimpleGrid>
                </VStack>
              </CardBody>
            </Card>

            {/* Arşivlenen Sohbetler - Enhanced */}
            <Card
              bg={cardBg}
              borderColor={borderColor}
              borderWidth="1px"
              _hover={{
                borderColor: accentPrimary,
                boxShadow: `0 4px 16px ${useColorModeValue("rgba(26, 127, 55, 0.08)", "rgba(63, 185, 80, 0.12)")}`,
              }}
              transition="all 0.3s"
              position="relative"
              overflow="hidden"
            >
              <Box
                position="absolute"
                top={0}
                left={0}
                right={0}
                height="4px"
                bgGradient={`linear(to-r, ${accentPrimary}, ${accentHover})`}
              />
              <CardBody p={6}>
                <VStack align="stretch" spacing={4}>
                  <HStack justify="space-between" align="center">
                    <HStack spacing={3}>
                      <Box
                        p={2}
                        borderRadius="lg"
                        bg={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                        color={accentPrimary}
                      >
                        <Icon as={FaArchive} boxSize={5} />
                      </Box>
                      <VStack align="start" spacing={0}>
                        <Heading size="md" color={textPrimary} fontWeight="700">
                          Arşivlenen Sohbetler
                        </Heading>
                        <Text fontSize="xs" color={textSecondary}>
                          Arşivlenmiş sohbetlerinizi yönetin
                        </Text>
                      </VStack>
                    </HStack>
                    {archivedChats.length > 0 && (
                      <Badge
                        borderRadius="full"
                        px={4}
                        py={1.5}
                        bg={accentPrimary}
                        color={avatarBg}
                        fontSize="sm"
                        fontWeight="700"
                        boxShadow={`0 2px 8px ${useColorModeValue("rgba(26, 127, 55, 0.2)", "rgba(63, 185, 80, 0.3)")}`}
                      >
                        {archivedChats.length}
                      </Badge>
                    )}
                  </HStack>

                  {loading ? (
                    <Flex justify="center" py={12}>
                      <VStack spacing={3}>
                        <Spinner color={accentPrimary} size="lg" thickness="3px" />
                        <Text color={textSecondary} fontSize="sm">
                          Yükleniyor...
                        </Text>
                      </VStack>
                    </Flex>
                  ) : archivedChats.length === 0 ? (
                    <Box
                      py={12}
                      textAlign="center"
                      borderWidth="2px"
                      borderStyle="dashed"
                      borderColor={borderColor}
                      borderRadius="lg"
                      bg={bgColor}
                    >
                      <Icon as={FaArchive} color={textSecondary} boxSize={8} mb={3} />
                      <Text color={textSecondary} fontSize="sm" fontWeight="medium">
                        Arşivlenen sohbet bulunmuyor
                      </Text>
                      <Text color={textSecondary} fontSize="xs" mt={1}>
                        Sohbetleri arşivlemek için sidebar'daki arşivle butonunu kullanın
                      </Text>
                    </Box>
                  ) : (
                    <VStack align="stretch" spacing={3}>
                      {archivedChats.map((chat) => {
                        const updatedDate = new Date(chat.updated_at);
                        const now = new Date();
                        const diffMs = now.getTime() - updatedDate.getTime();
                        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

                        let dateDisplay = "";
                        if (diffDays === 0) {
                          dateDisplay = "Bugün " + updatedDate.toLocaleTimeString("tr-TR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          });
                        } else if (diffDays === 1) {
                          dateDisplay = "Dün " + updatedDate.toLocaleTimeString("tr-TR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          });
                        } else if (diffDays < 7) {
                          dateDisplay = `${diffDays} gün önce`;
                        } else {
                          dateDisplay = updatedDate.toLocaleDateString("tr-TR", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          });
                        }

                        return (
                          <Box
                            key={chat.id}
                            p={4}
                            borderWidth="1px"
                            borderRadius="lg"
                            borderColor={borderColor}
                            bg={useColorModeValue("rgba(26, 127, 55, 0.02)", "rgba(63, 185, 80, 0.03)")}
                            position="relative"
                            _hover={{
                              borderColor: accentPrimary,
                              bg: useColorModeValue("rgba(26, 127, 55, 0.05)", "rgba(63, 185, 80, 0.08)"),
                              transform: "translateY(-2px)",
                              boxShadow: `0 6px 20px ${useColorModeValue("rgba(26, 127, 55, 0.15)", "rgba(63, 185, 80, 0.2)")}`,
                            }}
                            transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                            cursor="pointer"
                            onClick={() => router.push(`/chat/${chat.id}`)}
                          >
                            <HStack justify="space-between" align="start" spacing={4}>
                              <VStack align="start" spacing={2} flex={1} overflow="hidden" minW={0}>
                                <HStack spacing={3} w="100%" align="start">
                                  <Box
                                    p={1.5}
                                    borderRadius="md"
                                    bg={useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)")}
                                    color={accentPrimary}
                                    flexShrink={0}
                                  >
                                    <Icon as={FaArchive} boxSize={3} />
                                  </Box>
                                  <VStack align="start" spacing={1} flex={1} minW={0}>
                                    <Text
                                      fontWeight="600"
                                      color={textPrimary}
                                      noOfLines={2}
                                      wordBreak="break-word"
                                      fontSize="sm"
                                    >
                                      {chat.title}
                                    </Text>
                                    <HStack spacing={2} color={textSecondary}>
                                      <Icon as={FaCalendarAlt} boxSize={2.5} />
                                      <Text fontSize="xs" fontWeight="500">
                                        {dateDisplay}
                                      </Text>
                                    </HStack>
                                  </VStack>
                                </HStack>
                              </VStack>
                              <HStack
                                spacing={1}
                                ml={2}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Tooltip label="Arşivden çıkar" placement="top">
                                  <IconButton
                                    aria-label="Geri yükle"
                                    icon={<Icon as={FaUndo} />}
                                    size="sm"
                                    variant="ghost"
                                    color={accentPrimary}
                                    _hover={{
                                      bg: useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)"),
                                      color: accentPrimary,
                                      transform: "scale(1.15) rotate(-15deg)",
                                    }}
                                    onClick={() => handleUnarchive(chat.id)}
                                    transition="all 0.2s"
                                  />
                                </Tooltip>
                                <Tooltip label="Kalıcı olarak sil" placement="top">
                                  <IconButton
                                    aria-label="Kalıcı olarak sil"
                                    icon={<Icon as={FaTrash} />}
                                    size="sm"
                                    variant="ghost"
                                    color={errorColor}
                                    _hover={{
                                      bg: useColorModeValue("rgba(207, 34, 46, 0.1)", "rgba(248, 81, 73, 0.15)"),
                                      color: errorColor,
                                      transform: "scale(1.15)",
                                    }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDeleteClick(chat.id);
                                    }}
                                    transition="all 0.2s"
                                  />
                                </Tooltip>
                              </HStack>
                            </HStack>
                          </Box>
                        );
                      })}
                    </VStack>
                  )}
                </VStack>
              </CardBody>
            </Card>
          </VStack>
        </Box>

        {/* Delete Confirmation Dialog */}
        <AlertDialog
          isOpen={isDeleteOpen}
          leastDestructiveRef={cancelRef}
          onClose={onDeleteClose}
          motionPreset="slideInBottom"
          returnFocusOnClose={false}
        >
          <AlertDialogOverlay
            bg={useColorModeValue("blackAlpha.600", "blackAlpha.800")}
            backdropFilter="blur(4px)"
          />
          <AlertDialogContent
            borderRadius="xl"
            boxShadow="2xl"
            bg={cardBg}
            borderColor={borderColor}
            borderWidth="1px"
          >
            <AlertDialogHeader
              fontSize="lg"
              fontWeight="bold"
              pb={2}
              color={textPrimary}
            >
              Sohbeti Sil
            </AlertDialogHeader>
            <AlertDialogBody>
              <Text mb={2} color={textPrimary}>
                <Text as="span" fontWeight="bold">{chatToDelete?.title || "Bu sohbet"}</Text> sohbetini kalıcı olarak silmek istediğinize emin misiniz?
              </Text>
              <Text fontSize="sm" color={textSecondary}>
                Bu işlem geri alınamaz. Sohbet ve tüm mesajları kalıcı olarak silinecektir.
              </Text>
            </AlertDialogBody>
            <AlertDialogFooter gap={3}>
              <Button
                ref={cancelRef}
                onClick={onDeleteClose}
                variant="ghost"
                color={textPrimary}
                _hover={{ bg: buttonHoverBg }}
              >
                İptal
              </Button>
              <Button
                ref={deleteButtonRef}
                onClick={handleDeleteConfirm}
                bg={errorColor}
                color={avatarBg}
                border="2px solid"
                borderColor={errorColor}
                _hover={{
                  bg: useColorModeValue("#B91C1C", "#DC2626"),
                  borderColor: useColorModeValue("#B91C1C", "#DC2626"),
                  transform: "scale(1.02)",
                }}
                _active={{
                  bg: useColorModeValue("#991B1B", "#B91C1C"),
                  borderColor: useColorModeValue("#991B1B", "#B91C1C"),
                  transform: "scale(0.98)",
                }}
                _focus={{
                  boxShadow: `0 0 0 3px ${useColorModeValue("rgba(207, 34, 46, 0.3)", "rgba(248, 81, 73, 0.3)")}`,
                  outline: "none",
                }}
                transition="all 0.2s ease"
              >
                Sil
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </Box>
    </AuthGuard>
  );
}
