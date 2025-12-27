"use client";

import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
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
} from "@chakra-ui/react";
import { ArrowUpIcon, AddIcon, AttachmentIcon } from "@chakra-ui/icons";
import { FaFilePdf, FaFileWord, FaFileAlt, FaEnvelope, FaCopy, FaInfoCircle } from "react-icons/fa";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { apiFetch, uploadDocument, DocumentUploadResponse, listDocuments, DocumentListItem, createChat, listChats, getGenerationRun, cancelGenerationRun, GenerationRunStatus, getChatMessages, sendChatMessage, SendChatMessageRequest } from "@/lib/api";
import { useToast } from "@chakra-ui/react";
import { useSidebar } from "@/contexts/SidebarContext";
import DocumentPicker from "@/components/DocumentPicker";
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
  status?: "cancelled" | "completed"; // ChatGPT style: cancelled messages stay visible
  sources?: SourceInfo[];
  client_message_id?: string; // For duplicate detection
  attachments?: {
    id: string;
    filename: string;
    type: string;
    size: number;
    documentId?: string;
  }[];
}

interface SourceInfo {
  documentId: string;
  filename: string;
  chunkIndex: number;
  score: number;
  preview: string;
}

interface ChatResponse {
  message: string;
  role: "assistant";
  chatId?: string; // Backend may return chatId for new chats
  sources?: SourceInfo[];
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
  const superscripts: Record<string, string> = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
  };
  for (const [unicode, num] of Object.entries(superscripts)) {
    const escapedUnicode = unicode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    result = result.replace(
      new RegExp(`([a-zA-Z0-9)]+)${escapedUnicode}`, 'g'),
      `$$$$1^{${num}}$$`
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
      `$$$$1_{${num}}$$`
    );
  }
  
  // Math operators
  result = result.replace(/×/g, '$\\times$');
  result = result.replace(/÷/g, '$\\div$');
  result = result.replace(/±/g, '$\\pm$');
  result = result.replace(/≠/g, '$\\neq$');
  result = result.replace(/≤/g, '$\\leq$');
  result = result.replace(/≥/g, '$\\geq$');
  
  // Step 3: Restore protected LaTeX blocks
  // CRITICAL FIX: Use replaceAll with escaped $ to prevent $$ from being treated as special character
  // JavaScript replace() treats $$ as escape sequence - we must use replaceAll or escape the $
  for (let i = protectedBlocks.length - 1; i >= 0; i--) {
    // Use split+join instead of replace to avoid $$ escape issues
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
 * 3. Unicode → LaTeX conversion (Layer 2)
 * 4. Protect code blocks from math rendering
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
  
  // B) Inline math: $...$ (but NOT $$)
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
// CRITICAL: isStreaming=false iken kullanılmalı (tam delimiter'lar için)
function MessageContent({ content, isStreaming = false }: { content: string; isStreaming?: boolean }) {
  // STREAMING GUARD: Check if message is incomplete (yarım mesajlar)
  // This prevents rendering broken math during streaming
  const isIncomplete = !isStreaming && (() => {
    // Check 1: Odd number of backslashes at end (incomplete escape)
    if (content.endsWith('\\')) {
      const trailingBackslashes = content.match(/\\+$/)?.[0].length || 0;
      if (trailingBackslashes % 2 !== 0) {
        return true;
      }
    }
    
    // Check 2: Odd number of $$ (unmatched block delimiter)
    const dollarPairs = (content.match(/\$\$/g) || []).length;
    if (dollarPairs % 2 !== 0) {
      return true;
    }
    
    // Check 3: Incomplete \sqrt{ or other LaTeX commands
    const openBraces = (content.match(/\\sqrt\{/g) || []).length;
    const closeBraces = (content.match(/\\sqrt\{[^}]*\}/g) || []).length;
    if (openBraces > closeBraces) {
      return true;
    }
    
    return false;
  })();
  
  // If incomplete, show as plain text (no KaTeX render)
  if (isIncomplete) {
    return (
      <Box fontSize="14px" lineHeight="1.6" color="gray.600">
        <Text fontFamily="monospace" whiteSpace="pre-wrap">
          {content}
        </Text>
        <Text fontSize="xs" color="orange.500" mt={1}>
          ⚠️ Mesaj henüz tamamlanmadı, render bekleniyor...
        </Text>
      </Box>
    );
  }
  
  // Normalize math before rendering (only when not streaming)
  const normalizedContent = isStreaming ? content : normalizeMath(content);
  const contentRef = useRef<HTMLDivElement>(null);
  

  // PROOF: Check if KaTeX CSS is loaded and verify computed styles
  useEffect(() => {
    if (isStreaming || typeof window === 'undefined') return;
    
    const shouldCheck = process.env.NODE_ENV === 'development' || 
                        (typeof window !== 'undefined' && (window as any).__MATH_DEBUG__);
    
    if (!shouldCheck) return;

    // Wait for DOM to update after ReactMarkdown renders
    const timeoutId = setTimeout(() => {
      if (!contentRef.current) return;

      // Check if katex.min.css is loaded
      const katexStylesheet = Array.from(document.styleSheets).find(sheet => {
        try {
          return sheet.href?.includes('katex.min.css') || 
                 sheet.ownerNode?.textContent?.includes('KaTeX');
        } catch (e) {
          return false;
        }
      });

      // Find KaTeX elements in the rendered content
      const katexElements = contentRef.current.querySelectorAll('.katex');
      
      if (katexElements.length > 0) {
        const firstKatex = katexElements[0] as HTMLElement;
        const computedStyle = window.getComputedStyle(firstKatex);
        const fontFamily = computedStyle.fontFamily;
        const display = computedStyle.display;
        const whiteSpace = computedStyle.whiteSpace;
        const lineHeight = computedStyle.lineHeight;

      }
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [content, isStreaming]);

  // STREAMING: Plain text göster (math parse etme - yarım delimiter'lar parçalanır)
  // KRİTİK FIX #1: Streaming sırasında KaTeX render KAPALI
  // IMPROVEMENT: Mask unmatched LaTeX delimiters during streaming
  if (isStreaming) {
    
    // Mask unmatched LaTeX delimiters to improve streaming appearance
    // Hide any unmatched $ or $$ delimiters and their content until completion
    const maskUnmatchedDelimiters = (text: string): string => {
      let result = '';
      let i = 0;
      let inInlineMath = false;
      let inBlockMath = false;
      let mathStart = -1;
      
      while (i < text.length) {
        // Check for block math delimiter $$
        if (i < text.length - 1 && text[i] === '$' && text[i + 1] === '$') {
          if (inBlockMath) {
            // Closing $$ found - show everything from mathStart to here
            result += text.slice(mathStart, i + 2);
            inBlockMath = false;
            mathStart = -1;
            i += 2;
          } else {
            // Opening $$ found
            if (inInlineMath) {
              // Close inline math first (unmatched, so don't show it)
              inInlineMath = false;
              mathStart = -1;
            }
            inBlockMath = true;
            mathStart = i;
            i += 2;
          }
          continue;
        }
        
        // Check for inline math delimiter $
        if (text[i] === '$') {
          if (inInlineMath) {
            // Closing $ found - show everything from mathStart to here
            result += text.slice(mathStart, i + 1);
            inInlineMath = false;
            mathStart = -1;
            i += 1;
          } else if (!inBlockMath) {
            // Opening $ found (not inside block math)
            inInlineMath = true;
            mathStart = i;
            i += 1;
          } else {
            // $ inside block math - treat as regular character, continue collecting
            i += 1;
          }
          continue;
        }
        
        // Regular character
        if (!inInlineMath && !inBlockMath) {
          // Not in math - show character
          result += text[i];
        }
        // If in math, don't add to result yet (wait for closing delimiter)
        i += 1;
      }
      
      // If still in math at the end, don't show the unmatched portion
      // (mathStart to end is hidden)
      
      return result;
    };
    
    const maskedContent = maskUnmatchedDelimiters(normalizedContent);
    
    return (
      <Text 
        whiteSpace="pre-wrap" 
        wordBreak="normal"
        lineHeight="1.6"
        color="inherit"
      >
        {maskedContent}
      </Text>
    );
  }

  // COMPLETE: Full markdown + math render
  // KRİTİK FIX #2: remark-math + rehype-katex bağlantısı doğrulandı
  // DOĞRULAMA: Paketler kurulu ve bağlı
  // - remark-math@6.0.0 ✅
  // - rehype-katex@7.0.1 ✅
  // - react-markdown@10.1.0 ✅
  // - katex@0.16.27 ✅
  
  
  return (
    <Box
      ref={contentRef}
      className="messageContent"
      sx={{
        // CRITICAL FIX: Remove top spacing for assistant messages
        marginTop: '0 !important',
        paddingTop: '0 !important',
        // CRITICAL: No vertical scroll in message content - only main list scrolls
        overflow: 'visible',
        overflowY: 'visible',
        overflowX: 'visible',
        // Hide webkit scrollbar buttons everywhere inside message content
        '& ::-webkit-scrollbar-button': {
          display: 'none !important',
          width: '0 !important',
          height: '0 !important',
        },
        // Hide scrollbar buttons in KaTeX elements
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
        // ChatGPT style: Clean, readable, no column splits
        '& p': {
          marginBottom: '1.15em',
          lineHeight: '1.6', // Readable line height for markdown content
          whiteSpace: 'normal',
          wordWrap: 'normal',
          color: 'inherit', // Ensure text color inherits from parent (user: white, assistant: inherit)
        },
        '& p:first-of-type': {
          marginTop: 0,
        },
        '& p:last-child': {
          marginBottom: 0,
        },
        // KaTeX block math styling - ChatGPT style
        // ONLY .katex-display may have overflow-x:auto (for wide equations)
        '& .katex-display': {
          display: 'block',
          margin: '1em 0 !important',
          overflowX: 'auto', // Only horizontal scroll for wide equations
          overflowY: 'hidden !important', // CRITICAL: NO vertical scroll - prevents ▲▼ buttons
          textAlign: 'center',
          padding: '0.75em 0.25em',
          whiteSpace: 'normal !important', // CRITICAL: nowrap breaks KaTeX vertical layout
          wordBreak: 'normal !important',
          overflowWrap: 'normal !important',
          // CRITICAL: Prevent any height constraints that could cause scroll
          maxHeight: 'none !important',
          height: 'auto !important',
          // CRITICAL: Hide scrollbar buttons in KaTeX display - ALL VARIATIONS
          '& ::-webkit-scrollbar-button': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
            background: 'transparent !important',
            border: 'none !important',
            padding: '0 !important',
            margin: '0 !important',
          },
          '& ::-webkit-scrollbar-button:start:decrement': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
          },
          '& ::-webkit-scrollbar-button:end:increment': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
          },
          '& ::-webkit-scrollbar-button:vertical:start:decrement': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
          },
          '& ::-webkit-scrollbar-button:vertical:end:increment': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
          },
          '& ::-webkit-scrollbar-button:horizontal:start:decrement': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
          },
          '& ::-webkit-scrollbar-button:horizontal:end:increment': {
            display: 'none !important',
            width: '0 !important',
            height: '0 !important',
          },
          // CRITICAL: Hide vertical scrollbar completely
          '& ::-webkit-scrollbar:vertical': {
            display: 'none !important',
            width: '0 !important',
          },
        },
        // KaTeX inline math styling - ChatGPT style
        '& .katex:not(.katex-display > .katex)': {
          fontSize: '1em',
          lineHeight: '1.2', // Proper line height for KaTeX vertical layout
          whiteSpace: 'normal !important', // CRITICAL: nowrap breaks KaTeX vertical layout (vlist/msupsub)
          wordBreak: 'normal !important',
          overflowWrap: 'normal !important',
        },
        // Ensure KaTeX internal elements can use their own line metrics
        '& .katex *': {
          lineHeight: 'inherit',
        },
        // Prevent text splitting/columns - CRITICAL
        // BUT: KaTeX elementlerine dokunma
        '& *:not(.katex):not(.katex *)': {
          maxWidth: '100%',
          wordWrap: 'normal', // break-word LaTeX'i parçalar
        },
        // Ensure no column layout
        '&': {
          columnCount: 'unset !important',
          columns: 'unset !important',
        },
        // First heading should have no top margin
        '& > .markdown-heading:first-of-type': {
          marginTop: '0 !important',
        },
        '& > h1:first-of-type, & > h2:first-of-type, & > h3:first-of-type, & > h4:first-of-type, & > h5:first-of-type, & > h6:first-of-type': {
          marginTop: '0 !important',
        },
        // Preserve line breaks in code blocks
        '& pre': {
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflowX: 'auto',
          overflowY: 'visible', // CRITICAL: No vertical scroll in code blocks
          maxHeight: 'none !important', // Prevent height constraints
        },
        // List styling
        '& ul, & ol': {
          marginLeft: '1.5em',
          marginBottom: '0.75em',
        },
        '& li': {
          marginBottom: '0.25em',
        },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkMath]} // KRİTİK: Math delimiter'ları algılar ($ ve $$)
        rehypePlugins={[rehypeKatex]} // KRİTİK: LaTeX'i KaTeX'e dönüştürür
        components={{
          // KRİTİK FIX: Custom component'ler math node'larını parçalayabilir
          // ReactMarkdown'ın default component'lerini kullan, sadece CSS ile styling yap
          // p component'ini override etme - math node'ları için default davranışı koru
          // Customize headings (preserve markdown structure)
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
          // Customize lists (preserve markdown structure)
          ul: ({ children }) => (
            <Box as="ul" ml={6} mb={3} listStyleType="disc">
              {children}
            </Box>
          ),
          ol: ({ children }) => (
            <Box as="ol" ml={6} mb={3} listStyleType="decimal">
              {children}
            </Box>
          ),
          li: ({ children }) => (
            <Text as="li" mb={1} lineHeight="1.7">
              {children}
            </Text>
          ),
          // Customize code blocks
          code: ({ className, children, ...props }: any) => {
            const isInline = !className;
            if (isInline) {
              return (
                <Box
                  as="code"
                  bg="gray.700"
                  px={1.5}
                  py={0.5}
                  borderRadius="sm"
                  fontSize="0.9em"
                  display="inline"
                  {...props}
                >
                  {children}
                </Box>
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
        {normalizedContent}
      </ReactMarkdown>
    </Box>
  );
}

// FileChip Component - ChatGPT style with loading animation
function FileChip({ file, onRemove, isUploading }: { file: AttachedFile; onRemove: () => void; isUploading?: boolean }) {
  return (
    <Box
      display="inline-flex"
      alignItems="center"
      gap={2}
      px={3}
      py={1.5}
      bg="gray.600"
      borderRadius="full"
      maxW="200px"
      animation="slideDown 0.2s ease"
      sx={{
        "@keyframes slideDown": {
          "0%": { opacity: 0, transform: "translateY(-5px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
      }}
    >
      {isUploading ? (
        <Spinner 
          size="xs" 
          color="green.500"
          thickness="3px"
          speed="0.8s"
          sx={{
            animation: "rotate 1s linear infinite",
          }}
        />
      ) : (
        <Box
          w="16px"
          h="16px"
          bg="blue.500"
          borderRadius="sm"
          display="flex"
          alignItems="center"
          justifyContent="center"
          flexShrink={0}
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </Box>
      )}
      <Text
        fontSize="xs"
        color="white"
        isTruncated
        flex={1}
        minW={0}
      >
        {file.name}
      </Text>
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
      maxW="200px"
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
        aria-label="Dokümanı kaldır"
        size="xs"
        variant="ghost"
        onClick={onRemove}
        minW="auto"
        h="auto"
        p={0}
        _hover={{ bg: "rgba(255,255,255,0.4)" }}
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
  
  // CRITICAL FIX: Sync attachedFiles state to ref SYNCHRONOUSLY
  // Instead of useEffect (async), update ref directly in setAttachedFiles calls
  // This ensures ref is always in sync when handleSend is called
  useEffect(() => {
    attachedFilesRef.current = attachedFiles;
  }, [attachedFiles]);
  
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
  }

  interface ChatData {
    messageIds: string[];
  }

  // Normalize edilmiş store
  const storeRef = useRef<{
    chats: Map<string, ChatData>;
    messages: Map<string, NormalizedMessage>;
    runs: Map<string, Run>;
  }>({
    chats: new Map(),
    messages: new Map(),
    runs: new Map(),
  });

  // Idempotency: Inflight requests Set (duplicate gönderim engelleme)
  const inflightRequestsRef = useRef<Set<string>>(new Set());
  // Send lock: prevents double-trigger (Enter + button / rapid clicks)
  const sendLockRef = useRef<boolean>(false);

  // Store helper functions
  const getChatMessageIds = (chatId: string): string[] => {
    const chat = storeRef.current.chats.get(chatId);
    return chat ? [...chat.messageIds] : [];
  };

  const getMessage = (messageId: string): NormalizedMessage | undefined => {
    return storeRef.current.messages.get(messageId);
  };

  const getChatMessagesFromStore = (chatId: string): NormalizedMessage[] => {
    const messageIds = getChatMessageIds(chatId);
    return messageIds
      .map(id => getMessage(id))
      .filter((msg): msg is NormalizedMessage => msg !== undefined)
      .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
  };

  const addMessage = (message: NormalizedMessage) => {
    // CRITICAL: Prevent duplicate messages
    const existingMessage = storeRef.current.messages.get(message.id);
    if (existingMessage) {
      console.warn("[DUPLICATE_PREVENTION] Message already exists:", message.id);
      return; // Don't add duplicate
    }
    
    storeRef.current.messages.set(message.id, message);
    const chat = storeRef.current.chats.get(message.chatId);
    if (chat) {
      if (!chat.messageIds.includes(message.id)) {
        chat.messageIds.push(message.id);
      }
    } else {
      storeRef.current.chats.set(message.chatId, { messageIds: [message.id] });
    }
  };

  const updateMessage = (messageId: string, updates: Partial<NormalizedMessage>) => {
    const message = storeRef.current.messages.get(messageId);
    if (message) {
      storeRef.current.messages.set(messageId, { ...message, ...updates });
    }
  };

  const getRun = (runId: string): Run | undefined => {
    return storeRef.current.runs.get(runId);
  };

  const getRunByRequestId = (requestId: string): Run | undefined => {
    for (const run of storeRef.current.runs.values()) {
      if (run.requestId === requestId) {
        return run;
      }
    }
    return undefined;
  };

  const addRun = (run: Run) => {
    storeRef.current.runs.set(run.runId, run);
  };

  const updateRun = (runId: string, updates: Partial<Run>) => {
    const run = storeRef.current.runs.get(runId);
    if (run) {
      storeRef.current.runs.set(runId, { ...run, ...updates });
    }
  };

  const removeRun = (runId: string) => {
    storeRef.current.runs.delete(runId);
  };

  // Sync store to local state for active chat
  const syncStoreToLocalState = (chatId: string | null) => {
    if (!chatId) {
      setMessages([]);
      setStreamingContent("");
      setIsLoading(false);
      return;
    }

    const messages = getChatMessagesFromStore(chatId);
    const activeRun = Array.from(storeRef.current.runs.values()).find(
      r => r.chatId === chatId && r.status === "running"
    );

    // Convert normalized messages to legacy format for compatibility
    const legacyMessages: (Message & { _isStreaming?: boolean })[] = messages.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      timestamp: msg.createdAt,
      status: msg.status === "cancelled" ? "cancelled" : msg.status === "completed" ? "completed" : undefined,
      sources: msg.sources,
      client_message_id: msg.client_message_id,
      attachments: msg.attachments,
      // Add streaming status for typing indicator
      _isStreaming: msg.status === "streaming", // Internal flag for typing indicator
    }));

    setMessages(legacyMessages);

    // Set abort controller if there's an active run
    if (activeRun) {
      setAbortController(activeRun.abortController);
      setIsLoading(activeRun.status === "running");
    } else {
      setAbortController(null);
      setIsLoading(false);
    }
  };

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

    const legacyMessages: (Message & { _isStreaming?: boolean })[] = messages.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      timestamp: msg.createdAt,
      status: msg.status === "cancelled" ? "cancelled" : msg.status === "completed" ? "completed" : undefined,
      sources: msg.sources,
      client_message_id: msg.client_message_id,
      attachments: msg.attachments,
      // Add streaming status for typing indicator
      _isStreaming: msg.status === "streaming", // Internal flag for typing indicator
    }));

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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Profesyonel tema renk sistemi - GitHub tarzı, yeşil accent
  // Zemin & Yüzeyler (tema-aware)
  const bgColor = useColorModeValue("#FFFFFF", "#0D1117");
  const panelBg = useColorModeValue("#F6F8FA", "#161B22");
  const innerBg = useColorModeValue("#F0F3F6", "#1C2128");
  const hoverBg = useColorModeValue("#E7ECF0", "#22272E");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  
  // Yeşil Accent (tema-aware)
  const accentPrimary = useColorModeValue("#1A7F37", "#3FB950");
  const accentHover = useColorModeValue("#2EA043", "#2EA043");
  const accentActive = useColorModeValue("#238636", "#238636");
  const accentSoft = useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)");
  const accentBorder = useColorModeValue("rgba(26, 127, 55, 0.25)", "rgba(63, 185, 80, 0.3)");
  
  // Mesaj renkleri (tema-aware)
  const messageBg = panelBg; // Asistan mesaj arka plan
  const userMessageBg = useColorModeValue("#D4EDDA", "#3FB950"); // Kullanıcı mesaj arka plan (light: açık yeşil, dark: yeşil)
  const userMessageText = useColorModeValue("#1F2328", "#0D1117"); // Kullanıcı mesaj metin rengi
  const assistantMessageText = useColorModeValue("#1F2328", "#E6EDF3"); // Asistan mesaj metin rengi
  
  // Metin renkleri (tema-aware)
  const textPrimary = useColorModeValue("#1F2328", "#E6EDF3");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const textPlaceholder = useColorModeValue("#8B949E", "#6E7681");
  const textDisabled = useColorModeValue("#B1BAC4", "#484F58");
  // All color mode values - must be at top level to avoid hook order issues
  const attachmentBg = useColorModeValue("rgba(255,255,255,0.1)", "rgba(0,0,0,0.2)");
  const attachmentBorder = useColorModeValue("rgba(255,255,255,0.2)", "rgba(255,255,255,0.1)");
  const sidebarToggleColor = useColorModeValue("gray.700", "gray.200");
  const sidebarToggleBg = useColorModeValue("white", "gray.800");
  const sidebarToggleBorder = useColorModeValue("gray.200", "gray.700");
  const sidebarToggleHoverBg = useColorModeValue("gray.50", "gray.700");
  const sidebarToggleHoverColor = useColorModeValue("gray.900", "white");
  const sidebarToggleHoverBorder = useColorModeValue("gray.300", "gray.600");
  const systemMessageColor = useColorModeValue("gray.500", "gray.400");
  // Source badge renkleri - yeşil accent sistemi
  const sourceTitleColor = accentPrimary; // Yeşil accent
  const sourceBg = accentSoft; // Soft highlight
  const sourceTextColor = textSecondary; // İkincil metin
  const sourcePreviewColor = textPlaceholder; // Placeholder rengi
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
  const loadChatMessages = async (chatId: string) => {
    try {
      console.log("[CHATDBG] loadChatMessages chatId=" + chatId + " userId=unknown status=loading");
      // Preserve streaming messages
      const existingMessageIds = getChatMessageIds(chatId);
      const streamingIds = existingMessageIds.filter(id => {
        const msg = getMessage(id);
        return msg && msg.status === "streaming";
      });
      
      // Load from backend
      const cursorToUse = chatId === currentChatId ? messageCursor : null;
      const backendResponse = await getChatMessages(chatId, 50, cursorToUse);
      console.log("[CHATDBG] loadChatMessages chatId=" + chatId + " userId=unknown count=" + (backendResponse.messages?.length || 0) + " status=loaded");
      
      setMessageCursor(backendResponse.cursor || null);
      setHasMoreMessages(backendResponse.has_more);
      
      // Clear non-streaming messages
      existingMessageIds.forEach(id => {
        const msg = getMessage(id);
        if (msg && msg.status !== "streaming") {
          storeRef.current.messages.delete(id);
        }
      });
      
      // Add backend messages to store
      const newMessageIds: string[] = [];
      if (backendResponse.messages && backendResponse.messages.length > 0) {
        backendResponse.messages.forEach((msg) => {
          const existingMsg = getMessage(msg.message_id);
          if (existingMsg && existingMsg.status === "streaming") {
            return; // Preserve streaming message
          }
          
          if (storeRef.current.messages.has(msg.message_id)) {
            newMessageIds.push(msg.message_id);
            return;
          }
          
          const normalizedMsg: NormalizedMessage = {
            id: msg.message_id,
            chatId: chatId,
            role: msg.role,
            content: msg.content,
            createdAt: new Date(msg.created_at),
            status: "completed",
            sources: msg.sources,
            client_message_id: msg.client_message_id,
          };
          
          storeRef.current.messages.set(normalizedMsg.id, normalizedMsg);
          newMessageIds.push(normalizedMsg.id);
        });
      }
      
      // Rebuild chat's messageIds list
      const allMessageIds = [...new Set([...streamingIds, ...newMessageIds])];
      const sortedMessageIds = allMessageIds.sort((a, b) => {
        const msgA = getMessage(a);
        const msgB = getMessage(b);
        if (!msgA || !msgB) return 0;
        return msgA.createdAt.getTime() - msgB.createdAt.getTime();
      });
      
      storeRef.current.chats.set(chatId, { messageIds: sortedMessageIds });
      
      // Update React state
      // CRITICAL FIX: Don't clear messages if backend returns 0 - preserve optimistic messages
      // Always sync from store (which may contain optimistic messages)
      const loadedMessages = getChatMessagesFromStore(chatId);
      const legacyMessages: (Message & { _isStreaming?: boolean })[] = loadedMessages.map(msg => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        timestamp: msg.createdAt,
        status: msg.status === "cancelled" ? "cancelled" : msg.status === "completed" ? "completed" : undefined,
        sources: msg.sources,
        client_message_id: msg.client_message_id,
        attachments: msg.attachments,
        _isStreaming: msg.status === "streaming",
      }));
      // Always set messages from store (even if empty) - don't clear optimistic messages
      setMessages(legacyMessages);
      
      syncStoreToLocalState(chatId);
    } catch (error) {
      console.error("Failed to load chat messages:", error);
    }
  };
  
  // Sync store to local state when currentChatId changes
  useEffect(() => {
    if (currentChatId) {
    syncStoreToLocalState(currentChatId);
    }
  }, [currentChatId]);

  // Sohbet değiştiğinde state'i yükle - eski sohbetin stream'ini durdurma
  useEffect(() => {
    const urlChatId = params?.chatId as string | undefined;
    
    if (urlChatId && isValidObjectId(urlChatId) && urlChatId !== currentChatId) {
      // Yeni sohbetin state'ini yükle
      setCurrentChatId(urlChatId);
      loadChatMessages(urlChatId);
      loadChatSettings(urlChatId);
      
      // CRITICAL: Sync store to local state after a short delay
      // This ensures any background streaming updates from other chats are visible
      // when user switches back to a chat that was streaming in background
      setTimeout(() => {
        syncStoreToLocalState(urlChatId);
      }, 100);
      
      // Check for pending runs
      const checkPendingRuns = async (chatId: string) => {
        let pollInterval: NodeJS.Timeout | null = null;
        try {
          const pendingRunKey = `pending_run_${chatId}`;
          const pendingRunId = localStorage.getItem(pendingRunKey);
          
          if (pendingRunId) {
            // CRITICAL FIX: Check run status immediately before starting polling
            // If run doesn't exist (404), clean up and don't start polling
            try {
              const initialStatus = await getGenerationRun(pendingRunId);
              
              // Run exists, start polling
              pollInterval = setInterval(async () => {
                try {
                  const runStatus = await getGenerationRun(pendingRunId);
                  
                  if (runStatus.status === "completed" && runStatus.completed_text) {
                    if (pollInterval) clearInterval(pollInterval);
                    localStorage.removeItem(pendingRunKey);
                    
                    // REMOVED: Don't create new assistant message here
                    // The message should already exist in store from handleSend
                    // Just update it if it exists
                    const existingMessage = getMessage(runStatus.message_id);
                    if (existingMessage) {
                      updateMessage(runStatus.message_id, {
                        content: runStatus.completed_text,
                        status: "completed",
                      });
                      syncStoreToLocalState(chatId);
                    }
                  } else if (runStatus.status === "failed" || runStatus.status === "cancelled") {
                    if (pollInterval) clearInterval(pollInterval);
                    localStorage.removeItem(pendingRunKey);
                  }
                } catch (error: any) {
                  if (error && typeof error === "object" && "code" in error && error.code === "RUN_NOT_FOUND") {
                    if (pollInterval) clearInterval(pollInterval);
                    localStorage.removeItem(pendingRunKey);
                    return;
                  }
                  console.error(`[BACKGROUND] Error polling run ${pendingRunId}:`, error);
                }
              }, 2000);
            } catch (error: any) {
              // Run not found (404) - clean up and don't start polling
              if (error && typeof error === "object" && "code" in error && error.code === "RUN_NOT_FOUND") {
                localStorage.removeItem(pendingRunKey);
                return; // Silently exit
              }
              // Other errors - log but don't start polling
              console.error(`[BACKGROUND] Error checking initial run status ${pendingRunId}:`, error);
            }
          }
        } catch (error) {
          console.error("[BACKGROUND] Error checking pending runs:", error);
        }
        
        // Cleanup on unmount
        return () => {
          if (pollInterval) clearInterval(pollInterval);
        };
      };
      
      checkPendingRuns(urlChatId);
      
      // Save to localStorage
      try {
        localStorage.setItem("current_chat_id", urlChatId);
      } catch (error) {
        console.error("Failed to save current chat ID:", error);
      }
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
        const docs = await listDocuments();
        setAvailableDocuments(docs);
      } catch (error) {
        console.error("Failed to load available documents:", error);
        // Don't show toast, just log error
      }
    };
    loadAvailableDocuments();
  }, []);

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
  const getOrCreateChatId = async (): Promise<string> => {
    const existingChatId = getChatId();
    if (existingChatId) {
      return existingChatId;
    }
    // Create new chat if doesn't exist
    const newChat = await createChat();
    router.push(`/chat/${newChat.id}`);
    return newChat.id;
  };
  
  // Handle chatId from URL - don't create chat if not present
  // Chat will be created when first message is sent
  useEffect(() => {
    const chatId = getChatId();
    if (chatId && chatId !== currentChatId) {
      setCurrentChatId(chatId);
      loadChatMessages(chatId);
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
              console.warn(`Failed to parse checkpoint ${key}:`, error);
            }
          }
          
          if (latestCheckpoint && latestCheckpoint.chatId) {
            
            // Load chat messages first
            loadChatMessages(latestCheckpoint.chatId);
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
                const response = await apiFetch<ChatResponse>("/api/chat", {
                  method: "POST",
                  body: JSON.stringify({
                    message: latestCheckpoint.message,
                    chatId: latestCheckpoint.chatId,
                    client_message_id: requestId,
                    mode: "qa",
                  }),
                });
                
                // REMOVED: Checkpoint resume no longer creates new messages
                // The message should already exist in store from original handleSend
                // Just update it if it exists
                const existingRun = getRunByRequestId(requestId);
                if (existingRun) {
                  await streamMessage(response.message, existingRun.runId, response.sources, undefined);
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
                
                if (runStatus.status === "completed" && runStatus.completed_text) {
                  // Run completed - update existing message in store
                  if (pollInterval) clearInterval(pollInterval);
                  localStorage.removeItem(pendingRunKey);
                  
                  // REMOVED: Don't create new assistant message here
                  // The message should already exist in store from handleSend
                  // Just update it if it exists
                  const existingMessage = getMessage(runStatus.message_id);
                  if (existingMessage) {
                    updateMessage(runStatus.message_id, {
                      content: runStatus.completed_text,
                      status: "completed",
                    });
                    syncStoreToLocalState(chatId);
                  }
                  
                } else if (runStatus.status === "failed" || runStatus.status === "cancelled") {
                  // Run failed or cancelled
                  if (pollInterval) clearInterval(pollInterval);
                  localStorage.removeItem(pendingRunKey);
                }
                // If still running, continue polling
              } catch (error: any) {
                // If run not found, stop polling silently
                if (error && typeof error === "object" && "code" in error && error.code === "RUN_NOT_FOUND") {
                  if (pollInterval) clearInterval(pollInterval);
                  localStorage.removeItem(pendingRunKey);
                  return; // Silently exit, don't log
                }
                // Only log other errors
                console.error(`[BACKGROUND] Error polling run ${pendingRunId}:`, error);
              }
            }, 2000); // Poll every 2 seconds
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

    const handleLoadChat = (e: CustomEvent) => {
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
    };

    const handleNewChat = async () => {
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
    };

    const handleChatDeleted = (e: CustomEvent) => {
      // Focus input after chat is deleted
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
    };

    window.addEventListener("newChat", handleNewChat);
    window.addEventListener("loadChat", handleLoadChat as EventListener);
    window.addEventListener("chatDeleted", handleChatDeleted as EventListener);
    
    return () => {
      window.removeEventListener("newChat", handleNewChat);
      window.removeEventListener("loadChat", handleLoadChat as EventListener);
      window.removeEventListener("chatDeleted", handleChatDeleted as EventListener);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params?.chatId]);

  // Save messages whenever they change
  useEffect(() => {
    if (currentChatId && messages.length > 0) {
      saveChatMessages(currentChatId, messages);
    }
  }, [messages, currentChatId]);

  // Auto-focus input after message sent or file upload completed
  useEffect(() => {
    if (!isLoading && !isUploading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading, isUploading, messages]);

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
        
        // Cursor pagination: Load older messages when scrolling to top
        if (scrollTop < 100 && hasMoreMessages && !isLoadingOlderMessages && currentChatId) {
          setIsLoadingOlderMessages(true);
          try {
            const oldScrollHeight = el.scrollHeight;
            const backendResponse = await getChatMessages(currentChatId, 50, messageCursor);
            
            if (backendResponse.messages && backendResponse.messages.length > 0) {
              // Prepend older messages to store
              const olderMessageIds: string[] = [];
              backendResponse.messages.forEach((msg) => {
                const normalizedMsg: NormalizedMessage = {
                  id: msg.message_id,
                  chatId: currentChatId,
                  role: msg.role,
                  content: msg.content,
                  createdAt: new Date(msg.created_at),
                  status: "completed",
                  sources: msg.sources,
                  client_message_id: msg.client_message_id,
                };
                
                if (!storeRef.current.messages.has(normalizedMsg.id)) {
                  storeRef.current.messages.set(normalizedMsg.id, normalizedMsg);
                  olderMessageIds.push(normalizedMsg.id);
                }
              });
              
              // Update chat's messageIds list (prepend older messages)
              const currentMessageIds = getChatMessageIds(currentChatId);
              const allMessageIds = [...olderMessageIds, ...currentMessageIds];
              const sortedMessageIds = allMessageIds.sort((a, b) => {
                const msgA = getMessage(a);
                const msgB = getMessage(b);
                if (!msgA || !msgB) return 0;
                return msgA.createdAt.getTime() - msgB.createdAt.getTime();
              });
              
              storeRef.current.chats.set(currentChatId, { messageIds: sortedMessageIds });
              
              // Update cursor and has_more
              setMessageCursor(backendResponse.cursor || null);
              setHasMoreMessages(backendResponse.has_more);
              
              // Sync to local state
              syncStoreToLocalState(currentChatId);
              
              // Maintain scroll position (adjust for new content height)
              setTimeout(() => {
                const newScrollHeight = el.scrollHeight;
                const heightDiff = newScrollHeight - oldScrollHeight;
                el.scrollTop = scrollTop + heightDiff;
              }, 0);
            } else {
              setHasMoreMessages(false);
            }
          } catch (error) {
            console.error("[PAGINATION] Failed to load older messages:", error);
          } finally {
            setIsLoadingOlderMessages(false);
          }
        }
        
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
  };

  // Stream message with throttle and duplicate chunk prevention
  // NEW ARCHITECTURE: Uses runId to update store, seq for duplicate prevention
  const streamMessage = async (
    fullMessage: string, 
    runId: string,
    sources?: SourceInfo[],
    abortSignal?: AbortSignal
  ) => {
    // Get run and assistant message
    const run = getRun(runId);
    if (!run || run.status !== "running") {
      console.warn("[STREAM] Run not found or not running:", runId);
      return;
    }

    const assistantMessage = getMessage(run.assistantMessageId);
    if (!assistantMessage) {
      console.warn("[STREAM] Assistant message not found:", run.assistantMessageId);
      return;
    }

    let accumulatedText = "";
    let lastUpdateTime = 0;
    let currentSeq = 0;
    const THROTTLE_MS = 50;

    for (let i = 0; i < fullMessage.length; i++) {
      // Check if run is still active
      const currentRun = getRun(runId);
      if (!currentRun || currentRun.status !== "running") {
        // Run was cancelled or completed
        accumulatedText = fullMessage.substring(0, i);
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "cancelled",
          sources: sources,
        });
        updateRun(runId, { status: "cancelled" });
        syncStoreToLocalState(run.chatId);
        return;
      }

      // Check if aborted
      if (abortSignal?.aborted) {
        accumulatedText = fullMessage.substring(0, i);
        updateMessage(run.assistantMessageId, {
          content: accumulatedText,
          status: "cancelled",
          sources: sources,
        });
        updateRun(runId, { status: "cancelled" });
        syncStoreToLocalState(run.chatId);
        return;
      }

      // Update with throttle and seq (duplicate chunk prevention)
      const now = Date.now();
      accumulatedText = fullMessage.substring(0, i + 1);
      currentSeq = i + 1;

      // Only update if seq is greater than lastSeq (duplicate prevention)
      if (currentSeq > currentRun.lastSeq) {
        if (now - lastUpdateTime >= THROTTLE_MS) {
          if (abortSignal?.aborted) {
            accumulatedText = fullMessage.substring(0, i);
            updateMessage(run.assistantMessageId, {
              content: accumulatedText,
              status: "cancelled",
              sources: sources,
            });
            updateRun(runId, { status: "cancelled" });
            syncStoreToLocalState(run.chatId);
            return;
          }

          // Update message content and run seq
          updateMessage(run.assistantMessageId, {
            content: accumulatedText,
            status: "streaming",
          });
          updateRun(runId, { lastSeq: currentSeq });

          // CRITICAL: Always update store, but only sync to local state if this is active chat
          // This ensures background streaming continues and updates are saved
          // When user returns to this chat, syncStoreToLocalState will load the latest content
          if (run.chatId === currentChatId) {
            syncStoreToLocalState(currentChatId);
          }
          // Note: If chatId !== currentChatId, streaming continues in background
          // Store is updated, and will be synced when user returns to this chat

          lastUpdateTime = now;
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 10));
    }

    // Final check for abort
    if (abortSignal?.aborted) {
      updateMessage(run.assistantMessageId, {
        content: fullMessage,
        status: "cancelled",
        sources: sources,
      });
      updateRun(runId, { status: "cancelled" });
      syncStoreToLocalState(run.chatId);
      return;
    }

    // Finalize: Update message to completed
    updateMessage(run.assistantMessageId, {
      content: fullMessage,
      status: "completed",
      sources: sources,
    });
    updateRun(runId, { status: "completed", lastSeq: fullMessage.length });

    // Sync to local state
    syncStoreToLocalState(run.chatId);

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
      console.warn("[SEND] Duplicate trigger ignored (lock active)");
      return;
    }
    
      // CRITICAL: Check for active run BEFORE creating requestId (prevent duplicate on rapid clicks)
      let tempChatId = currentChatId || getChatId();
      if (!tempChatId) {
        // No valid chatId, create new chat and update state immediately
        console.log("[CHATDBG] handleSend createChat chatId=null userId=unknown status=creating");
        const newChat = await createChat();
        console.log("[CHATDBG] handleSend createChat chatId=" + newChat.id + " userId=unknown status=created");
        // CRITICAL FIX: Update state immediately so subsequent calls use the new chatId
        setCurrentChatId(newChat.id);
        tempChatId = newChat.id; // Update tempChatId for activeRun check
        // Update URL in background (non-blocking)
        router.push(`/chat/${newChat.id}`);
        // Continue with the new chatId instead of returning
        // This prevents duplicate chat creation on rapid sends
      }
    // Use tempChatId (which may have been updated above) or currentChatId
    const finalChatIdForRunCheck = tempChatId || currentChatId || getChatId();
    const activeRun = Array.from(storeRef.current.runs.values()).find(
      r => r.chatId === finalChatIdForRunCheck && r.status === "running"
    );
    if (activeRun) {
      console.warn("[IDEMPOTENCY] Chat already has active run:", activeRun.runId);
      return;
    }
    
    // Set lock IMMEDIATELY to prevent double-invoke
    sendLockRef.current = true;

    let requestId: string | null = null;
    let runId: string | null = null;
    let chatId: string | null = null;
    let wasAborted = false;
    const abortController = new AbortController();

    try {
      // Get chat ID from URL params or use currentChatId (which may have been set above)
      chatId = getChatId() || currentChatId;
      if (!chatId) {
        // No valid chatId, create new chat and update state immediately
        // CRITICAL FIX: Prevent duplicate chat creation - check if we already created one
        console.log("[CHATDBG] handleSend createChat chatId=null userId=unknown status=creating");
        const newChat = await createChat();
        console.log("[CHATDBG] handleSend createChat chatId=" + newChat.id + " userId=unknown status=created");
        // CRITICAL FIX: Update state immediately so subsequent calls use the new chatId
        setCurrentChatId(newChat.id);
        chatId = newChat.id;
        // Update URL in background (non-blocking)
        router.push(`/chat/${newChat.id}`);
        // Continue with the new chatId instead of returning
        // This prevents duplicate chat creation on rapid sends
      }

      // CRITICAL: Set currentChatId immediately if not already set
      if (chatId && chatId !== currentChatId) {
        setCurrentChatId(chatId);
      }

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
        console.warn("[IDEMPOTENCY] Request already in flight:", requestId);
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
        console.warn("[DUPLICATE_PREVENTION] Run already exists for requestId:", requestId);
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }
      
      // DUPLICATE PREVENTION: Check if same message content already exists in recent messages
      const chatMessages = getChatMessagesFromStore(chatId);
      
      // Check if there's already a streaming assistant message in this chat (prevent duplicate)
      const existingStreamingMessage = chatMessages.find(
        m => m.role === "assistant" && m.status === "streaming"
      );
      if (existingStreamingMessage) {
        console.warn("[DUPLICATE_PREVENTION] Streaming assistant message already exists:", existingStreamingMessage.id);
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
        console.warn("[DUPLICATE_PREVENTION] Duplicate user message content detected");
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }
      
      // Create user message and add to store
      const userMessageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      const userMessage: NormalizedMessage = {
        id: userMessageId,
        chatId: chatId,
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
      const finalCheckMessages = getChatMessagesFromStore(chatId);
      const finalCheckStreaming = finalCheckMessages.find(
        m => m.role === "assistant" && m.status === "streaming"
      );
      if (finalCheckStreaming) {
        console.warn("[DUPLICATE_PREVENTION] Final check: Streaming message exists, aborting");
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }
      
      const assistantMessageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      const assistantMessage: NormalizedMessage = {
        id: assistantMessageId,
        chatId: chatId,
        role: "assistant",
        content: "",
        createdAt: new Date(),
        status: "streaming",
        sources: undefined,
      };
      addMessage(assistantMessage);
      
      // Create run record
      runId = `run_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      const run: Run = {
        runId: runId,
        requestId: requestId,
        chatId: chatId,
        assistantMessageId: assistantMessageId,
        status: "running",
        startedAt: new Date(),
        lastSeq: 0,
        abortController: abortController,
      };
      addRun(run);
      
      // Sync store to local state
      syncStoreToLocalState(chatId);
      
      // Check if this is the first message in this chat
      const allChatMessages = getChatMessagesFromStore(chatId);
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
        const stored = localStorage.getItem(`chat_settings_${chatId}`);
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
        saveChatSettings(chatId);
      } else if (savedDocumentIds.length > 0) {
        documentIdsToUse = savedDocumentIds;
      }
      
      // API call
      const requestBody: { message: string; documentIds?: string[]; chatId?: string; client_message_id: string; mode?: string } = {
        message: userMessageText || "",
        client_message_id: clientMessageId,
        mode: "qa",
      };
      
      if (documentIdsToUse.length > 0) {
        requestBody.documentIds = documentIdsToUse;
      }
      
      if (chatId) {
        requestBody.chatId = chatId;
      }
      
      setLastDocumentIdsUsed(documentIdsToUse);
      
      if (chatId) {
        console.log(`[SEND] Sending message to chat ${chatId}`);
      } else {
        console.log(`[SEND] Creating new chat for message`);
      }
      
      // Use new endpoint: POST /api/chats/{chat_id}/messages
      const sendRequest: SendChatMessageRequest = {
        message: userMessageText || "",
        client_message_id: clientMessageId,
        mode: "qa",
        documentIds: documentIdsToUse.length > 0 ? documentIdsToUse : undefined,
        useDocuments: documentIdsToUse.length > 0,
      };
      
      const response = await sendChatMessage(chatId, sendRequest);
      
      console.log(`[SEND] Response received for chat ${chatId}`, {
        message_id: response.message_id,
        content_length: response.content?.length || 0,
        content_preview: response.content?.substring(0, 100) || "(empty)",
        has_sources: !!response.sources,
        role: response.role
      });

      // Validate response
      if (response.role !== "assistant") {
        console.error(`[SEND] Invalid response role from backend: ${response.role} (expected: assistant)`, response);
        // Backend returned wrong role (likely error case)
        updateMessage(assistantMessageId, {
          content: "Cevap oluşturulurken bir hata oluştu. Lütfen tekrar deneyin.",
          status: "completed",
        });
        if (chatId) {
          syncStoreToLocalState(chatId);
        }
        if (runId) {
          updateRun(runId, { status: "failed" });
        }
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // Validate response content
      if (!response.content || response.content.trim().length === 0) {
        console.warn(`[SEND] Empty response content from backend for chat ${chatId}`);
        // Still update message to show error state
        updateMessage(assistantMessageId, {
          content: "Cevap alınamadı. Lütfen tekrar deneyin.",
          status: "completed",
        });
        if (chatId) {
          syncStoreToLocalState(chatId);
        }
        if (runId) {
          updateRun(runId, { status: "failed" });
        }
        inflightRequestsRef.current.delete(requestId);
        sendLockRef.current = false;
        return;
      }

      // Check if run was aborted BEFORE updating message
      const currentRun = getRunByRequestId(requestId);
      if (!currentRun || currentRun.status !== "running" || abortController.signal.aborted) {
        if (currentRun) {
          updateRun(currentRun.runId, { status: "cancelled" });
          updateMessage(currentRun.assistantMessageId, { status: "cancelled" });
        }
        inflightRequestsRef.current.delete(requestId);
        if (chatId) {
          syncStoreToLocalState(chatId);
        }
        return;
      }

      // Update assistant message with response
      // CRITICAL: Update message ID if backend returned a different one
      if (response.message_id !== assistantMessageId) {
        // Backend returned a different message_id, need to update the message
        const existingMessage = getMessage(assistantMessageId);
        if (existingMessage) {
          // Remove old message and add new one with backend ID
          storeRef.current.messages.delete(assistantMessageId);
          const chat = storeRef.current.chats.get(chatId);
          if (chat) {
            chat.messageIds = chat.messageIds.filter(id => id !== assistantMessageId);
          }
        }
        // Add new message with backend ID
        const newAssistantMessage: NormalizedMessage = {
          id: response.message_id,
          chatId: chatId,
          role: "assistant",
          content: response.content || "",
          createdAt: new Date(),
          status: "completed",
          sources: response.sources,
        };
        addMessage(newAssistantMessage);
        // Update run to use new message ID
        updateRun(runId, { 
          status: "completed",
          assistantMessageId: response.message_id 
        });
      } else {
        // Same message ID, just update content
        updateMessage(assistantMessageId, {
          content: response.content || "",
          sources: response.sources,
          status: "completed",
        });
        // Finalize run
        const finalRun = getRun(runId);
        if (finalRun && finalRun.status === "running") {
          updateRun(runId, { status: "completed" });
        }
      }
      
      // CRITICAL: Sync store to local state immediately so UI updates
      if (chatId) {
        syncStoreToLocalState(chatId);
      }
      
      // Note: For now, we're using the simple response. Full streaming support would require
      // additional backend changes to support SSE/WebSocket for the new endpoint.
      
      // CRITICAL FIX: Reload messages from backend after streaming completes
      // This ensures backend-saved messages are loaded into frontend
      // Wait a bit for backend to finish saving messages (increased delay for reliability)
      if (chatId) {
        const chatIdToReload = chatId; // Capture for closure
        setTimeout(async () => {
          console.log(`[SEND] Reloading messages for chat ${chatIdToReload} after completion`);
          await loadChatMessages(chatIdToReload);
        }, 1000); // Increased from 500ms to 1000ms for backend to finish saving
      }
      
      // Check if first message for sidebar update
      const finalChatMessages = getChatMessagesFromStore(chatId);
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
      const currentChatStateError = getCurrentChatState(chatId);
      if (error?.name === 'AbortError' || abortController.signal.aborted || currentChatStateError.requestId !== requestId) {
        wasAborted = true;
        updateCurrentChatState(chatId, {
          isLoading: false,
          abortController: null,
          requestId: null,
          streamingContent: "",
          isStreaming: false,
        });

        if (chatId === currentChatId) {
          setIsLoading(false);
          setAbortController(null);
          setStreamingContent("");
        }
        return;
      }

      // Duplicate request error → no retry
      if (error?.code === 'DUPLICATE_REQUEST' || (error?.detail && error.detail.includes('zaten işlendi'))) {
        wasAborted = true;
        updateCurrentChatState(chatId, {
          isLoading: false,
          abortController: null,
          requestId: null,
          streamingContent: "",
          isStreaming: false,
        });

        if (chatId === currentChatId) {
          setIsLoading(false);
          setAbortController(null);
          setStreamingContent("");
        }
        return;
      }

      // Real error: mark run failed and surface a minimal message
      const runForError = requestId ? getRunByRequestId(requestId) : undefined;
      if (runForError) {
        updateRun(runForError.runId, { status: "failed" });
        updateMessage(runForError.assistantMessageId, {
          content: `Hata: ${error?.detail || "Mesaj gönderilemedi"}`,
          status: "completed",
        });
        syncStoreToLocalState(runForError.chatId);
      }
    } finally {
      const finalChatState = getCurrentChatState(chatId);
      const finalAbortState = abortController.signal.aborted || wasAborted || finalChatState.requestId !== requestId;

      if (!finalAbortState && finalChatState.requestId === requestId) {
        setIsLoading(false);
        setInput("");
        setTimeout(() => {
          if (inputRef.current) {
            inputRef.current.focus();
          }
        }, 100);
      } else {
        if (chatId === currentChatId) {
          setIsLoading(false);
        }
        setStreamingContent("");
      }

      // Clear active stream bindings for this chat
      if (finalChatState.requestId === requestId) {
        updateCurrentChatState(chatId, {
          abortController: null,
          requestId: null,
        });

        if (chatId === currentChatId) {
          setAbortController(null);
        }
      }

      // Release inflight/request locks
      if (requestId) {
        inflightRequestsRef.current.delete(requestId);
      }
      sendLockRef.current = false;
    }
  };

  // REMOVED handleKeyDown - form onSubmit handles everything
  // This prevents duplicate calls when Enter is pressed

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const allowedExtensions = [".pdf", ".docx", ".txt"];
    const allowedMimeTypes = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain"
    ];
    
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
        duration: 5000,
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
      
      // Her dosyayı hemen yükle
      const uploadPromises = validFiles.map(async (attachedFile) => {
        try {
          // AbortController'ı kontrol et
          if (attachedFile.abortController?.signal.aborted) {
            throw new Error("Yükleme iptal edildi");
          }
          
          const uploadResponse = await uploadDocument(
            attachedFile.file,
            chatId,
            undefined, // chatTitle - not needed for global document pool
            attachedFile.abortController?.signal
          );
          
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
                ? { ...f, documentId: uploadResponse.documentId, isUploading: false, abortController: undefined }
                : f
            );
          });
          
          // Show warning if truncated
          if (uploadResponse.truncated) {
            toast({
              title: "Uyarı",
              description: `${attachedFile.name} metni çok büyük, kısaltılarak kaydedildi.`,
              status: "warning",
              duration: 5000,
            });
          }
          
          // Show indexing status
          if (uploadResponse.indexing_success !== undefined) {
            if (uploadResponse.indexing_success && uploadResponse.indexing_chunks && uploadResponse.indexing_chunks > 0) {
              // Indexing successful - show brief info
              const duration = uploadResponse.indexing_duration_ms 
                ? `${(uploadResponse.indexing_duration_ms / 1000).toFixed(1)}s` 
                : "tamamlandı";
              toast({
                title: "Belge hazır",
                description: `${attachedFile.name} işlendi (${uploadResponse.indexing_chunks} bölüm, ${duration})`,
                status: "success",
                duration: 3000,
              });
            } else {
              // Indexing failed or no chunks
              toast({
                title: "Uyarı",
                description: `${attachedFile.name} işlenirken sorun oluştu. Belge yine de kaydedildi.`,
                status: "warning",
                duration: 5000,
              });
            }
          }
          
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
              duration: 5000,
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
          const updatedDocs = await listDocuments();
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
        
        // Başarılı yükleme mesajı göster
        if (successfulUploads.length > 0) {
          if (successfulUploads.length === 1) {
            toast({
              title: "Başarılı",
              description: `${successfulUploads[0].filename} başarıyla yüklendi.`,
              status: "success",
              duration: 2000,
            });
          } else {
            toast({
              title: "Başarılı",
              description: `${successfulUploads.length} dosya başarıyla yüklendi.`,
              status: "success",
              duration: 2000,
            });
          }
        }
        
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
                      border="2px solid"
                      borderColor={accentBorder}
                      transition="all 0.3s ease"
                      sx={{
                        animation: "pulseScale 2s ease-in-out infinite",
                        "&:hover": {
                          transform: "scale(1.1) rotate(5deg)",
                          boxShadow: `0 0 30px ${accentSoft}`,
                        },
                      }}
                    >
                      <Box
                        as="img"
                        src="/hace-logo.svg"
                        alt="HACE"
                        w="48px"
                        h="48px"
                        opacity={0.9}
                        sx={{
                          animation: "rotate 3s linear infinite",
                        }}
                      />
                    </Box>
                    <Text 
                      fontSize="2xl" 
                      fontWeight="bold" 
                      mb={2}
                      color={textPrimary}
                    >
                      Sohbete başlayın
                    </Text>
                    <Text 
                      color={textSecondary}
                      fontSize="md"
                    >
                      HACE asistanınıza bir soru sorun
                    </Text>
                  </Box>
                )}

                {messages.map((message) => {
                  // Render MessageContent for this message
                  const messageContentNode = message.content ? (
                    <MessageContent 
                      content={message.content} 
                      isStreaming={(message as any)._isStreaming === true} 
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
                        />
                      ))}
                    </Box>
                  )}

                  {/* Input Row - Inside container, bottom section */}
                  <HStack spacing={2} px={2} py={1.5} align="center">
                      <input
                        ref={fileInputRef}
                        type="file"
                        onChange={handleFileSelect}
                        style={{ display: "none" }}
                        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
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
                      placeholder="Herhangi bir şey sor..."
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
                      {isLoading && abortController ? (
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
                            // NOTE: Don't save message here - streamMessage() will save it when it detects abort
                            
                            // Abort the active stream
                            // Abort the active stream for this chat
                            if (currentChatId) {
                              const chatState = getCurrentChatState(currentChatId);
                              if (chatState.abortController) {
                                chatState.abortController.abort();
                              }
                              
                              // streamingContent'i temizleme - streamMessage() yarım mesajı bırakacak
                              updateCurrentChatState(currentChatId, {
                                abortController: null,
                                requestId: null,
                                isStreaming: false,
                                isLoading: false,
                                // streamingContent'i güncelleme - streamMessage() zaten güncelleyecek
                              });
                              
                              // Update local state - streamingContent'i temizleme, yarım mesaj kalacak
                              setIsLoading(false);
                              setAbortController(null);
                              // setStreamingContent("") - TEMİZLEME, yarım mesaj görünür kalacak
                            } else if (abortController) {
                              // Fallback: abort local controller if no chatId
                              abortController.abort();
                              console.log("[STREAM ABORT] AbortController aborted (no chatId)");
                              setIsLoading(false);
                              setAbortController(null);
                              // setStreamingContent("") - TEMİZLEME, yarım mesaj görünür kalacak
                            }
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
      </Box>

      {/* Document Picker Modal - Global Document Pool */}
      <DocumentPicker
        isOpen={isDocModalOpen}
        onClose={onDocModalClose}
        chatId={currentChatId || undefined}
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
                docsToUse = await listDocuments();
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
    </AuthGuard>
  );
}

export default ChatPage;
