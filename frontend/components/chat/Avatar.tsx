"use client";

import { Box } from "@chakra-ui/react";
import { useColorModeValue } from "@chakra-ui/react";

interface ChatAvatarProps {
  role: "assistant" | "user";
  username?: string;
}

export default function ChatAvatar({ role, username }: ChatAvatarProps) {
  const panelBg = useColorModeValue("#F6F8FA", "#161B22");
  const accentBorder = useColorModeValue("rgba(26, 127, 55, 0.3)", "rgba(63, 185, 80, 0.3)");
  const accentPrimary = useColorModeValue("#1A7F37", "#3FB950");
  const userMessageText = useColorModeValue("#FFFFFF", "#FFFFFF");

  if (role === "assistant") {
    return (
      <Box
        className="msgAvatarArea"
        w="36px"
        h="36px"
        flexShrink={0}
        display="flex"
        alignItems="center"
        justifyContent="center"
      >
        <Box
          w="32px"
          h="32px"
          borderRadius="full"
          display="flex"
          alignItems="center"
          justifyContent="center"
          bg={panelBg}
          border="2px solid"
          borderColor={accentBorder}
          transition="all 0.2s ease"
          _hover={{
            borderColor: accentPrimary,
          }}
        >
          <Box
            as="img"
            src="/hace-logo.svg"
            alt="HACE"
            w="24px"
            h="24px"
          />
        </Box>
      </Box>
    );
  }

  // User avatar - will be rendered separately in MessageItem
  return null;
}

