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
} from "@chakra-ui/react";
import { useRouter, useSearchParams } from "next/navigation";
import { removeToken } from "@/lib/auth";
import { useState, useEffect } from "react";
import { AddIcon, ViewIcon } from "@chakra-ui/icons";
import ChatContextMenu from "./ChatContextMenu";
import { useSidebar } from "@/contexts/SidebarContext";
import { listChats, deleteChat, deleteChatDocuments, ChatListItem, apiFetch, createChat } from "@/lib/api";

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
  const [chatHistory, setChatHistory] = useState<ChatHistory[]>([]);
  const [user, setUser] = useState<{ username: string } | null>(null);
  
  // Tema-aware renkler - TÜM hook'lar component'in en üstünde olmalı
  const bgColor = useColorModeValue("#F6F8FA", "#161B22"); // Panel / Card
  const borderColor = useColorModeValue("#D1D9E0", "#30363D"); // Border / divider
  const buttonHoverBg = useColorModeValue("#E7ECF0", "#22272E"); // Hover yüzey
  const selectedBg = useColorModeValue("#F0F3F6", "#1C2128"); // İç yüzey
  const textPrimary = useColorModeValue("#1F2328", "#E6EDF3");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const accentPrimary = useColorModeValue("#1A7F37", "#3FB950");
  const accentHover = useColorModeValue("#2EA043", "#2EA043");
  const accentActive = useColorModeValue("#238636", "#238636");
  const errorColor = useColorModeValue("#CF222E", "#F85149");
  const iconButtonColor = useColorModeValue("gray.600", "gray.300");
  const iconButtonHoverBg = useColorModeValue("gray.200", "gray.700");
  const iconButtonHoverColor = useColorModeValue("gray.800", "white");
  const buttonTextColor = useColorModeValue("#FFFFFF", "#0D1117");
  const avatarBg = useColorModeValue("#FFFFFF", "#0D1117");

  // Load chat history from backend (user-scoped)
  const loadHistory = async () => {
    try {
      const chats = await listChats();
      // Convert backend format to frontend format
      const history: ChatHistory[] = chats.map((chat) => ({
        id: chat.id,
        title: chat.title,
        timestamp: chat.created_at,
        pinned: false, // Backend doesn't support pinned yet
        archived: false, // Backend doesn't support archived yet
      }));
      // Sort by timestamp (newest first)
      const sorted = history.sort((a, b) => 
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      setChatHistory(sorted);
    } catch (error) {
      console.error("Failed to load chat history:", error);
      setChatHistory([]);
    }
  };

  useEffect(() => {
    loadHistory();

    // Listen for updates
    window.addEventListener("chatHistoryUpdated", loadHistory);
    return () => window.removeEventListener("chatHistoryUpdated", loadHistory);
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
    // TODO: Add PATCH /chats/{chat_id} endpoint for renaming
    // For now, just update local state (backend doesn't support rename yet)
    const history = [...chatHistory];
    const index = history.findIndex((chat) => chat.id === chatId);
    if (index >= 0) {
      history[index].title = newTitle;
      setChatHistory(history);
      // Note: Backend rename endpoint not implemented yet
    }
  };

  const handleDelete = async (chatId: string) => {
    try {
      // Delete chat from backend (cascade delete messages)
      await deleteChat(chatId);
      
      // Delete chat-scoped documents from backend (cascade delete)
      try {
        const result = await deleteChatDocuments(chatId);
        if (result.deleted_documents > 0) {
          console.log(`Deleted ${result.deleted_documents} documents and ${result.deleted_vectors} vectors for chat ${chatId}`);
        }
      } catch (error) {
        console.error("Failed to delete chat documents:", error);
        // Continue even if document deletion fails
      }
      
      // Notify other components (like documents page) that a chat was deleted
      // Note: focusInput will be set by ChatContextMenu after delete confirmation
      window.dispatchEvent(new CustomEvent("chatDeleted", { detail: { chatId } }));
      
      // Delete local state (messages and settings)
      localStorage.removeItem(`chat_messages_${chatId}`);
      localStorage.removeItem(`chat_settings_${chatId}`);
      
      // Reload history from backend
      await loadHistory();
      
      // If deleted chat was current, go to new chat
      if (currentChatId === chatId) {
        // Blur any active element before navigation to prevent focus on sidebar toggle
        try {
          const activeElement = document.activeElement as HTMLElement | null;
          if (activeElement && activeElement !== document.body) {
            activeElement.blur();
          }
        } catch (e) {
          // Ignore blur errors
        }
        router.push("/chat");
        window.dispatchEvent(new CustomEvent("newChat"));
      }
    } catch (error) {
      console.error("Failed to delete chat:", error);
      // Still reload history to sync with backend
      await loadHistory();
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

  const handleArchive = (chatId: string) => {
    // TODO: Backend doesn't support archived yet
    const history = [...chatHistory];
    const index = history.findIndex((chat) => chat.id === chatId);
    if (index >= 0) {
      history[index].archived = true;
      setChatHistory(history.filter((chat) => !chat.archived));
      
      if (currentChatId === chatId) {
        router.push("/chat");
        window.dispatchEvent(new CustomEvent("newChat"));
      }
    }
  };

  const handleUnarchive = (chatId: string) => {
    // TODO: Backend doesn't support archived yet
    const history = [...chatHistory];
    const index = history.findIndex((chat) => chat.id === chatId);
    if (index >= 0) {
      history[index].archived = false;
      setChatHistory(history);
    }
  };

  const handleNewChat = async () => {
    // Just navigate to chat page - chat will be created when first message is sent
    router.push("/chat");
    window.dispatchEvent(new CustomEvent("newChat"));
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
      transition="left 0.3s ease"
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
          leftIcon={<ViewIcon />}
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
                <HStack spacing={3} justify="flex-start">
                  <Avatar 
                    size="md" 
                    name={user.username}
                    bg={accentPrimary}
                    color={avatarBg}
                    fontWeight="600"
                  />
                  <VStack align="start" spacing={0} flex={1}>
                    <Text fontSize="sm" fontWeight="semibold" color={textPrimary}>
                      {user.username}
                    </Text>
                    <Text fontSize="xs" color={textSecondary}>
                      Profil
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

