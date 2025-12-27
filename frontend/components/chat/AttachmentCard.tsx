"use client";

import React from "react";
import { Box, HStack, VStack, Text, useColorModeValue } from "@chakra-ui/react";
import { FaFilePdf, FaFileWord, FaFileAlt, FaEnvelope } from "react-icons/fa";

interface AttachmentCardProps {
  attachment: {
    id: string;
    filename: string;
    type: string;
    size?: number;
    documentId?: string;
  };
  onClick?: () => void;
}

/**
 * AttachmentCard component - Displays a file attachment card with icon, name, and type.
 * Used in chat message flow to show attached files.
 */
export default function AttachmentCard({ attachment, onClick }: AttachmentCardProps) {
  // Truncate filename intelligently
  const truncateFilename = (filename: string, maxLength: number = 30) => {
    if (filename.length <= maxLength) return filename;
    const ext = filename.split('.').pop() || '';
    const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));
    const maxNameLength = maxLength - ext.length - 4; // -4 for "..." and "."
    if (nameWithoutExt.length <= maxNameLength) return filename;
    return `${nameWithoutExt.substring(0, maxNameLength)}...${ext}`;
  };

  // Get file icon and background color based on type
  const getFileIconData = (type: string, name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (type.includes('pdf') || ext === 'pdf') {
      return { icon: <FaFilePdf size={16} color="white" />, bgColor: "#DC2626" };
    } else if (type.includes('word') || type.includes('docx') || ext === 'docx' || ext === 'doc') {
      return { icon: <FaFileWord size={16} color="white" />, bgColor: "#2B5CD4" };
    } else if (type.includes('text') || ext === 'txt') {
      return { icon: <FaFileAlt size={16} color="white" />, bgColor: "#6B7280" };
    } else if (type.includes('mail') || ext === 'eml') {
      return { icon: <FaEnvelope size={16} color="white" />, bgColor: "#F59E0B" };
    }
    return { icon: <FaFileAlt size={16} color="white" />, bgColor: "#9CA3AF" };
  };

  // Get file type label
  const getFileTypeLabel = (type: string, name: string) => {
    const ext = name.split('.').pop()?.toUpperCase();
    if (type.includes('pdf') || ext === 'PDF') return 'PDF';
    if (type.includes('word') || type.includes('docx') || ext === 'DOCX' || ext === 'DOC') return 'DOCX';
    if (type.includes('text') || ext === 'TXT') return 'TXT';
    if (type.includes('mail') || ext === 'EML') return 'Mail';
    return ext || 'Dosya';
  };

  const fileIconData = getFileIconData(attachment.type, attachment.filename);

  const truncatedFilename = truncateFilename(attachment.filename, 20);

  // Tema-aware renkler
  const cardBg = useColorModeValue("#F6F8FA", "#161B22");
  const cardBorder = useColorModeValue("#D1D9E0", "#30363D");
  const cardHoverBg = useColorModeValue("#F0F3F6", "#1C2128");
  const cardHoverBorder = useColorModeValue("#E7ECF0", "#22272E");
  const textPrimary = useColorModeValue("#1F2328", "#E6EDF3");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");

  return (
    <Box
      position="relative"
      display="flex"
      alignItems="center"
      gap={2}
      p={2}
      bg={cardBg}
      borderRadius="md"
      border="1px solid"
      borderColor={cardBorder}
      maxW="250px"
      cursor={onClick ? "pointer" : "default"}
      _hover={{
        borderColor: cardHoverBorder,
        bg: cardHoverBg,
        transform: "translateY(-4px) scale(1.02)",
        boxShadow: "0 8px 16px rgba(0, 0, 0, 0.15)",
      }}
      transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
      sx={{
        animation: "fadeInUp 0.4s ease-out",
        "&:hover": {
          animation: "pulseScale 0.6s ease-in-out",
        },
      }}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      } : undefined}
    >
      {/* File Icon */}
      <Box
        w="32px"
        h="32px"
        bg={fileIconData.bgColor}
        borderRadius="sm"
        display="flex"
        alignItems="center"
        justifyContent="center"
        flexShrink={0}
      >
        {fileIconData.icon}
      </Box>

      {/* File Info */}
      <VStack align="start" spacing={0} flex={1} minW={0}>
        <Text
          fontSize="2xs"
          fontWeight="medium"
          color={textPrimary}
          isTruncated
          width="100%"
          title={attachment.filename} // Show full name on hover
        >
          {truncatedFilename}
        </Text>
        <Text fontSize="2xs" color={textSecondary} lineHeight="1.2">
          {getFileTypeLabel(attachment.type, attachment.filename)}
        </Text>
      </VStack>
    </Box>
  );
}

