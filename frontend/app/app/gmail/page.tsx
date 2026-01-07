"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Box,
  VStack,
  HStack,
  Button,
  Text,
  Heading,
  useColorModeValue,
  Input,
  IconButton,
  Spinner,
  useToast,
  Checkbox,
  Flex,
  Divider,
  InputGroup,
  InputLeftElement,
  Badge,
  Skeleton,
  SkeletonText,
  Progress,
} from "@chakra-ui/react";
import { useRouter } from "next/navigation";
import { SearchIcon, RepeatIcon, StarIcon, AttachmentIcon, ChevronLeftIcon, ChevronRightIcon } from "@chakra-ui/icons";
import AuthGuard from "@/components/AuthGuard";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { listGmailMessages, getGmailStatus, syncGmail, getGmailMessage } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";
import GmailIcon from "@/components/icons/GmailIcon";

interface GmailMessage {
  id: string;
  threadId: string;
  snippet: string;
  subject: string;
  sender: string;
  sender_email?: string;
  date?: string;
  internalDate?: string;
}

export default function GmailPage() {
  const router = useRouter();
  const toast = useToast();
  const { isOpen, toggle } = useSidebar();
  const [messages, setMessages] = useState<GmailMessage[]>([]);
  const [cachedMessages, setCachedMessages] = useState<GmailMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedMessages, setSelectedMessages] = useState<Set<string>>(new Set());
  const [gmailStatus, setGmailStatus] = useState<{ is_connected: boolean; email?: string; last_sync_at?: string } | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true); // Track status loading separately
  const [activeFolder, setActiveFolder] = useState("inbox");
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [messagesPerPage] = useState(20); // Sayfa başına mail sayısı
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesListRef = useRef<HTMLDivElement>(null);

  // Consistent theme colors matching app design - ALL hooks must be at top level
  // Aligned with app's emerald green accent palette
  const bgColor = useColorModeValue("#FFFFFF", "#0B0F14");
  const sidebarBg = useColorModeValue("#F6F8FA", "#111827");
  const borderColor = useColorModeValue("#E7ECF0", "#1F2937");
  const hoverBg = useColorModeValue("#F0F3F6", "#1F2937");
  const selectedBg = useColorModeValue("rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.15)");
  const selectedBorder = useColorModeValue("rgba(16, 185, 129, 0.2)", "rgba(16, 185, 129, 0.25)");
  const textPrimary = useColorModeValue("#1F2328", "#E5E7EB");
  const textSecondary = useColorModeValue("#656D76", "#9CA3AF");
  const textMuted = useColorModeValue("#8B949E", "#6B7280");
  const accentPrimary = useColorModeValue("#059669", "#10B981");
  const cardBg = useColorModeValue("#FFFFFF", "#111827");
  const spinnerEmptyColor = useColorModeValue("gray.200", "gray.700");
  // Additional color values used in JSX - must be at top level
  const sidebarToggleColor = useColorModeValue("gray.700", "gray.200");
  const sidebarToggleBg = useColorModeValue("white", "gray.800");
  const sidebarToggleBorder = useColorModeValue("gray.200", "gray.700");
  const sidebarToggleHoverBg = useColorModeValue("gray.50", "gray.700");
  const sidebarToggleHoverColor = useColorModeValue("gray.900", "white");
  const sidebarToggleHoverBorder = useColorModeValue("gray.300", "gray.600");

  // Cache utilities
  const getCacheKey = (folder: string, query: string) => {
    return `gmail-messages-${folder}-${query || 'default'}`;
  };

  const getCachedMessages = (folder: string, query: string): GmailMessage[] | null => {
    try {
      const cacheKey = getCacheKey(folder, query);
      const cached = localStorage.getItem(cacheKey);
      if (!cached) return null;

      const { data, timestamp } = JSON.parse(cached);
      const now = Date.now();
      const CACHE_DURATION = 30 * 60 * 1000; // 30 dakika - daha uzun cache süresi

      if (now - timestamp > CACHE_DURATION) {
        localStorage.removeItem(cacheKey);
        return null;
      }

      return data;
    } catch {
      return null;
    }
  };

  const saveCachedMessages = (folder: string, query: string, messages: GmailMessage[]) => {
    try {
      const cacheKey = getCacheKey(folder, query);
      localStorage.setItem(cacheKey, JSON.stringify({
        data: messages,
        timestamp: Date.now()
      }));
    } catch (error) {
      console.warn("Failed to cache messages:", error);
    }
  };

  // Restore scroll position on mount
  useEffect(() => {
    const scrollKey = `gmail-scroll-${activeFolder}`;
    const savedScroll = sessionStorage.getItem(scrollKey);
    if (savedScroll && messagesListRef.current) {
      setTimeout(() => {
        messagesListRef.current?.scrollTo(0, parseInt(savedScroll, 10));
      }, 100);
    }
  }, [activeFolder]);

  // Save scroll position before navigation
  useEffect(() => {
    const container = messagesListRef.current;
    if (!container) return;

    const handleScroll = () => {
      const scrollKey = `gmail-scroll-${activeFolder}`;
      sessionStorage.setItem(scrollKey, container.scrollTop.toString());
    };

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [activeFolder]);

  // Prefetch message detail when hovering over mail item - MUST be defined before useEffect
  const prefetchMessage = useCallback(async (messageId: string) => {
    try {
      // Check if already cached
      const cacheKey = `gmail-message-${messageId}`;
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const { timestamp } = JSON.parse(cached);
        const now = Date.now();
        const CACHE_DURATION = 30 * 60 * 1000; // 30 dakika (daha uzun cache)
        // If cache is still valid, don't prefetch
        if (now - timestamp < CACHE_DURATION) {
          return;
        }
      }

      // Prefetch route for Next.js optimization
      router.prefetch(`/app/gmail/${messageId}`);

      // Prefetch message data in background (don't await, fire and forget)
      getGmailMessage(messageId).then((msg) => {
        if (msg) {
          // Cache the prefetched message
          try {
            localStorage.setItem(cacheKey, JSON.stringify({
              data: msg,
              timestamp: Date.now()
            }));
          } catch (error) {
            console.warn("Failed to cache prefetched message:", error);
          }
        }
      }).catch(() => {
        // Silent fail for prefetch
      });
    } catch (error) {
      // Silent fail for prefetch
    }
  }, [router]);

  // CRITICAL: Auto-sync Gmail in background when page mounts
  // This runs silently, no UI blocking
  const autoSyncGmailInBackground = useCallback(async () => {
    try {
      if (gmailStatus?.is_connected) {
        // Check last sync time to avoid unnecessary syncs
        const lastSyncKey = `gmail_last_sync_${gmailStatus.email || 'default'}`;
        const lastSyncTime = localStorage.getItem(lastSyncKey);
        const now = Date.now();
        const SYNC_INTERVAL = 5 * 60 * 1000; // 5 dakika - minimum sync interval

        // Only sync if last sync was more than 5 minutes ago
        if (!lastSyncTime || (now - parseInt(lastSyncTime, 10)) > SYNC_INTERVAL) {
          // Sync in background (don't await, let it run silently)
          syncGmail().then((result) => {
            localStorage.setItem(lastSyncKey, now.toString());
            console.log(`[AUTO-SYNC] Gmail synced on Gmail page load: ${result.emails_indexed || 0} emails indexed`);

            // After sync, refresh messages if we're on the page
            loadMessages(searchQuery, true).catch(() => {
              // Silent fail
            });
          }).catch((error) => {
            // Silently fail - don't show error to user for background sync
            console.warn("[AUTO-SYNC] Gmail sync failed (silent):", error);
          });
        } else {
          console.log("[AUTO-SYNC] Gmail sync skipped (recent sync)");
        }
      } else {
        console.log("[AUTO-SYNC] Gmail not connected, skipping auto-sync");
      }
    } catch (error) {
      // Silently fail - don't show error to user for background sync
      console.warn("[AUTO-SYNC] Gmail auto-sync check failed (silent):", error);
    }
  }, [gmailStatus, searchQuery]);


  // CRITICAL: Load messages and status on mount
  useEffect(() => {
    const initializePage = async () => {
      // 1. Load Gmail status first
      await loadGmailStatus();

      // 2. Load messages from cache immediately (no loading screen if cache exists)
      const cached = getCachedMessages(activeFolder, searchQuery);
      if (cached && cached.length > 0) {
        setMessages(cached);
        setIsLoading(false);
        console.log(`[GMAIL] Loaded ${cached.length} messages from cache`);
      } else {
        // Only load from API if we haven't already confirmed disconnected status
        // loadGmailStatus sets gmailStatus, which is checked in the render
        setIsLoading(true);
        loadMessages(searchQuery, false);
      }

      // 3. Trigger auto-sync in background after initial load
      // Use a small delay to not compete with initial load
      setTimeout(() => {
        autoSyncGmailInBackground();
      }, 1000);
    };

    initializePage();
  }, []); // Run only once on mount

  // Handle folder changes (skip first mount since initializePage handles it)
  const isFirstMount = useRef(true);
  useEffect(() => {
    if (isFirstMount.current) {
      isFirstMount.current = false;
      return;
    }

    // Folder değiştiğinde önce cache'den yükle
    setCurrentPage(1);

    const cached = getCachedMessages(activeFolder, searchQuery);
    if (cached && cached.length > 0) {
      setMessages(cached);
      setIsLoading(false);

      // Arka planda fresh data çek (sessizce, sadece cache eskiyse)
      const cacheKey = getCacheKey(activeFolder, searchQuery);
      const cacheData = localStorage.getItem(cacheKey);
      if (cacheData) {
        try {
          const { timestamp } = JSON.parse(cacheData);
          if (Date.now() - timestamp > 10 * 60 * 1000) {
            loadMessages(searchQuery, true).catch(() => { });
          }
        } catch (e) { }
      }
    } else {
      setIsLoading(true);
      loadMessages(searchQuery, false);
    }
  }, [activeFolder]);

  // Auto-prefetch first 3 messages when list loads
  useEffect(() => {
    if (messages.length > 0) {
      // Prefetch first 3 messages automatically
      const messagesToPrefetch = messages.slice(0, 3);
      messagesToPrefetch.forEach((msg) => {
        prefetchMessage(msg.id);
      });
    }
  }, [messages, prefetchMessage]); // Prefetch when messages change

  const loadGmailStatus = async () => {
    try {
      setIsLoadingStatus(true);
      const status = await getGmailStatus();
      setGmailStatus(status);
    } catch (error: any) {
      console.error("Failed to load Gmail status:", error);
      setGmailStatus({ is_connected: false });
    } finally {
      setIsLoadingStatus(false);
    }
  };

  const loadMessages = async (query: string = "", isRefresh: boolean = false) => {
    try {
      let gmailQuery = query;
      if (!gmailQuery) {
        // Add folder filter
        if (activeFolder === "inbox") {
          gmailQuery = "in:inbox";
        } else if (activeFolder === "sent") {
          gmailQuery = "in:sent";
        } else if (activeFolder === "drafts") {
          gmailQuery = "in:drafts";
        } else if (activeFolder === "starred") {
          gmailQuery = "is:starred";
        }
      }

      // Try to load from cache first (only on initial load, not refresh)
      // Not: Folder değişiminde cache kontrolü useEffect'te yapılıyor, buraya gelmez
      if (!isRefresh) {
        const cached = getCachedMessages(activeFolder, query);
        if (cached && cached.length > 0) {
          setMessages(cached);
          setIsLoading(false);
          // Cache varsa arka planda fresh data çekme - sadece manuel refresh'te
          // Bu sayede gereksiz API çağrıları yapılmaz
        } else {
          setIsLoading(true);
        }
      } else {
        // Refresh durumunda direkt fresh data çek
        setIsRefreshing(true);
      }

      setError(null);

      // Fetch fresh data - Start with fewer messages for faster initial load
      // Backend fetches metadata sequentially (one API call per message), so fewer = faster
      // Strategy: Load 15 messages first (fast), then load more in background
      const initialLoadCount = 100; // Load 100 messages for pagination (5 pages x 20 messages)

      // Show progress for initial load
      if (!isRefresh) {
        setLoadingProgress(20);
        // Simulate progress (backend is slow, so we show progress)
        const progressInterval = setInterval(() => {
          setLoadingProgress((prev) => {
            if (prev >= 90) {
              clearInterval(progressInterval);
              return 90;
            }
            return prev + 5;
          });
        }, 200);

        try {
          const result = await listGmailMessages(gmailQuery, initialLoadCount);
          clearInterval(progressInterval);
          setLoadingProgress(100);

          if (!result || !result.messages) {
            console.warn("Gmail messages result is invalid:", result);
            if (messages.length === 0) {
              setMessages([]);
            }
          } else {
            setMessages(result.messages);
            saveCachedMessages(activeFolder, query, result.messages);
          }
          return; // Early return for initial load
        } catch (error) {
          clearInterval(progressInterval);
          throw error;
        }
      }

      // For refresh, load all messages
      const result = await listGmailMessages(gmailQuery, initialLoadCount);
      if (!result || !result.messages) {
        console.warn("Gmail messages result is invalid:", result);
        // Only clear if we don't have cached data
        if (!isRefresh || messages.length === 0) {
          setMessages([]);
        }
      } else {
        // Update messages and cache in localStorage
        setMessages(result.messages);
        saveCachedMessages(activeFolder, query, result.messages);
      }
    } catch (error: any) {
      console.error("Gmail messages load error:", error);
      const errorMessage = error.detail || error.message || "Mailler yüklenemedi";
      setError(errorMessage);

      // GMAIL_NOT_CONNECTED hatasını sessizce geç - sayfa zaten "Bağlı Değil" ekranını gösteriyor
      if (error.code === "GMAIL_NOT_CONNECTED") {
        console.log("[GMAIL] Ignoring GMAIL_NOT_CONNECTED error toast in Gmail page");
        return;
      }

      // Only show toast on initial load errors, not background refresh errors
      if (!isRefresh) {
        toast({
          title: "Hata",
          description: errorMessage,
          status: "error",
          duration: 5000,
        });
      }

      // Keep previous messages on error during refresh
      if (isRefresh) {
        // Keep existing messages visible
      } else {
        // Try to load from cache on error
        const cached = getCachedMessages(activeFolder, query);
        if (cached && cached.length > 0) {
          setMessages(cached);
        } else {
          setMessages([]);
        }
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  const handleSync = async () => {
    try {
      setIsSyncing(true);
      const result = await syncGmail();
      toast({
        title: "Başarılı",
        description: `${result.emails_indexed || 0} mail senkronize edildi`,
        status: "success",
        duration: 3000,
      });
      // Refresh messages in background without blocking UI
      await loadMessages(searchQuery, true);
      await loadGmailStatus();
    } catch (error: any) {
      toast({
        title: "Hata",
        description: error.detail || "Mail senkronizasyonu başarısız",
        status: "error",
        duration: 3000,
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSearch = () => {
    loadMessages(searchQuery, false);
  };

  const handleRetry = () => {
    loadMessages(searchQuery, false);
  };

  // Pagination calculations
  const totalPages = Math.ceil(messages.length / messagesPerPage);
  const startIndex = (currentPage - 1) * messagesPerPage;
  const endIndex = startIndex + messagesPerPage;
  const currentMessages = messages.slice(startIndex, endIndex);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    // Scroll to top when page changes
    if (messagesListRef.current) {
      messagesListRef.current.scrollTo(0, 0);
    }
    // Clear selection when changing pages
    setSelectedMessages(new Set());
  };

  const formatDate = (dateString?: string): string => {
    if (!dateString) return "";
    try {
      const date = new Date(dateString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return "Şimdi";
      if (diffMins < 60) return `${diffMins} dk`;
      if (diffHours < 24) return `${diffHours} sa`;
      if (diffDays < 7) return `${diffDays} gün`;

      // Format as date
      return date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
    } catch {
      return dateString;
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const newSelected = new Set(selectedMessages);
      currentMessages.forEach(m => newSelected.add(m.id));
      setSelectedMessages(newSelected);
    } else {
      const newSelected = new Set(selectedMessages);
      currentMessages.forEach(m => newSelected.delete(m.id));
      setSelectedMessages(newSelected);
    }
  };

  const handleSelectMessage = (messageId: string, checked: boolean) => {
    const newSelected = new Set(selectedMessages);
    if (checked) {
      newSelected.add(messageId);
    } else {
      newSelected.delete(messageId);
    }
    setSelectedMessages(newSelected);
  };

  const folders = [
    { id: "inbox", label: "Gelen Kutusu", icon: "📥" },
    { id: "starred", label: "Yıldızlı", icon: "⭐" },
    { id: "sent", label: "Gönderilen", icon: "📤" },
    { id: "drafts", label: "Taslaklar", icon: "📝" },
  ];

  // Gmail Icon Component
  const GmailLogoIcon = () => <GmailIcon size={20} />;

  // Custom Sidebar Toggle Icon
  const SidebarToggleIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
    </svg>
  );

  return (
    <AuthGuard>
      <Box display="flex" h="100vh" bg={bgColor} position="relative" overflow="hidden">
        {/* Sidebar Toggle Button */}
        {!isOpen && (
          <Box
            position="fixed"
            left={4}
            top="50%"
            transform="translateY(-50%)"
            zIndex={1001}
          >
            <IconButton
              icon={<SidebarToggleIcon />}
              aria-label="Kenar çubuğunu aç"
              onClick={toggle}
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
              borderRadius="lg"
              boxShadow="sm"
              minW="44px"
              h="44px"
            />
          </Box>
        )}
        <Sidebar />
        <Box
          flex={1}
          ml={isOpen ? "260px" : "0"}
          display="flex"
          flexDirection="column"
          transition="margin-left 0.3s ease"
          position="relative"
        >
          <Topbar />
          <Box flex={1} mt="60px" display="flex" overflow="hidden" position="relative">
            {/* Gmail Left Sidebar (Folders) */}
            <Box
              w="200px"
              bg={sidebarBg}
              borderRight="1px solid"
              borderColor={borderColor}
              p={4}
              overflowY="auto"
            >
              <VStack align="stretch" spacing={1}>
                <VStack spacing={2} mb={4}>
                  <Button
                    leftIcon={<RepeatIcon />}
                    colorScheme="green"
                    size="sm"
                    onClick={handleSync}
                    isLoading={isSyncing}
                    loadingText="Senkronize..."
                    w="full"
                    isDisabled={isSyncing || isRefreshing}
                  >
                    Senkronize Et
                  </Button>
                  {isRefreshing && (
                    <Box w="full" px={2}>
                      <Progress size="xs" colorScheme="blue" isIndeterminate borderRadius="full" />
                      <Text fontSize="xs" color={textSecondary} mt={1} textAlign="center" fontWeight="medium">
                        Yenileniyor...
                      </Text>
                    </Box>
                  )}
                  {gmailStatus?.last_sync_at && !isRefreshing && (
                    <Text fontSize="xs" color={textSecondary} textAlign="center" px={2}>
                      Son: {new Date(gmailStatus.last_sync_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}
                    </Text>
                  )}
                </VStack>
                {folders.map((folder) => (
                  <Button
                    key={folder.id}
                    leftIcon={<Text fontSize="md">{folder.icon}</Text>}
                    variant="ghost"
                    justifyContent="flex-start"
                    size="sm"
                    bg={activeFolder === folder.id ? selectedBg : "transparent"}
                    color={activeFolder === folder.id ? accentPrimary : textPrimary}
                    _hover={{ bg: hoverBg }}
                    onClick={() => setActiveFolder(folder.id)}
                    fontWeight={activeFolder === folder.id ? "600" : "400"}
                    borderLeft={activeFolder === folder.id ? "3px solid" : "3px solid transparent"}
                    borderColor={activeFolder === folder.id ? accentPrimary : "transparent"}
                    pl={activeFolder === folder.id ? "13px" : "16px"}
                  >
                    {folder.label}
                  </Button>
                ))}
              </VStack>
            </Box>

            {/* Main Content Area */}
            <Box flex={1} display="flex" flexDirection="column" overflow="hidden">
              {/* Search Bar */}
              <Box p={4} borderBottom="1px solid" borderColor={borderColor} bg={cardBg}>
                <InputGroup>
                  <InputLeftElement pointerEvents="none">
                    <SearchIcon color={textSecondary} />
                  </InputLeftElement>
                  <Input
                    placeholder="Mail ara"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === "Enter") {
                        handleSearch();
                      }
                    }}
                    bg={bgColor}
                    borderColor={borderColor}
                    _focus={{
                      borderColor: accentPrimary,
                      boxShadow: `0 0 0 1px ${accentPrimary}`,
                    }}
                    transition="all 0.2s ease"
                  />
                </InputGroup>
              </Box>

              {(isLoadingStatus || isLoading) ? (
                <Box flex={1} display="flex" flexDirection="column" alignItems="center" justifyContent="center" p={8}>
                  <VStack spacing={6}>
                    {/* Gmail Icon with Animation */}
                    <Box
                      sx={{
                        "@keyframes pulse": {
                          "0%, 100%": { transform: "scale(1)", opacity: 1 },
                          "50%": { transform: "scale(1.1)", opacity: 0.8 },
                        },
                        animation: "pulse 2s ease-in-out infinite",
                      }}
                    >
                      <Box
                        filter="drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1))"
                        display="flex"
                        alignItems="center"
                        justifyContent="center"
                      >
                        <img
                          src="/email.png"
                          alt="Email"
                          style={{
                            width: '80px',
                            height: '80px',
                            objectFit: 'contain'
                          }}
                        />
                      </Box>
                    </Box>
                    <VStack spacing={2}>
                      <Spinner
                        size="xl"
                        thickness="4px"
                        speed="0.65s"
                        color={accentPrimary}
                        emptyColor={spinnerEmptyColor}
                      />
                      <Text fontSize="lg" color={textPrimary} fontWeight="600">
                        Mailler yükleniyor...
                      </Text>
                      <Text fontSize="sm" color={textSecondary} textAlign="center">
                        Gmail hesabınız kontrol ediliyor
                      </Text>
                    </VStack>
                  </VStack>
                </Box>
              ) : !gmailStatus?.is_connected ? (
                <Box flex={1} display="flex" alignItems="center" justifyContent="center" p={8}>
                  <VStack spacing={4} maxW="400px">
                    <Box>
                      <img src="/email.png" alt="Email" style={{ width: '48px', height: '48px', objectFit: 'contain' }} />
                    </Box>
                    <Heading size="md" color={textPrimary} fontWeight="600">
                      Gmail Bağlı Değil
                    </Heading>
                    <Text color={textSecondary} textAlign="center" fontSize="sm" lineHeight="1.6">
                      Gmail hesabınızı bağlamak için profil ayarlarına gidin
                    </Text>
                    <Button
                      colorScheme="green"
                      onClick={() => router.push("/app")}
                      size="sm"
                      mt={2}
                    >
                      Profil Ayarlarına Git
                    </Button>
                  </VStack>
                </Box>
              ) : isLoading ? (
                <Box flex={1} display="flex" flexDirection="column" overflowY="auto" ref={messagesListRef}>
                  {/* Loading Progress Indicator */}
                  {loadingProgress > 0 && loadingProgress < 100 && (
                    <Box px={4} py={2} borderBottom="1px solid" borderColor={borderColor} bg={hoverBg}>
                      <Progress
                        value={loadingProgress}
                        colorScheme="blue"
                        size="sm"
                        borderRadius="full"
                        isAnimated
                      />
                      <Text fontSize="xs" color={textSecondary} mt={1} textAlign="center">
                        Mailler yükleniyor... {Math.round(loadingProgress)}%
                      </Text>
                    </Box>
                  )}
                  {/* Skeleton Loader for Mail List */}
                  <VStack align="stretch" spacing={0}>
                    <HStack px={4} py={2} borderBottom="1px solid" borderColor={borderColor} bg={hoverBg}>
                      <Skeleton height="20px" width="20px" />
                      <Skeleton height="16px" width="100px" />
                    </HStack>
                    {[...Array(8)].map((_, i) => (
                      <Box key={i} px={4} py={3} borderBottom="1px solid" borderColor={borderColor}>
                        <HStack spacing={3} align="start">
                          <Skeleton height="20px" width="20px" mt={1} />
                          <Skeleton height="20px" width="20px" mt={0.5} />
                          <Box flex="0 0 200px">
                            <Skeleton height="16px" width="150px" mb={2} />
                          </Box>
                          <Box flex={1}>
                            <Skeleton height="16px" width="60%" mb={2} />
                            <SkeletonText noOfLines={1} spacing="2" />
                          </Box>
                          <Box flex="0 0 80px">
                            <Skeleton height="12px" width="60px" />
                          </Box>
                        </HStack>
                      </Box>
                    ))}
                  </VStack>
                </Box>
              ) : error && messages.length === 0 ? (
                <Box flex={1} display="flex" alignItems="center" justifyContent="center" p={8}>
                  <VStack spacing={4} maxW="400px">
                    <Text fontSize="5xl">⚠️</Text>
                    <Heading size="md" color={textPrimary} fontWeight="600">
                      Yükleme Hatası
                    </Heading>
                    <Text color={textSecondary} textAlign="center" fontSize="sm" lineHeight="1.6">
                      {error}
                    </Text>
                    <Button colorScheme="green" onClick={handleRetry} size="sm" mt={2}>
                      Tekrar Dene
                    </Button>
                  </VStack>
                </Box>
              ) : messages.length === 0 ? (
                <Box flex={1} display="flex" alignItems="center" justifyContent="center" p={8}>
                  <VStack spacing={4} maxW="400px">
                    <Box>
                      <img src="/email.png" alt="Email" style={{ width: '48px', height: '48px', objectFit: 'contain' }} />
                    </Box>
                    <Heading size="md" color={textPrimary} fontWeight="600">
                      {searchQuery ? "Mail bulunamadı" : "Henüz mail yok"}
                    </Heading>
                    <Text color={textSecondary} textAlign="center" fontSize="sm" lineHeight="1.6">
                      {searchQuery
                        ? "Arama kriterlerinize uygun mail bulunamadı. Farklı bir arama terimi deneyin."
                        : "Gmail senkronizasyonu yaparak maillerinizi burada görebilirsiniz"}
                    </Text>
                    {!searchQuery && (
                      <Button
                        colorScheme="green"
                        onClick={handleSync}
                        isLoading={isSyncing}
                        size="sm"
                        mt={2}
                      >
                        Senkronize Et
                      </Button>
                    )}
                  </VStack>
                </Box>
              ) : (
                <Box flex={1} overflowY="auto" ref={messagesListRef} position="relative">
                  {/* Background refresh indicator */}
                  {isRefreshing && messages.length > 0 && (
                    <Box
                      position="absolute"
                      top={0}
                      left={0}
                      right={0}
                      height="2px"
                      zIndex={10}
                      bg="transparent"
                    >
                      <Box
                        height="100%"
                        bg={accentPrimary}
                        width="100%"
                        sx={{
                          animation: "shimmer 1.5s infinite",
                          "@keyframes shimmer": {
                            "0%": { transform: "translateX(-100%)" },
                            "100%": { transform: "translateX(100%)" },
                          },
                        }}
                      />
                    </Box>
                  )}
                  {/* Mail List - Gmail Style */}
                  <VStack align="stretch" spacing={0}>
                    {/* Select All Checkbox */}
                    <HStack
                      px={5}
                      py={3}
                      bg={cardBg}
                      borderBottom="1px solid"
                      borderColor={borderColor}
                    >
                      <Checkbox
                        isChecked={selectedMessages.size === currentMessages.length && currentMessages.length > 0 && currentMessages.every(m => selectedMessages.has(m.id))}
                        isIndeterminate={currentMessages.some(m => selectedMessages.has(m.id)) && !currentMessages.every(m => selectedMessages.has(m.id))}
                        onChange={(e) => {
                          if (e.target.checked) {
                            const newSelected = new Set(selectedMessages);
                            currentMessages.forEach(m => newSelected.add(m.id));
                            setSelectedMessages(newSelected);
                          } else {
                            const newSelected = new Set(selectedMessages);
                            currentMessages.forEach(m => newSelected.delete(m.id));
                            setSelectedMessages(newSelected);
                          }
                        }}
                        colorScheme="green"
                      />
                      <Text fontSize="xs" color={textMuted} fontWeight="500" letterSpacing="0.01em">
                        {selectedMessages.size > 0 ? `${selectedMessages.size} seçili` : `Sayfa ${currentPage} / ${totalPages} • ${messages.length} mail`}
                      </Text>
                    </HStack>

                    {/* Mail Items */}
                    {currentMessages.map((message, index) => (
                      <Box
                        key={message.id}
                        px={5}
                        py={4}
                        bg={selectedMessages.has(message.id) ? selectedBg : bgColor}
                        borderLeft={selectedMessages.has(message.id) ? "3px solid" : "3px solid transparent"}
                        borderColor={selectedMessages.has(message.id) ? accentPrimary : "transparent"}
                        _hover={{
                          bg: selectedMessages.has(message.id) ? selectedBg : hoverBg,
                          borderLeftColor: selectedMessages.has(message.id) ? accentPrimary : borderColor
                        }}
                        cursor="pointer"
                        onMouseEnter={() => {
                          // Prefetch on hover for instant loading
                          prefetchMessage(message.id);
                        }}
                        onClick={() => {
                          // Save scroll position before navigation
                          if (messagesListRef.current) {
                            const scrollKey = `gmail-scroll-${activeFolder}`;
                            sessionStorage.setItem(scrollKey, messagesListRef.current.scrollTop.toString());
                          }
                          // Also prefetch on click (in case hover didn't trigger)
                          prefetchMessage(message.id);
                          router.push(`/app/gmail/${message.id}`);
                        }}
                        transition="all 0.15s ease"
                        _active={{ transform: "scale(0.999)" }}
                        position="relative"
                      >
                        <HStack spacing={4} align="start">
                          {/* Checkbox */}
                          <Box onClick={(e) => e.stopPropagation()} flexShrink={0}>
                            <Checkbox
                              isChecked={selectedMessages.has(message.id)}
                              onChange={(e) => {
                                e.stopPropagation();
                                handleSelectMessage(message.id, e.target.checked);
                              }}
                              onClick={(e) => e.stopPropagation()}
                              colorScheme="green"
                              mt={0.5}
                            />
                          </Box>

                          {/* Star Icon */}
                          <Box onClick={(e) => e.stopPropagation()} flexShrink={0}>
                            <IconButton
                              icon={<StarIcon />}
                              aria-label="Yıldızla"
                              size="xs"
                              variant="ghost"
                              color={textMuted}
                              _hover={{ color: "yellow.500", bg: "transparent" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                // TODO: Implement star functionality
                              }}
                              minW="20px"
                              h="20px"
                            />
                          </Box>

                          {/* Sender - Strongest */}
                          <Box flex="0 0 180px" minW={0}>
                            <Text
                              fontSize="sm"
                              fontWeight="600"
                              color={textPrimary}
                              noOfLines={1}
                              letterSpacing="-0.015em"
                              lineHeight="1.4"
                            >
                              {message.sender || "Bilinmeyen"}
                            </Text>
                          </Box>

                          {/* Subject and Snippet */}
                          <Box flex={1} minW={0}>
                            <VStack align="stretch" spacing={1}>
                              {/* Subject - Second strongest */}
                              <Text
                                fontSize="sm"
                                fontWeight="500"
                                color={textPrimary}
                                noOfLines={1}
                                letterSpacing="-0.01em"
                                lineHeight="1.4"
                              >
                                {message.subject || "Konu yok"}
                              </Text>
                              {/* Snippet - Less prominent */}
                              {message.snippet && (
                                <Text
                                  fontSize="xs"
                                  color={textMuted}
                                  noOfLines={1}
                                  fontWeight="400"
                                  letterSpacing="0.01em"
                                  lineHeight="1.3"
                                >
                                  {message.snippet}
                                </Text>
                              )}
                            </VStack>
                          </Box>

                          {/* Date - Least prominent */}
                          <Box flex="0 0 70px" textAlign="right" flexShrink={0}>
                            <Text fontSize="xs" color={textMuted} fontWeight="400" letterSpacing="0.01em">
                              {formatDate(message.date || message.internalDate)}
                            </Text>
                          </Box>
                        </HStack>
                      </Box>
                    ))}
                  </VStack>

                  {/* Pagination Controls */}
                  {totalPages > 1 && (
                    <Box
                      px={4}
                      py={4}
                      borderTop="1px solid"
                      borderColor={borderColor}
                      bg={cardBg}
                      display="flex"
                      justifyContent="center"
                      alignItems="center"
                      gap={4}
                    >
                      {/* Önceki Butonu */}
                      <Button
                        size="sm"
                        variant="outline"
                        leftIcon={<ChevronLeftIcon />}
                        onClick={() => handlePageChange(currentPage - 1)}
                        isDisabled={currentPage === 1}
                        colorScheme="green"
                        borderColor={borderColor}
                        _hover={{ borderColor: accentPrimary, color: accentPrimary }}
                      >
                        Önceki
                      </Button>

                      {/* Sayfa Numaraları - Ortada */}
                      <HStack spacing={1}>
                        {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => {
                          // Show page numbers around current page
                          let pageNum: number;
                          if (totalPages <= 10) {
                            pageNum = i + 1;
                          } else if (currentPage <= 5) {
                            pageNum = i + 1;
                          } else if (currentPage >= totalPages - 4) {
                            pageNum = totalPages - 9 + i;
                          } else {
                            pageNum = currentPage - 4 + i;
                          }

                          return (
                            <Button
                              key={pageNum}
                              size="sm"
                              variant={currentPage === pageNum ? "solid" : "ghost"}
                              colorScheme="green"
                              onClick={() => handlePageChange(pageNum)}
                              minW="36px"
                              h="36px"
                              fontSize="xs"
                              fontWeight={currentPage === pageNum ? "600" : "400"}
                            >
                              {pageNum}
                            </Button>
                          );
                        })}
                      </HStack>

                      {/* Sonraki Butonu */}
                      <Button
                        size="sm"
                        variant="outline"
                        rightIcon={<ChevronRightIcon />}
                        onClick={() => handlePageChange(currentPage + 1)}
                        isDisabled={currentPage === totalPages}
                        colorScheme="green"
                        borderColor={borderColor}
                        _hover={{ borderColor: accentPrimary, color: accentPrimary }}
                      >
                        Sonraki
                      </Button>
                    </Box>
                  )}
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </AuthGuard>
  );
}
