"use client";

import React, { useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  Box,
  Text,
  useColorModeValue,
  HStack,
  Badge,
  VStack,
  Tooltip,
  Icon,
} from "@chakra-ui/react";
import { FaFilePdf, FaEnvelope } from "react-icons/fa";

interface SourceInfo {
  documentId: string;
  filename: string;
  chunkIndex: number;
  preview: string;
  score: number;
  source_scope?: "priority" | "global";
  source_type?: "document" | "email";
  subject?: string;
  sender?: string;
  date?: string;
}

interface SourcesPanelProps {
  sources: SourceInfo[];
}

export default function SourcesPanel({ sources }: SourcesPanelProps) {
  const router = useRouter();
  const borderColor = useColorModeValue("rgba(0, 0, 0, 0.1)", "rgba(255, 255, 255, 0.1)");
  const titleColor = useColorModeValue("#656D76", "#8B949E");
  const filenameColor = useColorModeValue("#1F2328", "#E6EDF3");
  const filenameHoverColor = useColorModeValue("#1A7F37", "#3FB950");
  const pdfIconColor = useColorModeValue("#DC2626", "#EF4444");
  const hoverBg = useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)");

  // Email-specific colors
  const emailIconColor = useColorModeValue("#2563EB", "#60A5FA");
  const emailBg = useColorModeValue("rgba(37, 99, 235, 0.1)", "rgba(96, 165, 250, 0.15)");
  const emailBgHover = useColorModeValue("rgba(37, 99, 235, 0.15)", "rgba(96, 165, 250, 0.2)");
  const emailBorder = useColorModeValue("rgba(37, 99, 235, 0.2)", "rgba(96, 165, 250, 0.3)");
  const emailBorderHover = useColorModeValue("rgba(37, 99, 235, 0.3)", "rgba(96, 165, 250, 0.4)");
  const emailSecondaryText = useColorModeValue("#6B7280", "#9CA3AF");

  // Remove duplicates by filename/subject, keep first occurrence
  const uniqueSources = useMemo(() => {
    const seen = new Set<string>();
    return sources.filter((source) => {
      const key = source.source_type === "email"
        ? `email-${source.subject}-${source.sender}`
        : `doc-${source.filename}`;

      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }, [sources]);

  const handleSourceClick = (source: SourceInfo) => {
    if (source.source_type === "email") {
      // Navigate to email detail page - documentId is actually the email message_id
      router.push(`/app/gmail/${source.documentId}`);
      return;
    }
    router.push(`/app/documents/${source.documentId}`);
  };

  return (
    <Box mt={4} pt={3} borderTop="1px solid" borderColor={borderColor}>
      {/* Header */}
      <Text fontSize="xs" fontWeight="500" color={titleColor} mb={3}>
        📚 Kaynaklar ({uniqueSources.length})
      </Text>

      {/* Source List - Enhanced with email details */}
      <HStack spacing={2} flexWrap="wrap" align="flex-start">
        {uniqueSources.map((source, idx) => {
          const isEmail = source.source_type === "email";

          // Format date for emails
          const formatEmailDate = (dateStr?: string) => {
            if (!dateStr) return "";
            try {
              const date = new Date(dateStr);
              const now = new Date();
              const diffMs = now.getTime() - date.getTime();
              const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

              if (diffDays === 0) return "Bugün";
              if (diffDays === 1) return "Dün";
              if (diffDays < 7) return `${diffDays} gün önce`;
              if (diffDays < 30) return `${Math.floor(diffDays / 7)} hafta önce`;
              return date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
            } catch {
              return "";
            }
          };

          const emailTooltip = isEmail && source.sender
            ? `${source.sender}${source.date ? ` • ${formatEmailDate(source.date)}` : ""}`
            : "";

          return (
            <Tooltip
              key={`${source.documentId}-${idx}`}
              label={emailTooltip}
              isDisabled={!isEmail || !emailTooltip}
              placement="top"
              hasArrow
            >
              <Box
                as="button" // Make both emails and documents clickable
                onClick={() => handleSourceClick(source)}
                px={3}
                py={2}
                borderRadius="8px"
                border="1px solid"
                borderColor={isEmail ? emailBorder : borderColor}
                bg={isEmail ? emailBg : "transparent"}
                transition="all 0.2s ease"
                _hover={{
                  bg: isEmail ? emailBgHover : hoverBg,
                  transform: "translateY(-1px)",
                  borderColor: isEmail ? emailBorderHover : undefined,
                }}
                cursor="pointer" // Always show pointer cursor
                maxW="280px"
              >
                <HStack spacing={2} align="flex-start">
                  <Box
                    color={isEmail ? emailIconColor : pdfIconColor}
                    fontSize="14px"
                    mt={0.5}
                  >
                    {isEmail ? <Icon as={FaEnvelope} /> : <FaFilePdf />}
                  </Box>
                  <VStack align="flex-start" spacing={0.5} flex={1} minW={0}>
                    <Text
                      fontSize="xs"
                      fontWeight="medium"
                      color={isEmail ? emailIconColor : filenameColor}
                      isTruncated
                      width="100%"
                      lineHeight="1.3"
                    >
                      {isEmail ? (source.subject || "E-posta") : source.filename}
                    </Text>
                    {isEmail && source.sender && (
                      <Text
                        fontSize="2xs"
                        color={emailSecondaryText}
                        isTruncated
                        width="100%"
                        lineHeight="1.2"
                      >
                        {source.sender}
                        {source.date && (
                          <Text as="span" ml={1.5} opacity={0.7}>
                            • {formatEmailDate(source.date)}
                          </Text>
                        )}
                      </Text>
                    )}
                  </VStack>
                  {source.source_scope && (
                    <Badge
                      fontSize="9px"
                      px={1.5}
                      py={0.5}
                      borderRadius="sm"
                      bg={source.source_scope === "priority" ? "blue.500" : "gray.500"}
                      color="white"
                      fontWeight="medium"
                      ml={1}
                    >
                      {source.source_scope === "priority" ? "Öncelikli" : "Global"}
                    </Badge>
                  )}
                </HStack>
              </Box>
            </Tooltip>
          );
        })}
      </HStack>
    </Box>
  );
}

