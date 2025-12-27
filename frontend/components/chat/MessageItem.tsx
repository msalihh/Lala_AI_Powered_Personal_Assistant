"use client";

import React from "react";
import { Box, Avatar, useColorModeValue } from "@chakra-ui/react";
import ChatAvatar from "./Avatar";
import MessageActions from "./MessageActions";
import AttachmentList from "./AttachmentList";

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
  const userMessageBg = useColorModeValue("#1A7F37", "#3FB950");
  const userMessageText = useColorModeValue("#FFFFFF", "#FFFFFF");
  const assistantMessageBg = useColorModeValue("#F6F8FA", "#161B22");
  const assistantMessageText = useColorModeValue("#1F2328", "#E6EDF3");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  const accentPrimary = useColorModeValue("#1A7F37", "#3FB950");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const sourceBg = useColorModeValue("#F0F3F6", "#1C2128");
  const sourceTitleColor = useColorModeValue("#1F2328", "#E6EDF3");
  const sourceTextColor = useColorModeValue("#656D76", "#8B949E");
  const sourcePreviewColor = useColorModeValue("#8B949E", "#8B949E");
  const accentBorder = useColorModeValue("rgba(26, 127, 55, 0.3)", "rgba(63, 185, 80, 0.3)");
  const hintBg = useColorModeValue("#F0F3F6", "#1C2128");
  const hintTextColor = useColorModeValue("#656D76", "#8B949E");

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

  return (
    <Box className={`msgRow msgRow--${message.role}`}>
      {!isUser && (
        <Box className="msgAvatarArea">
          <ChatAvatar role="assistant" />
        </Box>
      )}
      
      <Box className="msgBodyArea">
        {/* Attachments for user messages */}
        {isUser && message.attachments && Array.isArray(message.attachments) && message.attachments.length > 0 && (
          <Box mb={2}>
            <AttachmentList attachments={message.attachments} />
          </Box>
        )}

        {/* Message Bubble */}
        <Box className={`msgBubble msgBubble--${message.role}`}>
          <Box className="msgContent markdown">
            {message.content ? messageContent : null}
            {isStreaming && (
              <Box
                className="msgTypingInline"
                display="inline-flex"
                alignItems="center"
                gap="8px"
                lineHeight="1.55"
                verticalAlign="baseline"
                ml={message.content ? 2 : 0}
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
                        opacity: 0.7,
                      },
                      "30%": {
                        transform: "translateY(-8px)",
                        opacity: 1,
                      },
                    },
                  }}
                />
                <Box
                  w="8px"
                  h="8px"
                  bg={accentPrimary}
                  borderRadius="full"
                  sx={{
                    animation: "typing 1.4s ease-in-out infinite 0.2s",
                  }}
                />
                <Box
                  w="8px"
                  h="8px"
                  bg={accentPrimary}
                  borderRadius="full"
                  sx={{
                    animation: "typing 1.4s ease-in-out infinite 0.4s",
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
          <Box mt={4}>
            {/* Sources accordion - keeping existing structure */}
            <Box>
              <Box mb={2}>
                <Box fontSize="sm" fontWeight="semibold" color={sourceTitleColor}>
                  Kaynaklar ({message.sources.length})
                </Box>
              </Box>
              <Box>
                {message.sources.map((source, idx) => (
                  <Box
                    key={idx}
                    p={2}
                    bg={sourceBg}
                    border="1px solid"
                    borderColor={accentBorder}
                    borderRadius="md"
                    fontSize="xs"
                    mb={2}
                  >
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Box fontWeight="semibold" color={accentPrimary} isTruncated>
                        {source.filename}
                      </Box>
                      <Box
                        bg={accentPrimary}
                        color="white"
                        px={1.5}
                        py={0.5}
                        borderRadius="sm"
                        fontSize="2xs"
                      >
                        {Math.round(source.score * 100)}%
                      </Box>
                    </Box>
                    <Box fontSize="2xs" color={sourceTextColor} mb={1}>
                      Bölüm {source.chunkIndex}
                    </Box>
                    <Box fontSize="2xs" color={sourcePreviewColor} noOfLines={2}>
                      {source.preview}
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>
          </Box>
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

