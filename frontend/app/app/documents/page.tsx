"use client";

import { useState, useEffect, useRef } from "react";
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
  Input,
  IconButton,
  Spinner,
  useToast,
  Badge,
  Tooltip,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  useDisclosure,
  Flex,
  Divider,
  SimpleGrid,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
} from "@chakra-ui/react";
import { useRouter } from "next/navigation";
import { AddIcon, DeleteIcon, ViewIcon, DownloadIcon, AttachmentIcon } from "@chakra-ui/icons";
import AuthGuard from "@/components/AuthGuard";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { listDocuments, deleteDocument, uploadDocument, DocumentListItem } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";

export default function DocumentsPage() {
  const router = useRouter();
  const toast = useToast();
  const { isOpen, toggle } = useSidebar();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; id: string | null; filename: string }>({
    isOpen: false,
    id: null,
    filename: "",
  });
  const [activeTab, setActiveTab] = useState(0); // 0: Tümü, 1: Bağımsız, 2: Sohbetlerden
  // Yeni tema renkleri - GitHub tarzı
  const bgColor = useColorModeValue("#FFFFFF", "#0D1117");
  const cardBg = useColorModeValue("#F6F8FA", "#161B22");
  const borderColor = useColorModeValue("#D1D9E0", "#30363D");
  const hoverBg = useColorModeValue("#E7ECF0", "#22272E");
  const textPrimary = useColorModeValue("#1F2328", "#E6EDF3");
  const textSecondary = useColorModeValue("#656D76", "#8B949E");
  const accentPrimary = useColorModeValue("#1A7F37", "#3FB950");
  const accentSoft = useColorModeValue("rgba(26, 127, 55, 0.1)", "rgba(63, 185, 80, 0.15)");
  const gradientBg = useColorModeValue(
    "linear-gradient(180deg, rgba(26, 127, 55, 0.05) 0%, transparent 100%)",
    "radial-gradient(circle at 50% 0%, rgba(63, 185, 80, 0.1) 0%, transparent 50%)"
  );
  const headingGradient = useColorModeValue(
    "linear(to-r, #1A7F37, #2EA043)",
    "linear(to-r, #3FB950, #2EA043)"
  );
  const emptyStateBg = accentSoft;
  const pdfIconBg = accentSoft;
  const docxIconBg = accentSoft;
  const txtIconBg = useColorModeValue("#F0F3F6", "rgba(255, 255, 255, 0.05)");
  
  const getFileIconBg = (mimeType: string) => {
    const type = formatMimeType(mimeType);
    if (type === "PDF") return pdfIconBg;
    if (type === "DOCX") return docxIconBg;
    return txtIconBg;
  };
  
  const getFileIconColor = (mimeType: string) => {
    const type = formatMimeType(mimeType);
    return "green.500";
  };

  useEffect(() => {
    loadDocuments();
    
    // Listen for chat deletion events to refresh document list
    const handleChatDeleted = () => {
      loadDocuments(); // Refresh when a chat is deleted
    };
    
    window.addEventListener("chatDeleted", handleChatDeleted);
    return () => window.removeEventListener("chatDeleted", handleChatDeleted);
  }, []);

  const loadDocuments = async () => {
    try {
      setIsLoading(true);
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (error: any) {
      toast({
        title: "Hata",
        description: error.detail || "Dokümanlar yüklenemedi",
        status: "error",
        duration: 3000,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    
    // STRICT validation: Only PDF, DOCX, TXT
    const allowedExtensions = [".pdf", ".docx", ".txt"];
    const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf("."));
    if (!allowedExtensions.includes(fileExtension)) {
      toast({
        title: "Hata",
        description: `Desteklenmeyen dosya tipi. İzin verilen: ${allowedExtensions.join(", ")}`,
        status: "error",
        duration: 3000,
      });
      return;
    }
    
    // STRICT MIME type validation
    const allowedMimeTypes = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain"
    ];
    
    if (file.type && !allowedMimeTypes.includes(file.type)) {
      toast({
        title: "Hata",
        description: `Desteklenmeyen MIME tipi: ${file.type}. İzin verilen: ${allowedMimeTypes.join(", ")}`,
        status: "error",
        duration: 3000,
      });
      return;
    }

    // Validate file size (10MB)
    if (file.size > 10 * 1024 * 1024) {
      toast({
        title: "Hata",
        description: "Dosya boyutu çok büyük. Maksimum: 10MB",
        status: "error",
        duration: 3000,
      });
      return;
    }

    try {
      setIsUploading(true);
      const response = await uploadDocument(file);
      
      // Show success message
      let description = `${file.name} başarıyla yüklendi`;
      if (response.truncated) {
        description += ". Metin çok büyük, kısaltılarak kaydedildi.";
      }
      
      toast({
        title: "Başarılı",
        description: description,
        status: "success",
        duration: 5000,
      });
      await loadDocuments(); // Reload list
    } catch (error: any) {
      // Show specific error messages
      let errorMessage = error.detail || "Dosya yüklenemedi";
      
      if (error.code === "INVALID_FILE_SIGNATURE") {
        errorMessage = "Dosya imza kontrolü başarısız: Dosya gerçek bir " + 
          (file.name.toLowerCase().endsWith(".pdf") ? "PDF" : 
           file.name.toLowerCase().endsWith(".docx") ? "DOCX" : "TXT") + 
          " dosyası değil";
      } else if (error.code === "FILE_TOO_LARGE") {
        errorMessage = "Dosya boyutu çok büyük. Maksimum: 10MB";
      } else if (error.code === "INVALID_FILE_TYPE") {
        errorMessage = "Desteklenmeyen dosya tipi. İzin verilen: PDF, DOCX, TXT";
      }
      
      toast({
        title: "Hata",
        description: errorMessage,
        status: "error",
        duration: 5000,
      });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDeleteClick = (id: string, filename: string) => {
    setDeleteDialog({ isOpen: true, id, filename });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteDialog.id) return;

    try {
      await deleteDocument(deleteDialog.id);
      toast({
        title: "Başarılı",
        description: "Doküman silindi",
        status: "success",
        duration: 3000,
      });
      await loadDocuments();
      setDeleteDialog({ isOpen: false, id: null, filename: "" });
    } catch (error: any) {
      toast({
        title: "Hata",
        description: error.detail || "Doküman silinemedi",
        status: "error",
        duration: 3000,
      });
    }
  };

  const handleDeleteCancel = () => {
    setDeleteDialog({ isOpen: false, id: null, filename: "" });
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

  const formatMimeType = (mimeType: string): string => {
    // Convert long MIME types to short, readable format
    const mimeMap: Record<string, string> = {
      "application/pdf": "PDF",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
      "text/plain": "TXT",
    };
    
    return mimeMap[mimeType.toLowerCase()] || mimeType.split("/").pop()?.toUpperCase() || mimeType;
  };

  // Categorize documents
  const independentDocuments = documents.filter(doc => !doc.uploaded_from_chat_id);
  const chatDocuments = documents.filter(doc => doc.uploaded_from_chat_id);

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
          <Box 
            flex={1} 
            mt="60px" 
            overflowY="auto" 
            p={6}
            position="relative"
            _before={{
              content: '""',
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: gradientBg,
              pointerEvents: "none",
              zIndex: 0,
            }}
          >
            <VStack spacing={6} align="stretch" maxW="7xl" mx="auto" position="relative" zIndex={1}>
              <Flex justify="space-between" align="center" flexWrap="wrap" gap={4}>
                <VStack align="start" spacing={1}>
                  <Heading 
                    size="xl" 
                    bgGradient={headingGradient}
                    bgClip="text"
                    fontWeight="bold"
                  >
                    Dokümanlarım
                  </Heading>
                  <Text fontSize="sm" color={textSecondary}>
                    Yüklediğiniz tüm belgeleri buradan yönetebilirsiniz
                  </Text>
                </VStack>
                <HStack>
                  <input
                    ref={fileInputRef}
                    type="file"
                    onChange={handleFileSelect}
                    style={{ display: "none" }}
                    accept=".pdf,.docx,.txt"
                  />
                  <Button
                    leftIcon={<AddIcon />}
                    bgGradient="linear(to-r, green.500, green.600)"
                    color="white"
                    _hover={{
                      bgGradient: "linear(to-r, green.600, green.700)",
                      transform: "translateY(-2px)",
                      boxShadow: "0 10px 25px rgba(16, 185, 129, 0.3)",
                    }}
                    _active={{
                      transform: "translateY(0)",
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    isLoading={isUploading}
                    loadingText="Yükleniyor..."
                    transition="all 0.2s ease"
                    boxShadow="0 4px 15px rgba(16, 185, 129, 0.2)"
                    borderRadius="xl"
                    size="lg"
                    fontWeight="semibold"
                  >
                    Dosya Yükle
                  </Button>
                </HStack>
              </Flex>

              {isLoading ? (
                <Box textAlign="center" py={16}>
                  <Spinner 
                    size="xl" 
                    thickness="4px"
                    speed="0.65s"
                    color="green.500"
                    emptyColor={useColorModeValue("gray.200", "gray.700")}
                  />
                  <Text mt={6} fontSize="lg" color={textSecondary} fontWeight="medium">
                    Dokümanlar yükleniyor...
                  </Text>
                </Box>
              ) : documents.length === 0 ? (
                <Card 
                  bg={cardBg}
                  backdropFilter="blur(20px)"
                  border="1px solid"
                  borderColor={borderColor}
                  borderRadius="2xl"
                  boxShadow="0 8px 32px rgba(0, 0, 0, 0.1)"
                  overflow="hidden"
                  position="relative"
                  _before={{
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "4px",
                    bgGradient: "linear(to-r, blue.500, purple.500)",
                  }}
                >
                  <CardBody textAlign="center" py={16}>
                    <Box
                      mb={6}
                      display="inline-block"
                      p={4}
                      borderRadius="full"
                      bg={emptyStateBg}
                    >
                      <AttachmentIcon boxSize={12} color="green.500" />
                    </Box>
                    <Heading size="md" mb={2} color={textPrimary}>
                      Henüz doküman yüklenmedi
                    </Heading>
                    <Text fontSize="md" color={textSecondary} mb={6}>
                      İlk dokümanınızı yükleyerek başlayın
                    </Text>
                    <Button
                      leftIcon={<AddIcon />}
                      bgGradient="linear(to-r, green.500, green.600)"
                      color="white"
                      _hover={{
                        bgGradient: "linear(to-r, green.600, green.700)",
                        transform: "translateY(-2px)",
                        boxShadow: "0 10px 25px rgba(16, 185, 129, 0.3)",
                      }}
                      onClick={() => fileInputRef.current?.click()}
                      size="lg"
                      borderRadius="xl"
                      fontWeight="semibold"
                      boxShadow="0 4px 15px rgba(16, 185, 129, 0.2)"
                      transition="all 0.2s ease"
                    >
                      İlk Dosyayı Yükle
                    </Button>
                  </CardBody>
                </Card>
              ) : (
                <Tabs index={activeTab} onChange={setActiveTab} colorScheme="green" variant="enclosed">
                  <TabList mb={4} borderBottom="2px solid" borderColor={borderColor}>
                    <Tab 
                      _selected={{ 
                        color: "green.500", 
                        borderBottom: "2px solid",
                        borderColor: "green.500"
                      }}
                      fontWeight="semibold"
                    >
                      Tümü ({documents.length})
                    </Tab>
                    <Tab 
                      _selected={{ 
                        color: "green.500", 
                        borderBottom: "2px solid",
                        borderColor: "green.500"
                      }}
                      fontWeight="semibold"
                    >
                      Bağımsız ({independentDocuments.length})
                    </Tab>
                    <Tab 
                      _selected={{ 
                        color: "green.500", 
                        borderBottom: "2px solid",
                        borderColor: "green.500"
                      }}
                      fontWeight="semibold"
                    >
                      Sohbetlerden ({chatDocuments.length})
                    </Tab>
                  </TabList>

                  <TabPanels>
                    {/* Tümü Tab */}
                    <TabPanel px={0}>
                      <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4}>
                        {documents.map((doc) => (
                    <Card
                      key={doc.id}
                      bg={cardBg}
                      backdropFilter="blur(20px)"
                      border="1px solid"
                      borderColor={borderColor}
                      borderRadius="xl"
                      boxShadow="0 4px 20px rgba(0, 0, 0, 0.1)"
                      overflow="hidden"
                      position="relative"
                      transition="all 0.3s ease"
                      _hover={{
                        transform: "translateY(-4px)",
                        boxShadow: "0 12px 40px rgba(16, 185, 129, 0.2)",
                        borderColor: "green.400",
                      }}
                      _before={{
                        content: '""',
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        bgGradient: doc.source === "upload" 
                          ? "linear(to-r, green.500, green.600)"
                          : "linear(to-r, green.400, green.500)",
                      }}
                    >
                      <CardBody p={5}>
                        <VStack align="stretch" spacing={4}>
                          {/* File Header */}
                          <HStack justify="space-between" align="start">
                            <Box flex={1} minW={0}>
                              <HStack spacing={2} mb={2}>
                                <Box
                                  p={2}
                                  borderRadius="lg"
                                  bg={getFileIconBg(doc.mime_type)}
                                >
                                  <AttachmentIcon 
                                    boxSize={5} 
                                    color={getFileIconColor(doc.mime_type)}
                                  />
                                </Box>
                                <Badge
                                  colorScheme="green"
                                  fontSize="xs"
                                  px={2}
                                  py={1}
                                  borderRadius="md"
                                >
                                  {formatMimeType(doc.mime_type)}
                                </Badge>
                              </HStack>
                              <Text
                                fontWeight="semibold"
                                fontSize="md"
                                color={textPrimary}
                                noOfLines={2}
                                mb={1}
                              >
                                {doc.filename}
                              </Text>
                            </Box>
                          </HStack>

                          <Divider borderColor={borderColor} />

                          {/* File Info */}
                          <VStack align="stretch" spacing={2}>
                            <HStack justify="space-between" fontSize="sm">
                              <Text color={textSecondary}>Boyut:</Text>
                              <Text fontWeight="medium" color={textPrimary}>
                                {formatFileSize(doc.size)}
                              </Text>
                            </HStack>
                            <HStack justify="space-between" fontSize="sm">
                              <Text color={textSecondary}>Kaynak:</Text>
                              <Badge
                                colorScheme="green"
                                fontSize="xs"
                                px={2}
                                py={1}
                                borderRadius="md"
                                variant={doc.source === "upload" ? "solid" : "outline"}
                              >
                                {doc.source === "upload" ? "Yükleme" : "Sohbet"}
                              </Badge>
                            </HStack>
                            {doc.is_chat_scoped && doc.uploaded_from_chat_title && (
                              <HStack justify="space-between" fontSize="sm">
                                <Text color={textSecondary}>Sohbet:</Text>
                                <Tooltip
                                  label={`"${doc.uploaded_from_chat_title}" sohbetinden yüklendi`}
                                  placement="top"
                                  hasArrow
                                >
                                  <Text
                                    fontWeight="medium"
                                    color="green.400"
                                    noOfLines={1}
                                    maxW="150px"
                                    cursor="help"
                                  >
                                    {doc.uploaded_from_chat_title.length > 15
                                      ? doc.uploaded_from_chat_title.substring(0, 15) + "..."
                                      : doc.uploaded_from_chat_title}
                                  </Text>
                                </Tooltip>
                              </HStack>
                            )}
                            <HStack justify="space-between" fontSize="sm">
                              <Text color={textSecondary}>Tarih:</Text>
                              <Text fontWeight="medium" color={textPrimary} fontSize="xs">
                                {formatDate(doc.created_at)}
                              </Text>
                            </HStack>
                          </VStack>

                          <Divider borderColor={borderColor} />

                          {/* Actions */}
                          <HStack spacing={2} justify="flex-end">
                            <Tooltip label="Görüntüle" placement="top" hasArrow>
                              <IconButton
                                icon={<ViewIcon />}
                                aria-label="Görüntüle"
                                size="md"
                                variant="ghost"
                                colorScheme="green"
                                onClick={() => router.push(`/app/documents/${doc.id}`)}
                                _hover={{
                                  bg: "green.50",
                                  color: "green.600",
                                  transform: "scale(1.1)",
                                }}
                                transition="all 0.2s ease"
                              />
                            </Tooltip>
                            <Tooltip label="Sil" placement="top" hasArrow>
                              <IconButton
                                icon={<DeleteIcon />}
                                aria-label="Sil"
                                size="md"
                                variant="ghost"
                                colorScheme="red"
                                onClick={() => handleDeleteClick(doc.id, doc.filename)}
                                _hover={{
                                  bg: "red.50",
                                  color: "red.600",
                                  transform: "scale(1.1)",
                                }}
                                transition="all 0.2s ease"
                              />
                            </Tooltip>
                          </HStack>
                        </VStack>
                      </CardBody>
                    </Card>
                  ))}
                      </SimpleGrid>
                    </TabPanel>

                    {/* Bağımsız Tab */}
                    <TabPanel px={0}>
                      {independentDocuments.length === 0 ? (
                        <Card 
                          bg={cardBg}
                          backdropFilter="blur(20px)"
                          border="1px solid"
                          borderColor={borderColor}
                          borderRadius="2xl"
                          boxShadow="0 8px 32px rgba(0, 0, 0, 0.1)"
                          overflow="hidden"
                          position="relative"
                          _before={{
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            right: 0,
                            height: "4px",
                            bgGradient: "linear(to-r, green.500, green.600)",
                          }}
                        >
                          <CardBody textAlign="center" py={16}>
                            <Box
                              mb={6}
                              display="inline-block"
                              p={4}
                              borderRadius="full"
                              bg={emptyStateBg}
                            >
                              <AttachmentIcon boxSize={12} color="green.500" />
                            </Box>
                            <Heading size="md" mb={2} color={textPrimary}>
                              Henüz bağımsız doküman yok
                            </Heading>
                            <Text fontSize="md" color={textSecondary} mb={6}>
                              Dokümanlarım sayfasından bağımsız olarak dosya yükleyebilirsiniz
                            </Text>
                            <Button
                              leftIcon={<AddIcon />}
                              bgGradient="linear(to-r, green.500, green.600)"
                              color="white"
                              _hover={{
                                bgGradient: "linear(to-r, green.600, green.700)",
                                transform: "translateY(-2px)",
                                boxShadow: "0 10px 25px rgba(16, 185, 129, 0.3)",
                              }}
                              onClick={() => fileInputRef.current?.click()}
                              size="lg"
                              borderRadius="xl"
                              fontWeight="semibold"
                              boxShadow="0 4px 15px rgba(16, 185, 129, 0.2)"
                              transition="all 0.2s ease"
                            >
                              Dosya Yükle
                            </Button>
                          </CardBody>
                        </Card>
                      ) : (
                        <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4}>
                          {independentDocuments.map((doc) => (
                            <Card
                              key={doc.id}
                              bg={cardBg}
                              backdropFilter="blur(20px)"
                              border="1px solid"
                              borderColor={borderColor}
                              borderRadius="xl"
                              boxShadow="0 4px 20px rgba(0, 0, 0, 0.1)"
                              overflow="hidden"
                              position="relative"
                              transition="all 0.3s ease"
                              _hover={{
                                transform: "translateY(-4px)",
                                boxShadow: "0 12px 40px rgba(16, 185, 129, 0.2)",
                                borderColor: "green.400",
                              }}
                              _before={{
                                content: '""',
                                position: "absolute",
                                top: 0,
                                left: 0,
                                right: 0,
                                height: "3px",
                                bgGradient: "linear(to-r, green.500, green.600)",
                              }}
                            >
                              <CardBody p={5}>
                                <VStack align="stretch" spacing={4}>
                                  <HStack justify="space-between" align="start">
                                    <Box flex={1} minW={0}>
                                      <HStack spacing={2} mb={2}>
                                        <Box
                                          p={2}
                                          borderRadius="lg"
                                          bg={getFileIconBg(doc.mime_type)}
                                        >
                                          <AttachmentIcon 
                                            boxSize={5} 
                                            color={getFileIconColor(doc.mime_type)}
                                          />
                                        </Box>
                                        <Badge
                                          colorScheme="green"
                                          fontSize="xs"
                                          px={2}
                                          py={1}
                                          borderRadius="md"
                                        >
                                          {formatMimeType(doc.mime_type)}
                                        </Badge>
                                      </HStack>
                                      <Text
                                        fontWeight="semibold"
                                        fontSize="md"
                                        color={textPrimary}
                                        noOfLines={2}
                                        mb={1}
                                      >
                                        {doc.filename}
                                      </Text>
                                    </Box>
                                  </HStack>

                                  <Divider borderColor={borderColor} />

                                  <VStack align="stretch" spacing={2}>
                                    <HStack justify="space-between" fontSize="sm">
                                      <Text color={textSecondary}>Boyut:</Text>
                                      <Text fontWeight="medium" color={textPrimary}>
                                        {formatFileSize(doc.size)}
                                      </Text>
                                    </HStack>
                                    <HStack justify="space-between" fontSize="sm">
                                      <Text color={textSecondary}>Kaynak:</Text>
                                      <Badge
                                        colorScheme="green"
                                        fontSize="xs"
                                        px={2}
                                        py={1}
                                        borderRadius="md"
                                        variant="solid"
                                      >
                                        Bağımsız
                                      </Badge>
                                    </HStack>
                                    <HStack justify="space-between" fontSize="sm">
                                      <Text color={textSecondary}>Tarih:</Text>
                                      <Text fontWeight="medium" color={textPrimary} fontSize="xs">
                                        {formatDate(doc.created_at)}
                                      </Text>
                                    </HStack>
                                  </VStack>

                                  <Divider borderColor={borderColor} />

                                  <HStack spacing={2} justify="flex-end">
                                    <Tooltip label="Görüntüle" placement="top" hasArrow>
                                      <IconButton
                                        icon={<ViewIcon />}
                                        aria-label="Görüntüle"
                                        size="md"
                                        variant="ghost"
                                        colorScheme="green"
                                        onClick={() => router.push(`/app/documents/${doc.id}`)}
                                        _hover={{
                                          bg: "green.50",
                                          color: "green.600",
                                          transform: "scale(1.1)",
                                        }}
                                        transition="all 0.2s ease"
                                      />
                                    </Tooltip>
                                    <Tooltip label="Sil" placement="top" hasArrow>
                                      <IconButton
                                        icon={<DeleteIcon />}
                                        aria-label="Sil"
                                        size="md"
                                        variant="ghost"
                                        colorScheme="red"
                                        onClick={() => handleDeleteClick(doc.id, doc.filename)}
                                        _hover={{
                                          bg: "red.50",
                                          color: "red.600",
                                          transform: "scale(1.1)",
                                        }}
                                        transition="all 0.2s ease"
                                      />
                                    </Tooltip>
                                  </HStack>
                                </VStack>
                              </CardBody>
                            </Card>
                          ))}
                        </SimpleGrid>
                      )}
                    </TabPanel>

                    {/* Sohbetlerden Tab */}
                    <TabPanel px={0}>
                      {chatDocuments.length === 0 ? (
                        <Card 
                          bg={cardBg}
                          backdropFilter="blur(20px)"
                          border="1px solid"
                          borderColor={borderColor}
                          borderRadius="2xl"
                          boxShadow="0 8px 32px rgba(0, 0, 0, 0.1)"
                          overflow="hidden"
                          position="relative"
                          _before={{
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            right: 0,
                            height: "4px",
                            bgGradient: "linear(to-r, green.500, green.600)",
                          }}
                        >
                          <CardBody textAlign="center" py={16}>
                            <Box
                              mb={6}
                              display="inline-block"
                              p={4}
                              borderRadius="full"
                              bg={emptyStateBg}
                            >
                              <AttachmentIcon boxSize={12} color="green.500" />
                            </Box>
                            <Heading size="md" mb={2} color={textPrimary}>
                              Henüz sohbetten doküman yok
                            </Heading>
                            <Text fontSize="md" color={textSecondary}>
                              Sohbetlerden yüklediğiniz dosyalar burada görünecek
                            </Text>
                          </CardBody>
                        </Card>
                      ) : (
                        <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4}>
                          {chatDocuments.map((doc) => (
                            <Card
                              key={doc.id}
                              bg={cardBg}
                              backdropFilter="blur(20px)"
                              border="1px solid"
                              borderColor={borderColor}
                              borderRadius="xl"
                              boxShadow="0 4px 20px rgba(0, 0, 0, 0.1)"
                              overflow="hidden"
                              position="relative"
                              transition="all 0.3s ease"
                              _hover={{
                                transform: "translateY(-4px)",
                                boxShadow: "0 12px 40px rgba(16, 185, 129, 0.2)",
                                borderColor: "green.400",
                              }}
                              _before={{
                                content: '""',
                                position: "absolute",
                                top: 0,
                                left: 0,
                                right: 0,
                                height: "3px",
                                bgGradient: "linear(to-r, green.400, green.500)",
                              }}
                            >
                              <CardBody p={5}>
                                <VStack align="stretch" spacing={4}>
                                  <HStack justify="space-between" align="start">
                                    <Box flex={1} minW={0}>
                                      <HStack spacing={2} mb={2}>
                                        <Box
                                          p={2}
                                          borderRadius="lg"
                                          bg={getFileIconBg(doc.mime_type)}
                                        >
                                          <AttachmentIcon 
                                            boxSize={5} 
                                            color={getFileIconColor(doc.mime_type)}
                                          />
                                        </Box>
                                        <Badge
                                          colorScheme="green"
                                          fontSize="xs"
                                          px={2}
                                          py={1}
                                          borderRadius="md"
                                        >
                                          {formatMimeType(doc.mime_type)}
                                        </Badge>
                                      </HStack>
                                      <Text
                                        fontWeight="semibold"
                                        fontSize="md"
                                        color={textPrimary}
                                        noOfLines={2}
                                        mb={1}
                                      >
                                        {doc.filename}
                                      </Text>
                                    </Box>
                                  </HStack>

                                  <Divider borderColor={borderColor} />

                                  <VStack align="stretch" spacing={2}>
                                    <HStack justify="space-between" fontSize="sm">
                                      <Text color={textSecondary}>Boyut:</Text>
                                      <Text fontWeight="medium" color={textPrimary}>
                                        {formatFileSize(doc.size)}
                                      </Text>
                                    </HStack>
                                    <HStack justify="space-between" fontSize="sm">
                                      <Text color={textSecondary}>Kaynak:</Text>
                                      <Badge
                                        colorScheme="green"
                                        fontSize="xs"
                                        px={2}
                                        py={1}
                                        borderRadius="md"
                                        variant="outline"
                                      >
                                        Sohbet
                                      </Badge>
                                    </HStack>
                                    {doc.uploaded_from_chat_title && (
                                      <HStack justify="space-between" fontSize="sm">
                                        <Text color={textSecondary}>Sohbet:</Text>
                                        <Tooltip
                                          label={`"${doc.uploaded_from_chat_title}" sohbetinden yüklendi`}
                                          placement="top"
                                          hasArrow
                                        >
                                          <Text
                                            fontWeight="medium"
                                            color="green.400"
                                            noOfLines={1}
                                            maxW="150px"
                                            cursor="help"
                                          >
                                            {doc.uploaded_from_chat_title.length > 15
                                              ? doc.uploaded_from_chat_title.substring(0, 15) + "..."
                                              : doc.uploaded_from_chat_title}
                                          </Text>
                                        </Tooltip>
                                      </HStack>
                                    )}
                                    <HStack justify="space-between" fontSize="sm">
                                      <Text color={textSecondary}>Tarih:</Text>
                                      <Text fontWeight="medium" color={textPrimary} fontSize="xs">
                                        {formatDate(doc.created_at)}
                                      </Text>
                                    </HStack>
                                  </VStack>

                                  <Divider borderColor={borderColor} />

                                  <HStack spacing={2} justify="flex-end">
                                    <Tooltip label="Görüntüle" placement="top" hasArrow>
                                      <IconButton
                                        icon={<ViewIcon />}
                                        aria-label="Görüntüle"
                                        size="md"
                                        variant="ghost"
                                        colorScheme="green"
                                        onClick={() => router.push(`/app/documents/${doc.id}`)}
                                        _hover={{
                                          bg: "green.50",
                                          color: "green.600",
                                          transform: "scale(1.1)",
                                        }}
                                        transition="all 0.2s ease"
                                      />
                                    </Tooltip>
                                    <Tooltip label="Sil" placement="top" hasArrow>
                                      <IconButton
                                        icon={<DeleteIcon />}
                                        aria-label="Sil"
                                        size="md"
                                        variant="ghost"
                                        colorScheme="red"
                                        onClick={() => handleDeleteClick(doc.id, doc.filename)}
                                        _hover={{
                                          bg: "red.50",
                                          color: "red.600",
                                          transform: "scale(1.1)",
                                        }}
                                        transition="all 0.2s ease"
                                      />
                                    </Tooltip>
                                  </HStack>
                                </VStack>
                              </CardBody>
                            </Card>
                          ))}
                        </SimpleGrid>
                      )}
                    </TabPanel>
                  </TabPanels>
                </Tabs>
              )}
            </VStack>
          </Box>
        </Box>
      </Box>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        isOpen={deleteDialog.isOpen}
        leastDestructiveRef={cancelRef}
        onClose={handleDeleteCancel}
        motionPreset="slideInBottom"
      >
        <AlertDialogOverlay bg="blackAlpha.600" backdropFilter="blur(4px)" />
                  <AlertDialogContent bg={cardBg} borderRadius="xl" boxShadow="2xl" border="1px solid" borderColor={borderColor}>
          <AlertDialogHeader fontSize="lg" fontWeight="bold" pb={2} color={textPrimary}>
            Dosyayı Sil
          </AlertDialogHeader>
          <AlertDialogBody>
            <Text mb={2}>
              <Text as="span" fontWeight="bold">{deleteDialog.filename}</Text> dosyasını silmek istediğinize emin misiniz?
            </Text>
            <Text fontSize="sm" color="gray.500">
              Bu işlem geri alınamaz. Dosya ve içeriği kalıcı olarak silinecektir.
            </Text>
          </AlertDialogBody>
          <AlertDialogFooter gap={3}>
            <Button ref={cancelRef} onClick={handleDeleteCancel} variant="ghost">
              İptal
            </Button>
            <Button
              colorScheme="red"
              onClick={handleDeleteConfirm}
              _hover={{ bg: "red.600" }}
            >
              Sil
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AuthGuard>
  );
}

