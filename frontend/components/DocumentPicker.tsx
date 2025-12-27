"use client";

import React, { useState, useEffect } from "react";
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  VStack,
  HStack,
  Button,
  Text,
  Box,
  Checkbox,
  List,
  ListItem,
  Badge,
  Divider,
  Spinner,
  useToast,
  Icon,
  useColorModeValue,
} from "@chakra-ui/react";
import { AttachmentIcon, AddIcon } from "@chakra-ui/icons";
import { listDocuments, DocumentListItem, uploadDocument } from "@/lib/api";

interface DocumentPickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (documentIds: string[]) => void; // Callback with selected document IDs
  selectedDocumentIds?: string[]; // Pre-selected document IDs
  chatId?: string; // Optional chat ID to associate uploaded documents with a chat
  chatTitle?: string; // Optional chat title for document metadata
}

/**
 * DocumentPicker Modal Component
 * 
 * Allows users to:
 * 1. Upload new documents from computer
 * 2. Select from previously uploaded documents
 * 
 * Selected documents are added to chat context (not shown as messages)
 */
export default function DocumentPicker({
  isOpen,
  onClose,
  onSelect,
  selectedDocumentIds = [],
  chatId,
  chatTitle,
}: DocumentPickerProps) {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(selectedDocumentIds)
  );
  const [activeTab, setActiveTab] = useState<"upload" | "select">("select");
  const [uploadedDocuments, setUploadedDocuments] = useState<DocumentListItem[]>([]); // Yüklenen dosyaları upload tab'ında göstermek için
  const toast = useToast();

  // Load documents when modal opens
  useEffect(() => {
    if (isOpen) {
      loadDocuments();
      // Reset selected IDs to match prop
      setSelectedIds(new Set(selectedDocumentIds));
    }
  }, [isOpen, selectedDocumentIds]);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (error: any) {
      toast({
        title: "Hata",
        description: error.detail || "Dokümanlar yüklenemedi",
        status: "error",
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const allowedExtensions = [".pdf", ".docx", ".txt"];
    const allowedMimeTypes = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
    ];

    const validFiles: File[] = [];
    const invalidFiles: string[] = [];

    Array.from(files).forEach((file) => {
      const fileExtension = file.name
        .toLowerCase()
        .substring(file.name.lastIndexOf("."));
      const isValidExtension = allowedExtensions.includes(fileExtension);
      const isValidMime = !file.type || allowedMimeTypes.includes(file.type);

      if (isValidExtension && isValidMime) {
        validFiles.push(file);
      } else {
        invalidFiles.push(file.name);
      }
    });

    if (invalidFiles.length > 0) {
      toast({
        title: "Hata",
        description: `Şu dosyalar desteklenmiyor: ${invalidFiles.join(", ")}. İzin verilen: ${allowedExtensions.join(", ")}`,
        status: "error",
        duration: 5000,
      });
    }

    if (validFiles.length > 0) {
      setUploading(true);
      try {
        const uploadPromises = validFiles.map(async (file) => {
          // If chatId is provided, associate the document with the chat
          const response = await uploadDocument(file, chatId, chatTitle);
          return { documentId: response.documentId, filename: file.name, file: file };
        });

        const uploadResults = await Promise.all(uploadPromises);
        const uploadedIds = uploadResults.map(r => r.documentId);

        // Add uploaded documents to selection
        const newSelectedIds = new Set(selectedIds);
        uploadedIds.forEach((id) => newSelectedIds.add(id));
        setSelectedIds(newSelectedIds);

        // Refresh documents list to get full document info
        const refreshedDocs = await listDocuments();
        setDocuments(refreshedDocs);
        
        // Get uploaded documents from the refreshed list to show in upload tab
        const newlyUploadedDocs = refreshedDocs.filter(doc => uploadedIds.includes(doc.id));
        // Add to uploadedDocuments state to show in upload tab
        setUploadedDocuments((prev) => {
          const existingIds = new Set(prev.map(d => d.id));
          const newDocs = newlyUploadedDocs.filter(doc => !existingIds.has(doc.id));
          return [...prev, ...newDocs];
        });

        toast({
          title: "Başarılı",
          description: `${validFiles.length} dosya başarıyla yüklendi ve seçildi.`,
          status: "success",
          duration: 2000,
        });

        // Keep upload tab active - don't switch to select tab
        // User can manually switch if they want to see uploaded documents
      } catch (error: any) {
        toast({
          title: "Hata",
          description: error.detail || "Dosya yüklenirken hata oluştu",
          status: "error",
          duration: 5000,
        });
      } finally {
        setUploading(false);
        // Reset file input
        const fileInput = document.getElementById(
          "document-upload-input"
        ) as HTMLInputElement;
        if (fileInput) {
          fileInput.value = "";
        }
      }
    }
  };

  const handleToggleSelect = (documentId: string) => {
    const newSelectedIds = new Set(selectedIds);
    if (newSelectedIds.has(documentId)) {
      newSelectedIds.delete(documentId);
    } else {
      newSelectedIds.add(documentId);
    }
    setSelectedIds(newSelectedIds);
  };

  const handleConfirm = () => {
    onSelect(Array.from(selectedIds));
    onClose();
  };

  const getFileTypeLabel = (mimeType: string): string => {
    if (mimeType === "application/pdf") return "PDF";
    if (
      mimeType ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
      return "DOCX";
    if (mimeType === "text/plain") return "TXT";
    return "Bilinmeyen";
  };

  const formatDate = (dateString: string): string => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString("tr-TR", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateString;
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Tema-aware renkler
  const bgColor = useColorModeValue("#FFFFFF", "#0D1117");
  const cardBg = useColorModeValue("#F6F8FA", "#161B22");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  const textColor = useColorModeValue("#1F2328", "#E6EDF3");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const accentColor = useColorModeValue("#1A7F37", "#3FB950");
  const accentHover = useColorModeValue("#2EA043", "#2EA043");
  const hoverBg = useColorModeValue("#E7ECF0", "#22272E");

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" isCentered>
      <ModalOverlay 
        bg="blackAlpha.700" 
        sx={{
          animation: "fadeIn 0.3s ease-out",
        }}
      />
      <ModalContent 
        bg={bgColor} 
        color={textColor}
        sx={{
          animation: "scaleIn 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <ModalHeader color={textColor} borderBottom={`1px solid ${borderColor}`}>
          Doküman Seç
        </ModalHeader>
        <ModalCloseButton color={textSecondary} _hover={{ color: textColor }} />
        <ModalBody pb={6}>
          <VStack spacing={4} align="stretch">
            {/* Tab Selection */}
            <HStack spacing={2}>
              <Button
                size="sm"
                variant={activeTab === "upload" ? "solid" : "outline"}
                bg={activeTab === "upload" ? accentColor : "transparent"}
                color={activeTab === "upload" ? useColorModeValue("#FFFFFF", "#0D1117") : textColor}
                borderColor={activeTab === "upload" ? accentColor : borderColor}
                borderWidth="1px"
                leftIcon={<AddIcon />}
                onClick={() => setActiveTab("upload")}
                flex={1}
                _hover={{
                  bg: activeTab === "upload" ? accentHover : hoverBg,
                  borderColor: activeTab === "upload" ? accentHover : accentColor,
                }}
                transition="all 0.2s ease"
              >
                Bilgisayardan Yükle
              </Button>
              <Button
                size="sm"
                variant={activeTab === "select" ? "solid" : "outline"}
                bg={activeTab === "select" ? accentColor : "transparent"}
                color={activeTab === "select" ? useColorModeValue("#FFFFFF", "#0D1117") : textColor}
                borderColor={activeTab === "select" ? accentColor : borderColor}
                borderWidth="1px"
                leftIcon={<AttachmentIcon />}
                onClick={() => setActiveTab("select")}
                flex={1}
                _hover={{
                  bg: activeTab === "select" ? accentHover : hoverBg,
                  borderColor: activeTab === "select" ? accentHover : accentColor,
                }}
                transition="all 0.2s ease"
              >
                Mevcut Dokümanlar ({documents.length})
              </Button>
            </HStack>

            <Divider borderColor={borderColor} />

            {/* Upload Tab */}
            {activeTab === "upload" && (
              <VStack spacing={4} align="stretch">
                <Box
                  borderWidth={2}
                  borderStyle="dashed"
                  borderColor={borderColor}
                  borderRadius="md"
                  p={6}
                  textAlign="center"
                  bg={cardBg}
                  _hover={{ borderColor: accentColor, bg: hoverBg }}
                  cursor="pointer"
                  transition="all 0.2s"
                  onClick={() =>
                    document.getElementById("document-upload-input")?.click()
                  }
                >
                  <input
                    id="document-upload-input"
                    type="file"
                    multiple
                    accept=".pdf,.docx,.txt"
                    onChange={handleFileSelect}
                    style={{ display: "none" }}
                  />
                  <Icon as={AddIcon} boxSize={8} color={textSecondary} mb={2} />
                  <Text fontSize="sm" color={textColor}>
                    PDF, DOCX veya TXT dosyaları seçin
                  </Text>
                  <Text fontSize="xs" color={textSecondary} mt={1}>
                    Çoklu seçim yapabilirsiniz
                  </Text>
                </Box>

                {uploading && (
                  <HStack justify="center" py={4}>
                    <Spinner size="sm" color={accentColor} />
                    <Text fontSize="sm" color={textSecondary}>
                      Dosyalar yükleniyor...
                    </Text>
                  </HStack>
                )}

                {/* Show uploaded documents in upload tab */}
                {uploadedDocuments.length > 0 && !uploading && (
                  <VStack
                    spacing={2}
                    align="stretch"
                    maxH="300px"
                    overflowY="auto"
                    sx={{
                      "&::-webkit-scrollbar": {
                        width: "8px",
                      },
                      "&::-webkit-scrollbar-track": {
                        bg: bgColor,
                      },
                      "&::-webkit-scrollbar-thumb": {
                        bg: borderColor,
                        borderRadius: "4px",
                        _hover: {
                          bg: textSecondary,
                        },
                      },
                    }}
                  >
                    <Text fontSize="sm" fontWeight="medium" color={textColor} mb={2}>
                      Yüklenen Dosyalar:
                    </Text>
                    <List spacing={2}>
                      {uploadedDocuments.map((doc) => (
                        <ListItem
                          key={doc.id}
                          p={3}
                          borderWidth={1}
                          borderColor={
                            selectedIds.has(doc.id) ? accentColor : borderColor
                          }
                          borderRadius="md"
                          bg={selectedIds.has(doc.id) ? `${accentColor}20` : cardBg}
                          cursor="pointer"
                          transition="all 0.2s"
                          _hover={{
                            borderColor: accentColor,
                            bg: selectedIds.has(doc.id) ? `${accentColor}30` : hoverBg,
                          }}
                          onClick={() => handleToggleSelect(doc.id)}
                        >
                          <HStack spacing={3} align="start">
                            <Checkbox
                              isChecked={selectedIds.has(doc.id)}
                              onChange={() => handleToggleSelect(doc.id)}
                              mt={1}
                              colorScheme="green"
                              borderColor={borderColor}
                              _checked={{
                                bg: accentColor,
                                borderColor: accentColor,
                              }}
                            />
                            <VStack align="start" spacing={1} flex={1}>
                              <HStack>
                                <Text fontWeight="medium" fontSize="sm" color={textColor}>
                                  {doc.filename}
                                </Text>
                                <Badge
                                  bg={
                                    doc.mime_type === "application/pdf"
                                      ? "#ef4444"
                                      : doc.mime_type ===
                                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                      ? "#3b82f6"
                                      : "#6b7280"
                                  }
                                  color="white"
                                  fontSize="xs"
                                  px={2}
                                  py={0.5}
                                  borderRadius="sm"
                                >
                                  {getFileTypeLabel(doc.mime_type)}
                                </Badge>
                              </HStack>
                              <HStack spacing={2} fontSize="xs" color={textSecondary}>
                                <Text>{formatFileSize(doc.size)}</Text>
                                <Text>•</Text>
                                <Text>{formatDate(doc.created_at)}</Text>
                              </HStack>
                            </VStack>
                          </HStack>
                        </ListItem>
                      ))}
                    </List>
                  </VStack>
                )}
              </VStack>
            )}

            {/* Select Tab */}
            {activeTab === "select" && (
              <VStack
                spacing={2}
                align="stretch"
                maxH="400px"
                overflowY="auto"
                sx={{
                  "&::-webkit-scrollbar": {
                    width: "8px",
                  },
                  "&::-webkit-scrollbar-track": {
                    bg: bgColor,
                  },
                  "&::-webkit-scrollbar-thumb": {
                    bg: borderColor,
                    borderRadius: "4px",
                    _hover: {
                      bg: textSecondary,
                    },
                  },
                }}
              >
                {loading ? (
                  <HStack justify="center" py={8}>
                    <Spinner size="sm" color={accentColor} />
                    <Text fontSize="sm" color={textSecondary}>
                      Dokümanlar yükleniyor...
                    </Text>
                  </HStack>
                ) : documents.length === 0 ? (
                  <Box textAlign="center" py={8}>
                    <Text fontSize="sm" color={textSecondary}>
                      Henüz doküman yüklenmemiş.
                    </Text>
                    <Text fontSize="xs" color={textSecondary} mt={2} opacity={0.7}>
                      "Bilgisayardan Yükle" sekmesinden dosya yükleyebilirsiniz.
                    </Text>
                  </Box>
                ) : (
                  <List spacing={2}>
                    {documents.map((doc) => (
                      <ListItem
                        key={doc.id}
                        p={3}
                        borderWidth={1}
                        borderColor={
                          selectedIds.has(doc.id) ? accentColor : borderColor
                        }
                        borderRadius="md"
                        bg={selectedIds.has(doc.id) ? `${accentColor}20` : cardBg}
                        cursor="pointer"
                        transition="all 0.2s"
                        _hover={{
                          borderColor: accentColor,
                          bg: selectedIds.has(doc.id) ? `${accentColor}30` : hoverBg,
                        }}
                        onClick={() => handleToggleSelect(doc.id)}
                      >
                        <HStack spacing={3} align="start">
                          <Checkbox
                            isChecked={selectedIds.has(doc.id)}
                            onChange={() => handleToggleSelect(doc.id)}
                            mt={1}
                            colorScheme="green"
                            borderColor={borderColor}
                            _checked={{
                              bg: accentColor,
                              borderColor: accentColor,
                            }}
                          />
                          <VStack align="start" spacing={1} flex={1}>
                            <HStack>
                              <Text fontWeight="medium" fontSize="sm" color={textColor}>
                                {doc.filename}
                              </Text>
                              <Badge
                                bg={
                                  doc.mime_type === "application/pdf"
                                    ? "#ef4444"
                                    : doc.mime_type ===
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    ? "#3b82f6"
                                    : "#6b7280"
                                }
                                color="white"
                                fontSize="xs"
                                px={2}
                                py={0.5}
                                borderRadius="sm"
                              >
                                {getFileTypeLabel(doc.mime_type)}
                              </Badge>
                            </HStack>
                            <HStack spacing={2} fontSize="xs" color={textSecondary}>
                              <Text>{formatFileSize(doc.size)}</Text>
                              <Text>•</Text>
                              <Text>{formatDate(doc.created_at)}</Text>
                            </HStack>
                          </VStack>
                        </HStack>
                      </ListItem>
                    ))}
                  </List>
                )}
              </VStack>
            )}

            {/* Action Buttons */}
            <HStack justify="flex-end" spacing={3} pt={2}>
              <Button
                variant="ghost"
                onClick={onClose}
                color={textColor}
                _hover={{ bg: hoverBg }}
              >
                İptal
              </Button>
              <Button
                bg={selectedIds.size > 0 ? accentColor : borderColor}
                color="white"
                onClick={handleConfirm}
                isDisabled={selectedIds.size === 0}
                _hover={{
                  bg: selectedIds.size > 0 ? accentColor : borderColor,
                  opacity: selectedIds.size > 0 ? 0.9 : 0.6,
                }}
                _disabled={{
                  bg: borderColor,
                  color: textSecondary,
                  cursor: "not-allowed",
                }}
              >
                Seç ({selectedIds.size})
              </Button>
            </HStack>
          </VStack>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
}

