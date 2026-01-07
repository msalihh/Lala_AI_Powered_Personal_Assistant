"use client";

import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import Image from "next/image";
import {
  Box,
  VStack,
  Input,
  Button,
  Text,
  useColorModeValue,
  HStack,
  Avatar,
  Spinner,
  IconButton,
  Tooltip,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Badge,
  Divider,
  Switch,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  useDisclosure,
  Checkbox,
  List,
  ListItem,
  Select,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
} from "@chakra-ui/react";
import { ArrowUpIcon, AddIcon, AttachmentIcon } from "@chakra-ui/icons";
import { FaFilePdf, FaFileWord, FaFileAlt, FaEnvelope, FaCopy, FaInfoCircle } from "react-icons/fa";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { apiFetch, uploadDocument, DocumentUploadResponse, listDocuments, DocumentListItem, getGenerationRun, cancelGenerationRun, GenerationRunStatus, sendChatMessage, SendChatMessageRequest, getChatMessages, createChat, getChat } from "@/lib/api";
import { useToast } from "@chakra-ui/react";
import { useSidebar } from "@/contexts/SidebarContext";
import { useChatStore, Run } from "@/contexts/ChatStoreContext";
import DocumentPicker from "@/components/DocumentPicker";
import LalaAILogo from "@/components/icons/LalaAILogo";
import AttachmentList from "@/components/chat/AttachmentList";
import MessageItem from "@/components/chat/MessageItem";
// KaTeX CSS is now imported globally in layout.tsx
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  status?: "cancelled" | "completed" | "streaming"; // ChatGPT style: cancelled messages stay visible
  sources?: SourceInfo[];
  used_documents?: boolean; // Whether documents were actually used (relevance gate passed)
  is_partial?: boolean; // Whether message is partial (streaming/cancelled)
  document_ids?: string[]; // For user messages: which documents were attached
  client_message_id?: string; // For duplicate detection
  attachments?: {
    id: string;
    filename: string;
    type: string;
    size: number;
    documentId?: string;
  }[];
  module?: string; // Track which module generated this message
}

interface SourceInfo {
  documentId: string;
  filename: string;
  chunkIndex: number;
  score: number;
  preview: string;
  source_type?: "document" | "email";
  sender?: string;
  subject?: string;
  date?: string;
}

interface ChatResponse {
  message: string;
  role: "assistant";
  chatId?: string; // Backend may return chatId for new chats
  sources?: SourceInfo[];
  used_documents?: boolean; // Whether documents were actually used (relevance gate passed)
  debug_info?: {
    incoming_document_ids?: string[];
    incoming_document_ids_count?: number;
  };
}

interface AttachedFile {
  id: string;
  name: string;
  type: string;
  size: number;
  file: File;
  documentId?: string;
  isUploading?: boolean;
  uploadProgress?: number; // 0-100 percentage
  abortController?: AbortController;
}

interface UploadedDocument {
  id: string;
  name: string;
  type: string;
  source: "upload" | "email";
  uploadedAt: string;
}

/**
 * Convert Unicode math symbols to LaTeX format.
 * FIXED: Uses single $ delimiters for inline math, not $$
 */
function convertUnicodeToLatex(content: string): string {
  let result = content;

  // Step 1: Protect existing LaTeX blocks ($$...$$ and $...$)
  const latexBlockRegex = /\$\$[\s\S]*?\$\$/g;
  const latexInlineRegex = /\$[^$\n]+\$/g;

  const protectedBlocks: string[] = [];
  const protectedInlines: string[] = [];

  result = result.replace(latexBlockRegex, (match) => {
    const placeholder = `__LATEX_BLOCK_${protectedBlocks.length}__`;
    protectedBlocks.push(match);
    return placeholder;
  });

  result = result.replace(latexInlineRegex, (match) => {
    const placeholder = `__LATEX_INLINE_${protectedInlines.length}__`;
    protectedInlines.push(match);
    return placeholder;
  });

  // Superscripts: x² → $x^{2}$, a³ → $a^{3}$
  // FIXED: Use function replacement to avoid $$ issues in regex
  const superscripts: Record<string, string> = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
  };
  for (const [unicode, num] of Object.entries(superscripts)) {
    const escapedUnicode = unicode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    result = result.replace(
      new RegExp(`([a-zA-Z0-9)]+)${escapedUnicode}`, 'g'),
      (match, p1) => `$${p1}^{${num}}$`
    );
  }

  // Subscripts: a₁ → $a_{1}$, x₂ → $x_{2}$
  const subscripts: Record<string, string> = {
    '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
    '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9'
  };
  for (const [unicode, num] of Object.entries(subscripts)) {
    const escapedUnicode = unicode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    result = result.replace(
      new RegExp(`([a-zA-Z0-9)]+)${escapedUnicode}`, 'g'),
      (match, p1) => `$${p1}_{${num}}$`
    );
  }

  // Math operators - use function replacement
  result = result.replace(/×/g, () => '$\\times$');
  result = result.replace(/÷/g, () => '$\\div$');
  result = result.replace(/±/g, () => '$\\pm$');
  result = result.replace(/≠/g, () => '$\\neq$');
  result = result.replace(/≤/g, () => '$\\leq$');
  result = result.replace(/≥/g, () => '$\\geq$');

  // Step 3: Restore protected LaTeX blocks
  for (let i = protectedBlocks.length - 1; i >= 0; i--) {
    result = result.split(`__LATEX_BLOCK_${i}__`).join(protectedBlocks[i]);
  }

  for (let i = protectedInlines.length - 1; i >= 0; i--) {
    result = result.split(`__LATEX_INLINE_${i}__`).join(protectedInlines[i]);
  }

  return result;
}


/**
 * Normalize math expressions in markdown content.
 * CRITICAL RULES:
 * 1. $$...$$ stays as $$...$$ (block math - NEVER convert to single $)
 * 2. $...$ stays as $...$ (inline math)
 * 3. \( ... \) → $...$ (ChatGPT-style inline math)
 * 4. Unicode → LaTeX conversion (Layer 2)
 * 5. Protect code blocks from math rendering
 */
function normalizeMath(content: string): string {
  // LAYER 2: Unicode→LaTeX conversion FIRST
  let result = convertUnicodeToLatex(content);

  // Step 1: Protect code blocks (fenced code blocks and inline code)
  const codeBlockRegex = /```[\s\S]*?```/g;
  const inlineCodeRegex = /`[^`\n]+`/g;

  const codeBlocks: string[] = [];
  const inlineCodes: string[] = [];

  result = result.replace(codeBlockRegex, (match) => {
    const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push(match);
    return placeholder;
  });

  result = result.replace(inlineCodeRegex, (match) => {
    const placeholder = `__INLINE_CODE_${inlineCodes.length}__`;
    inlineCodes.push(match);
    return placeholder;
  });

  // Step 2: Canonicalize math delimiters
  // CRITICAL: Handle $$...$$ FIRST to avoid conflicts with $...$

  // A) Block math: $$\n...\n$$ → keep as block (clean up whitespace)
  result = result.replace(/\$\$\s*([\s\S]*?)\s*\$\$/g, (match, inner) => {
    const cleaned = inner.trim();
    return `$$\n${cleaned}\n$$`;
  });

  // B) ChatGPT-style inline math: \( ... \) → $...$
  // B) ChatGPT-style math delimiters: \( ... \) → $...$ and \[ ... \] → $$...$$
  // This is the key conversion for ChatGPT-style output
  result = result.replace(/\\\(([^)]*?)\\\)/g, (match, inner) => {
    const cleaned = inner.trim();
    return `$${cleaned}$`;
  });

  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (match, inner) => {
    const cleaned = inner.trim();
    return `$$\n${cleaned}\n$$`;
  });

  // D) Heuristic: Catch [ ... ] if it contains typical LaTeX commands but missing backslash
  // This happens when LLM starts hallucinating delimiters
  result = result.replace(/(?<!\\)\[\s*([\s\S]*?\\(text|frac|sqrt|times|Delta|alpha|beta|sigma|cdot|deg|angle)[\s\S]*?)\s*\]/g, (match, inner) => {
    const cleaned = inner.trim();
    return `$${cleaned}$`;
  });

  // C) Inline math: $...$ (but NOT $$)
  // Use negative lookahead/lookbehind to avoid matching $$
  // Pattern: $ (not preceded/followed by $) ... $ (not preceded/followed by $)
  result = result.replace(/(?<!\$)\$(?!\$)([^\$\n]+?)(?<!\$)\$(?!\$)/g, (match, inner) => {
    const cleaned = inner.trim();
    return `$${cleaned}$`;
  });

  // Step 3: Restore code blocks
  codeBlocks.forEach((codeBlock, index) => {
    result = result.replace(`__CODE_BLOCK_${index}__`, codeBlock);
  });

  inlineCodes.forEach((inlineCode, index) => {
    result = result.replace(`__INLINE_CODE_${index}__`, inlineCode);
  });

  return result;
}


// MessageContent Component - Renders markdown with KaTeX math support (ChatGPT style)
// CHATGPT-LIKE: Real-time KaTeX rendering during streaming
function MessageContent({ content, isStreaming = false, isPartial = false, module }: { content: string; isStreaming?: boolean; isPartial?: boolean; module?: string }): React.JSX.Element {
  // displayContent holds what's currently rendered
  const [displayContent, setDisplayContent] = React.useState(content);
  const [contentVersion, setContentVersion] = React.useState(0);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Update displayContent when content prop changes
  React.useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    if (isStreaming || isPartial) {
      // During streaming, use a 80ms debounce for smoother chunks (ChatGPT style)
      debounceTimerRef.current = setTimeout(() => {
        if (content !== displayContent) {
          setDisplayContent(content);
          setContentVersion(prev => prev + 1);
        }
      }, 80);
    } else {
      // Completed message: update immediately
      setDisplayContent(content);
      setContentVersion(prev => prev + 1);

      // Force KaTeX render event
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent("forceKatexRender"));
      }, 200);
    }

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [content, isStreaming, isPartial, displayContent]);

  // Force re-render on custom events
  React.useEffect(() => {
    const handleForceRender = () => setContentVersion(p => p + 1);
    window.addEventListener("forceKatexRender", handleForceRender);
    return () => {
      window.removeEventListener("forceKatexRender", handleForceRender);
    };
  }, []);

  // ATOMIC MATH BALANCER: Prevents rendering incomplete LaTeX blocks
  // ================================================================
  const { safePart, riskyPart } = React.useMemo(() => {
    if (!displayContent) return { safePart: "", riskyPart: "" };

    let text = displayContent;

    // LATEX FORMAT CONVERTER: Convert \(...\) to $...$ and \[...\] to $$...$$
    // Backend sends \( and \) (single backslash in actual text)
    // remark-math expects $...$ for inline and $$...$$ for display math
    // CRITICAL FIX: Use captured groups, not manual slicing
    text = text.replace(/\\\(([^\)]*?)\\\)/g, (match, inner) => {
      return `$${inner.trim()}$`;
    });

    text = text.replace(/\\\[([^\]]*?)\\\]/g, (match, inner) => {
      return `$$\n${inner.trim()}\n$$`;
    });

    // 1. Block Math ($$) Check
    const blockMathSplit = text.split('$$');
    const isBlockMathIncomplete = blockMathSplit.length % 2 === 0;

    // 2. Inline Math ($) Check - count unescaped single $
    const singleDollarMatches = text.match(/(?<!\$)\$(?!\$)/g) || [];
    const isInlineMathIncomplete = singleDollarMatches.length % 2 !== 0;

    // If streaming and we have an open block, find the last safe index
    if ((isStreaming || isPartial) && (isBlockMathIncomplete || isInlineMathIncomplete)) {
      let lastSafeIndex = text.length;

      if (isBlockMathIncomplete) {
        const lastOpenIndex = text.lastIndexOf('$$');
        if (lastOpenIndex !== -1) {
          lastSafeIndex = Math.min(lastSafeIndex, lastOpenIndex);
        }
      }

      if (isInlineMathIncomplete) {
        // Find last unmatched single $
        const lastOpenIndex = text.lastIndexOf('$');
        if (lastOpenIndex !== -1) {
          lastSafeIndex = Math.min(lastSafeIndex, lastOpenIndex);
        }
      }

      return {
        safePart: text.substring(0, lastSafeIndex),
        riskyPart: text.substring(lastSafeIndex)
      };
    }

    // Fully balanced content
    return { safePart: text, riskyPart: "" };
  }, [displayContent, isStreaming, isPartial]);

  return (
    <Box
      className={`messageContent ${module === 'lgs_karekok' ? 'lgs-education-block' : ''}`}
      sx={{
        // Enable text selection for copying
        userSelect: 'text',
        WebkitUserSelect: 'text',
        cursor: 'text',
        ...(module === 'lgs_karekok' && {
          lineHeight: '1.8',
          fontSize: '16px',
          padding: '4px 8px',
        }),
        marginTop: '0 !important',
        paddingTop: '0 !important',
        overflow: 'visible',
        overflowY: 'visible',
        overflowX: 'visible',
        '& ::-webkit-scrollbar-button': {
          display: 'none !important',
          width: '0 !important',
          height: '0 !important',
        },
        '& .katex-display ::-webkit-scrollbar-button': {
          display: 'none !important',
          width: '0 !important',
          height: '0 !important',
        },
        '& .katex ::-webkit-scrollbar-button': {
          display: 'none !important',
          width: '0 !important',
          height: '0 !important',
        },
        '& p': {
          marginBottom: '1.15em',
          lineHeight: module === 'lgs_karekok' ? '1.8' : '1.6',
          whiteSpace: 'pre-wrap',
          wordWrap: 'normal',
          color: 'inherit',
        },
        '& p:first-of-type': {
          marginTop: 0,
        },
        '& p:last-child': {
          marginBottom: 0,
        },
        '& .katex-display': {
          display: 'block',
          margin: '1.25em 0 !important',
          overflowX: 'auto',
          overflowY: 'hidden !important',
          textAlign: 'center',
          padding: '1em 0.25em',
          whiteSpace: 'normal !important',
          wordBreak: 'normal !important',
          overflowWrap: 'normal !important',
          maxHeight: 'none !important',
          height: 'auto !important',
          '& ::-webkit-scrollbar-button': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
            background: 'transparent !important',
            border: 'none !important',
            padding: '0 !important',
            margin: '0 !important',
          },
        },
        '& .katex': {
          fontSize: '1.15em',
        },
        '& li': {
          marginBottom: '0.25em',
        },
      }}
    >
      <ReactMarkdown
        key={`markdown-${contentVersion}`}
        remarkPlugins={[remarkMath]}  // FIXED: removed invalid singleDollarTextMath option
        rehypePlugins={[[rehypeKatex, {
          strict: false,
          throwOnError: false,
          errorColor: '#FF0000',
          output: 'html',
          trust: true,
          macros: {},
        }]]}

        components={{
          h1: ({ children }) => (
            <Text as="h1" fontSize="2xl" fontWeight="bold" mb={3} mt={4} className="markdown-heading">
              {children}
            </Text>
          ),
          h2: ({ children }) => (
            <Text as="h2" fontSize="xl" fontWeight="bold" mb={2} mt={3} className="markdown-heading">
              {children}
            </Text>
          ),
          h3: ({ children }) => (
            <Text as="h3" fontSize="lg" fontWeight="semibold" mb={2} mt={2} className="markdown-heading">
              {children}
            </Text>
          ),
          ul: ({ children }) => (
            <ul style={{
              marginLeft: '24px',
              marginBottom: '12px',
              listStyleType: 'disc',
              userSelect: 'text',
              WebkitUserSelect: 'text',
              cursor: 'text'
            }}>
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol style={{
              marginLeft: '24px',
              marginBottom: '12px',
              listStyleType: 'decimal',
              userSelect: 'text',
              WebkitUserSelect: 'text',
              cursor: 'text'
            }}>
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li style={{
              marginBottom: '4px',
              lineHeight: '1.7',
              userSelect: 'text',
              WebkitUserSelect: 'text',
              cursor: 'text'
            }}>
              {children}
            </li>
          ),
          code: ({ className, children, ...props }: any) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code
                  style={{
                    backgroundColor: 'var(--chakra-colors-gray-700)',
                    padding: '2px 6px',
                    borderRadius: '3px',
                    fontSize: '0.9em',
                    fontFamily: 'monospace',
                    userSelect: 'text',
                    WebkitUserSelect: 'text',
                    cursor: 'text',
                    display: 'inline',
                    verticalAlign: 'baseline'
                  }}
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <Box
                as="pre"
                bg="gray.800"
                p={3}
                borderRadius="md"
                overflowX="auto"
                my={2}
                {...props}
              >
                <Text as="code" fontSize="sm" whiteSpace="pre" display="block">
                  {children}
                </Text>
              </Box>
            );
          },
        }}
      >
        {normalizeMath(safePart)}
      </ReactMarkdown>

      {/* RENDER RISKY CONTENT (PLAIN TEXT ONLY) */}
      {
        riskyPart && (
          <Text
            as="span"
            whiteSpace="pre-wrap"
            fontFamily="inherit"
            color="inherit"
            fontSize="inherit"
            lineHeight="inherit"
            display="inline"
          >
            {riskyPart}
          </Text>
        )
      }
    </Box >
  );
}

// FileChip Component - ChatGPT style with loading animation and progress
function FileChip({ file, onRemove, isUploading, uploadProgress }: {
  file: AttachedFile;
  onRemove: () => void;
  isUploading?: boolean;
  uploadProgress?: number;
}): React.JSX.Element {
  const progressValue = uploadProgress ?? 0;

  return (
    <Box
      display="inline-flex"
      alignItems="center"
      gap={2}
      px={3}
      py={1.5}
      bg="gray.600"
      borderRadius="full"
      maxW="220px"
      animation="slideDown 0.2s ease"
      position="relative"
      overflow="hidden"
      sx={{
        "@keyframes slideDown": {
          "0%": { opacity: 0, transform: "translateY(-5px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
      }}
    >
      {/* Progress bar background */}
      {isUploading && (
        <Box
          position="absolute"
          left={0}
          top={0}
          bottom={0}
          width={`${progressValue}%`}
          bg="green.500"
          opacity={0.3}
          transition="width 0.3s ease"
          borderRadius="full"
        />
      )}

      {isUploading ? (
        <Box
          position="relative"
          w="20px"
          h="20px"
          display="flex"
          alignItems="center"
          justifyContent="center"
          flexShrink={0}
        >
          {/* Circular progress */}
          <Box
            as="svg"
            w="20px"
            h="20px"
            viewBox="0 0 36 36"
            sx={{
              transform: "rotate(-90deg)",
            }}
          >
            {/* Background circle */}
            <circle
              cx="18"
              cy="18"
              r="14"
              fill="none"
              stroke="rgba(255,255,255,0.2)"
              strokeWidth="3"
            />
            {/* Progress circle */}
            <circle
              cx="18"
              cy="18"
              r="14"
              fill="none"
              stroke="#48BB78"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${progressValue * 0.88} 88`}
              style={{
                transition: "stroke-dasharray 0.3s ease",
              }}
            />
          </Box>
          {/* Percentage text in center */}
          <Text
            position="absolute"
            fontSize="6px"
            fontWeight="bold"
            color="white"
          >
            {progressValue < 100 ? `${progressValue}` : "✓"}
          </Text>
        </Box>
      ) : (
        <Box
          w="16px"
          h="16px"
          bg="green.500"
          borderRadius="sm"
          display="flex"
          alignItems="center"
          justifyContent="center"
          flexShrink={0}
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <polyline points="9 15 12 18 15 15" />
            <line x1="12" y1="12" x2="12" y2="18" />
          </svg>
        </Box>
      )}
      <VStack spacing={0} align="start" flex={1} minW={0}>
        <Text
          fontSize="xs"
          color="white"
          isTruncated
          width="100%"
        >
          {file.name}
        </Text>
        {isUploading && (
          <Text fontSize="9px" color="green.300">
            Yükleniyor... {progressValue}%
          </Text>
        )}
      </VStack>
      <IconButton
        icon={
          <Box
            as="span"
            display="inline-block"
            w="14px"
            h="14px"
            borderRadius="full"
            bg={isUploading ? "red.500" : "gray.500"}
            color="white"
            fontSize="10px"
            lineHeight="14px"
            textAlign="center"
          >
            {isUploading ? "⏹" : "×"}
          </Box>
        }
        aria-label={isUploading ? "Yüklemeyi iptal et" : "Dosyayı kaldır"}
        size="xs"
        variant="ghost"
        onClick={onRemove}
        minW="auto"
        h="auto"
        p={0}
        _hover={{ bg: isUploading ? "red.600" : "gray.500" }}
      />
    </Box>
  );
}

// DocumentChip Component - For selected documents from global pool
function DocumentChip({
  documentId,
  filename,
  onRemove
}: {
  documentId: string;
  filename: string;
  onRemove: () => void;
}) {
  return (
    <Box
      display="inline-flex"
      alignItems="center"
      gap={2}
      px={3}
      py={1.5}
      bg="green.500"
      borderRadius="full"
      maxW="250px"
      animation="slideDown 0.2s ease"
      sx={{
        "@keyframes slideDown": {
          "0%": { opacity: 0, transform: "translateY(-5px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
      }}
    >
      <Box
        w="16px"
        h="16px"
        bg="white"
        borderRadius="sm"
        display="flex"
        alignItems="center"
        justifyContent="center"
        flexShrink={0}
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="green.500" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      </Box>
      <Text
        fontSize="xs"
        color="white"
        isTruncated
        flex={1}
        minW={0}
      >
        {filename}
      </Text>
      <Badge
        fontSize="9px"
        px={1.5}
        py={0.5}
        borderRadius="full"
        bg="rgba(255,255,255,0.25)"
        color="white"
        fontWeight="bold"
        flexShrink={0}
      >
        Öncelikli
      </Badge>
      <IconButton
        icon={
          <Box
            as="span"
            display="inline-block"
            w="14px"
            h="14px"
            borderRadius="full"
            bg="rgba(255,255,255,0.3)"
            color="white"
            fontSize="10px"
            lineHeight="14px"
            textAlign="center"
          >
            ×
          </Box>
        }
        aria-label="Önceliği kaldır"
        size="xs"
        variant="ghost"
        onClick={onRemove}
        minW="auto"
        h="auto"
        p={0}
        _hover={{ bg: "rgba(255,255,255,0.4)" }}
        title="Önceliği kaldır"
      />
    </Box>
  );
}

function ChatPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  const { isOpen, toggle } = useSidebar();
  const chatStore = useChatStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [messageCursor, setMessageCursor] = useState<string | null>(null); // Cursor for pagination
  const [hasMoreMessages, setHasMoreMessages] = useState(false); // Whether there are more messages to load
  const [isLoadingOlderMessages, setIsLoadingOlderMessages] = useState(false); // Loading older messages
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [responseStyle, setResponseStyle] = useState<string>("auto"); // Response length style: "auto" | "short" | "medium" | "long" | "detailed"
  const [selectedModule, setSelectedModule] = useState<"none" | "lgs_karekok">("none"); // Prompt module: "none" | "lgs_karekok"
  // CRITICAL FIX: Explicit states for lifecycle management
  const [isStreaming, setIsStreaming] = useState(false);
  const [canSendMessage, setCanSendMessage] = useState(true);

  // CRITICAL FIX: Sync attachedFiles state to ref SYNCHRONOUSLY
  // Instead of useEffect (async), update ref directly in setAttachedFiles calls
  // This ensures ref is always in sync when handleSend is called
  useEffect(() => {
    attachedFilesRef.current = attachedFiles;
  }, [attachedFiles]);

  // MODULE CHANGE CLEANUP: Reset state when module changes
  // This ensures each module has independent state (Lala AI principle)
  useEffect(() => {
    // Only cleanup if there's an active run
    const hasActiveRun = Array.from(storeRef.current.runs.values()).some(
      run => run.status === "running"
    );

    if (hasActiveRun) {
      // Cancel all active runs
      Array.from(storeRef.current.runs.values()).forEach(run => {
        if (run.status === "running") {
          removeRun(run.runId);
        }
      });

      // Reset loading states
      setIsStreaming(false);
      setIsLoading(false);
      setCanSendMessage(true);

      // Force finalize if there's a current chat
      if (currentChatId) {
        finalizeRun(currentChatId, true);
      }
    }
  }, [selectedModule]); // Trigger cleanup when module changes

  // Sync module selection from Topbar (localStorage) - with real-time updates
  useEffect(() => {
    const updateModuleFromStorage = () => {
      if (typeof window !== 'undefined') {
        const savedModule = localStorage.getItem('selectedModule');
        if (savedModule === 'lgs_karekok') {
          setSelectedModule('lgs_karekok');
        } else {
          setSelectedModule('none');
        }
      }
    };

    // Initial load
    updateModuleFromStorage();

    // Listen for storage changes (when module changes in Topbar)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'selectedModule') {
        updateModuleFromStorage();
      }
    };

    // Listen for custom event (when module changes in same tab)
    const handleModuleChange = () => {
      updateModuleFromStorage();
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('moduleChanged', handleModuleChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('moduleChanged', handleModuleChange);
    };
  }, []); // Run once on mount

  // Helper: Update both state and ref synchronously
  const setAttachedFilesSync = (updater: (prev: AttachedFile[]) => AttachedFile[] | AttachedFile[]) => {
    setAttachedFiles((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      // CRITICAL: Update ref synchronously, not in useEffect
      attachedFilesRef.current = next;

      return next;
    });
  };
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [availableDocuments, setAvailableDocuments] = useState<DocumentListItem[]>([]);
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedDocument[]>([]); // Sohbet içindeki yüklenen dosyalar
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [lastDocumentIdsUsed, setLastDocumentIdsUsed] = useState<string[]>([]); // Debug için
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true); // Auto-scroll aktif - ChatGPT style
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const userScrollLockRef = useRef(false); // Hard lock ref - no re-renders

  // Debug flag for scroll logging
  const DEBUG_SCROLL = false;
  const [user, setUser] = useState<{ username: string } | null>(null);

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

  // ============================================
  // NORMALIZE EDİLMİŞ MESSAGE STORE (CHATGPT MODELİ)
  // ============================================
  interface NormalizedMessage {
    id: string;
    chatId: string;
    role: "user" | "assistant" | "system";
    content: string;
    createdAt: Date;
    status?: "streaming" | "completed" | "cancelled";
    sources?: SourceInfo[];
    client_message_id?: string;
    attachments?: {
      id: string;
      filename: string;
      type: string;
      size: number;
      documentId?: string;
    }[];
    module?: string;
  }

  interface Run {
    runId: string;
    requestId: string;
    chatId: string;
    assistantMessageId: string;
    status: "running" | "completed" | "cancelled" | "failed";
    startedAt: Date;
    lastSeq: number; // Stream event sequence number (duplicate chunk engelleme)
    abortController: AbortController;
    module?: string;
  }

  // Use global chat store context
  const {
    store: storeRef,
    getChatMessageIds,
    getMessage,
    getChatMessagesFromStore,
    addMessage,
    updateMessage,
    getRun,
    getRunByRequestId,
    addRun,
    updateRun,
    removeRun,
  } = chatStore;

  // Idempotency: Inflight requests Set (duplicate gönderim engelleme)
  const inflightRequestsRef = useRef<Set<string>>(new Set());
  // Send lock: prevents double-trigger (Enter + button / rapid clicks)
  const sendLockRef = useRef<boolean>(false);

  // Sync store to local state for active chat
  // CRITICAL: Wrap in useCallback to prevent unnecessary re-renders and allow use in dependency arrays
  // CRITICAL: Centralized function to finalize a run and reset ALL related state
  // This ensures isLoading, abortController, streamingContent are ALWAYS reset
  // THIS IS THE SINGLE SOURCE OF TRUTH FOR STREAM CLEANUP
  // THIS IS THE SINGLE SOURCE OF TRUTH FOR STREAM CLEANUP
  const finalizeInteraction = useCallback((chatId: string | null = null, forceReset: boolean = false) => {
    const targetChatId = chatId || currentChatId;

    // 1. Abort existing stream
    if (abortController && !abortController.signal.aborted) {
      abortController.abort();
    }

    // 2. Identify active runs
    const allRuns = Array.from(storeRef.current.runs.values());
    const chatRuns = allRuns.filter(r => r.chatId === targetChatId);
    const activeRun = chatRuns.find(r => r.status === "running");

    // 3. Conditional Reset
    if (!activeRun || forceReset) {
      // Clear all runs for this chat if force resetting
      if (forceReset) {
        chatRuns.forEach(run => {
          removeRun(run.runId);
        });
      }

      setIsLoading(false);
      setIsStreaming(false);
      setCanSendMessage(true);
      setAbortController(null);
      setStreamingContent("");
      return;
    }

    // 4. Sync to active run
    setAbortController(activeRun.abortController);
    setIsLoading(true);
    setIsStreaming(true);
    setCanSendMessage(false);
  }, [abortController, currentChatId, removeRun, storeRef]);

  // Aliasing finalizeRun for compatibility
  const finalizeRun = finalizeInteraction;

  const syncStoreToLocalState = useCallback((chatId: string | null) => {
    if (!chatId) {
      setMessages([]);
      setStreamingContent("");
      setIsLoading(false);
      setAbortController(null);
      return;
    }

    const messages = getChatMessagesFromStore(chatId);

    // CRITICAL: Find ONLY running runs for this chat
    // Completed/failed/cancelled runs should already be removed
    const activeRun = Array.from(storeRef.current.runs.values()).find(
      r => r.chatId === chatId && r.status === "running"
    );

    // Convert normalized messages to legacy format for compatibility
    const legacyMessages: (Message & { _isStreaming?: boolean })[] = messages.map(msg => {
      // Convert document_ids to attachments format for rendering
      const attachments = msg.document_ids && msg.document_ids.length > 0
        ? msg.document_ids.map((docId, idx) => {
          // TRY to find actual document info from availableDocuments or attachedFiles
          const existingInfo =
            availableDocuments.find(d => d.id === docId) ||
            attachedFiles.find(f => f.documentId === docId);

          return {
            id: `doc-${docId}-${idx}`,
            filename: (existingInfo && 'filename' in existingInfo ? existingInfo.filename : null) || (existingInfo && 'name' in existingInfo ? existingInfo.name : null) || `Doküman ${docId.substring(0, 4)}...`,
            type: (existingInfo && 'mime_type' in existingInfo ? existingInfo.mime_type : null) || (existingInfo && 'type' in existingInfo ? existingInfo.type : null) || "application/pdf",
            size: existingInfo?.size || 0,
            documentId: docId,
          };
        })
        : msg.attachments;

      return {
        id: msg.id,
        role: msg.role,
        content: msg.content,
        timestamp: msg.createdAt,
        status: msg.status === "cancelled" ? "cancelled" : msg.status === "completed" ? "completed" : undefined,
        sources: msg.sources,
        used_documents: msg.used_documents,
        client_message_id: msg.client_message_id,
        attachments: attachments,
        module: msg.module,
        // CRITICAL: Typing indicator shows ONLY when message is NOT completed
        // Message is streaming if status is "streaming" OR status is undefined (not yet completed)
        _isStreaming: msg.status !== "completed" && msg.status !== "cancelled", // Internal flag for typing indicator
      };
    });

    setMessages(legacyMessages);

    // CRITICAL: Save messages to localStorage for persistence across page reloads
    // Messages are stored independently of runs (runs are temporary, messages persist)
    // Only save completed messages (not streaming) to avoid saving incomplete data
    const completedMessages = legacyMessages.filter(msg =>
      msg.status !== "streaming" &&
      !msg._isStreaming &&
      msg.status !== "cancelled" &&
      msg.content &&
      msg.content.trim().length > 0
    );
    if (completedMessages.length > 0) {
      try {
        saveChatMessages(chatId, completedMessages);
      } catch (error) {
        console.error("Failed to save messages to localStorage:", error);
      }
    }

    // CRITICAL: Use finalizeRun to ensure consistent state reset
    // If no active run, finalizeRun will reset isLoading, abortController, streamingContent
    // If there's an active run, finalizeRun will set them correctly
    finalizeRun(chatId, !activeRun);
  }, [getChatMessagesFromStore, storeRef, finalizeRun]);

  // Legacy wrapper functions for backward compatibility (will be removed gradually)
  interface LegacyChatState {
    messages: Message[];
    streamingContent: string;
    isLoading: boolean;
    abortController: AbortController | null;
    requestId: string | null;
    isStreaming: boolean;
  }

  const getCurrentChatState = (chatId: string | null): LegacyChatState => {
    if (!chatId) {
      return {
        messages: [],
        streamingContent: "",
        isLoading: false,
        abortController: null,
        requestId: null,
        isStreaming: false,
      };
    }

    const messages = getChatMessagesFromStore(chatId);
    const activeRun = Array.from(storeRef.current.runs.values()).find(
      r => r.chatId === chatId && r.status === "running"
    );

    const legacyMessages: (Message & { _isStreaming?: boolean })[] = messages.map(msg => {
      // Convert document_ids to attachments format for rendering
      const attachments = msg.document_ids && msg.document_ids.length > 0
        ? msg.document_ids.map((docId, idx) => ({
          id: `doc-${docId}-${idx}`,
          filename: `Document ${docId.substring(0, 8)}...`, // Placeholder, will be replaced with actual filename
          type: "application/pdf", // Placeholder
          size: 0,
          documentId: docId,
        }))
        : msg.attachments;

      return {
        id: msg.id,
        role: msg.role,
        content: msg.content,
        timestamp: msg.createdAt,
        status: msg.status === "cancelled" ? "cancelled" : msg.status === "completed" ? "completed" : undefined,
        sources: msg.sources,
        used_documents: msg.used_documents,
        client_message_id: msg.client_message_id,
        attachments: attachments,
        // CRITICAL: Typing indicator shows ONLY when message is NOT completed
        // Message is streaming if status is "streaming" OR status is undefined (not yet completed)
        _isStreaming: msg.status !== "completed" && msg.status !== "cancelled", // Internal flag for typing indicator
      };
    });

    return {
      messages: legacyMessages,
      streamingContent: "", // REMOVED: No longer used, content comes from message itself
      isLoading: activeRun ? activeRun.status === "running" : false,
      abortController: activeRun?.abortController || null,
      requestId: activeRun?.requestId || null,
      isStreaming: activeRun?.status === "running" || false,
    };
  };

  const updateCurrentChatState = (chatId: string | null, updates: Partial<LegacyChatState>) => {
    if (!chatId) return;

    // For backward compatibility, sync updates to store if needed
    // Most updates should go through new store API, but this wrapper handles legacy code
    if (updates.messages !== undefined) {
      // Convert legacy messages to normalized and update store
      // This is a fallback for legacy code paths
      syncStoreToLocalState(chatId);
    }

    // Sync to local state if this is active chat
    if (chatId === currentChatId) {
      syncStoreToLocalState(chatId);
    }
  };

  // CRITICAL: Keep attachedFiles in ref for synchronous access in handleSend
  const attachedFilesRef = useRef<AttachedFile[]>([]); // Send lock: prevent duplicate sends

  // BACKGROUND PROCESSING: Checkpoint system for resume capability
  const checkpointRef = useRef<{
    requestId: string;
    chatId: string;
    message: string;
    sources?: SourceInfo[];
    timestamp: number;
  } | null>(null);
  const { isOpen: isDocModalOpen, onOpen: onDocModalOpen, onClose: onDocModalClose } = useDisclosure();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Profesyonel tema renk sistemi - Premium Dark UI
  // Zemin & Yüzeyler (tema-aware)
  const bgColor = useColorModeValue("#F9FAFB", "#0B0F14");
  const panelBg = useColorModeValue("#F3F4F6", "#111827");
  const innerBg = useColorModeValue("#E5E7EB", "#1F2937");
  const hoverBg = useColorModeValue("#F3F4F6", "#1F2937");
  const borderColor = useColorModeValue("#E5E7EB", "#1F2937");

  // Primary Accent (Emerald Green)
  const accentPrimary = useColorModeValue("#10B981", "#10B981");
  const accentHover = useColorModeValue("#34D399", "#34D399");
  const accentActive = useColorModeValue("#059669", "#059669");
  const accentSoft = useColorModeValue("rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.15)");
  const accentBorder = useColorModeValue("rgba(16, 185, 129, 0.25)", "rgba(16, 185, 129, 0.3)");

  // Secondary Accent (Purple)
  const accentSecondary = useColorModeValue("#8B5CF6", "#8B5CF6");
  const accentSecondarySoft = useColorModeValue("rgba(139, 92, 246, 0.1)", "rgba(139, 92, 246, 0.15)");

  // Mesaj renkleri (tema-aware)
  const messageBg = panelBg; // Asistan mesaj arka plan
  const userMessageBg = useColorModeValue("rgba(16, 185, 129, 0.15)", "rgba(16, 185, 129, 0.15)"); // accent-soft
  const userMessageText = useColorModeValue("#111827", "#E5E7EB");
  const assistantMessageText = useColorModeValue("#111827", "#E5E7EB");

  // Metin renkleri (tema-aware)
  const textPrimary = useColorModeValue("#111827", "#E5E7EB");
  const textSecondary = useColorModeValue("#6B7280", "#9CA3AF");
  const textPlaceholder = useColorModeValue("#9CA3AF", "#6B7280");
  const textDisabled = useColorModeValue("#D1D5DB", "#4B5563");
  // All color mode values - must be at top level to avoid hook order issues
  const attachmentBg = useColorModeValue("rgba(16, 185, 129, 0.05)", "rgba(16, 185, 129, 0.1)");
  const attachmentBorder = useColorModeValue("rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.2)");
  const sidebarToggleColor = useColorModeValue("gray.600", "gray.400");
  const sidebarToggleBg = useColorModeValue("white", "#1F2937");
  const sidebarToggleBorder = useColorModeValue("gray.200", "#374151");
  const sidebarToggleHoverBg = useColorModeValue("gray.50", "#374151");
  const sidebarToggleHoverColor = useColorModeValue("gray.900", "white");
  const sidebarToggleHoverBorder = useColorModeValue("gray.300", "#4B5563");
  const systemMessageColor = useColorModeValue("gray.500", "gray.400");
  // Source badge renkleri
  const sourceTitleColor = accentPrimary;
  const sourceBg = accentSoft;
  const sourceTextColor = textSecondary;
  const sourcePreviewColor = textPlaceholder;
  const hintBg = useColorModeValue("yellow.50", "yellow.900");
  const hintTextColor = useColorModeValue("yellow.800", "yellow.200");

  // Load chat settings from localStorage
  const loadChatSettings = (chatId: string) => {
    try {
      const stored = localStorage.getItem(`chat_settings_${chatId}`);
      if (stored) {
        const settings = JSON.parse(stored);
        setSelectedDocumentIds(settings.selectedDocumentIds || []);
        const loadedDocs = settings.uploadedDocuments || [];
        setUploadedDocuments(loadedDocs); // Yüklenen dosyaları yükle
      } else {
        setSelectedDocumentIds([]);
        setUploadedDocuments([]);
      }
    } catch (error) {
      console.error("Failed to load chat settings:", error);
      setSelectedDocumentIds([]);
      setUploadedDocuments([]);
    }
  };

  // Save chat settings to localStorage
  const saveChatSettings = (chatId: string) => {
    try {
      localStorage.setItem(`chat_settings_${chatId}`, JSON.stringify({
        selectedDocumentIds,
        uploadedDocuments, // Yüklenen dosyaları kaydet
      }));
    } catch (error) {
      console.error("Failed to save chat settings:", error);
    }
  };

  // Load messages from backend and populate store
  // CHAT SAVING ENABLED: Load messages from backend
  const loadChatMessages = async (chatId: string) => {
    if (!chatId || !isValidObjectId(chatId)) {
      return;
    }

    try {
      const response = await getChatMessages(chatId, 50);

      if (response.messages && response.messages.length > 0) {
        console.log(`[LOAD] Loading ${response.messages.length} messages from API for chat ${chatId}`);

        // Clear existing messages for this chat by removing all messages
        const existingMessageIds = getChatMessageIds(chatId);
        existingMessageIds.forEach((msgId) => {
          storeRef.current.messages.delete(msgId);
        });
        // Clear chat's messageIds
        const chat = storeRef.current.chats.get(chatId);
        if (chat) {
          chat.messageIds = [];
        }

        // Add messages to store
        response.messages.forEach((msg) => {
          // CRITICAL: Ensure content is never null/undefined
          const messageContent = msg.content || "";
          const isPartial = msg.is_partial === true;

          // CRITICAL: Messages are loaded independently of runs
          // If message is in DB, it's completed (even if is_partial flag exists)
          // Only mark as streaming if there's an active run for this message
          // For now, all messages from DB are treated as completed
          addMessage({
            id: msg.message_id,
            chatId: chatId,
            role: msg.role as "user" | "assistant",
            content: messageContent,
            sources: msg.sources || undefined,
            used_documents: msg.used_documents,
            is_partial: false,  // When loaded from DB, treat as complete (not partial)
            document_ids: msg.document_ids || undefined,  // Load document IDs from DB
            status: "completed",  // Always completed when loaded from backend (independent of runs)
            createdAt: new Date(msg.created_at),
            client_message_id: msg.client_message_id,
            module: (msg as any).module, // Track module from DB
          });
        });

        // Sync to local state
        syncStoreToLocalState(chatId);
        console.log(`[LOAD] Messages synced to local state for chat ${chatId}`);
      } else {
        console.log(`[LOAD] No messages found in API for chat ${chatId}`);
        // CRITICAL: Even if no messages from API, sync store to local state
        // This ensures any messages in store (from background polling) are shown
        syncStoreToLocalState(chatId);
      }

      // CRITICAL: Force KaTeX re-render after messages are loaded from backend
      // Messages loaded from DB are always completed, so KaTeX should render
      setTimeout(() => {
        // Trigger a window resize event to force KaTeX to re-render
        window.dispatchEvent(new Event('resize'));
        // Also force a re-render of all MessageContent components
        const event = new CustomEvent('forceKatexRender');
        window.dispatchEvent(event);
      }, 200);
    } catch (error: any) {
      // Handle 404 (chat not found) gracefully - might be archived or deleted
      if (error?.code === "CHAT_NOT_FOUND") {
        // Clear any existing messages for this chat
        const existingMessageIds = getChatMessageIds(chatId);
        existingMessageIds.forEach((msgId) => {
          storeRef.current.messages.delete(msgId);
        });
        const chat = storeRef.current.chats.get(chatId);
        if (chat) {
          chat.messageIds = [];
        }
        return;
      }
      console.error(`[LOAD] Error loading messages:`, error);
      // Don't show error toast for other errors - just log it
    }
  };

  // Sync store to local state when currentChatId changes
  useEffect(() => {
    if (currentChatId) {
      syncStoreToLocalState(currentChatId);
    }
  }, [currentChatId]);

  // CRITICAL: Monitor isLoading and canSendMessage states and ensure they're correct
  // This effect ensures isLoading and canSendMessage are always in sync with actual run status
  useEffect(() => {
    if (!currentChatId) {
      setIsLoading(false);
      setCanSendMessage(true);
      setAbortController(null);
      return;
    }

    const checkLoadingState = () => {
      // Get all runs for this chat
      const allRuns = Array.from(storeRef.current.runs.values());
      const activeRun = allRuns.find(
        r => r.chatId === currentChatId && r.status === "running"
      );

      // Clean up any non-running runs for this chat
      allRuns.forEach(run => {
        if (run.chatId === currentChatId && run.status !== "running") {
          removeRun(run.runId);
        }
      });

      // CRITICAL: Use finalizeRun to ensure consistent state reset
      // If no active run, finalizeRun will reset isLoading, abortController, streamingContent
      // If there's an active run, finalizeRun will set them correctly
      finalizeRun(currentChatId, !activeRun);
    };

    // CRITICAL: Listen for runRemoved events from ChatStoreContext
    // When a run is removed (completed/failed/cancelled), immediately finalize state
    const handleRunRemoved = (e: CustomEvent<{ runId: string; chatId: string }>) => {
      if (e.detail.chatId === currentChatId) {
        // Run was removed for this chat - immediately finalize state
        finalizeRun(currentChatId, true);
      }
    };

    // Check immediately
    checkLoadingState();

    // Check frequently to catch state changes quickly
    const checkInterval = setInterval(checkLoadingState, 150);

    // Listen for runRemoved events
    window.addEventListener("runRemoved", handleRunRemoved as EventListener);

    return () => {
      clearInterval(checkInterval);
      window.removeEventListener("runRemoved", handleRunRemoved as EventListener);
    };
  }, [currentChatId, removeRun, finalizeRun]);

  // BACKGROUND PROCESSING: Listen to store updates and sync active chat
  // This ensures that when global polling updates store, active chat UI is updated
  // CRITICAL: Continue syncing even when tab is hidden
  useEffect(() => {
    if (!currentChatId) return;

    // Poll store for updates (global polling updates store, we sync UI)
    // Continue syncing even when tab is hidden/background
    const syncInterval = setInterval(() => {
      syncStoreToLocalState(currentChatId);
    }, 300); // Sync every 300ms for faster UI updates

    // CRITICAL: When tab becomes visible, immediately sync to show any updates
    // that happened while tab was hidden
    const handleVisibilityChange = () => {
      if (!document.hidden && currentChatId) {
        // Tab became visible - sync immediately to show updates
        syncStoreToLocalState(currentChatId);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(syncInterval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [currentChatId, syncStoreToLocalState]);

  // CRITICAL: Check if chat module matches selected module when chat loads
  useEffect(() => {
    const checkChatModule = async () => {
      const urlChatId = params?.chatId as string | undefined;
      if (!urlChatId || !isValidObjectId(urlChatId)) {
        return;
      }

      try {
        // Get chat details to check module
        const chat = await getChat(urlChatId);
        const chatModule = chat.prompt_module || 'none';

        // Get current selected module
        const currentModule = typeof window !== 'undefined'
          ? (localStorage.getItem('selectedModule') === 'lgs_karekok' ? 'lgs_karekok' : 'none')
          : 'none';

        // If modules don't match, create new chat and navigate
        if (chatModule !== currentModule) {
          console.log(`[MODULE_MISMATCH] Chat module (${chatModule}) != selected module (${currentModule}), creating new chat`);
          try {
            const newChat = await createChat(undefined, currentModule as "none" | "lgs_karekok");
            router.push(`/chat/${newChat.id}`);
            window.dispatchEvent(new CustomEvent("newChat", { detail: { chatId: newChat.id } }));
          } catch (error) {
            console.error("Failed to create new chat:", error);
            // Fallback: navigate to /chat
            router.push("/chat");
          }
        }
      } catch (error) {
        // Chat not found or error - ignore, let normal flow handle it
        console.error("Error checking chat module:", error);
      }
    };

    checkChatModule();
  }, [params?.chatId, selectedModule, router]);

  // Sohbet değiştiğinde state'i yükle - eski sohbetin stream'ini durdurma
  useEffect(() => {
    const urlChatId = params?.chatId as string | undefined;

    if (urlChatId && isValidObjectId(urlChatId) && urlChatId !== currentChatId) {
      // Yeni sohbetin state'ini yükle
      setCurrentChatId(urlChatId);
      // CHAT SAVING ENABLED: Load messages from backend
      loadChatSettings(urlChatId);
      loadChatMessages(urlChatId);

      // CRITICAL: Sync store to local state after a short delay
      // This ensures any background streaming updates from other chats are visible
      // when user switches back to a chat that was streaming in background
      // Global polling in ChatStoreContext handles background updates automatically
      setTimeout(() => {
        syncStoreToLocalState(urlChatId);
      }, 100);

      // Save to localStorage
      try {
        localStorage.setItem("current_chat_id", urlChatId);
      } catch (error) {
        console.error("Failed to save current chat ID:", error);
      }

      // CRITICAL: Auto-focus input when new chat is opened
      // Use multiple attempts to ensure focus works
      const focusInput = () => {
        if (inputRef.current) {
          try {
            inputRef.current.focus();
            return document.activeElement === inputRef.current;
          } catch (error) {
            return false;
          }
        }
        return false;
      };

      // Try to focus after a short delay to ensure DOM is ready
      setTimeout(() => {
        if (!focusInput()) {
          setTimeout(() => {
            focusInput();
          }, 100);
        }
      }, 200);
    }
    // Note: currentChatId dependency removed to prevent double loading
    // URL change is the single source of truth for chat loading
  }, [params?.chatId]);

  // Save messages to localStorage
  const saveChatMessages = (chatId: string, msgs: Message[]) => {
    try {
      localStorage.setItem(`chat_messages_${chatId}`, JSON.stringify(msgs));
    } catch (error) {
      console.error("Failed to save chat messages:", error);
    }
  };

  // Lock body scroll - only message list scrolls (ChatGPT style)
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, []);

  // Load available documents for chip display
  useEffect(() => {
    const loadAvailableDocuments = async () => {
      try {
        const docs = await listDocuments(selectedModule);
        setAvailableDocuments(docs);
      } catch (error) {
        console.error("Failed to load available documents:", error);
        // Don't show toast, just log error
      }
    };
    loadAvailableDocuments();
  }, [selectedModule]);

  // Helper function to validate MongoDB ObjectId format
  const isValidObjectId = (id: string): boolean => {
    // MongoDB ObjectId is 24 hex characters
    return /^[0-9a-fA-F]{24}$/.test(id);
  };

  // Get chat ID from URL params
  const getChatId = (): string | null => {
    const chatId = params?.chatId as string | undefined;
    if (chatId && isValidObjectId(chatId)) {
      return chatId;
    }
    return null;
  };

  // Get or create chat ID (for file uploads)
  // CHAT SAVING ENABLED: Create chat if needed, or return existing chatId
  const getOrCreateChatId = async (): Promise<string | null> => {
    const existingChatId = getChatId();
    if (existingChatId) {
      return existingChatId;
    }
    // If no chatId, try to create a new chat
    try {
      const currentModule = typeof window !== 'undefined'
        ? (localStorage.getItem('selectedModule') === 'lgs_karekok' ? 'lgs_karekok' as const : 'none' as const)
        : 'none' as const;
      const newChat = await createChat(undefined, currentModule);
      const newChatId = newChat.id;
      // Update URL without navigation
      const newUrl = `/chat/${newChatId}`;
      window.history.replaceState({}, "", newUrl);
      setCurrentChatId(newChatId);
      return newChatId;
    } catch (error) {
      console.error("Failed to create chat for file upload:", error);
      // Return null if chat creation fails - document will be saved as independent
      return null;
    }
  };

  // Handle chatId from URL - don't create chat if not present
  // Chat will be created when first message is sent
  useEffect(() => {
    const chatId = getChatId();
    if (chatId && chatId !== currentChatId) {
      setCurrentChatId(chatId);
      // CHAT SAVING DISABLED: No need to load messages
      loadChatSettings(chatId);
    } else if (!chatId) {
      // No chatId - clear state, chat will be created on first message
      setCurrentChatId(null);
      setMessages([]);
    }
  }, [params?.chatId]);

  // BACKGROUND PROCESSING: Resume from checkpoint on page load
  useEffect(() => {
    const resumeFromCheckpoint = async () => {
      try {
        // Find all checkpoint keys
        const checkpointKeys: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && key.startsWith("chat_checkpoint_")) {
            checkpointKeys.push(key);
          }
        }

        // Resume from most recent checkpoint
        if (checkpointKeys.length > 0) {
          let latestCheckpoint: any = null;
          let latestTimestamp = 0;

          for (const key of checkpointKeys) {
            try {
              const checkpointData = localStorage.getItem(key);
              if (checkpointData) {
                const checkpoint = JSON.parse(checkpointData);
                if (checkpoint.timestamp > latestTimestamp) {
                  latestTimestamp = checkpoint.timestamp;
                  latestCheckpoint = checkpoint;
                }
              }
            } catch (error) {
            }
          }

          if (latestCheckpoint && latestCheckpoint.chatId) {

            // Load chat messages first
            // CHAT SAVING DISABLED: No need to load messages
            loadChatSettings(latestCheckpoint.chatId);
            setCurrentChatId(latestCheckpoint.chatId);

            // Update URL
            window.history.pushState({}, "", `/chat?chatId=${latestCheckpoint.chatId}`);

            // Resume streaming from checkpoint
            // Note: Response already received, just need to display it
            if (latestCheckpoint.sources !== undefined) {
              // Response was received, stream it
              const requestId = latestCheckpoint.requestId;
              // Update chat state with requestId
              updateCurrentChatState(latestCheckpoint.chatId, {
                requestId: requestId,
                isStreaming: true,
              });

              // Get full response from backend (idempotency cache)
              try {
                // Get current module from localStorage
                const currentModule = typeof window !== 'undefined'
                  ? (localStorage.getItem('selectedModule') === 'lgs_karekok' ? 'lgs_karekok' : 'none')
                  : 'none';

                const response = await apiFetch<ChatResponse>("/api/chat", {
                  method: "POST",
                  body: JSON.stringify({
                    message: latestCheckpoint.message,
                    chatId: latestCheckpoint.chatId,
                    client_message_id: requestId,
                    mode: "qa",
                    prompt_module: currentModule,  // Include module for checkpoint resume
                  }),
                });

                // REMOVED: Checkpoint resume no longer creates new messages
                // The message should already exist in store from original handleSend
                // Just update it if it exists
                const existingRun = getRunByRequestId(requestId);
                if (existingRun) {
                  // Use run's chatId for activeChatId parameter
                  await streamMessage(response.message, existingRun.runId, response.sources, undefined, existingRun.chatId, response.used_documents);
                }

                // Clear checkpoint after successful resume
                localStorage.removeItem(`chat_checkpoint_${requestId}`);
                checkpointRef.current = null;
              } catch (error) {
                console.error("[BACKGROUND] Failed to resume from checkpoint:", error);
                // Checkpoint might be stale, clear it
                localStorage.removeItem(`chat_checkpoint_${latestCheckpoint.requestId}`);
              }
            }
          }
        }
      } catch (error) {
        console.error("[BACKGROUND] Error resuming from checkpoint:", error);
      }
    };

    resumeFromCheckpoint();
  }, []); // Run once on mount

  // Event handlers for chat navigation
  const handleLoadChat = useCallback((e: CustomEvent) => {
    const { chatId } = e.detail;
    if (chatId && chatId !== currentChatId) {
      // CRITICAL: Do NOT abort ongoing streaming in old chat - let it continue
      // Just save the current chat state before switching
      if (currentChatId) {
        const currentState = getCurrentChatState(currentChatId);
        // Save current local state to chat-specific state before switching
        updateCurrentChatState(currentChatId, {
          messages,
          streamingContent,
          isLoading,
          abortController,
        });
        // Do NOT abort - let the stream continue in background
      }

      // Clear local state only (not chat-specific state)
      setStreamingContent("");
      setIsLoading(false);
      setAbortController(null);

      // Navigate to new chat
      router.push(`/chat/${chatId}`);
    }
  }, [currentChatId, messages, streamingContent, isLoading, abortController, router]);

  const handleNewChat = useCallback(async () => {
    // CRITICAL: Do NOT abort ongoing streaming in old chat - let it continue
    // Just save the current chat state before switching
    if (currentChatId) {
      const currentState = getCurrentChatState(currentChatId);
      // Save current local state to chat-specific state before switching
      updateCurrentChatState(currentChatId, {
        messages,
        streamingContent,
        isLoading,
        abortController,
      });
      // Do NOT abort - let the stream continue in background
      // Do NOT delete chat state - keep it for when user returns
    }

    // Clear local state only (not chat-specific state)
    setMessages([]);
    setInput("");
    setCurrentChatId(null);
    setStreamingContent(""); // Clear local streaming content
    setIsLoading(false);
    setAbortController(null); // Clear local abort controller

    // CRITICAL: Use sync updater to clear both state and ref
    setAttachedFilesSync(() => []);
    setSelectedDocumentIds([]);

    // Clear localStorage chat state
    try {
      localStorage.removeItem("current_chat_id");
      // Clear all chat-related localStorage items
      const keys = Object.keys(localStorage);
      keys.forEach(key => {
        if (key.startsWith("chat_messages_") || key.startsWith("chat_settings_") || key.startsWith("chat_checkpoint_")) {
          localStorage.removeItem(key);
        }
      });
    } catch (error) {
      console.error("Failed to clear chat state:", error);
    }

    // Clear URL chatId parameter - chat will be created when first message is sent
    router.push("/chat");
  }, [currentChatId, messages, streamingContent, isLoading, abortController, router, setAttachedFilesSync]);

  const handleChatDeleted = useCallback((e: CustomEvent) => {
    const deletedChatId = e.detail?.chatId;

    // If the deleted chat is the current chat, navigate to new chat page
    if (deletedChatId && deletedChatId === currentChatId) {
      router.push("/chat");
      return;
    }

    // Focus input after chat is deleted (if not navigating away)
    if (e.detail?.focusInput) {
      // Try to focus input with multiple attempts
      const tryFocusInput = () => {
        try {
          // Aggressively blur any active element first (including sidebar toggle)
          const activeElement = document.activeElement as HTMLElement | null;
          if (activeElement && activeElement !== document.body) {
            // Check if it's not the input before blurring
            if (activeElement !== inputRef.current) {
              activeElement.blur();
            }
          }
          // Also ensure body doesn't have focus
          if (document.activeElement === document.body) {
            (document.body as HTMLElement).blur();
          }
          // Focus input if it exists
          if (inputRef.current) {
            inputRef.current.focus();
            return true;
          }
        } catch (error) {
          // Ignore focus errors
        }
        return false;
      };

      // Try immediately
      if (!tryFocusInput()) {
        // If input not ready, try again after a short delay
        setTimeout(() => {
          if (!tryFocusInput()) {
            // Last attempt after longer delay
            setTimeout(tryFocusInput, 100);
          }
        }, 50);
      }
    }
  }, [currentChatId, router]);

  // Set up event listeners for chat navigation
  useEffect(() => {
    window.addEventListener("newChat", handleNewChat);
    window.addEventListener("loadChat", handleLoadChat as EventListener);
    window.addEventListener("chatDeleted", handleChatDeleted as EventListener);

    return () => {
      window.removeEventListener("newChat", handleNewChat);
      window.removeEventListener("loadChat", handleLoadChat as EventListener);
      window.removeEventListener("chatDeleted", handleChatDeleted as EventListener);
    };
  }, [handleNewChat, handleLoadChat, handleChatDeleted]);

  // Check for pending generation runs when chat loads
  useEffect(() => {
    const checkPendingRuns = async (chatId: string) => {
      try {
        // Check localStorage for pending run IDs for this chat
        const pendingRunKey = `pending_run_${chatId}`;
        const pendingRunId = localStorage.getItem(pendingRunKey);

        if (pendingRunId) {
          // CRITICAL FIX: Check run status immediately before starting polling
          // If run doesn't exist (404), clean up and don't start polling
          let pollInterval: NodeJS.Timeout | null = null;
          try {
            const initialStatus = await getGenerationRun(pendingRunId);

            // Run exists, start polling
            pollInterval = setInterval(async () => {
              try {
                const runStatus = await getGenerationRun(pendingRunId);

                // CRITICAL: Backend uses content_so_far for streaming content
                const content = runStatus.content_so_far || runStatus.completed_text || "";

                if (runStatus.status === "completed" && content) {
                  // Run completed - update existing message in store
                  if (pollInterval) clearInterval(pollInterval);
                  localStorage.removeItem(pendingRunKey);

                  // Update message with final content
                  const existingMessage = getMessage(runStatus.message_id || "");
                  if (existingMessage) {
                    updateMessage(runStatus.message_id || "", {
                      content: content,
                      status: "completed",
                      sources: runStatus.sources,
                      used_documents: runStatus.used_documents,
                      is_partial: false,
                    });

                    // CRITICAL: Remove the completed run from store
                    const runToRemove = Array.from(storeRef.current.runs.values()).find(
                      r => (r.runId === pendingRunId || r.requestId === pendingRunId) && r.chatId === chatId
                    );
                    if (runToRemove) {
                      removeRun(runToRemove.runId);
                      // CRITICAL: Force finalize run state IMMEDIATELY
                      finalizeRun(chatId, true);
                    }

                    // CRITICAL: Sync state after removing run
                    syncStoreToLocalState(chatId);
                  }

                } else if (runStatus.status === "failed" || runStatus.status === "cancelled") {
                  // Run failed or cancelled - keep partial content
                  if (pollInterval) clearInterval(pollInterval);
                  localStorage.removeItem(pendingRunKey);

                  // CRITICAL: Remove run from store
                  const runToRemove = Array.from(storeRef.current.runs.values()).find(
                    r => r.runId === pendingRunId || r.requestId === pendingRunId
                  );
                  if (runToRemove) {
                    removeRun(runToRemove.runId);
                    // CRITICAL: Force finalize run state IMMEDIATELY
                    finalizeRun(chatId, true);
                  }

                  // Update message with partial content if available
                  if (content) {
                    const existingMessage = getMessage(runStatus.message_id || "");
                    if (existingMessage) {
                      updateMessage(runStatus.message_id || "", {
                        content: content,
                        status: runStatus.status === "cancelled" ? "cancelled" : "completed",
                        is_partial: true,
                      });
                      syncStoreToLocalState(chatId);
                    }
                  }
                } else if (runStatus.status === "running" && content) {
                  // STREAMING: Update partial content during streaming
                  const existingMessage = getMessage(runStatus.message_id || "");
                  if (existingMessage) {
                    // Only update if content is longer (to avoid overwriting with older data)
                    if (content.length >= existingMessage.content.length) {
                      updateMessage(runStatus.message_id || "", {
                        content: content,
                        status: "streaming",
                        sources: runStatus.sources,
                        used_documents: runStatus.used_documents,
                        is_partial: true,
                      });
                      syncStoreToLocalState(chatId);
                    }
                  } else {
                    // Message doesn't exist - create placeholder
                    if (runStatus.message_id) {
                      addMessage({
                        id: runStatus.message_id,
                        chatId: chatId,
                        role: "assistant",
                        content: content,
                        createdAt: new Date(),
                        status: "streaming",
                        is_partial: true,
                        module: selectedModule, // Ensure module is set during polling
                      });
                      syncStoreToLocalState(chatId);
                    }
                  }
                }
                // If still running, continue polling
              } catch (error: any) {
                // If run not found, stop polling silently
                if (error && typeof error === "object" && "code" in error && error.code === "RUN_NOT_FOUND") {
                  if (pollInterval) clearInterval(pollInterval);
                  localStorage.removeItem(pendingRunKey);

                  // CRITICAL: Remove run from store and reset loading state
                  const runToRemove = Array.from(storeRef.current.runs.values()).find(
                    r => r.runId === pendingRunId || r.requestId === pendingRunId
                  );
                  if (runToRemove) {
                    removeRun(runToRemove.runId);
                    // CRITICAL: Force finalize run state IMMEDIATELY
                    finalizeRun(chatId, true);
                  }
                  syncStoreToLocalState(chatId);

                  return; // Silently exit, don't log
                }
                // Only log other errors
                console.error(`[BACKGROUND] Error polling run ${pendingRunId}:`, error);
              }
            }, 500); // Poll every 500ms for faster streaming updates
          } catch (error: any) {
            // Run not found (404) - clean up and don't start polling
            if (error && typeof error === "object" && "code" in error && error.code === "RUN_NOT_FOUND") {
              localStorage.removeItem(pendingRunKey);
              return; // Silently exit, don't log
            }
            // Other errors - log but don't start polling
            console.error(`[BACKGROUND] Error checking initial run status ${pendingRunId}:`, error);
          }

          // Cleanup on unmount
          return () => {
            if (pollInterval) clearInterval(pollInterval);
          };
        }
      } catch (error) {
        console.error("[BACKGROUND] Error checking pending runs:", error);
      }
    };

    if (currentChatId) {
      checkPendingRuns(currentChatId);
    }
  }, [currentChatId]);

  // Save messages whenever they change
  useEffect(() => {
    if (currentChatId && messages.length > 0) {
      saveChatMessages(currentChatId, messages);
    }
  }, [messages, currentChatId]);

  // Auto-focus input only when a new message is ADDED (not on every change)
  // This allows text selection in messages without losing focus
  const prevMessagesLengthRef = useRef(messages.length);
  useEffect(() => {
    // Only focus if new message was added and we're not loading/uploading
    if (
      !isLoading &&
      !isUploading &&
      messages.length > prevMessagesLengthRef.current &&
      inputRef.current
    ) {
      // Small delay to allow text selection to complete if in progress
      setTimeout(() => {
        if (document.activeElement?.tagName !== 'TEXTAREA' && inputRef.current) {
          inputRef.current.focus();
        }
      }, 100);
    }
    prevMessagesLengthRef.current = messages.length;
  }, [isLoading, isUploading, messages.length]);

  // STEP B: Single Scroll Gate Function
  // ====================================
  // ALL scroll operations must go through this function
  // This is the ONLY place where scrollIntoView is called
  function maybeScrollToBottom(reason: string, force: boolean = false, smooth: boolean = false) {
    const container = messagesContainerRef.current;
    const bottomElement = messagesEndRef.current;

    if (!container || !bottomElement) {
      return;
    }

    // Calculate distance from bottom
    const el = container;
    const dist = el.scrollHeight - (el.scrollTop + el.clientHeight);
    const scrollBehavior: ScrollBehavior = smooth ? "smooth" : "auto";

    if (force) {
      // Force scroll: reset lock and scroll
      userScrollLockRef.current = false;
      setAutoScrollEnabled(true);
      setIsUserScrolledUp(false);
      bottomElement.scrollIntoView({ behavior: scrollBehavior, block: "end" });
      return;
    }

    // CRITICAL: Check lock first - if locked, do nothing regardless of distance
    if (userScrollLockRef.current) {
      return;
    }

    // For streaming: if lock is false, always scroll (streaming should follow bottom)
    if (reason === "stream") {
      bottomElement.scrollIntoView({ behavior: scrollBehavior, block: "end" });
      return;
    }

    // For other reasons: only scroll if user is near bottom
    if (dist <= 20) {
      bottomElement.scrollIntoView({ behavior: scrollBehavior, block: "end" });
      return;
    }
  }

  // Smart Auto-Scroll Implementation
  // =================================
  // 1. Scroll listener: Track user scroll position
  // 2. Auto-scroll effect: Scroll to bottom when enabled and content changes
  // 3. handleSend: Force scroll to bottom and enable auto-scroll
  // 4. Scroll to bottom button: Re-enable auto-scroll

  // Scroll detection: Track if user is at bottom (80px threshold to disable, 20px to enable)
  // STEP A: Find the real scroll container
  // STEP C: Simple lock rules - distance + wheel up
  useEffect(() => {
    // Wait for container to be ready
    const checkContainer = () => {
      const container = messagesContainerRef.current;
      if (!container) {
        setTimeout(checkContainer, 100);
        return;
      }


      cleanup = setupScrollListeners(container);
    };

    let cleanup: (() => void) | null = null;

    checkContainer();

    function setupScrollListeners(container: HTMLElement) {
      // STEP C: Lock rules - simple distance + wheel up
      const handleScrollContainer = async (e: Event) => {
        const el = container;
        const dist = el.scrollHeight - (el.scrollTop + el.clientHeight);
        const scrollTop = el.scrollTop;

        // CHAT SAVING DISABLED: No pagination needed (messages only in local state)
        // Cursor pagination disabled - messages are not saved to database

        // Lock rules: dist > 80 => lock true, dist <= 20 => lock false
        if (dist > 80) {
          userScrollLockRef.current = true;
          setAutoScrollEnabled(false);
          setIsUserScrolledUp(true);
        } else if (dist <= 20) {
          userScrollLockRef.current = false;
          setAutoScrollEnabled(true);
          setIsUserScrolledUp(false);
        }
      };

      // Wheel event handler - lock on upward scroll
      const handleWheel = (e: WheelEvent) => {
        const target = e.target as HTMLElement;
        const isWithinContainer = container.contains(target);

        if (!isWithinContainer) return;

        // Lock rule - wheel up (deltaY < 0) => lock true
        if (e.deltaY < 0) {
          userScrollLockRef.current = true;
          setAutoScrollEnabled(false);
          setIsUserScrolledUp(true);
        }
      };

      // Add listeners to container
      container.addEventListener('scroll', handleScrollContainer, { passive: true });
      container.addEventListener('wheel', handleWheel, { passive: true, capture: true });

      // Initial check
      const { scrollTop, scrollHeight, clientHeight } = container;
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
      const initialIsAtBottom = distanceFromBottom <= 20;
      userScrollLockRef.current = !initialIsAtBottom;
      setAutoScrollEnabled(initialIsAtBottom);
      setIsUserScrolledUp(!initialIsAtBottom);

      // Return cleanup function
      return () => {
        container.removeEventListener('scroll', handleScrollContainer);
        container.removeEventListener('wheel', handleWheel);
      };
    }

    // Return cleanup from useEffect
    return () => {
      if (cleanup) cleanup();
    };
  }, []); // No dependencies - only run once on mount

  // Autoscroll effect - only scroll if lock is false
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (!userScrollLockRef.current) {
        maybeScrollToBottom("stream");
      }
    }, 0);

    return () => clearTimeout(timeoutId);
  }, [messages, streamingContent]);

  /**
   * ChatGPT tarzı sohbet başlığı oluşturma
   * 
   * Strateji:
   * 1. İlk mesajdan ana konu çıkar (%60-70 ağırlık)
   * 2. Niyet çıkarımı (öğrenme, kod, hata, tasarım)
   * 3. Tekrar eden anahtar kelimeler
   * 4. Teknik detayları filtrele
   * 5. Başlık sonradan değişmez (sadece ilk mesajda oluşturulur)
   */
  const generateChatTitle = (firstMessage: string, firstFewMessages?: Message[]): string => {
    if (!firstMessage || firstMessage.trim().length === 0) {
      return "Yeni Sohbet";
    }

    const message = firstMessage.trim();

    // 1. İlk mesajdan ana konuyu çıkar (%60-70 ağırlık)
    // Kısa ve öz mesajlar direkt başlık olabilir
    if (message.length <= 40 && !message.includes("?") && !message.includes("hata") && !message.includes("error")) {
      // Basit, direkt başlık olabilecek mesajlar
      return message.length > 30 ? message.substring(0, 30) + "..." : message;
    }

    // 2. Niyet çıkarımı ve ana konu tespiti
    const intentKeywords = {
      learning: ["öğren", "anlamak", "nasıl", "nedir", "ne demek", "açıkla", "öğret"],
      coding: ["kod", "yaz", "oluştur", "implement", "function", "class", "component"],
      debugging: ["hata", "error", "bug", "çalışmıyor", "sorun", "problem", "neden"],
      design: ["tasarım", "design", "ui", "renk", "stil", "görünüm", "arayüz"],
      project: ["proje", "project", "bitirme", "bitirme projesi", "uygulama", "sistem"],
      analysis: ["analiz", "incele", "değerlendir", "karşılaştır"],
    };

    // Niyet tespiti
    let detectedIntent: string | null = null;
    const lowerMessage = message.toLowerCase();

    for (const [intent, keywords] of Object.entries(intentKeywords)) {
      if (keywords.some(keyword => lowerMessage.includes(keyword))) {
        detectedIntent = intent;
        break;
      }
    }

    // 3. Anahtar kelime çıkarımı (teknik detayları filtrele)
    const stopWords = new Set([
      "bir", "bu", "şu", "o", "ve", "ile", "için", "gibi", "kadar", "daha", "çok", "az",
      "var", "yok", "olmak", "etmek", "yapmak", "gelmek", "gitmek",
      "useEffect", "useState", "line", "error", "bug", "hata", "satır", "kod",
      "şimdi", "şu an", "şu anda", "bugün", "dün", "yarın"
    ]);

    // Cümleleri ayır ve önemli kelimeleri çıkar
    const sentences = message.split(/[.!?。，、\n]/).filter(s => s.trim().length > 0);
    const importantWords: string[] = [];

    sentences.forEach(sentence => {
      // Türkçe ve İngilizce kelimeleri ayır
      const words = sentence
        .toLowerCase()
        .replace(/[^\w\sğüşıöçĞÜŞİÖÇ]/g, " ")
        .split(/\s+/)
        .filter(word =>
          word.length > 2 &&
          !stopWords.has(word) &&
          !/^\d+$/.test(word) && // Sayıları filtrele
          !word.includes("line") && // Line 42 gibi teknik detayları filtrele
          !word.includes("error") &&
          !word.includes("bug")
        );

      importantWords.push(...words);
    });

    // 4. Başlık oluşturma stratejisi
    let title = "";

    // Strateji 1: Proje/konu bazlı başlıklar
    if (detectedIntent === "project" || lowerMessage.includes("proje") || lowerMessage.includes("project")) {
      const projectMatch = message.match(/(?:proje|project)[\s:–-]*(.+?)(?:[\s\.\?]|$)/i);
      if (projectMatch && projectMatch[1]) {
        title = projectMatch[1].trim();
        if (title.length > 50) {
          title = title.substring(0, 50) + "...";
        }
        return title;
      }
    }

    // Strateji 2: "X nedir" / "X ne demek" formatı
    const whatIsMatch = message.match(/(.+?)\s+(?:nedir|ne demek|what is|what does)/i);
    if (whatIsMatch && whatIsMatch[1]) {
      title = whatIsMatch[1].trim();
      if (title.length > 40) {
        title = title.substring(0, 40) + "...";
      }
      return title;
    }

    // Strateji 2.5: "X örnek çöz" / "X örnek ver" formatı
    const exampleMatch = message.match(/(.+?)\s+(?:örnek|example|örnek çöz|örnek ver)/i);
    if (exampleMatch && exampleMatch[1]) {
      title = exampleMatch[1].trim();
      // "1 tane" gibi sayıları temizle
      title = title.replace(/\d+\s*(tane|adet|piece)/gi, "").trim();
      if (title.length > 40) {
        title = title.substring(0, 40) + "...";
      }
      return title;
    }

    // Strateji 3: "X yapmak istiyorum" / "X tasarlıyorum" formatı
    const doingMatch = message.match(/(.+?)\s+(?:yapmak|tasarlıyorum|oluşturuyorum|geliştiriyorum|yapıyorum)/i);
    if (doingMatch && doingMatch[1]) {
      title = doingMatch[1].trim();
      if (title.length > 40) {
        title = title.substring(0, 40) + "...";
      }
      return title;
    }

    // Strateji 4: İlk cümleden ana konuyu çıkar
    if (sentences.length > 0) {
      const firstSentence = sentences[0].trim();

      // Uzun cümleleri kısalt
      if (firstSentence.length > 50) {
        // Önemli kelimeleri bul ve başlık oluştur
        const keyWords = importantWords.slice(0, 4).filter(w => w.length > 3);
        if (keyWords.length > 0) {
          title = keyWords
            .map(w => w.charAt(0).toUpperCase() + w.slice(1))
            .join(" ");

          // Niyet ekle
          if (detectedIntent === "learning") {
            title = title + " Öğrenme";
          } else if (detectedIntent === "coding") {
            title = title + " Geliştirme";
          } else if (detectedIntent === "debugging") {
            title = title + " Sorun Çözme";
          } else if (detectedIntent === "design") {
            title = title + " Tasarım";
          }

          if (title.length > 50) {
            title = title.substring(0, 50) + "...";
          }
          return title;
        }
      } else {
        // Kısa cümleler direkt başlık olabilir
        title = firstSentence;
        if (title.length > 50) {
          title = title.substring(0, 50) + "...";
        }
        return title;
      }
    }

    // Strateji 5: Fallback - İlk 40 karakter
    title = message.substring(0, 40).trim();
    if (message.length > 40) {
      title += "...";
    }

    return title;
  };

  // Save chat to history - ChatGPT style: title is set only once from first message
  // NOTE: Title generation is now handled by backend automatically, this function is not used
  // const saveChatToHistory = async (chatId: string, title: string) => {
  //   // Backend automatically generates title after first message
  //   // No need to manually update title
  // };

  // Clear composer state (attachments, selected docs, input)
  const clearComposer = () => {
    // CRITICAL: Use sync updater to clear both state and ref
    setAttachedFilesSync(() => []);
    setSelectedDocumentIds([]);
    setInput("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }

    // CRITICAL: Auto-focus input after clearing (for seamless typing experience)
    // Use multiple attempts to ensure focus works reliably
    const focusInput = () => {
      if (inputRef.current) {
        try {
          inputRef.current.focus();
          return document.activeElement === inputRef.current;
        } catch (error) {
          return false;
        }
      }
      return false;
    };

    // Try immediately, then retry if needed
    setTimeout(() => {
      if (!focusInput()) {
        setTimeout(() => {
          focusInput();
        }, 100);
      }
    }, 50);
  };

  // Stream message with throttle and duplicate chunk prevention
  // NEW ARCHITECTURE: Uses runId to update store, seq for duplicate prevention
  const streamMessage = async (
    fullMessage: string,
    runId: string,
    sources?: SourceInfo[],
    abortSignal?: AbortSignal,
    activeChatId?: string,  // Optional: explicitly pass chatId to ensure UI updates
    used_documents?: boolean  // Whether documents were actually used (relevance gate passed)
  ) => {
    // Get run and assistant message
    const run = getRun(runId);
    if (!run) {
      return;
    }

    if (run.status !== "running") {
      // Still update message even if run is not running
    }

    const assistantMessage = getMessage(run.assistantMessageId);
    if (!assistantMessage) {
      return;
    }

    // CRITICAL: Check if tab is hidden - if so, show message immediately without animation
    const isTabVisible = typeof document !== 'undefined' && !document.hidden;

    // If tab is hidden, show full message immediately and return
    if (!isTabVisible) {
      updateMessage(run.assistantMessageId, {
        content: fullMessage,
        status: "streaming",
        sources: sources,
        used_documents: used_documents,
      });
      updateRun(runId, { lastSeq: fullMessage.length });
      const chatIdToCheck = activeChatId || currentChatId;
      if (run.chatId === chatIdToCheck) {
        syncStoreToLocalState(run.chatId);
      }
      return;
    }

    let accumulatedText = "";
    let currentSeq = 0;
    const CHAR_DELAY_MS = 15; // Delay between batches (15ms = slower, allows KaTeX to render)
    const BATCH_SIZE = 5; // Show 5 characters at a time for slower, smoother streaming with KaTeX

    // Start from beginning - message is already visible, we're just animating it
    // Stream in batches for faster visual effect
    // CRITICAL: Continue streaming even when tab is hidden (but check visibility in loop)
    for (let i = 0; i < fullMessage.length; i += BATCH_SIZE) {
      // Check if tab became hidden during streaming - if so, show rest immediately
      const stillVisible = typeof document !== 'undefined' && !document.hidden;
      if (!stillVisible && i < fullMessage.length - BATCH_SIZE) {
        // Tab became hidden, show remaining message immediately
        accumulatedText = fullMessage;
        currentSeq = fullMessage.length;
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "streaming",
          sources: sources,
          used_documents: used_documents,
        });
        updateRun(runId, { lastSeq: currentSeq });
        const chatIdToCheck = activeChatId || currentChatId;
        if (run.chatId === chatIdToCheck) {
          syncStoreToLocalState(run.chatId);
        }
        return;
      }
      // Check if run is still active
      const currentRun = getRun(runId);
      if (!currentRun) {
        return;
      }

      if (currentRun.status !== "running") {
        // Run was cancelled or completed
        accumulatedText = fullMessage.substring(0, i);
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "cancelled",
          sources: sources,
          used_documents: used_documents,
        });
        removeRun(runId);
        // CRITICAL: Finalize interaction when cancelled
        finalizeInteraction();
        syncStoreToLocalState(run.chatId);
        return;
      }

      // Check if aborted (only abort if user explicitly cancelled, not on tab switch)
      if (abortSignal?.aborted) {
        accumulatedText = fullMessage.substring(0, i);
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "cancelled",
          sources: sources,
          used_documents: used_documents,
        });
        removeRun(runId);
        // CRITICAL: Finalize interaction when aborted
        finalizeInteraction();
        syncStoreToLocalState(run.chatId);
        return;
      }

      // Show batch of characters at a time for faster streaming
      const endIndex = Math.min(i + BATCH_SIZE, fullMessage.length);
      accumulatedText = fullMessage.substring(0, endIndex);
      currentSeq = endIndex;

      // Update message content and run seq immediately (no throttle for better UX)
      if (currentSeq > currentRun.lastSeq) {
        if (abortSignal?.aborted) {
          accumulatedText = fullMessage.substring(0, i);
          updateMessage(run.assistantMessageId, {
            content: accumulatedText,
            status: "cancelled",
            sources: sources,
            used_documents: used_documents,
          });
          removeRun(runId);
          // CRITICAL: Finalize run state when aborted
          finalizeRun(run.chatId, true);
          syncStoreToLocalState(run.chatId);
          return;
        }

        // CRITICAL: Update message content during streaming (plain text only, no KaTeX)
        // Message status remains "streaming" until stream fully completes
        // DO NOT finalize or render KaTeX until streaming is 100% complete
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "streaming", // Keep as streaming until fully complete
        });
        updateRun(runId, { lastSeq: currentSeq });

        // CRITICAL: Sync to local state immediately for every character update
        // Use activeChatId if provided (for new chats), otherwise use currentChatId
        const chatIdToCheck = activeChatId || currentChatId;
        if (run.chatId === chatIdToCheck) {
          // Sync immediately for smooth UI updates (plain text only during streaming)
          // DO NOT render KaTeX during streaming - only after completion
          syncStoreToLocalState(run.chatId);
        }
        // Note: If chatId !== chatIdToCheck, streaming continues in background
        // Store is updated, and will be synced when user returns to this chat
      }

      // Wait before showing next character (smooth typing effect)
      // CRITICAL: Check visibility again - if tab became hidden, skip remaining animation
      const stillVisibleInLoop = typeof document !== 'undefined' && !document.hidden;
      if (!stillVisibleInLoop) {
        // Tab became hidden during loop - show rest immediately
        accumulatedText = fullMessage;
        currentSeq = fullMessage.length;
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "streaming",
          sources: sources,
          used_documents: used_documents,
        });
        updateRun(runId, { lastSeq: currentSeq });
        const chatIdToCheck = activeChatId || currentChatId;
        if (run.chatId === chatIdToCheck) {
          syncStoreToLocalState(run.chatId);
        }
        return;
      }

      // Use setTimeout - browsers may throttle in background but it still works
      await new Promise((resolve) => setTimeout(resolve, CHAR_DELAY_MS));
    }

    // CRITICAL: Ensure full message is displayed even if loop ended early
    if (accumulatedText.length < fullMessage.length) {
      accumulatedText = fullMessage;
      currentSeq = fullMessage.length;
      updateMessage(run.assistantMessageId, {
        content: accumulatedText,
        status: "streaming",
        sources: sources,
        used_documents: used_documents,
      });
      updateRun(runId, { lastSeq: currentSeq });
      const chatIdToCheck = activeChatId || currentChatId;
      if (run.chatId === chatIdToCheck) {
        syncStoreToLocalState(run.chatId);
      }
    }

    // Final check for abort
    if (abortSignal?.aborted) {
      updateMessage(run.assistantMessageId, {
        content: fullMessage,
        status: "cancelled",
        sources: sources,
        used_documents: used_documents,
      });
      removeRun(runId);
      // CRITICAL: Finalize run state when aborted
      finalizeRun(run.chatId, true);
      syncStoreToLocalState(run.chatId);
      return;
    }

    // CRITICAL: Streaming lifecycle - stream has fully completed
    // IMPORTANT: Backend has already saved message to DB before run is marked as completed
    // So we can safely mark message as completed here

    // Step 1: Update message to completed status (this stops typing indicator and triggers KaTeX render)
    updateMessage(run.assistantMessageId, {
      content: fullMessage,
      status: "completed", // CRITICAL: Status change from "streaming" to "completed" stops typing indicator and triggers KaTeX render
      sources: sources,
      used_documents: used_documents,
    });

    // Step 2: Remove run from store (runs are temporary, messages persist independently)
    removeRun(runId);

    // Step 3: Finalize interaction to ensure UI state is reset (isLoading, isStreaming, etc.)
    finalizeInteraction(run.chatId, false);

    // Step 4: Sync to local state and save to localStorage (message persists independently of run)
    syncStoreToLocalState(run.chatId);

    // Step 5: Force KaTeX render after message is completed (not during streaming)
    // This is the ONLY place KaTeX should be rendered
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("forceKatexRender"));
    }, 100);

    // Cleanup: Remove from inflight requests
    inflightRequestsRef.current.delete(run.requestId);
  };

  const handleSend = async (e: React.FormEvent | React.KeyboardEvent) => {
    // Her zaman prevent default ve stop propagation
    if (e && 'preventDefault' in e) {
      e.preventDefault();
    }
    if (e && 'stopPropagation' in e) {
      e.stopPropagation();
    }

    // CRITICAL: Double-trigger guard - check BEFORE any async operations
    if (sendLockRef.current) {
      return;
    }

    // Set lock IMMEDIATELY to prevent double-invoke
    sendLockRef.current = true;

    let requestId: string | null = null;
    let runId: string | null = null;
    let wasAborted = false;
    const abortController = new AbortController();
    let finalChatId: string = "";  // Declare outside try block
    let skipFinalize = false; // CRITICAL: Flag to skip cleanup if streaming continues

    setIsLoading(true);
    setIsStreaming(true);
    setCanSendMessage(false);

    try {
      // Get current chatId
      let chatId = currentChatId || getChatId() || "";

      // Use chatId for activeRun check
      if (chatId) {
        const activeRun = Array.from(storeRef.current.runs.values()).find(
          r => r.chatId === chatId && r.status === "running"
        );
        if (activeRun) {
          sendLockRef.current = false;
          return;
        }
      }

      // Initialize finalChatId
      finalChatId = chatId;

      // Generate requestId (UUID) for idempotency
      const generateUUID = () => {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
          return crypto.randomUUID();
        }
        return `${Date.now()}-${Math.random().toString(36).substring(2, 15)}-${Math.random().toString(36).substring(2, 15)}`;
      };

      requestId = generateUUID();

      // IDEMPOTENCY CHECK: Prevent duplicate sends with same requestId (strict mode double-invoke guard)
      if (inflightRequestsRef.current.has(requestId)) {
        sendLockRef.current = false;
        return;
      }

      // KESİNLİKLE: Boş input kontrolü - en başta
      const userInput = input.trim();

      // Empty input check
      if (!userInput || userInput === "") {
        // Boş input + dosya yoksa kesinlikle backend'e gitme
        if (attachedFiles.length === 0) {
          sendLockRef.current = false;
          return; // Boş mesaj gönderilmez
        }
        // Dosya varsa ama metin yoksa, kullanıcıya "Mesaj yazın" uyarısı göster
        toast({
          title: "Lütfen bir mesaj yazın",
          description: "Dosya eklediniz, ancak bir mesaj yazmanız gerekiyor.",
          status: "info",
          duration: 3000,
        });
        sendLockRef.current = false;
        return;
      }

      // Dosya yüklenirken veya yükleme devam ederken mesaj gönderilmemeli
      // Ayrıca yüklenmemiş dosya varsa mesaj gönderilmemeli
      const hasUnuploadedFiles = attachedFiles.some((f) => f.isUploading || !f.documentId);
      if (isLoading || isUploading || hasUnuploadedFiles) {
        if (hasUnuploadedFiles) {
          toast({
            title: "Lütfen bekleyin",
            description: "Dosyalar hala yükleniyor, lütfen tamamlanmasını bekleyin.",
            status: "info",
            duration: 3000,
          });
        }
        sendLockRef.current = false;
        return;
      }

      // CHAT SAVING ENABLED: Create chat if needed
      if (!finalChatId || !isValidObjectId(finalChatId)) {
        try {
          const newChat = await createChat(undefined, selectedModule);
          finalChatId = newChat.id;
          setCurrentChatId(finalChatId);

          // Update URL without navigation
          const newUrl = `/chat/${finalChatId}`;
          window.history.replaceState({}, "", newUrl);

        } catch (error: any) {
          console.error("[SEND] Error creating chat:", error);
          toast({
            title: "Hata",
            description: error.detail || "Chat oluşturulamadı",
            status: "error",
            duration: 2000,
          });
          sendLockRef.current = false;
          inflightRequestsRef.current.delete(requestId);
          return;
        }
      }

      // Mark request as in-flight
      inflightRequestsRef.current.add(requestId);

      // userMessageText: use userInput
      const userMessageText = userInput;

      // Dosyaları kopyala (clearComposer'dan önce - çünkü clearComposer attachedFiles'ı temizler)
      const filesToUse = [...attachedFilesRef.current];

      // Generate client_message_id (same as requestId for consistency)
      const clientMessageId = requestId;

      // CRITICAL: Check if assistant message already exists for this requestId (prevent duplicate)
      const existingRunForRequest = getRunByRequestId(requestId);
      if (existingRunForRequest) {
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // DUPLICATE PREVENTION: Check if same message content already exists in recent messages
      const chatMessages = getChatMessagesFromStore(finalChatId);

      // Check if there's already a streaming assistant message in this chat (prevent duplicate)
      const existingStreamingMessage = chatMessages.find(
        m => m.role === "assistant" && m.status === "streaming"
      );
      if (existingStreamingMessage) {
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // Check for duplicate user message content (rapid double-submit prevention)
      const recentUserMessages = chatMessages.filter(m => m.role === "user").slice(-5);
      const isDuplicateContent = recentUserMessages.some(m =>
        m.content.trim() === userMessageText.trim() &&
        Date.now() - m.createdAt.getTime() < 5000 // Within 5 seconds
      );

      if (isDuplicateContent) {
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // Create user message and add to store
      const userMessageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      const userMessage: NormalizedMessage = {
        id: userMessageId,
        chatId: finalChatId,
        role: "user",
        content: userMessageText || "",
        createdAt: new Date(),
        status: "completed",
        client_message_id: clientMessageId,
        attachments: filesToUse.length > 0 ? filesToUse
          .filter(f => f.documentId)
          .map((file) => ({
            id: file.id,
            filename: file.name,
            type: file.type,
            size: file.size,
            documentId: file.documentId,
          })) : undefined,
      };
      addMessage(userMessage);

      // Create placeholder assistant message (will be updated during streaming)
      // CRITICAL: Only ONE assistant message per user message
      // Double-check before creating (race condition prevention)
      const finalCheckMessages = getChatMessagesFromStore(finalChatId);
      const finalCheckStreaming = finalCheckMessages.find(
        m => m.role === "assistant" && m.status === "streaming"
      );
      if (finalCheckStreaming) {
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      const assistantMessageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      const assistantMessage: NormalizedMessage = {
        id: assistantMessageId,
        chatId: finalChatId,
        role: "assistant",
        content: "",
        createdAt: new Date(),
        status: "streaming",
        sources: undefined,
        module: selectedModule, // Set module immediately for premium rendering
      };
      addMessage(assistantMessage);

      // Create run record
      runId = `run_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      const run: Run = {
        runId: runId,
        requestId: requestId,
        chatId: finalChatId,
        assistantMessageId: assistantMessageId,
        status: "running",
        startedAt: new Date(),
        lastSeq: 0,
        abortController: abortController,
        module: selectedModule,
      };
      addRun(run);

      // Sync store to local state
      syncStoreToLocalState(finalChatId);

      // Check if this is the first message in this chat
      const allChatMessages = getChatMessagesFromStore(finalChatId);
      const userMessageCount = allChatMessages.filter(m => m.role === "user").length;
      if (userMessageCount === 1) {
        // First message - notify sidebar
        setTimeout(() => window.dispatchEvent(new CustomEvent("chatHistoryUpdated")), 500);
        setTimeout(() => window.dispatchEvent(new CustomEvent("chatHistoryUpdated")), 2000);
        setTimeout(() => window.dispatchEvent(new CustomEvent("chatHistoryUpdated")), 4000);
        setTimeout(() => window.dispatchEvent(new CustomEvent("chatHistoryUpdated")), 6000);
      } else {
        setTimeout(() => window.dispatchEvent(new CustomEvent("chatHistoryUpdated")), 1000);
      }

      // Scroll to bottom and clear composer
      setTimeout(() => maybeScrollToBottom("user-send", true), 0);
      clearComposer();

      // Get documentIds
      const uploadedDocumentIdsFromFiles = filesToUse.filter((f) => f.documentId).map((f) => f.documentId!);
      const uploadedDocumentIdsFromState = uploadedDocuments
        .filter((doc) => filesToUse.some((f) => f.name === doc.name || f.id === doc.id))
        .map((doc) => doc.id);
      const uploadedDocumentIds = [...new Set([...uploadedDocumentIdsFromFiles, ...uploadedDocumentIdsFromState])];

      // Determine which documentIds to use
      let documentIdsToUse: string[] = [];
      let savedDocumentIds: string[] = [];
      try {
        const stored = localStorage.getItem(`chat_settings_${finalChatId}`);
        if (stored) {
          const settings = JSON.parse(stored);
          savedDocumentIds = settings.selectedDocumentIds || [];
        }
      } catch (error) {
        console.error("Failed to load chat settings:", error);
      }

      if (selectedDocumentIds.length > 0) {
        documentIdsToUse = selectedDocumentIds;
      } else if (uploadedDocumentIds.length > 0) {
        documentIdsToUse = uploadedDocumentIds;
        setSelectedDocumentIds(uploadedDocumentIds);
        saveChatSettings(finalChatId);
      } else if (savedDocumentIds.length > 0) {
        documentIdsToUse = savedDocumentIds;
      }

      setLastDocumentIdsUsed(documentIdsToUse);


      // Use /api/chat endpoint (chat saving enabled)
      // CRITICAL: Get current module from localStorage to ensure it's always up-to-date
      const currentModule = typeof window !== 'undefined'
        ? (localStorage.getItem('selectedModule') === 'lgs_karekok' ? 'lgs_karekok' as const : 'none' as const)
        : 'none' as const;

      const sendRequest: SendChatMessageRequest = {
        message: userMessageText || "",
        client_message_id: clientMessageId,
        mode: "qa",
        documentIds: documentIdsToUse.length > 0 ? documentIdsToUse : undefined,
        useDocuments: documentIdsToUse.length > 0,
        chatId: finalChatId,  // Include chatId for saving
        response_style: responseStyle !== "auto" ? responseStyle as "short" | "medium" | "long" | "detailed" : undefined,
        prompt_module: currentModule,  // Always get from localStorage to ensure it's current
      };

      // CRITICAL: Send message with keepalive to continue even when tab is hidden
      // The request itself continues in background, backend processes it independently
      const response = await sendChatMessage(finalChatId, sendRequest);

      // STREAMING: Check if backend returned run_id and message_id for polling
      // Backend returns debug_info with run_id, message_id, and streaming flag
      const debugInfo = (response as any).debug_info || {};
      const backendRunId = debugInfo.run_id;
      const backendMessageId = debugInfo.message_id;
      const isStreaming = debugInfo.streaming === true;

      // CRITICAL: Check for streaming mode FIRST before validating message content
      if (isStreaming && backendRunId && backendMessageId) {
        // STREAMING MODE: Personal Assistant (Gemini) - Backend is streaming, use polling
        // Update assistant message ID to backend's message_id
        updateMessage(assistantMessageId, {
          id: backendMessageId,  // Use backend message_id
          status: "streaming",
          is_partial: true,
        });

        // Update run with backend run_id
        if (runId) {
          updateRun(runId, {
            runId: backendRunId,  // Use backend run_id
            status: "running",
          });
        }

        // Store run_id for polling
        localStorage.setItem(`pending_run_${finalChatId}`, backendRunId);

        // Start polling (already handled by useEffect for pending runs)
        syncStoreToLocalState(finalChatId);
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        skipFinalize = true; // DO NOT reset UI states in finally block

        // Auto-focus input after sending message (for seamless typing experience)
        setTimeout(() => {
          if (inputRef.current) {
            inputRef.current.focus();
          }
        }, 100);

        return; // Exit early - polling will update content
      } else if (!isStreaming && backendRunId && backendMessageId) {
        // NON-STREAMING MODE: LGS Module (DeepSeek R1) - Wait for complete response via polling
        // Update assistant message ID to backend's message_id
        updateMessage(assistantMessageId, {
          id: backendMessageId,  // Use backend message_id
          status: "streaming",  // Still "streaming" until polling confirms completion
          is_partial: true,
        });

        // Update run with backend run_id
        if (runId) {
          updateRun(runId, {
            runId: backendRunId,  // Use backend run_id
            status: "running",
          });
        }

        // Store run_id for polling (non-streaming still uses polling to check completion)
        localStorage.setItem(`pending_run_${finalChatId}`, backendRunId);

        // Start polling (will detect when run is completed)
        syncStoreToLocalState(finalChatId);
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        skipFinalize = true; // DO NOT reset UI states in finally block

        // Auto-focus input after sending message
        setTimeout(() => {
          if (inputRef.current) {
            inputRef.current.focus();
          }
        }, 100);

        return; // Exit early - polling will update content when complete
      }

      // FALLBACK: Non-streaming response (legacy support)
      // Validate response
      if (response.role !== "assistant") {
        console.error(`[SEND] Invalid response role from backend: ${response.role} (expected: assistant)`, response);
        // Backend returned wrong role (likely error case)
        updateMessage(assistantMessageId, {
          content: "Cevap oluşturulurken bir hata oluştu. Lütfen tekrar deneyin.",
          status: "completed",
        });

        // CRITICAL: Remove run from store (not just update status)
        if (runId) {
          removeRun(runId);
          // CRITICAL: Force finalize run state IMMEDIATELY
          if (finalChatId) {
            finalizeRun(finalChatId, true);
          }
        }

        if (finalChatId) {
          syncStoreToLocalState(finalChatId);
        }

        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // Validate response content - but only if NOT in streaming mode
      // (Streaming mode already handled above)
      if (!response.message || response.message.trim().length === 0) {
        // Check if this is actually a streaming response that we missed
        if (backendRunId || backendMessageId) {
          // This might be a streaming response - try to use polling
          if (backendRunId) {
            localStorage.setItem(`pending_run_${finalChatId}`, backendRunId);
            updateMessage(assistantMessageId, {
              status: "streaming",
              is_partial: true,
            });
            if (runId) {
              updateRun(runId, {
                runId: backendRunId,
                status: "running",
              });
            }
            syncStoreToLocalState(finalChatId);
            inflightRequestsRef.current.delete(requestId);
            sendLockRef.current = false;
            skipFinalize = true; // DO NOT reset UI states in finally block
            return;
          }
        }

        // Still update message to show error state
        updateMessage(assistantMessageId, {
          content: "Cevap alınamadı. Lütfen tekrar deneyin.",
          status: "completed",
        });

        // CRITICAL: Remove run from store (not just update status)
        if (runId) {
          removeRun(runId);
          // CRITICAL: Force finalize run state IMMEDIATELY
          if (finalChatId) {
            finalizeRun(finalChatId, true);
          }
        }

        if (finalChatId) {
          syncStoreToLocalState(finalChatId);
        }

        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // Check if run was aborted BEFORE updating message
      const currentRun = getRunByRequestId(requestId);
      if (!currentRun || currentRun.status !== "running" || abortController.signal.aborted) {
        if (currentRun) {
          updateMessage(currentRun.assistantMessageId, { status: "cancelled" });
          removeRun(currentRun.runId);
          // CRITICAL: Finalize run state when aborted
          finalizeRun(finalChatId, true);
        }
        inflightRequestsRef.current.delete(requestId);
        if (finalChatId) {
          syncStoreToLocalState(finalChatId);
        }
        return;
      }

      // CRITICAL: Get runId and assistantMessageId from currentRun (they might not be in scope)
      const activeRunId = currentRun.runId;
      const activeAssistantMessageId = currentRun.assistantMessageId;


      // Stream the response message character by character for better UX
      // CHAT SAVING ENABLED: Stream the response instead of showing it all at once
      // CRITICAL: Pass finalChatId explicitly to ensure UI updates even if currentChatId state hasn't updated yet
      // Show message immediately, then stream for visual effect
      if (activeRunId && activeAssistantMessageId) {
        // CRITICAL: Show full message immediately so user sees response right away
        updateMessage(activeAssistantMessageId, {
          content: response.message || "",
          status: "streaming",
          sources: response.sources,
          used_documents: response.used_documents,
        });

        // Force immediate sync to show message
        syncStoreToLocalState(finalChatId);
        // Also force React state update directly
        const initialMessages = getChatMessagesFromStore(finalChatId);
        const initialLegacyMessages: (Message & { _isStreaming?: boolean })[] = initialMessages.map(msg => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: msg.createdAt,
          status: msg.status === "cancelled" ? "cancelled" : msg.status === "completed" ? "completed" : undefined,
          sources: msg.sources,
          used_documents: msg.used_documents,
          document_ids: msg.document_ids,  // Include document_ids for rendering
          client_message_id: msg.client_message_id,
          attachments: msg.attachments,
          // CRITICAL: Typing indicator shows ONLY when message is NOT completed
          _isStreaming: msg.status !== "completed" && msg.status !== "cancelled",
        }));
        setMessages(initialLegacyMessages);
      }

      // Stream message for visual effect (but message is already visible)
      // CRITICAL: If tab is hidden, skip animation and show message immediately
      const isTabVisible = typeof document !== 'undefined' && !document.hidden;
      if (activeRunId && response.message && isTabVisible) {
        // Only animate if tab is visible
        await streamMessage(
          response.message,
          activeRunId,
          response.sources,
          abortController.signal,
          finalChatId,
          response.used_documents
        );
        // streamMessage already removes the run from store, just sync state
        syncStoreToLocalState(finalChatId);
      } else if (activeRunId && response.message && !isTabVisible) {
        // Tab is hidden - just mark as completed without animation
        updateMessage(activeAssistantMessageId, {
          content: response.message,
          status: "completed",
          sources: response.sources,
          used_documents: response.used_documents,
        });

        // CRITICAL: Remove run from store (not just update status)
        removeRun(activeRunId);

        // CRITICAL: Force finalize run state IMMEDIATELY
        finalizeRun(finalChatId, true);

        // Sync state after removing run
        syncStoreToLocalState(finalChatId);
      } else {
        // No active run or no message - ensure run is removed
        if (activeRunId) {
          const finalRun = getRun(activeRunId);
          if (finalRun) {
            removeRun(activeRunId);
          }
        }

        // CRITICAL: Force finalize run state IMMEDIATELY
        finalizeRun(finalChatId, true);

        syncStoreToLocalState(finalChatId);
      }

      // Note: For now, we're using the simple response. Full streaming support would require
      // additional backend changes to support SSE/WebSocket for the new endpoint.

      // CRITICAL FIX: Reload messages from backend after streaming completes
      // This ensures backend-saved messages are loaded into frontend
      // Wait a bit for backend to finish saving messages (increased delay for reliability)
      if (finalChatId) {
        // CHAT SAVING ENABLED: Messages are saved, no need to reload (they're already in store)
      }

      // Check if first message for sidebar update
      const finalChatMessages = getChatMessagesFromStore(finalChatId);
      const finalUserMessageCount = finalChatMessages.filter(m => m.role === "user").length;
      if (finalUserMessageCount === 1) {
        // Backend automatically generates title and sets has_messages: true
        // Notify sidebar after a delay to allow backend to process
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("chatHistoryUpdated"));
        }, 500); // First update after 500ms

        // Poll again after 2 seconds for title update
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("chatHistoryUpdated"));
        }, 2000);

        // Poll once more after 4 seconds to ensure title is updated
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("chatHistoryUpdated"));
        }, 4000);

        // Poll once more after 6 seconds to ensure chat appears in history
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("chatHistoryUpdated"));
        }, 6000);
      } else {
        // Not first message, but still update sidebar to refresh chat list
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("chatHistoryUpdated"));
        }, 1000);
      }
    } catch (error: any) {
      const currentChatStateError = getCurrentChatState(finalChatId);
      if (error?.name === 'AbortError' || abortController.signal.aborted || currentChatStateError.requestId !== requestId) {
        wasAborted = true;
        updateCurrentChatState(finalChatId, {
          isLoading: false,
          abortController: null,
          requestId: null,
          streamingContent: "",
          isStreaming: false,
        });

        if (finalChatId === currentChatId) {
          setIsLoading(false);
          setAbortController(null);
          setStreamingContent("");
        }
        return;
      }

      // Duplicate request error → no retry
      if (error?.code === 'DUPLICATE_REQUEST' || (error?.detail && error.detail.includes('zaten işlendi'))) {
        wasAborted = true;
        updateCurrentChatState(finalChatId, {
          isLoading: false,
          abortController: null,
          requestId: null,
          streamingContent: "",
          isStreaming: false,
        });

        if (finalChatId === currentChatId) {
          setIsLoading(false);
          setAbortController(null);
          setStreamingContent("");
        }
        return;
      }

      // Real error: mark run failed and surface a minimal message
      const runForError = requestId ? getRunByRequestId(requestId) : undefined;
      if (runForError) {
        updateMessage(runForError.assistantMessageId, {
          content: `Hata: ${error?.detail || "Mesaj gönderilemedi"}`,
          status: "completed",
        });

        // CRITICAL: Remove run from store (not just update status)
        removeRun(runForError.runId);

        // CRITICAL: Force finalize run state IMMEDIATELY
        finalizeRun(runForError.chatId, true);

        syncStoreToLocalState(runForError.chatId);
      }
    } finally {
      const finalChatState = getCurrentChatState(finalChatId);
      const finalAbortState = abortController.signal.aborted || wasAborted || finalChatState.requestId !== requestId;

      // CRITICAL: Use finalizeRun to ensure consistent state reset
      // This will check store for active runs and reset state accordingly
      finalizeRun(finalChatId, false);

      // CRITICAL: Always focus input after sending message (unless aborted)
      if (!finalAbortState && finalChatState.requestId === requestId) {
        setInput("");

        // Focus input with multiple attempts to ensure it works
        const focusInput = () => {
          if (inputRef.current) {
            try {
              inputRef.current.focus();
              return document.activeElement === inputRef.current;
            } catch (error) {
              return false;
            }
          }
          return false;
        };

        // Try to focus after a short delay
        setTimeout(() => {
          if (!focusInput()) {
            setTimeout(() => {
              focusInput();
            }, 100);
          }
        }, 100);
      } else {
        setStreamingContent("");
      }

      // Clear active stream bindings for this chat
      if (finalChatState.requestId === requestId) {
        updateCurrentChatState(finalChatId, {
          abortController: null,
          requestId: null,
        });

        if (finalChatId === currentChatId) {
          setAbortController(null);
        }
      }

      // Release inflight/request locks
      if (requestId) {
        inflightRequestsRef.current.delete(requestId);
      }
      sendLockRef.current = false;

      // CRITICAL: Finalize interaction to ensure UI state is correct
      if (finalChatId && !skipFinalize) {
        finalizeInteraction(finalChatId, true);
        syncStoreToLocalState(finalChatId);
      } else if (skipFinalize) {
        // Ensure UI stays in streaming mode
        setIsStreaming(true);
        setCanSendMessage(false);
      }
    }
  };

  // REMOVED handleKeyDown - form onSubmit handles everything
  // This prevents duplicate calls when Enter is pressed

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>, isImage: boolean = false) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Determine allowed types based on file type
    let allowedExtensions: string[];
    let allowedMimeTypes: string[];

    if (isImage) {
      allowedExtensions = [".jpg", ".jpeg", ".png", ".webp"];
      allowedMimeTypes = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
    } else {
      allowedExtensions = [".pdf", ".docx", ".txt"];
      allowedMimeTypes = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain"
      ];
    }

    const validFiles: AttachedFile[] = [];
    const invalidFiles: string[] = [];

    Array.from(files).forEach((file) => {
      const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf("."));
      const isValidExtension = allowedExtensions.includes(fileExtension);
      const isValidMime = !file.type || allowedMimeTypes.includes(file.type);

      if (isValidExtension && isValidMime) {
        const fileId = `${Date.now()}_${Math.random()}`;
        const abortController = new AbortController();
        validFiles.push({
          id: fileId,
          name: file.name,
          type: file.type || "unknown",
          size: file.size,
          file: file,
          isUploading: true, // Yükleme başlıyor
          abortController: abortController, // İptal için controller
        });
      } else {
        invalidFiles.push(file.name);
      }
    });

    if (invalidFiles.length > 0) {
      const errorMsg = `Şu dosyalar desteklenmiyor: ${invalidFiles.join(", ")}. İzin verilen: ${allowedExtensions.join(", ")}`;
      toast({
        title: "Hata",
        description: errorMsg,
        status: "error",
        duration: 2000,
      });
    }

    if (validFiles.length > 0) {
      // Dosyaları state'e ekle (yükleniyor olarak)
      // CRITICAL: Use sync updater to update both state and ref
      setAttachedFilesSync((prev) => {
        return [...prev, ...validFiles];
      });
      setIsUploading(true);

      // Chat ID'yi önce al (tüm dosyalar için aynı)
      const chatId = await getOrCreateChatId();

      // Get chat title if chatId exists
      let chatTitle: string | undefined = undefined;
      if (chatId) {
        try {
          const chat = await getChat(chatId);
          chatTitle = chat.title;
        } catch (error) {
          // Continue without title - backend will use default
        }
      }

      // Her dosyayı hemen yükle
      const uploadPromises = validFiles.map(async (attachedFile) => {
        try {
          // AbortController'ı kontrol et
          if (attachedFile.abortController?.signal.aborted) {
            throw new Error("Yükleme iptal edildi");
          }

          // Upload with progress tracking using XMLHttpRequest
          const uploadResponse = await new Promise<{ documentId: string; truncated: boolean; indexing_success: boolean }>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const formData = new FormData();
            formData.append("file", attachedFile.file);
            if (chatId) formData.append("chat_id", chatId);
            if (chatTitle) formData.append("chat_title", chatTitle);
            if (selectedModule) formData.append("prompt_module", selectedModule);

            // Progress event
            xhr.upload.onprogress = (event) => {
              if (event.lengthComputable) {
                const percentComplete = Math.round((event.loaded / event.total) * 100);
                // Update progress in state
                setAttachedFilesSync((prev) =>
                  prev.map((f) =>
                    f.id === attachedFile.id
                      ? { ...f, uploadProgress: percentComplete }
                      : f
                  )
                );
              }
            };

            // Success
            xhr.onload = () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                try {
                  const response = JSON.parse(xhr.responseText);
                  resolve({
                    documentId: response.documentId || response.document_id || response.doc_id || response.id,
                    truncated: response.truncated || false,
                    indexing_success: response.indexing_success || false,
                  });
                } catch (e) {
                  reject(new Error("Geçersiz sunucu yanıtı"));
                }
              } else {
                try {
                  const errorResponse = JSON.parse(xhr.responseText);
                  reject(new Error(errorResponse.detail || `Yükleme hatası: ${xhr.status}`));
                } catch (e) {
                  reject(new Error(`Yükleme hatası: ${xhr.status}`));
                }
              }
            };

            // Error
            xhr.onerror = () => {
              reject(new Error("Ağ hatası"));
            };

            // Abort handling
            if (attachedFile.abortController) {
              attachedFile.abortController.signal.addEventListener("abort", () => {
                xhr.abort();
                reject(new Error("Yükleme iptal edildi"));
              });
            }

            // Get auth token
            const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

            // Send request
            xhr.open("POST", `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/documents/upload`);
            if (token) {
              xhr.setRequestHeader("Authorization", `Bearer ${token}`);
            }
            xhr.send(formData);
          });

          // AbortController tekrar kontrol et (yükleme sırasında iptal edilmiş olabilir)
          // CRITICAL: Use sync updater to update both state and ref
          setAttachedFilesSync((prev) => {
            const currentFile = prev.find((f) => f.id === attachedFile.id);
            if (currentFile?.abortController?.signal.aborted) {
              // Yükleme iptal edilmiş, dosyayı kaldır
              return prev.filter((f) => f.id !== attachedFile.id);
            }
            // Dosya yükleme başarılı, documentId'yi güncelle
            return prev.map((f) =>
              f.id === attachedFile.id
                ? { ...f, documentId: uploadResponse.documentId, isUploading: false, uploadProgress: 100, abortController: undefined }
                : f
            );
          });

          // REMOVED: Toast notifications for file uploads (user requested no notifications)
          // Files are shown as chips in the input box, no need for toast

          // Wait a bit for indexing to complete (if it's still running)
          // This ensures the document is ready before user asks questions
          if (uploadResponse.indexing_success === true) {
            // Indexing already completed, no need to wait
            await new Promise(resolve => setTimeout(resolve, 500)); // Small delay for UI
          } else {
            // Indexing might still be running, wait a bit longer
            await new Promise(resolve => setTimeout(resolve, 2000)); // 2 second wait
          }

          // Yüklenen dosya bilgisini döndür (tüm dosyalar yüklendikten sonra state'e eklenecek)
          return {
            documentId: uploadResponse.documentId,
            filename: attachedFile.name,
            type: attachedFile.type || "unknown",
          };
        } catch (error: any) {
          // Abort edilmişse sessizce çık
          if (error.code === "ABORTED" || error.message === "Yükleme iptal edildi" || error.name === "AbortError") {
            // Dosyayı state'ten kaldır
            setAttachedFilesSync((prev) => prev.filter((f) => f.id !== attachedFile.id));
            return null;
          }

          // Hata durumunda dosyayı listeden kaldır
          setAttachedFilesSync((prev) => {
            const fileStillExists = prev.find((f) => f.id === attachedFile.id);
            if (fileStillExists && !fileStillExists.abortController?.signal.aborted) {
              return prev.filter((f) => f.id !== attachedFile.id);
            }
            return prev;
          });

          // Sadece abort edilmemiş hatalar için toast göster
          if (error.code !== "ABORTED" && error.message !== "Yükleme iptal edildi" && error.name !== "AbortError") {
            toast({
              title: "Hata",
              description: `${attachedFile.name} yüklenirken hata oluştu: ${error.detail || "Bilinmeyen hata"}`,
              status: "error",
              duration: 2000,
            });
          }
          return null; // Return null instead of throwing to allow other files to continue
        }
      });

      // Tüm yüklemeleri bekle
      try {
        const uploadResults = await Promise.all(uploadPromises);
        const successfulUploads = uploadResults.filter((result): result is { documentId: string; filename: string; type: string } => result !== null);
        const successfulIds = successfulUploads.map(u => u.documentId);

        // availableDocuments listesini güncelle (tüm dosyalar yüklendikten sonra bir kez)
        try {
          const updatedDocs = await listDocuments(selectedModule);
          setAvailableDocuments(updatedDocs);
        } catch (error) {
          console.error("Failed to refresh documents list:", error);
        }

        // Tüm başarılı yüklenen dosyaları uploadedDocuments state'ine ekle (bir kerede)
        if (successfulUploads.length > 0) {
          const newUploadedDocs: UploadedDocument[] = successfulUploads.map(upload => ({
            id: upload.documentId,
            name: upload.filename,
            type: upload.type,
            source: "upload",
            uploadedAt: new Date().toISOString(),
          }));

          // Mevcut state ile birleştir
          setUploadedDocuments((prev) => {
            const existingIds = new Set(prev.map(doc => doc.id));
            const uniqueNewDocs = newUploadedDocs.filter(doc => !existingIds.has(doc.id));
            return [...prev, ...uniqueNewDocs];
          });

        }

        // REMOVED: Toast notifications for file uploads (user requested no notifications)

        // Dosyalar yüklendiğinde documentIds'yi ve uploadedDocuments'ı chat settings'e kaydet
        if (successfulIds.length > 0) {
          // Mevcut chat settings'i yükle ve yeni documentIds'yi ekle
          try {
            const stored = localStorage.getItem(`chat_settings_${chatId}`);
            let existingIds: string[] = [];
            let existingDocs: UploadedDocument[] = [];
            if (stored) {
              const settings = JSON.parse(stored);
              existingIds = settings.selectedDocumentIds || [];
              existingDocs = settings.uploadedDocuments || [];
            }

            // Yeni documentIds'yi ekle (duplicate'leri önle)
            const combinedIds = [...new Set([...existingIds, ...successfulIds])];
            setSelectedDocumentIds(combinedIds);

            // Yeni uploadedDocuments'ı ekle (duplicate'leri önle)
            const existingDocIds = new Set(existingDocs.map(doc => doc.id));
            const newDocs = successfulUploads.map(upload => ({
              id: upload.documentId,
              name: upload.filename,
              type: upload.type,
              source: "upload" as const,
              uploadedAt: new Date().toISOString(),
            }));
            const uniqueNewDocs = newDocs.filter(doc => !existingDocIds.has(doc.id));
            const combinedDocs = [...existingDocs, ...uniqueNewDocs];

            // State'i güncelle (hemen görünsün)
            setUploadedDocuments(combinedDocs);

            // Chat settings'e kaydet
            localStorage.setItem(`chat_settings_${chatId}`, JSON.stringify({
              selectedDocumentIds: combinedIds,
              uploadedDocuments: combinedDocs,
            }));
          } catch (error) {
            console.error("Failed to save chat settings after file upload:", error);
          }
        }
      } catch (error) {
        // Hata zaten toast ile gösterildi
      } finally {
        // Tüm dosyalar yüklendi mi kontrol et
        setAttachedFilesSync((prev) => {
          const allUploaded = prev.every((f) => !f.isUploading && f.documentId);
          if (allUploaded) {
            setIsUploading(false);
            // Input'a otomatik focus yap (kullanıcı fareyle tıklamak zorunda kalmasın)
            setTimeout(() => {
              if (inputRef.current) {
                inputRef.current.focus();
              }
            }, 50); // Daha hızlı focus (50ms)
          }
          // attachedFiles state'ini temizleme - mesaj gönderilirken kullanılacak
          // clearComposer() mesaj gönderildikten sonra temizleyecek
          return prev;
        });
      }
    }

    // Reset input to allow selecting same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
  };

  const handleRemoveFile = (fileId: string) => {
    setAttachedFilesSync((prev) => {
      const fileToRemove = prev.find((f) => f.id === fileId);

      // Eğer dosya yükleniyorsa, yüklemeyi iptal et
      if (fileToRemove?.isUploading && fileToRemove.abortController) {
        fileToRemove.abortController.abort();
        toast({
          title: "İptal edildi",
          description: `${fileToRemove.name} yüklemesi iptal edildi.`,
          status: "info",
          duration: 2000,
        });
      }

      // Eğer bu bir DocumentPicker'dan seçilen dosya ise (id starts with 'doc_'), selectedDocumentIds'den de kaldır
      if (fileToRemove?.id.startsWith('doc_') && fileToRemove.documentId) {
        setSelectedDocumentIds((prevIds) => {
          const newIds = prevIds.filter(id => id !== fileToRemove.documentId);
          // Save to chat settings
          const chatId = params?.chatId as string | undefined;
          if (chatId) {
            try {
              const stored = localStorage.getItem(`chat_settings_${chatId}`);
              const currentSettings = stored ? JSON.parse(stored) : {};
              localStorage.setItem(`chat_settings_${chatId}`, JSON.stringify({
                selectedDocumentIds: newIds,
                uploadedDocuments: currentSettings.uploadedDocuments || [],
              }));
            } catch (error) {
              console.error("Failed to save document selection:", error);
            }
          }
          return newIds;
        });
      }

      // Dosyayı listeden kaldır
      const updated = prev.filter((f) => f.id !== fileId);

      // Tüm dosyalar yüklendi mi kontrol et
      const allUploaded = updated.every((f) => !f.isUploading && f.documentId);
      if (allUploaded) {
        setIsUploading(false);
      }

      return updated;
    });
  };

  // Format file size helper
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  return (
    <AuthGuard>
      <Box
        display="flex"
        h="100vh"
        overflow="hidden"
        flexDirection="column"
        bg={bgColor}
        position="relative"
      >
        <Sidebar />
        <Box
          flex={1}
          ml={isOpen ? "260px" : "0"}
          display="flex"
          flexDirection="column"
          transition="margin-left 0.3s ease"
          h="100vh"
          overflow="hidden"
        >
          <Box flexShrink={0}>
            <Topbar />
          </Box>
          <Box flex={1} display="flex" flexDirection="column" overflow="hidden" minH={0} pt="60px">
            {/* Messages Area */}
            <Box
              flex={1}
              overflowY="auto"
              p={6}
              ref={messagesContainerRef}
              minH={0}
              position="relative"
              zIndex={1}
              sx={{
                "&::-webkit-scrollbar": {
                  width: "8px",
                },
                "&::-webkit-scrollbar-track": {
                  background: "transparent",
                },
                "&::-webkit-scrollbar-thumb": {
                  background: "rgba(255, 255, 255, 0.1)",
                  borderRadius: "4px",
                  "&:hover": {
                    background: "rgba(255, 255, 255, 0.15)",
                  },
                },
              }}
            >
              <VStack spacing={4} align="stretch" maxW="4xl" mx="auto">
                {/* Yüklenen Dosyalar Listesi - Sohbet ekranında */}
                {uploadedDocuments && uploadedDocuments.length > 0 && (
                  <Box
                    p={4}
                    bg={panelBg}
                    borderRadius="lg"
                    border="1px solid"
                    borderColor={borderColor}
                    mb={4}
                  >
                    <Text fontSize="sm" color={textSecondary} mb={3} fontWeight="medium">
                      📎 Yüklenen Dosyalar ({uploadedDocuments.length})
                    </Text>
                    <VStack align="stretch" spacing={2}>
                      {uploadedDocuments.map((doc) => {
                        // Dosya türüne göre icon seç
                        const getFileIcon = (type: string, name: string) => {
                          const ext = name.split('.').pop()?.toLowerCase();
                          if (type.includes('pdf') || ext === 'pdf') {
                            return <FaFilePdf size={20} color="#EF4444" />;
                          } else if (type.includes('word') || type.includes('docx') || ext === 'docx' || ext === 'doc') {
                            return <FaFileWord size={20} color="#3B82F6" />;
                          } else if (type.includes('text') || ext === 'txt') {
                            return <FaFileAlt size={20} color={textPlaceholder} />;
                          } else if (type.includes('mail') || ext === 'eml' || doc.source === 'email') {
                            return <FaEnvelope size={20} color="#F59E0B" />;
                          }
                          return <FaFileAlt size={20} color={textSecondary} />;
                        };

                        const getFileTypeLabel = (type: string, name: string) => {
                          const ext = name.split('.').pop()?.toUpperCase();
                          if (type.includes('pdf') || ext === 'PDF') return 'PDF';
                          if (type.includes('word') || type.includes('docx') || ext === 'DOCX' || ext === 'DOC') return 'DOCX';
                          if (type.includes('text') || ext === 'TXT') return 'TXT';
                          if (type.includes('mail') || ext === 'EML' || doc.source === 'email') return 'Mail';
                          return ext || 'Dosya';
                        };

                        return (
                          <Box
                            key={doc.id}
                            display="flex"
                            alignItems="center"
                            gap={3}
                            p={3}
                            bg={accentSoft}
                            borderRadius="md"
                            border="1px solid"
                            borderColor={accentBorder}
                            _hover={{
                              bg: accentSoft,
                              borderColor: accentPrimary,
                            }}
                          >
                            <Box flexShrink={0}>
                              {getFileIcon(doc.type, doc.name)}
                            </Box>
                            <VStack align="start" spacing={0} flex={1} minW={0}>
                              <Text fontSize="sm" fontWeight="medium" color={textPrimary} isTruncated width="100%">
                                {doc.name}
                              </Text>
                              <HStack spacing={2} mt={1}>
                                <Badge bg={accentSoft} color={accentPrimary} fontSize="2xs" px={1.5} py={0.5} border="1px solid" borderColor={accentBorder}>
                                  {getFileTypeLabel(doc.type, doc.name)}
                                </Badge>
                                {doc.source === 'email' && (
                                  <Badge bg="rgba(245, 158, 11, 0.15)" color="#F59E0B" fontSize="2xs" px={1.5} py={0.5} border="1px solid" borderColor="rgba(245, 158, 11, 0.3)">
                                    Mail
                                  </Badge>
                                )}
                              </HStack>
                            </VStack>
                          </Box>
                        );
                      })}
                    </VStack>
                  </Box>
                )}

                {messages.length === 0 && (
                  <Box
                    textAlign="center"
                    py={20}
                    sx={{
                      animation: "fadeInUp 0.6s ease-out",
                    }}
                  >
                    <Box
                      w="80px"
                      h="80px"
                      mx="auto"
                      mb={6}
                      borderRadius="full"
                      bg={panelBg}
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                      border="1px solid"
                      borderColor={accentBorder}
                      transition="all-round 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)"
                      overflow="hidden"
                      p={4}
                      sx={{
                        boxShadow: `0 8px 32px ${accentSoft}`,
                        "&:hover": {
                          transform: "scale(1.15) rotate(5deg)",
                          boxShadow: `0 12px 40px ${accentSoft}`,
                          borderColor: accentPrimary,
                        },
                      }}
                    >
                      <Image
                        src={selectedModule === 'lgs_karekok' ? '/square-root.png' : '/chat.png'}
                        alt="Assistant Logo"
                        width={48}
                        height={48}
                        style={{ objectFit: 'contain' }}
                      />
                    </Box>
                    <Text
                      fontSize="2xl"
                      fontWeight="bold"
                      mb={2}
                      color={textPrimary}
                    >
                      {selectedModule === 'lgs_karekok' ? 'LGS Karekök Asistanı' : 'Kişisel Asistan'}
                    </Text>
                    <Text
                      color={textSecondary}
                      fontSize="md"
                    >
                      {selectedModule === 'lgs_karekok'
                        ? 'Matematik ve kareköklü ifadeler konusunda size yardımcı olabilirim.'
                        : 'Size nasıl yardımcı olabilirim?'}
                    </Text>
                  </Box>
                )}

                {messages.map((message) => {
                  // Render MessageContent for this message
                  const messageContentNode = message.content ? (
                    <MessageContent
                      content={message.content}
                      isStreaming={(message as any)._isStreaming === true}
                      isPartial={message.is_partial === true}
                      module={message.module}
                    />
                  ) : null;

                  return (
                    <MessageItem
                      key={message.id}
                      message={message as any}
                      messageContent={messageContentNode}
                      username={user?.username}
                    />
                  );
                })}

                {/* REMOVED: Global streaming message and typing indicator */}
                {/* Typing indicator is now shown inside assistant message bubble when status === "streaming" */}

                <div ref={messagesEndRef} />
              </VStack>
            </Box>

            {/* Input Area */}
            <Box
              flexShrink={0}
              p={4}
              borderTop="1px"
              borderColor={borderColor}
              bg={bgColor}
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault(); // Her zaman prevent default
                  e.stopPropagation(); // Event propagation'ı durdur
                  // Dosya yüklenirken form submit edilmesini engelle
                  if (isUploading || isLoading) {
                    if (isUploading) {
                      toast({
                        title: "Lütfen bekleyin",
                        description: "Dosya yükleniyor, lütfen tamamlanmasını bekleyin.",
                        status: "info",
                        duration: 3000,
                      });
                    }
                    return false;
                  }
                  // Boş input kontrolü
                  if (!input.trim() && attachedFiles.length === 0) {
                    return false;
                  }
                  // Sadece manuel submit (buton tıklama) veya Enter tuşu ile gönder
                  handleSend(e);
                }}
                onKeyDown={(e) => {
                  // Form içinde Enter'a basıldığında submit'i engelle
                  // Sadece input içinde Enter'a basıldığında handleKeyDown çalışacak
                  if (e.key === "Enter" && e.target !== inputRef.current) {
                    e.preventDefault();
                    e.stopPropagation();
                  }
                }}
              >
                {/* Single Input Container - expands when files added */}
                <Box
                  maxW="4xl"
                  mx="auto"
                  bg={panelBg}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor={borderColor}
                  display="flex"
                  flexDirection="column"
                  transition="all 0.2s ease"
                  minH="40px"
                  _focusWithin={{
                    borderColor: accentBorder,
                    bg: hoverBg,
                  }}
                >
                  {/* Yüklenen Dosyalar Listesi - Input alanının üstünde */}
                  {uploadedDocuments && uploadedDocuments.length > 0 && (
                    <Box
                      px={3}
                      pt={3}
                      pb={2}
                      borderBottom="1px"
                      borderColor={borderColor}
                    >
                      <Text fontSize="xs" color={textSecondary} mb={2} fontWeight="medium">
                        Yüklenen Dosyalar ({uploadedDocuments.length})
                      </Text>
                      <VStack align="stretch" spacing={2}>
                        {uploadedDocuments.map((doc) => {
                          // Dosya türüne göre icon seç
                          const getFileIcon = (type: string, name: string) => {
                            const ext = name.split('.').pop()?.toLowerCase();
                            if (type.includes('pdf') || ext === 'pdf') {
                              return <FaFilePdf size={18} color="#EF4444" />;
                            } else if (type.includes('word') || type.includes('docx') || ext === 'docx' || ext === 'doc') {
                              return <FaFileWord size={18} color="#3B82F6" />;
                            } else if (type.includes('text') || ext === 'txt') {
                              return <FaFileAlt size={18} color={textPlaceholder} />;
                            } else if (type.includes('mail') || ext === 'eml' || doc.source === 'email') {
                              return <FaEnvelope size={18} color="#F59E0B" />;
                            }
                            return <FaFileAlt size={18} color={textSecondary} />;
                          };

                          const getFileTypeLabel = (type: string, name: string) => {
                            const ext = name.split('.').pop()?.toUpperCase();
                            if (type.includes('pdf') || ext === 'PDF') return 'PDF';
                            if (type.includes('word') || type.includes('docx') || ext === 'DOCX' || ext === 'DOC') return 'DOCX';
                            if (type.includes('text') || ext === 'TXT') return 'TXT';
                            if (type.includes('mail') || ext === 'EML' || doc.source === 'email') return 'Mail';
                            return ext || 'Dosya';
                          };

                          return (
                            <Box
                              key={doc.id}
                              display="flex"
                              alignItems="center"
                              gap={3}
                              p={2.5}
                              bg={accentSoft}
                              borderRadius="md"
                              border="1px solid"
                              borderColor={accentBorder}
                              _hover={{
                                bg: accentSoft,
                                borderColor: accentPrimary,
                              }}
                            >
                              <Box flexShrink={0}>
                                {getFileIcon(doc.type, doc.name)}
                              </Box>
                              <VStack align="start" spacing={0} flex={1} minW={0}>
                                <Text fontSize="sm" fontWeight="medium" color="white" isTruncated width="100%">
                                  {doc.name}
                                </Text>
                                <HStack spacing={2}>
                                  <Badge colorScheme="blue" fontSize="2xs" px={1.5} py={0.5}>
                                    {getFileTypeLabel(doc.type, doc.name)}
                                  </Badge>
                                  {doc.source === 'email' && (
                                    <Badge colorScheme="orange" fontSize="2xs" px={1.5} py={0.5}>
                                      Mail
                                    </Badge>
                                  )}
                                </HStack>
                              </VStack>
                            </Box>
                          );
                        })}
                      </VStack>
                    </Box>
                  )}

                  {/* File Chips Row - Show attached files (includes both uploaded and selected) */}
                  {attachedFiles.length > 0 && (
                    <Box
                      px={3}
                      pt={2}
                      pb={1}
                      display="flex"
                      flexWrap="wrap"
                      gap={2}
                      borderBottom="1px"
                      borderColor={borderColor}
                    >
                      {/* Uploaded files and selected documents - now all in attachedFiles */}
                      {attachedFiles.map((file) => (
                        <FileChip
                          key={file.id}
                          file={file}
                          onRemove={() => handleRemoveFile(file.id)}
                          isUploading={file.isUploading}
                          uploadProgress={file.uploadProgress}
                        />
                      ))}
                    </Box>
                  )}

                  {/* Input Row - Inside container, bottom section */}
                  <HStack spacing={2} px={2} py={1.5} align="center">
                    <input
                      ref={fileInputRef}
                      type="file"
                      onChange={(e) => handleFileSelect(e, false)}
                      style={{ display: "none" }}
                      accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                      multiple
                    />
                    <input
                      ref={imageInputRef}
                      type="file"
                      onChange={(e) => handleFileSelect(e, true)}
                      style={{ display: "none" }}
                      accept="image/jpeg,image/jpg,image/png,image/webp"
                      multiple
                    />
                    <IconButton
                      icon={<AttachmentIcon />}
                      aria-label="Dosya ekle"
                      variant="ghost"
                      onClick={onDocModalOpen}
                      size="md"
                      color={selectedDocumentIds.length > 0 ? accentPrimary : textSecondary}
                      bg={selectedDocumentIds.length > 0 ? accentSoft : "transparent"}
                      borderRadius="md"
                      minW="40px"
                      h="40px"
                      title={selectedDocumentIds.length > 0 ? `${selectedDocumentIds.length} doküman seçili` : "Doküman ekle"}
                      transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                      _hover={{
                        transform: "scale(1.1)",
                        bg: selectedDocumentIds.length > 0 ? accentSoft : hoverBg,
                        color: selectedDocumentIds.length > 0 ? accentHover : textPrimary,
                        animation: "pulseScale 0.6s ease-in-out",
                      }}
                      _active={{
                        transform: "scale(0.95)",
                      }}
                    />
                    <IconButton
                      icon={
                        <Box
                          as="svg"
                          w="20px"
                          h="20px"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                          <circle cx="12" cy="13" r="4" />
                        </Box>
                      }
                      aria-label="Fotoğraf ekle"
                      variant="ghost"
                      onClick={() => imageInputRef.current?.click()}
                      size="md"
                      color={textSecondary}
                      bg="transparent"
                      borderRadius="md"
                      minW="40px"
                      h="40px"
                      title="Fotoğraf ekle"
                      transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                      _hover={{
                        transform: "scale(1.1)",
                        bg: hoverBg,
                        color: textPrimary,
                        animation: "pulseScale 0.6s ease-in-out",
                      }}
                      _active={{
                        transform: "scale(0.95)",
                      }}
                    />
                    <Input
                      ref={inputRef}
                      value={input}
                      onChange={(e) => {
                        // Sadece input değerini güncelle, başka bir şey yapma
                        setInput(e.target.value);
                      }}
                      onKeyDown={(e) => {
                        // CRITICAL: Only prevent default for Shift+Enter (new line)
                        // Let Enter trigger form submit naturally (no duplicate call)
                        if (e.key === "Enter" && !e.shiftKey) {
                          // Don't prevent default - let form onSubmit handle it
                          // This ensures only ONE call to handleSend
                          // Just stop propagation to prevent bubbling
                          e.stopPropagation();
                        }
                      }}
                      placeholder={
                        selectedModule === "lgs_karekok"
                          ? "LGS Karekök Asistanı'na bir soru yaz..."
                          : "Kişisel Asistan'a bir soru yaz..."
                      }
                      disabled={isUploading}
                      bg="transparent"
                      border="none"
                      color={textPrimary}
                      borderRadius="lg"
                      h="40px"
                      fontSize="15px"
                      _placeholder={{
                        color: textPlaceholder,
                      }}
                      _focus={{
                        borderColor: "transparent",
                        boxShadow: `0 0 0 2px ${accentSoft}`,
                        outline: "none",
                        color: textPrimary,
                      }}
                      transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                      sx={{
                        // Yazı yazarken animasyon yok
                        "&:focus": {
                          animation: "none !important",
                        },
                      }}
                      autoFocus
                      flex={1}
                      type="text"
                    />
                    {/* Premium Detaylı Toggle */}
                    <Tooltip label={responseStyle === "detailed" ? "Detaylı açıklama aktif" : "Normal cevap modu"} placement="top" hasArrow>
                      <Button
                        size="sm"
                        h="36px"
                        px={4}
                        fontSize="12px"
                        fontWeight="700"
                        variant="unstyled"
                        display="flex"
                        alignItems="center"
                        gap={2}
                        position="relative"
                        overflow="hidden"
                        transition="all 0.4s cubic-bezier(0.4, 0, 0.2, 1)"
                        bg={responseStyle === "detailed" ? "rgba(16, 185, 129, 0.15)" : "transparent"}
                        border="1px solid"
                        borderColor={responseStyle === "detailed" ? accentPrimary : borderColor}
                        color={responseStyle === "detailed" ? accentPrimary : textSecondary}
                        borderRadius="full"
                        onClick={() => setResponseStyle(prev => prev === "detailed" ? "auto" : "detailed")}
                        _hover={{
                          borderColor: accentPrimary,
                          bg: "rgba(16, 185, 129, 0.1)",
                          color: accentPrimary,
                          transform: "translateY(-1px)",
                          boxShadow: responseStyle === "detailed"
                            ? `0 0 15px ${accentPrimary}40`
                            : "none"
                        }}
                        _active={{
                          transform: "translateY(0) scale(0.98)",
                        }}
                        mr={2}
                      >
                        {/* Pulse effect for detailed mode */}
                        {responseStyle === "detailed" && (
                          <Box
                            position="absolute"
                            top="50%"
                            left="12px"
                            transform="translate(-50%, -50%)"
                            w="8px"
                            h="8px"
                            bg={accentPrimary}
                            borderRadius="full"
                            sx={{
                              animation: "pulseGlow 2s infinite",
                              "@keyframes pulseGlow": {
                                "0%": { transform: "translate(-50%, -50%) scale(1)", opacity: 1 },
                                "50%": { transform: "translate(-50%, -50%) scale(2.5)", opacity: 0 },
                                "100%": { transform: "translate(-50%, -50%) scale(1)", opacity: 0 },
                              }
                            }}
                          />
                        )}

                        <Box
                          transition="all 0.4s cubic-bezier(0.4, 0, 0.2, 1)"
                          transform={responseStyle === "detailed" ? "translateX(4px)" : "none"}
                        >
                          <Box as="svg" w="14px" h="14px" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                            <path d="M8 6h10" />
                            <path d="M8 10h10" />
                            <path d="M8 14h10" />
                          </Box>
                        </Box>

                        <Text
                          ml={responseStyle === "detailed" ? 1 : 0}
                          transition="all 0.3s ease"
                        >
                          Detaylı
                        </Text>
                      </Button>
                    </Tooltip>




                    {/* Send Button */}
                    <Box
                      position="relative"
                      minW="40px"
                      h="40px"
                      sx={{
                        "& > *": {
                          position: "absolute",
                          top: 0,
                          left: 0,
                          width: "100%",
                          height: "100%",
                        },
                      }}
                    >
                      {isStreaming ? (
                        <IconButton
                          aria-label="Durdur"
                          icon={
                            <Box
                              as="svg"
                              w="20px"
                              h="20px"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <rect x="6" y="6" width="12" height="12" rx="2" />
                            </Box>
                          }
                          onClick={() => {
                            // ChatGPT style: Abort the active stream
                            finalizeInteraction();
                          }}
                          size="md"
                          bg="red.500"
                          color="white"
                          borderRadius="lg"
                          minW="40px"
                          h="40px"
                          _hover={{
                            bg: "red.600",
                            transform: "scale(1.05)",
                          }}
                          _active={{
                            bg: "red.700",
                            transform: "scale(0.95)",
                          }}
                          transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                          sx={{
                            animation: "buttonTransitionIn 0.4s cubic-bezier(0.4, 0, 0.2, 1)",
                            "@keyframes buttonTransitionIn": {
                              "0%": {
                                opacity: 0,
                                transform: "scale(0.8) rotate(-90deg)",
                              },
                              "100%": {
                                opacity: 1,
                                transform: "scale(1) rotate(0deg)",
                              },
                            },
                          }}
                        />
                      ) : (
                        <IconButton
                          type="button"
                          aria-label="Mesaj gönder"
                          icon={<ArrowUpIcon />}
                          isLoading={isLoading || isUploading}
                          disabled={(!input.trim() && attachedFiles.length === 0) || isUploading || isLoading}
                          onClick={(e) => {
                            // Trigger form submit programmatically (single call)
                            e.preventDefault();
                            e.stopPropagation();
                            const form = e.currentTarget.closest('form');
                            if (form) {
                              form.requestSubmit(); // This triggers onSubmit once
                            }
                          }}
                          size="md"
                          bg={accentPrimary}
                          color={userMessageText}
                          borderRadius="lg"
                          minW="40px"
                          h="40px"
                          fontWeight="500"
                          _hover={{
                            bg: accentHover,
                            transform: "translateY(-2px) scale(1.05)",
                            boxShadow: "0 4px 12px rgba(63, 185, 80, 0.4)",
                          }}
                          _active={{
                            bg: accentActive,
                            transform: "translateY(0) scale(0.95)",
                          }}
                          transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                          sx={{
                            "&:hover": {
                              animation: "pulseScale 0.6s ease-in-out",
                            },
                            "&:active": {
                              animation: "scaleOut 0.2s ease-out",
                            },
                            animation: isLoading && abortController
                              ? "buttonTransitionOut 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                              : "none",
                            "@keyframes buttonTransitionOut": {
                              "0%": {
                                opacity: 1,
                                transform: "scale(1) rotate(0deg)",
                              },
                              "100%": {
                                opacity: 0,
                                transform: "scale(0.8) rotate(90deg)",
                              },
                            },
                          }}
                          _disabled={{
                            opacity: 0.5,
                            cursor: "not-allowed",
                            bg: accentActive,
                          }}
                        />
                      )}
                    </Box>
                  </HStack>
                </Box>
              </form>
            </Box>
          </Box>
        </Box>
      </Box >

      {/* Document Picker Modal - Global Document Pool */}
      <DocumentPicker
        isOpen={isDocModalOpen}
        onClose={onDocModalClose}
        chatId={currentChatId || undefined}
        promptModule={selectedModule}
        onSelect={async (documentIds) => {
          // Update selected document IDs
          setSelectedDocumentIds(documentIds);

          // CRITICAL FIX: Also add selected documents to attachedFiles
          // This ensures they appear in chips and are included in handleSend
          if (documentIds.length > 0) {
            // Reload availableDocuments if needed
            let docsToUse = availableDocuments;
            const missingDocIds = documentIds.filter(
              (docId) => !availableDocuments.find((d) => d.id === docId)
            );

            if (missingDocIds.length > 0 || availableDocuments.length === 0) {
              try {
                // PASS the current module to listDocuments to find LGS-specific documents
                docsToUse = await listDocuments(selectedModule);
                setAvailableDocuments(docsToUse);
              } catch (error) {
                console.error("Failed to reload documents:", error);
              }
            }

            // Convert selected document IDs to AttachedFile format
            const newAttachedFiles: AttachedFile[] = documentIds
              .map((docId) => {
                const doc = docsToUse.find((d) => d.id === docId);
                if (!doc) {
                  return null;
                }
                // Create a temporary file object for AttachedFile interface
                const tempFile = new File([], doc.filename, { type: doc.mime_type || "unknown" });
                return {
                  id: `doc_${docId}`, // Unique ID for selected document
                  name: doc.filename,
                  type: doc.mime_type || "unknown",
                  size: doc.size || 0,
                  file: tempFile,
                  documentId: docId, // Already has documentId
                  isUploading: false, // Already uploaded
                } as AttachedFile;
              })
              .filter((f): f is AttachedFile => f !== null);

            // Upsert to attachedFiles (don't duplicate if already exists)
            setAttachedFilesSync((prev) => {
              const existingIds = new Set(prev.map(f => f.documentId));
              const uniqueNewFiles = newAttachedFiles.filter(f => f.documentId && !existingIds.has(f.documentId));
              return [...prev, ...uniqueNewFiles];
            });
          } else {
            // If no documents selected, remove all document-based attachedFiles
            // (keep only newly uploaded files)
            setAttachedFilesSync((prev) => prev.filter(f => !f.id.startsWith('doc_')));
          }

          // Save to chat settings (persist selection)
          const chatId = searchParams.get("chatId");
          if (chatId) {
            try {
              const stored = localStorage.getItem(`chat_settings_${chatId}`);
              const currentSettings = stored ? JSON.parse(stored) : {};
              localStorage.setItem(`chat_settings_${chatId}`, JSON.stringify({
                selectedDocumentIds: documentIds,
                uploadedDocuments: currentSettings.uploadedDocuments || [], // uploadedDocuments'ı koru
              }));
            } catch (error) {
              console.error("Failed to save document selection:", error);
            }
          }

          // Input'a otomatik focus yap (kullanıcı fareyle tıklamak zorunda kalmasın)
          setTimeout(() => {
            if (inputRef.current) {
              inputRef.current.focus();
            }
          }, 100);
        }}
        selectedDocumentIds={selectedDocumentIds}
      />
    </AuthGuard >
  );
}

export default ChatPage;
