"use client";

import { Box, HStack, Text, Avatar, Menu, MenuButton, MenuList, MenuItem, IconButton, Divider, useColorMode, useColorModeValue } from "@chakra-ui/react";
import { SunIcon, MoonIcon } from "@chakra-ui/icons";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Image from "next/image";
import { apiFetch } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";
import LalaAILogo from "@/components/icons/LalaAILogo";

interface UserResponse {
  id: string;
  username: string;
  email: string | null;
  avatar_url?: string | null;
}

export default function Topbar() {
  const router = useRouter();
  const { isOpen, toggle } = useSidebar();
  const { colorMode, toggleColorMode } = useColorMode();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [selectedModule, setSelectedModule] = useState<"none" | "lgs_karekok">("none");

  // Tema-aware renkler - Premium UI
  const bgColor = useColorModeValue("rgba(255, 255, 255, 0.8)", "rgba(13, 17, 23, 0.8)");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  const textColor = useColorModeValue("#1F2328", "#E6EDF3");
  const accentPrimary = "#10B981";
  const accentSoft = "rgba(16, 185, 129, 0.1)";
  const glassBg = useColorModeValue("rgba(246, 248, FA, 0.5)", "rgba(22, 27, 34, 0.5)");

  useEffect(() => {
    async function fetchUser() {
      try {
        const response = await apiFetch<UserResponse>("/api/me");
        setUser(response);
      } catch (error) {
        console.error("Failed to fetch user:", error);
      }
    }
    fetchUser();

    if (typeof window !== 'undefined') {
      const savedModule = localStorage.getItem('selectedModule');
      setSelectedModule(savedModule === 'lgs_karekok' ? 'lgs_karekok' : 'none');
    }

    const handleModuleChange = () => {
      if (typeof window !== 'undefined') {
        const savedModule = localStorage.getItem('selectedModule');
        setSelectedModule(savedModule === 'lgs_karekok' ? 'lgs_karekok' : 'none');
      }
    };

    window.addEventListener('moduleChanged', handleModuleChange);
    window.addEventListener('storage', (e) => {
      if (e.key === 'selectedModule') {
        handleModuleChange();
      }
    });

    return () => {
      window.removeEventListener('moduleChanged', handleModuleChange);
    };
  }, []);

  const handleModuleSwitch = async (module: "none" | "lgs_karekok") => {
    if (typeof window === 'undefined' || selectedModule === module) return;

    localStorage.setItem('selectedModule', module);

    try {
      const { createChat } = await import("@/lib/api");
      const newChat = await createChat(undefined, module);
      router.push(`/chat/${newChat.id}`);
      window.dispatchEvent(new CustomEvent("newChat", { detail: { chatId: newChat.id } }));
      window.dispatchEvent(new CustomEvent('moduleChanged'));
    } catch (error) {
      console.error("Failed to switch module:", error);
      window.location.reload();
    }
  };

  return (
    <Box
      h="64px"
      bg={bgColor}
      backdropFilter="blur(12px)"
      borderBottom="1px"
      borderColor={borderColor}
      display="flex"
      alignItems="center"
      justifyContent="space-between"
      px={6}
      position="fixed"
      top={0}
      left={isOpen ? "260px" : "0"}
      right={0}
      zIndex={1000}
      transition="left 0.3s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.3s ease, border-color 0.3s ease"
      boxShadow="sm"
    >
      <HStack spacing={4} align="center">
        {!isOpen && (
          <Box
            w="36px"
            h="36px"
            display="flex"
            alignItems="center"
            justifyContent="center"
            borderRadius="xl"
            bg={accentSoft}
            cursor="pointer"
            onClick={toggle}
            _hover={{ bg: "rgba(16, 185, 129, 0.2)" }}
            transition="all 0.2s"
          >
            <LalaAILogo size={24} />
          </Box>
        )}

        {/* Premium Module Selector */}
        <Box
          display="flex"
          alignItems="center"
          bg={glassBg}
          borderRadius="xl"
          p="4px"
          border="1px"
          borderColor={borderColor}
          position="relative"
          overflow="hidden"
          boxShadow="inner"
        >
          <HStack spacing={1} position="relative">
            {/* Sliding Indicator */}
            <AnimatePresence>
              <motion.div
                key={selectedModule}
                layoutId="module-active-bg"
                initial={false}
                style={{
                  position: "absolute",
                  top: 0,
                  bottom: 0,
                  left: selectedModule === "none" ? 0 : "165px",
                  width: selectedModule === "none" ? "165px" : "210px",
                  backgroundColor: accentPrimary,
                  borderRadius: "8px",
                  zIndex: 0,
                }}
                transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
              />
            </AnimatePresence>

            <Box
              as="button"
              onClick={() => handleModuleSwitch("none")}
              px={4}
              py={2}
              borderRadius="lg"
              fontSize="sm"
              fontWeight="600"
              transition="color 0.2s"
              position="relative"
              zIndex={1}
              color={selectedModule === "none" ? "white" : textColor}
              _hover={{ color: selectedModule === "none" ? "white" : accentPrimary }}
              display="flex"
              alignItems="center"
              gap={2}
              minW="165px"
              justifyContent="center"
            >
              <Image src="/chat.png" alt="Chat" width={20} height={20} style={{ objectFit: 'contain' }} />
              <Text>Kişisel Asistan</Text>
            </Box>

            <Box
              as="button"
              onClick={() => handleModuleSwitch("lgs_karekok")}
              px={4}
              py={2}
              borderRadius="lg"
              fontSize="sm"
              fontWeight="600"
              transition="color 0.2s"
              position="relative"
              zIndex={1}
              color={selectedModule === "lgs_karekok" ? "white" : textColor}
              _hover={{ color: selectedModule === "lgs_karekok" ? "white" : accentPrimary }}
              display="flex"
              alignItems="center"
              gap={2}
              minW="210px"
              justifyContent="center"
            >
              <Image src="/square-root.png" alt="Square Root" width={20} height={20} style={{ objectFit: 'contain' }} />
              <Text>LGS Karekök Asistanı</Text>
            </Box>
          </HStack>
        </Box>
      </HStack>

      <HStack spacing={4}>
        <IconButton
          aria-label="Tema değiştir"
          icon={colorMode === "dark" ? <SunIcon /> : <MoonIcon />}
          onClick={toggleColorMode}
          size="md"
          variant="ghost"
          color={accentPrimary}
          _hover={{ bg: accentSoft }}
          borderRadius="full"
        />
        {user && (
          <Menu>
            <MenuButton>
              <Avatar
                size="sm"
                name={user.username}
                src={user.avatar_url || undefined}
                border={`2px solid ${accentPrimary}`}
              />
            </MenuButton>
            <MenuList bg={useColorModeValue("white", "#161B22")} borderColor={borderColor}>
              <MenuItem onClick={() => router.push("/app")}>Profil</MenuItem>
              <Divider />
              <MenuItem color="red.500" onClick={() => {
                const { removeToken } = require("@/lib/auth");
                removeToken();
                router.push("/login");
              }}>Çıkış Yap</MenuItem>
            </MenuList>
          </Menu>
        )}
      </HStack>
    </Box>
  );
}
