"use client";

import {
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Portal,
  IconButton,
  useDisclosure,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Input,
  Button,
  useToast,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Text,
  Checkbox,
  Box,
} from "@chakra-ui/react";
import { HamburgerIcon } from "@chakra-ui/icons";

// 3 nokta ikonu için custom component
const MoreVerticalIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <circle cx="8" cy="3" r="1.5" />
    <circle cx="8" cy="8" r="1.5" />
    <circle cx="8" cy="13" r="1.5" />
  </svg>
);
import { useState, useRef, useEffect } from "react";

interface ChatContextMenuProps {
  chatId: string;
  chatTitle: string;
  isPinned?: boolean;
  isArchived?: boolean;
  onRename: (chatId: string, newTitle: string) => void;
  onDelete: (chatId: string) => void;
  onPin: (chatId: string) => void;
  onUnpin: (chatId: string) => void;
  onArchive: (chatId: string) => void;
  onUnarchive: (chatId: string) => void;
}

export default function ChatContextMenu({
  chatId,
  chatTitle,
  isPinned = false,
  isArchived = false,
  onRename,
  onDelete,
  onPin,
  onUnpin,
  onArchive,
  onUnarchive,
}: ChatContextMenuProps) {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const deleteButtonRef = useRef<HTMLButtonElement>(null);
  const [newTitle, setNewTitle] = useState(chatTitle);
  const [deleteDocuments, setDeleteDocuments] = useState(false);
  const toast = useToast();

  const handleRename = () => {
    if (newTitle.trim()) {
      onRename(chatId, newTitle.trim());
      onClose();
      toast({
        title: "Sohbet yeniden adlandırıldı",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    }
  };

  const handleDelete = () => {
    onDeleteOpen();
  };

  const handleDeleteConfirm = () => {
    // Close dialog first to prevent focus return
    onDeleteClose();

    // Immediately blur any active element to prevent focus on sidebar toggle
    try {
      const activeElement = document.activeElement as HTMLElement | null;
      if (activeElement && activeElement !== document.body) {
        activeElement.blur();
      }
      // Force blur on body to ensure no element has focus
      if (document.body) {
        (document.body as HTMLElement).blur();
      }
    } catch (e) {
      // Ignore blur errors
    }

    // Call delete after blur
    // Note: onDelete callback (Sidebar.handleDelete) will show toast and handle navigation
    // Pass deleteDocuments flag to onDelete
    (onDelete as any)(chatId, deleteDocuments);

    // Dispatch event to focus input - use multiple attempts with delays
    // First attempt: immediate
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("chatDeleted", { detail: { focusInput: true } }));
    }, 50);

    // Second attempt: after a bit longer (in case DOM isn't ready)
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("chatDeleted", { detail: { focusInput: true } }));
    }, 200);

    // Third attempt: after even longer (fallback)
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("chatDeleted", { detail: { focusInput: true } }));
    }, 500);
  };

  // Focus delete button when modal opens and handle Enter key
  useEffect(() => {
    if (isDeleteOpen && deleteButtonRef.current) {
      // Small delay to ensure modal is fully rendered
      setTimeout(() => {
        deleteButtonRef.current?.focus();
      }, 100);
    }
  }, [isDeleteOpen]);

  // Handle Enter key press in delete modal
  const handleDeleteKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleDeleteConfirm();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onDeleteClose();
    }
  };

  const handlePin = () => {
    if (isPinned) {
      onUnpin(chatId);
      toast({
        title: "Sabitleme kaldırıldı",
        status: "info",
        duration: 2000,
        isClosable: true,
      });
    } else {
      onPin(chatId);
      toast({
        title: "Sohbet sabitlendi",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    }
  };

  const handleArchive = () => {
    if (isArchived) {
      onUnarchive(chatId);
      toast({
        title: "Sohbet arşivden çıkarıldı",
        description: `${chatTitle} sohbeti arşivden çıkarıldı`,
        status: "success",
        duration: 3000,
        isClosable: true,
        position: "top-right",
      });
    } else {
      onArchive(chatId);
      toast({
        title: "Sohbet arşivlendi",
        description: `${chatTitle} sohbeti arşivlendi`,
        status: "info",
        duration: 3000,
        isClosable: true,
        position: "top-right",
      });
    }
  };

  const handleShare = () => {
    const chatUrl = `${window.location.origin}/chat?chatId=${chatId}`;
    navigator.clipboard.writeText(chatUrl).then(() => {
      toast({
        title: "Link kopyalandı",
        description: "Sohbet linki panoya kopyalandı",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    });
  };

  const handleMoveToProject = () => {
    toast({
      title: "Projeye taşı",
      description: "Bu özellik yakında eklenecek",
      status: "info",
      duration: 2000,
      isClosable: true,
    });
  };

  return (
    <>
      <Menu
        isLazy
        placement="bottom-end"
        closeOnBlur={true}
        closeOnSelect={true}
        strategy="fixed"
      >
        <MenuButton
          as={IconButton}
          icon={<MoreVerticalIcon />}
          variant="ghost"
          size="sm"
          onMouseDown={(e) => {
            e.stopPropagation();
          }}
          aria-label="Sohbet seçenekleri"
          minW="24px"
          h="24px"
          zIndex={10}
        />
        <Portal>
          <MenuList
            bg="#111827"
            borderColor="rgba(16, 185, 129, 0.2)"
            boxShadow="0 4px 20px rgba(0, 0, 0, 0.4)"
            py={1.5}
            minW="180px"
            zIndex={9999}
            borderRadius="xl"
            onClick={(e) => {
              e.stopPropagation();
            }}
            onMouseDown={(e) => {
              e.stopPropagation();
            }}
          >
            <MenuItem
              onClick={(e) => {
                e.stopPropagation();
                handleShare();
              }}
              py={2.5}
              px={4}
              fontSize="14px"
              fontWeight="500"
              color="gray.200"
              bg="transparent"
              _hover={{ bg: "rgba(16, 185, 129, 0.1)", color: "#10B981" }}
              transition="all 0.2s"
            >
              Paylaş
            </MenuItem>
            <MenuItem
              onClick={(e) => {
                e.stopPropagation();
                onOpen();
              }}
              py={2.5}
              px={4}
              fontSize="14px"
              fontWeight="500"
              color="gray.200"
              bg="transparent"
              _hover={{ bg: "rgba(16, 185, 129, 0.1)", color: "#10B981" }}
              transition="all 0.2s"
            >
              Yeniden adlandır
            </MenuItem>
            <MenuItem
              onClick={(e) => {
                e.stopPropagation();
                handleMoveToProject();
              }}
              py={2.5}
              px={4}
              fontSize="14px"
              fontWeight="500"
              color="gray.200"
              bg="transparent"
              _hover={{ bg: "rgba(16, 185, 129, 0.1)", color: "#10B981" }}
              transition="all 0.2s"
            >
              Projeye taşı
              <Box as="span" ml="auto" fontSize="18px" opacity={0.5}>›</Box>
            </MenuItem>
            <MenuItem
              onClick={(e) => {
                e.stopPropagation();
                handlePin();
              }}
              py={2.5}
              px={4}
              fontSize="14px"
              fontWeight="500"
              color="gray.200"
              bg="transparent"
              _hover={{ bg: "rgba(16, 185, 129, 0.1)", color: "#10B981" }}
              transition="all 0.2s"
            >
              {isPinned ? "Sabitlemeyi kaldır" : "Sohbeti sabitle"}
            </MenuItem>
            <MenuItem
              onClick={(e) => {
                e.stopPropagation();
                handleArchive();
              }}
              py={2.5}
              px={4}
              fontSize="14px"
              fontWeight="500"
              color="gray.200"
              bg="transparent"
              _hover={{ bg: "rgba(16, 185, 129, 0.1)", color: "#10B981" }}
              transition="all 0.2s"
            >
              {isArchived ? "Arşivden çıkar" : "Arşivle"}
            </MenuItem>
            <Box h="1px" bg="rgba(16, 185, 129, 0.1)" my={1} />
            <MenuItem
              onClick={(e) => {
                e.stopPropagation();
                handleDelete();
              }}
              py={2.5}
              px={4}
              fontSize="14px"
              fontWeight="500"
              color="red.400"
              bg="transparent"
              _hover={{ bg: "rgba(220, 38, 38, 0.1)", color: "red.500" }}
              transition="all 0.2s"
            >
              Sil
            </MenuItem>
          </MenuList>
        </Portal>
      </Menu>

      <Modal isOpen={isOpen} onClose={onClose}>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Sohbeti Yeniden Adlandır</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Sohbet adı"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleRename();
                }
              }}
              autoFocus
            />
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose}>
              İptal
            </Button>
            <Button colorScheme="blue" onClick={handleRename}>
              Kaydet
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
        motionPreset="slideInBottom"
        returnFocusOnClose={false}
      >
        <AlertDialogOverlay bg="rgba(0, 0, 0, 0.7)" backdropFilter="blur(8px)" />
        <AlertDialogContent
          bg="#111827"
          color="gray.100"
          borderRadius="2xl"
          boxShadow="0 10px 40px rgba(0, 0, 0, 0.5)"
          border="1px solid"
          borderColor="rgba(16, 185, 129, 0.2)"
          onKeyDown={handleDeleteKeyDown}
          mx={4}
        >
          <AlertDialogHeader fontSize="xl" fontWeight="bold" pt={6} pb={2}>
            Sohbeti Sil
          </AlertDialogHeader>
          <AlertDialogBody>
            <Text mb={6} fontSize="17px" color="gray.200" fontWeight="500">
              <Text as="span" fontWeight="700" color="#10B981">{chatTitle}</Text> sohbetini silmek istediğinize emin misiniz?
            </Text>

            <Box py={2}>
              <Checkbox
                isChecked={deleteDocuments}
                onChange={(e) => setDeleteDocuments(e.target.checked)}
                colorScheme="green"
                size="md"
                sx={{
                  "span.chakra-checkbox__control": {
                    borderRadius: "4px",
                    bg: "transparent",
                    borderColor: "rgba(16, 185, 129, 0.4)",
                  },
                  "span.chakra-checkbox__control[data-checked]": {
                    bg: "#10B981",
                    borderColor: "#10B981",
                    color: "white",
                  }
                }}
              >
                <Text fontSize="15px" fontWeight="500" color="gray.300">
                  Bu sohbette yüklenen dosyaları da sil
                </Text>
              </Checkbox>
            </Box>
          </AlertDialogBody>
          <AlertDialogFooter pt={2} pb={6} gap={3}>
            <Button
              ref={cancelRef}
              onClick={onDeleteClose}
              variant="ghost"
              px={6}
              fontWeight="600"
              color="gray.400"
              _hover={{ bg: "rgba(255, 255, 255, 0.05)", color: "white" }}
            >
              İptal
            </Button>
            <Button
              ref={deleteButtonRef}
              onClick={handleDeleteConfirm}
              bg="#EF4444"
              color="white"
              px={8}
              fontWeight="700"
              borderRadius="xl"
              boxShadow="0 4px 12px rgba(239, 68, 68, 0.3)"
              _hover={{
                bg: "#DC2626",
                transform: "translateY(-1px)",
                boxShadow: "0 6px 15px rgba(239, 68, 68, 0.4)",
              }}
              _active={{
                bg: "#B91C1C",
                transform: "translateY(0)",
              }}
              transition="all 0.2s"
            >
              Kalıcı Olarak Sil
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

