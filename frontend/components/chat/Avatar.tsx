import { Box } from "@chakra-ui/react";
import { useColorModeValue } from "@chakra-ui/react";
import Image from "next/image";

interface ChatAvatarProps {
  role: "assistant" | "user";
  username?: string;
  module?: string;
}

export default function ChatAvatar({ role, username, module }: ChatAvatarProps) {
  const panelBg = useColorModeValue("#F6F8FA", "#161B22");
  const accentBorder = useColorModeValue("rgba(16, 185, 129, 0.3)", "rgba(16, 185, 129, 0.3)");
  const accentPrimary = "#10B981";

  if (role === "assistant") {
    const isLgs = module === "lgs_karekok";
    const iconSrc = isLgs ? "/square-root.png" : "/chat.png";

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
          border="1px solid"
          borderColor={accentBorder}
          transition="all 0.2s ease"
          overflow="hidden"
          p={1}
          _hover={{
            borderColor: accentPrimary,
          }}
        >
          <Image src={iconSrc} alt="Assistant" width={24} height={24} style={{ objectFit: 'contain' }} />
        </Box>
      </Box>
    );
  }

  // User avatar - will be rendered separately in MessageItem
  return null;
}

