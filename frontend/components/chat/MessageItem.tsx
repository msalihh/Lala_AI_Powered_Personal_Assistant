"use client";

import React from "react";
import { Box, Avatar, useColorModeValue, Text, HStack } from "@chakra-ui/react";
import ChatAvatar from "./Avatar";
import MessageActions from "./MessageActions";
import AttachmentList from "./AttachmentList";
import SourcesPanel from "./SourcesPanel";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  status?: "cancelled" | "completed";
  sources?: Array<{
    documentId: string;
    filename: string;
    chunkIndex: number;
    preview: string;
    score: number;
  }>;
  used_documents?: boolean; // Whether documents were actually used (relevance gate passed)
  document_ids?: string[]; // For user messages: which documents were attached
  attachments?: Array<{
    id: string;
    filename: string;
    type: string;
    size: number;
    documentId?: string;
  }>;
  _isStreaming?: boolean;
}

interface MessageItemProps {
  message: Message;
  messageContent: React.ReactNode; // MessageContent component result
  username?: string;
}

export default function MessageItem({ message, messageContent, username }: MessageItemProps) {
  // Premium dark theme colors
  const userMessageBg = useColorModeValue("rgba(16, 185, 129, 0.15)", "rgba(16, 185, 129, 0.15)"); // accent-soft
  const userMessageText = useColorModeValue("#111827", "#E5E7EB");
  const assistantMessageBg = useColorModeValue("#F3F4F6", "#111827"); // bg-secondary
  const assistantMessageText = useColorModeValue("#111827", "#E5E7EB");
  const borderColor = useColorModeValue("#E5E7EB", "#1F2937"); // border-subtle
  const accentPrimary = useColorModeValue("#10B981", "#10B981"); // accent-primary
  const textSecondary = useColorModeValue("#6B7280", "#9CA3AF"); // text-secondary
  const sourceBg = useColorModeValue("#F9FAFB", "#1F2937"); // bg-tertiary
  const sourceTitleColor = useColorModeValue("#111827", "#E5E7EB");
  const sourceTextColor = useColorModeValue("#4B5563", "#9CA3AF");
  const sourcePreviewColor = useColorModeValue("#9CA3AF", "#6B7280");
  const accentBorder = useColorModeValue("rgba(16, 185, 129, 0.25)", "rgba(16, 185, 129, 0.3)");
  const hintBg = useColorModeValue("#F9FAFB", "#1F2937");
  const hintTextColor = useColorModeValue("#6B7280", "#9CA3AF");

  // Skip system messages
  if (message.role === "system") {
    return (
      <Box className="msgRow msgRow--system" textAlign="center" py={2}>
        <Box fontSize="sm" color={textSecondary} fontStyle="italic">
          {message.content}
        </Box>
      </Box>
    );
  }

  const isUser = message.role === "user";
  const isStreaming = message._isStreaming === true;
  const isLgsModule = (message as any).module === "lgs_karekok";

  return (
    <Box
      className={`msgRow msgRow--${message.role} ${isLgsModule ? 'msgRow--lgs' : ''}`}
      {... (isLgsModule && !isUser && {
        borderBottom: "1px solid",
        borderColor: borderColor,
        pb: 8,
        mb: 8,
      })}
    >
      {!isUser && (
        <Box className="msgAvatarArea">
          <ChatAvatar role="assistant" module={(message as any).module} />
        </Box>
      )}

      <Box className="msgBodyArea">
        {/* Attachments for user messages */}
        {isUser && message.attachments && Array.isArray(message.attachments) && message.attachments.length > 0 && (
          <Box mb={2}>
            <AttachmentList attachments={message.attachments} />
          </Box>
        )}

        {/* Message Bubble - LGS is borderless/backgroundless */}
        <Box
          className={`msgBubble msgBubble--${message.role} ${isLgsModule && !isUser ? 'msgBubble--lgs' : ''}`}
          {... (isLgsModule && !isUser && {
            bg: "transparent",
            boxShadow: "none",
            border: "none",
            maxW: "100%",
            px: 0,
          })}
        >
          <Box className="msgContent markdown">
            {message.content ? messageContent : null}
            {isStreaming && (
              <Box
                className="msgTypingInline"
                display="inline-flex"
                alignItems="center"
                gap="12px"
                lineHeight="1.55"
                verticalAlign="baseline"
                ml={message.content ? 2 : 0}
                mt={message.content ? 4 : 0}
              >
                <Box
                  w="8px"
                  h="8px"
                  bg={accentPrimary}
                  borderRadius="full"
                  sx={{
                    animation: "typing 1.4s ease-in-out infinite",
                    "@keyframes typing": {
                      "0%, 60%, 100%": {
                        transform: "translateY(0)",
                        opacity: 0.5,
                      },
                      "30%": {
                        transform: "translateY(-4px)",
                        opacity: 1,
                      },
                    },
                  }}
                />
              </Box>
            )}
          </Box>
        </Box>

        {/* Meta Bar (Actions + Time) - For both assistant and user */}
        <Box className={`msgMetaBar ${isUser ? 'msgMetaBar--user' : 'msgMetaBar--assistant'}`}>
          {isUser && <Box className="msgTimeOrSpacer" />}
          <MessageActions content={message.content} timestamp={message.timestamp} />
          {!isUser && <Box className="msgTimeOrSpacer" />}
        </Box>

        {/* Cancelled status */}
        {message.status === "cancelled" && (
          <Box mt={2} pt={2} borderTop="1px" borderColor={borderColor}>
            <Box fontSize="xs" color={textSecondary} fontStyle="italic">
              Durduruldu
            </Box>
          </Box>
        )}

        {/* Sources UI for assistant messages */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourcesPanel sources={message.sources} />
        )}

        {/* Hint for no sources */}
        {!isUser && message.content.includes("Bu dokümanlarda bulamadım") &&
          (!message.sources || message.sources.length === 0) && (
            <Box mt={3} p={2} bg={hintBg} borderRadius="md">
              <Box fontSize="xs" color={hintTextColor}>
                💡 İpucu: Doküman yükleyip indexlemeyi deneyin.
              </Box>
            </Box>
          )}
      </Box>

      {/* User Avatar - Right side */}
      {isUser && (
        <Box className="msgAvatarArea">
          <Avatar
            size="sm"
            name={username || "User"}
            bg={accentPrimary}
            color={userMessageText}
            fontWeight="600"
            w="36px"
            h="36px"
          />
        </Box>
      )}
    </Box>
  );
}

