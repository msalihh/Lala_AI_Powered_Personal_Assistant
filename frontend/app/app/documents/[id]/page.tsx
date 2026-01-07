"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Box,
  VStack,
  HStack,
  Button,
  Text,
  Heading,
  useColorModeValue,
  Card,
  CardBody,
  Spinner,
  useToast,
  Badge,
  Code,
  IconButton,
  Tooltip,
} from "@chakra-ui/react";
import { useRouter, useParams } from "next/navigation";
import { ArrowBackIcon } from "@chakra-ui/icons";
import AuthGuard from "@/components/AuthGuard";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { getDocument, DocumentDetail } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";

export default function DocumentDetailPage() {
  const router = useRouter();
  const params = useParams();
  const toast = useToast();
  const { isOpen, toggle } = useSidebar();
  const documentId = params.id as string;
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [fileBlobUrl, setFileBlobUrl] = useState<string | null>(null);
  const bgColor = useColorModeValue("gray.50", "gray.900");
  const cardBg = useColorModeValue("white", "gray.800");
  const codeBg = useColorModeValue("gray.100", "gray.700");
  
  // Load file as blob when document is loaded
  useEffect(() => {
    if (document && documentId) {
      const loadFile = async () => {
        try {
          const token = localStorage.getItem("auth_token");
          const response = await fetch(`/api/documents/${documentId}/file`, {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });
          
          if (response.ok) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            setFileBlobUrl(url);
          }
        } catch (error) {
          console.error("Failed to load file:", error);
        }
      };
      
      loadFile();
      
    }
    
    // Cleanup blob URL on unmount
    return () => {
      if (fileBlobUrl) {
        URL.revokeObjectURL(fileBlobUrl);
      }
    };
  }, [document, documentId]);

  useEffect(() => {
    if (documentId) {
      loadDocument();
    }
  }, [documentId]);

  const loadDocument = async () => {
    try {
      setIsLoading(true);
      const doc = await getDocument(documentId);
      setDocument(doc);
    } catch (error: any) {
      toast({
        title: "Hata",
        description: error.detail || "Doküman yüklenemedi",
        status: "error",
        duration: 3000,
      });
      router.push("/app/documents");
    } finally {
      setIsLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleString("tr-TR");
    } catch {
      return dateString;
    }
  };

  // Custom Sidebar Toggle Icon Component - ChatGPT style
  const SidebarToggleIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
    </svg>
  );

  return (
    <AuthGuard>
      <Box display="flex" h="100vh" bg={bgColor} position="relative">
        {/* Sidebar Toggle Button (when sidebar is closed) */}
        {!isOpen && (
          <Tooltip 
            label="Kenar çubuğunu aç" 
            placement="right"
            hasArrow
          >
            <IconButton
              icon={<SidebarToggleIcon />}
              aria-label="Kenar çubuğunu aç"
              onClick={toggle}
              position="fixed"
              left={4}
              top="50%"
              transform="translateY(-50%)"
              size="md"
              variant="ghost"
              color={useColorModeValue("gray.700", "gray.200")}
              bg={useColorModeValue("white", "gray.800")}
              border="1px"
              borderColor={useColorModeValue("gray.200", "gray.700")}
              _hover={{ 
                bg: useColorModeValue("gray.50", "gray.700"), 
                color: useColorModeValue("gray.900", "white"),
                borderColor: useColorModeValue("gray.300", "gray.600")
              }}
              transition="all 0.2s ease"
              zIndex={1000}
              borderRadius="lg"
              boxShadow="sm"
              minW="44px"
              h="44px"
            />
          </Tooltip>
        )}
        <Sidebar />
        <Box 
          flex={1} 
          ml={isOpen ? "260px" : "0"} 
          display="flex" 
          flexDirection="column"
          transition="margin-left 0.3s ease"
        >
          <Topbar />
          <Box flex={1} mt="60px" overflowY="auto" p={6}>
            <VStack spacing={6} align="stretch" maxW="6xl" mx="auto">
              <HStack>
                <Button
                  leftIcon={<ArrowBackIcon />}
                  variant="ghost"
                  onClick={() => router.push("/app/documents")}
                >
                  Geri
                </Button>
              </HStack>

              {isLoading ? (
                <Box textAlign="center" py={8}>
                  <Spinner size="xl" />
                  <Text mt={4}>Yükleniyor...</Text>
                </Box>
              ) : !document ? (
                <Card bg={cardBg}>
                  <CardBody textAlign="center" py={12}>
                    <Text fontSize="lg" color="gray.500">
                      Doküman bulunamadı
                    </Text>
                  </CardBody>
                </Card>
              ) : (
                <>
                  <Card bg={cardBg}>
                    <CardBody>
                      <VStack align="stretch" spacing={4}>
                        <HStack justify="space-between">
                          <Heading size="md">{document.filename}</Heading>
                          <VStack align="end" spacing={1}>
                            <Badge colorScheme={document.source === "upload" ? "green" : "purple"}>
                              {document.source === "upload" ? "Yükleme" : "Sohbet"}
                            </Badge>
                            {document.is_chat_scoped && document.uploaded_from_chat_title && (
                              <Tooltip label={`Chat ID: ${document.uploaded_from_chat_id || "N/A"}`} placement="top" hasArrow>
                                <Badge colorScheme="blue" fontSize="xs">
                                  Sohbet: {document.uploaded_from_chat_title}
                                </Badge>
                              </Tooltip>
                            )}
                          </VStack>
                        </HStack>
                        <HStack spacing={4}>
                          <Text fontSize="sm" color="gray.500">
                            <strong>Tip:</strong> {document.mime_type}
                          </Text>
                          <Text fontSize="sm" color="gray.500">
                            <strong>Boyut:</strong> {formatFileSize(document.size)}
                          </Text>
                          <Text fontSize="sm" color="gray.500">
                            <strong>Yüklenme:</strong> {formatDate(document.created_at)}
                          </Text>
                        </HStack>
                      </VStack>
                    </CardBody>
                  </Card>

                  {/* Document Viewer */}
                  <Card bg={cardBg}>
                    <CardBody>
                      <VStack align="stretch" spacing={4}>
                        <Heading size="sm">Doküman Görüntüleyici</Heading>
                        {(() => {
                          const fileUrl = fileBlobUrl || `/api/documents/${documentId}/file`;
                          const mimeType = document.mime_type || "";
                          
                          // PDF Viewer
                          if (mimeType === "application/pdf") {
                            return (
                              <Box
                                w="100%"
                                h="80vh"
                                border="1px solid"
                                borderColor={useColorModeValue("gray.200", "gray.700")}
                                borderRadius="md"
                                overflow="hidden"
                                bg={useColorModeValue("gray.100", "gray.900")}
                              >
                                {fileBlobUrl ? (
                                  <iframe
                                    src={fileBlobUrl}
                                    width="100%"
                                    height="100%"
                                    style={{ border: "none" }}
                                    title={document.filename}
                                  />
                                ) : (
                                  <Box
                                    display="flex"
                                    alignItems="center"
                                    justifyContent="center"
                                    h="100%"
                                  >
                                    <Spinner size="xl" />
                                  </Box>
                                )}
                              </Box>
                            );
                          }
                          
                          // Word Document Viewer (using Office Online)
                          if (mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") {
                            return (
                              <Box
                                w="100%"
                                h="80vh"
                                border="1px solid"
                                borderColor={useColorModeValue("gray.200", "gray.700")}
                                borderRadius="md"
                                overflow="hidden"
                                bg={useColorModeValue("gray.100", "gray.900")}
                              >
                                {fileBlobUrl ? (
                                  <iframe
                                    src={`https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(window.location.origin + fileUrl)}`}
                                    width="100%"
                                    height="100%"
                                    style={{ border: "none" }}
                                    title={document.filename}
                                  />
                                ) : (
                                  <Box
                                    display="flex"
                                    alignItems="center"
                                    justifyContent="center"
                                    h="100%"
                                  >
                                    <Spinner size="xl" />
                                  </Box>
                                )}
                              </Box>
                            );
                          }
                          
                          // TXT Viewer
                          if (mimeType === "text/plain") {
                            return (
                              <Box
                                bg={codeBg}
                                p={4}
                                borderRadius="md"
                                maxH="80vh"
                                overflowY="auto"
                                fontFamily="mono"
                              >
                                <Code
                                  display="block"
                                  whiteSpace="pre-wrap"
                                  wordBreak="break-word"
                                  bg="transparent"
                                  color="inherit"
                                  fontSize="sm"
                                >
                                  {document.text_content || "(Metin içeriği yok)"}
                                </Code>
                              </Box>
                            );
                          }
                          
                          // Fallback: Show text content
                          return (
                            <Box
                              bg={codeBg}
                              p={4}
                              borderRadius="md"
                              maxH="600px"
                              overflowY="auto"
                              fontFamily="mono"
                            >
                              <Code
                                display="block"
                                whiteSpace="pre-wrap"
                                wordBreak="break-word"
                                bg="transparent"
                                color="inherit"
                              >
                                {document.text_content || "(Metin içeriği yok)"}
                              </Code>
                            </Box>
                          );
                        })()}
                      </VStack>
                    </CardBody>
                  </Card>
                  
                  {/* Text Content (Collapsible) */}
                  {document.text_content && (
                    <Card bg={cardBg}>
                      <CardBody>
                        <VStack align="stretch" spacing={4}>
                          <Heading size="sm">Metin İçeriği (Arama için)</Heading>
                          <Box
                            bg={codeBg}
                            p={4}
                            borderRadius="md"
                            maxH="400px"
                            overflowY="auto"
                            fontFamily="mono"
                          >
                            <Code
                              display="block"
                              whiteSpace="pre-wrap"
                              wordBreak="break-word"
                              bg="transparent"
                              color="inherit"
                              fontSize="xs"
                            >
                              {document.text_content}
                            </Code>
                          </Box>
                        </VStack>
                      </CardBody>
                    </Card>
                  )}
                </>
              )}
            </VStack>
          </Box>
        </Box>
      </Box>
    </AuthGuard>
  );
}

