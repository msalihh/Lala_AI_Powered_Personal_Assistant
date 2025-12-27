"use client";

import { HStack, IconButton, Tooltip, useColorModeValue } from "@chakra-ui/react";
import { FaCopy, FaInfoCircle } from "react-icons/fa";
import { useToast } from "@chakra-ui/react";

interface MessageActionsProps {
  content: string;
  timestamp: Date;
  onCopy?: () => void;
}

export default function MessageActions({ content, timestamp, onCopy }: MessageActionsProps) {
  const accentPrimary = useColorModeValue("#1A7F37", "#3FB950");
  const toast = useToast();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      toast({
        title: "Kopyalandı",
        description: "Mesaj panoya kopyalandı",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
      onCopy?.();
    } catch (error) {
      toast({
        title: "Hata",
        description: "Mesaj kopyalanamadı",
        status: "error",
        duration: 2000,
        isClosable: true,
      });
    }
  };

  const timestampString = timestamp.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });

  return (
    <HStack className="msgActions" spacing={1}>
      <Tooltip label="Kopyala" placement="top">
        <IconButton
          aria-label="Mesajı kopyala"
          icon={<FaCopy size={14} />}
          size="xs"
          variant="ghost"
          colorScheme="gray"
          color="gray.400"
          w="28px"
          h="28px"
          minW="28px"
          _hover={{ 
            color: accentPrimary, 
            bg: useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.2)") 
          }}
          onClick={handleCopy}
        />
      </Tooltip>
      <Tooltip label={timestampString} placement="top">
        <IconButton
          aria-label="Mesaj bilgisi"
          icon={<FaInfoCircle size={14} />}
          size="xs"
          variant="ghost"
          colorScheme="gray"
          color="gray.400"
          w="28px"
          h="28px"
          minW="28px"
          _hover={{ 
            color: accentPrimary, 
            bg: useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.2)") 
          }}
        />
      </Tooltip>
    </HStack>
  );
}

