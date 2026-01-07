"use client";

import {
  Box,
  VStack,
  Button,
  Text,
  Divider,
  useColorModeValue,
  HStack,
  IconButton,
  Tooltip,
  Avatar,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  useToast,
} from "@chakra-ui/react";
import { FaTrash } from "react-icons/fa";
import { useRouter, useSearchParams } from "next/navigation";
import { removeToken } from "@/lib/auth";
import { useState, useEffect } from "react";
import { AddIcon, ViewIcon } from "@chakra-ui/icons";
import ChatContextMenu from "./ChatContextMenu";
import { useSidebar } from "@/contexts/SidebarContext";
import { deleteChatDocuments, apiFetch, listChats, deleteChat, updateChatTitle, archiveChat } from "@/lib/api";
import GmailIcon from "@/components/icons/GmailIcon";
import DocumentIcon from "@/components/icons/DocumentIcon";

interface ChatHistory {
  id: string;
  title: string;
  timestamp: string;
  pinned?: boolean;
  archived?: boolean;
}

export default function Sidebar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isOpen, toggle } = useSidebar();
  const toast = useToast();
  const [chatHistory, setChatHistory] = useState<ChatHistory[]>([]);
  const [user, setUser] = useState<{ username: string } | null>(null);

  // Tema-aware renkler - TÜM hook'lar component'in en üstünde olmalı
  const bgColor = useColorModeValue("#F6F8FA", "#161B22"); // Panel / Card
  const borderColor = useColorModeValue("#D1D9E0", "#30363D"); // Border / divider
  const buttonHoverBg = useColorModeValue("#E7ECF0", "#22272E"); // Hover yüzey
  const selectedBg = useColorModeValue("#F0F3F6", "#1C2128"); // İç yüzey
  const textPrimary = useColorModeValue("#1F2328", "#E6EDF3");
  const toastBg = useColorModeValue("white", "#161B22"); // Toast background
  const toastBorder = useColorModeValue("#D1D9E0", "#30363D"); // Toast border
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const accentPrimary = useColorModeValue("#10B981", "#10B981");
  const accentHover = useColorModeValue("#34D399", "#34D399");
  const accentActive = useColorModeValue("#059669", "#059669");
  const errorColor = useColorModeValue("#CF222E", "#F85149");
  const iconButtonColor = useColorModeValue("gray.600", "gray.300");
  const iconButtonHoverBg = useColorModeValue("gray.200", "gray.700");
  const iconButtonHoverColor = useColorModeValue("gray.800", "white");
  const buttonTextColor = useColorModeValue("#FFFFFF", "#0D1117");
  const avatarBg = useColorModeValue("#FFFFFF", "#0D1117");

  // CHAT SAVING ENABLED: Load chat history from backend (filtered by module)
  const loadHistory = async () => {
    try {
      // Get current module from localStorage
      const currentModule = typeof window !== 'undefined' 
        ? (localStorage.getItem('selectedModule') === 'lgs_karekok' ? 'lgs_karekok' as const : 'none' as const)
        : 'none' as const;
      
      const chats = await listChats(currentModule);
      // Convert backend format to frontend format
      const history: ChatHistory[] = chats.map((chat) => ({
        id: chat.id,
        title: chat.title,
        timestamp: chat.updated_at || chat.created_at,
        pinned: false, // TODO: Add pinned support from backend
        archived: false, // TODO: Add archived support from backend
      }));

      // Sort by updated_at (most recent first)
      history.sort((a, b) => {
        const dateA = new Date(a.timestamp).getTime();
        const dateB = new Date(b.timestamp).getTime();
        return dateB - dateA;
      });

      setChatHistory(history);
    } catch (error) {
      console.error("Failed to load chat history:", error);
      // On error, set empty history
      setChatHistory([]);
    }
  };

  useEffect(() => {
    loadHistory();

    // Listen for updates
    window.addEventListener("chatHistoryUpdated", loadHistory);
    
    // Listen for module changes (both storage event and custom event)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'selectedModule') {
        loadHistory();
      }
    };
    
    const handleModuleChange = () => {
      loadHistory();
    };
    
    window.addEventListener("storage", handleStorageChange);
    window.addEventListener("moduleChanged", handleModuleChange);
    
    return () => {
      window.removeEventListener("chatHistoryUpdated", loadHistory);
      window.removeEventListener("storage", handleStorageChange);
      window.removeEventListener("moduleChanged", handleModuleChange);
    };
  }, []);

  // Fetch user info for avatar
  useEffect(() => {
    async function fetchUser() {
      try {
        const response = await apiFetch<{ username: string }>("/api/me");
        setUser(response);
      } catch (error) {
        console.error("Failed to fetch user:", error);
      }
    }
    fetchUser();
  }, []);

  const currentChatId = searchParams.get("chatId");

  const handleChatClick = (chatId: string) => {
    router.push(`/chat/${chatId}`);
    window.dispatchEvent(new CustomEvent("loadChat", { detail: { chatId } }));
  };

  const handleRename = async (chatId: string, newTitle: string) => {
    try {
      // Update title in backend
      await updateChatTitle(chatId, newTitle);

      // Update local state
      const history = [...chatHistory];
      const index = history.findIndex((chat) => chat.id === chatId);
      if (index >= 0) {
        history[index].title = newTitle;
        setChatHistory(history);
      }
    } catch (error) {
      console.error("Failed to rename chat:", error);
    }
  };

  // CHAT SAVING ENABLED: Delete chat from backend
  const handleDelete = async (chatId: string, deleteDocuments?: boolean) => {
    try {
      const chatTitle = chatHistory.find(c => c.id === chatId)?.title || "Sohbet";
      await deleteChat(chatId, deleteDocuments);

      // Clear local storage
      localStorage.removeItem(`chat_messages_${chatId}`);
      localStorage.removeItem(`chat_settings_${chatId}`);

      // Dispatch chatDeleted event for chat page to handle
      window.dispatchEvent(new CustomEvent("chatDeleted", {
        detail: { chatId, focusInput: false }
      }));

      // If deleted chat was current, go to new chat
      if (currentChatId === chatId) {
        router.push("/chat");
      }

      // Reload history from backend
      try {
        await loadHistory();
      } catch (historyError) {
        // History reload failed, but chat was already deleted successfully
        // Just log the error, don't show toast (chat deletion was successful)
        console.error("Failed to reload chat history:", historyError);
      }
    } catch (error) {
      // Only show error toast if deleteChat itself failed
      console.error("Failed to delete chat:", error);
      toast({
        title: "Hata",
        description: "Sohbet silinemedi",
        status: "error",
        duration: 3000,
        isClosable: true,
        position: "top-right",
      });
    }
  };

  const handlePin = (chatId: string) => {
    // TODO: Backend doesn't support pinned yet
    const history = [...chatHistory];
    const index = history.findIndex((chat) => chat.id === chatId);
    if (index >= 0) {
      history[index].pinned = true;
      setChatHistory(history);
    }
  };

  const handleUnpin = (chatId: string) => {
    // TODO: Backend doesn't support pinned yet
    const history = [...chatHistory];
    const index = history.findIndex((chat) => chat.id === chatId);
    if (index >= 0) {
      history[index].pinned = false;
      setChatHistory(history);
    }
  };

  const handleArchive = async (chatId: string) => {
    try {
      const chat = chatHistory.find(c => c.id === chatId);
      await archiveChat(chatId, true);
      // Reload history from backend (archived chat will be excluded)
      await loadHistory();

      if (currentChatId === chatId) {
        router.push("/chat");
        window.dispatchEvent(new CustomEvent("newChat"));
      }
    } catch (error) {
      console.error("Failed to archive chat:", error);
    }
  };

  const handleUnarchive = async (chatId: string) => {
    try {
      await archiveChat(chatId, false);
      // Reload history from backend (unarchived chat will be included)
      await loadHistory();
    } catch (error) {
      console.error("Failed to unarchive chat:", error);
    }
  };

  const handleNewChat = async () => {
    try {
      // Get current module from localStorage
      const currentModule = typeof window !== 'undefined' 
        ? (localStorage.getItem('selectedModule') === 'lgs_karekok' ? 'lgs_karekok' as const : 'none' as const)
        : 'none' as const;
      
      // Create a new chat first
      const { createChat } = await import("@/lib/api");
      const newChat = await createChat(undefined, currentModule);
      // Navigate to the new chat
      router.push(`/chat/${newChat.id}`);
      // Dispatch event for chat page to handle
      window.dispatchEvent(new CustomEvent("newChat", { detail: { chatId: newChat.id } }));
    } catch (error) {
      console.error("Failed to create new chat:", error);
      // Fallback: navigate to /chat and let the page handle it
      router.push("/chat");
      window.dispatchEvent(new CustomEvent("newChat"));
    }
  };

  const handleLogout = () => {
    // Clear all chat-related localStorage
    try {
      const keys = Object.keys(localStorage);
      keys.forEach(key => {
        if (key.startsWith("chat_") || key === "current_chat_id" || key === "chat_history") {
          localStorage.removeItem(key);
        }
      });
    } catch (error) {
      console.error("Failed to clear chat state on logout:", error);
    }
    removeToken();
    router.push("/login");
  };

  return (
    <Box
      w="260px"
      h="100vh"
      bg={bgColor}
      transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
      sx={{
        animation: isOpen ? "slideInLeft 0.3s ease-out" : "none",
        "@keyframes slideInLeft": {
          "0%": {
            transform: "translateX(-100%)",
            opacity: 0,
          },
          "100%": {
            transform: "translateX(0)",
            opacity: 1,
          },
        },
      }}
      borderRight="1px"
      borderColor={borderColor}
      display="flex"
      flexDirection="column"
      position="fixed"
      left={isOpen ? "0" : "-260px"}
      top={0}
      zIndex={999}
      boxShadow="2px 0 8px rgba(0, 0, 0, 0.1)"
      overflow="visible"
    >
      {/* Sidebar Header with Toggle Button (when open) */}
      {isOpen && (
        <Box position="relative" p={4} pb={2} minH="60px">
          <Tooltip
            label="Kenar çubuğunu kapa"
            placement="right"
            hasArrow
          >
            <IconButton
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                </svg>
              }
              aria-label="Kenar çubuğunu kapa"
              onClick={toggle}
              position="absolute"
              top={2}
              right={2}
              size="sm"
              variant="ghost"
              color={iconButtonColor}
              bg="transparent"
              _hover={{
                bg: iconButtonHoverBg,
                color: iconButtonHoverColor
              }}
              transition="all 0.2s ease"
              zIndex={10}
              borderRadius="md"
            />
          </Tooltip>
        </Box>
      )}

      {/* New Chat Button */}
      <Box p={4} pt={2}>
        <Button
          w="100%"
          bg={accentPrimary}
          color={buttonTextColor}
          onClick={handleNewChat}
          leftIcon={<AddIcon />}
          _hover={{ bg: accentHover }}
          _active={{ bg: accentActive }}
          transition="all 0.2s ease"
        >
          Yeni Sohbet
        </Button>
      </Box>

      {/* Documents Button */}
      <Box px={4} pb={2}>
        <Button
          w="100%"
          variant="outline"
          borderColor={borderColor}
          color={textPrimary}
          onClick={() => router.push("/app/documents")}
          leftIcon={<DocumentIcon size={18} />}
          _hover={{
            bg: buttonHoverBg,
            borderColor: borderColor,
            transform: "translateY(-2px)",
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.1)",
          }}
          transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
        >
          Dokümanlarım
        </Button>
      </Box>

      {/* Gmail Button */}
      <Box px={4} pb={2}>
        <Button
          w="100%"
          variant="outline"
          borderColor={borderColor}
          color={textPrimary}
          onClick={() => router.push("/app/gmail")}
          leftIcon={<img src="/email.png" alt="Email" style={{ width: '18px', height: '18px', objectFit: 'contain' }} />}
          _hover={{
            bg: buttonHoverBg,
            borderColor: borderColor,
            transform: "translateY(-2px)",
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.1)",
          }}
          transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
        >
          Gmail
        </Button>
      </Box>

      <Divider borderColor={borderColor} />

      {/* Chat History */}
      <Box
        flex={1}
        overflowY="auto"
        overflowX="hidden"
        p={2}
        position="relative"
        sx={{
          "&::-webkit-scrollbar": {
            width: "8px",
          },
          "&::-webkit-scrollbar-track": {
            background: "transparent",
          },
          "&::-webkit-scrollbar-thumb": {
            background: borderColor,
            borderRadius: "4px",
            "&:hover": {
              background: textSecondary,
            },
          },
        }}
      >
        <Text fontSize="sm" fontWeight="semibold" color={textSecondary} px={2} mb={2}>
          Sohbetlerin
        </Text>
        <VStack align="stretch" spacing={1}>
          {chatHistory.length === 0 && (
            <Text fontSize="sm" color={textSecondary} textAlign="center" py={4}>
              Sohbet geçmişi yok
            </Text>
          )}
          {chatHistory.map((chat) => (
            <HStack
              key={chat.id}
              spacing={1}
              p={1}
              borderRadius="md"
              bg={currentChatId === chat.id ? selectedBg : "transparent"}
              _hover={{
                bg: buttonHoverBg,
                transform: "translateX(4px)",
              }}
              cursor="pointer"
              onClick={() => handleChatClick(chat.id)}
              transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
              sx={{
                "&:hover": {
                  "& .chat-title": {
                    color: textPrimary,
                  },
                },
              }}
              position="relative"
            >
              <Box flex={1} minW={0}>
                <Text
                  isTruncated
                  fontSize="sm"
                  title={chat.title}
                  fontWeight={chat.pinned ? "semibold" : "normal"}
                  color={textPrimary}
                >
                  {chat.pinned && "📌 "}
                  {chat.title}
                </Text>
              </Box>
              <Box
                onClick={(e) => {
                  e.stopPropagation();
                }}
                onMouseDown={(e) => {
                  e.stopPropagation();
                }}
                position="relative"
                zIndex={10}
                flexShrink={0}
              >
                <ChatContextMenu
                  chatId={chat.id}
                  chatTitle={chat.title}
                  isPinned={chat.pinned}
                  isArchived={chat.archived}
                  onRename={handleRename}
                  onDelete={handleDelete}
                  onPin={handlePin}
                  onUnpin={handleUnpin}
                  onArchive={handleArchive}
                  onUnarchive={handleUnarchive}
                />
              </Box>
            </HStack>
          ))}
        </VStack>
      </Box>

      <Divider />

      {/* User Avatar and Logout */}
      <Box p={4}>
        {user && (
          <VStack spacing={3} align="stretch">
            <Menu>
              <MenuButton w="100%">
                <HStack spacing={3} justify="flex-start" p={2} borderRadius="md" _hover={{ bg: buttonHoverBg }} transition="all 0.2s">
                  <Avatar
                    size="sm"
                    name={user.username}
                    bg={accentPrimary}
                    color="white"
                    fontWeight="600"
                  />
                  <VStack align="start" spacing={0} flex={1}>
                    <Text fontSize="sm" fontWeight="semibold" color={textPrimary} noOfLines={1}>
                      {user.username}
                    </Text>
                    <Text fontSize="xs" color={textSecondary}>
                      Hesap Ayarları
                    </Text>
                  </VStack>
                </HStack>
              </MenuButton>
              <MenuList bg={selectedBg} borderColor={borderColor}>
                <MenuItem
                  onClick={() => router.push("/app")}
                  bg={selectedBg}
                  color={textPrimary}
                  _hover={{ bg: buttonHoverBg }}
                >
                  Profil
                </MenuItem>
              </MenuList>
            </Menu>
            <Button
              w="100%"
              variant="outline"
              borderColor={borderColor}
              color={errorColor}
              onClick={handleLogout}
              _hover={{ bg: buttonHoverBg, borderColor: errorColor }}
              transition="all 0.2s ease"
            >
              Çıkış Yap
            </Button>
          </VStack>
        )}
        {!user && (
          <Button
            w="100%"
            variant="outline"
            borderColor={borderColor}
            color={errorColor}
            onClick={handleLogout}
            _hover={{ bg: buttonHoverBg, borderColor: errorColor }}
            transition="all 0.2s ease"
          >
            Çıkış Yap
          </Button>
        )}
      </Box>
    </Box>
  );
}

