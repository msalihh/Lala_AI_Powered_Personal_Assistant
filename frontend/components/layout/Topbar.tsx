"use client";

import { Box, HStack, Text, Avatar, Menu, MenuButton, MenuList, MenuItem, IconButton, VStack, useColorMode, useColorModeValue } from "@chakra-ui/react";
import { HamburgerIcon, CloseIcon, SunIcon, MoonIcon } from "@chakra-ui/icons";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";

interface UserResponse {
  id: string;
  username: string;
  email: string | null;
}

export default function Topbar() {
  const router = useRouter();
  const { isOpen, toggle } = useSidebar();
  const { colorMode, toggleColorMode } = useColorMode();
  const [user, setUser] = useState<UserResponse | null>(null);
  
  // Tema-aware renkler
  const bgColor = useColorModeValue("#FFFFFF", "#0D1117");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  const textColor = useColorModeValue("#1F2328", "#E6EDF3");
  const hoverBg = useColorModeValue("#E7ECF0", "#22272E");

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
  }, []);

  return (
    <Box
      h="60px"
      bg={bgColor}
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
      sx={{
        animation: "fadeInDown 0.4s ease-out",
      }}
      boxShadow="0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)"
    >
      <HStack spacing={3}>
        <Box
          position="relative"
          w="32px"
          h="32px"
          sx={
            !isOpen
              ? {
                  "&:hover .hace-logo": {
                    opacity: "0 !important",
                  },
                  "&:hover .sidebar-toggle": {
                    opacity: "1 !important",
                  }
                }
              : {}
          }
        >
          <Box
            className="hace-logo"
            as="img"
            src="/hace-logo.svg"
            alt="HACE Logo"
            w="32px"
            h="32px"
            position="absolute"
            top={0}
            left={0}
            transition="opacity 0.2s ease"
            opacity={1}
          />
          {/* Sidebar Toggle Button (hidden by default, shows on hover when sidebar is closed) */}
          {!isOpen && (
            <IconButton
              className="sidebar-toggle"
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                </svg>
              }
              aria-label="Kenar çubuğunu aç"
              onClick={toggle}
              size="sm"
              variant="ghost"
          color={useColorModeValue("#656D76", "#8B949E")}
          bg="transparent"
          position="absolute"
          top={0}
          left={0}
          w="32px"
          h="32px"
          opacity={0}
          _hover={{ 
            bg: hoverBg, 
            color: textColor,
          }}
              transition="all 0.2s ease"
              borderRadius="md"
              pointerEvents="auto"
            />
          )}
        </Box>
        <Text 
          fontSize="xl" 
          fontWeight="600"
          color={textColor}
          letterSpacing="tight"
        >
          HACE
        </Text>
      </HStack>

      {/* Tema Toggle Butonu - Sağ üst köşe */}
      <HStack spacing={2}>
        <IconButton
          aria-label={colorMode === "dark" ? "Aydınlık temaya geç" : "Karanlık temaya geç"}
          icon={colorMode === "dark" ? <SunIcon /> : <MoonIcon />}
          onClick={toggleColorMode}
          size="md"
          variant="ghost"
          color={useColorModeValue("#656D76", "#8B949E")}
          bg="transparent"
          _hover={{ 
            bg: hoverBg, 
            color: textColor,
          }}
          transition="all 0.2s ease"
          borderRadius="md"
        />
      </HStack>
    </Box>
  );
}

