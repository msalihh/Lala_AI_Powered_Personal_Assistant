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
    onDelete(chatId);
    
    toast({
      title: "Sohbet silindi",
      status: "info",
      duration: 2000,
      isClosable: true,
    });
    
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
        title: "Arşivden çıkarıldı",
        status: "info",
        duration: 2000,
        isClosable: true,
      });
    } else {
      onArchive(chatId);
      toast({
        title: "Sohbet arşivlendi",
        status: "info",
        duration: 2000,
        isClosable: true,
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
            boxShadow="xl"
            minW="200px"
            zIndex={9999}
            onClick={(e) => {
              e.stopPropagation();
            }}
            onMouseDown={(e) => {
              e.stopPropagation();
            }}
            sx={{
              zIndex: "9999 !important",
              position: 'relative',
            }}
          >
            <MenuItem 
            icon={<span>📤</span>} 
            onClick={(e) => {
              e.stopPropagation();
              handleShare();
            }}
          >
            Paylaş
          </MenuItem>
          <MenuItem 
            icon={<span>✏️</span>} 
            onClick={(e) => {
              e.stopPropagation();
              onOpen();
            }}
          >
            Yeniden adlandır
          </MenuItem>
          <MenuItem 
            icon={<span>📁</span>} 
            onClick={(e) => {
              e.stopPropagation();
              handleMoveToProject();
            }}
          >
            Projeye taşı
            <span style={{ marginLeft: "auto" }}>›</span>
          </MenuItem>
          <MenuItem 
            icon={<span>📌</span>} 
            onClick={(e) => {
              e.stopPropagation();
              handlePin();
            }}
          >
            {isPinned ? "Sabitlemeyi kaldır" : "Sohbeti sabitle"}
          </MenuItem>
          <MenuItem 
            icon={<span>📦</span>} 
            onClick={(e) => {
              e.stopPropagation();
              handleArchive();
            }}
          >
            {isArchived ? "Arşivden çıkar" : "Arşivle"}
          </MenuItem>
          <MenuItem 
            icon={<span>🗑️</span>} 
            onClick={(e) => {
              e.stopPropagation();
              handleDelete();
            }} 
            color="red.500"
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
        <AlertDialogOverlay bg="blackAlpha.600" backdropFilter="blur(4px)" />
        <AlertDialogContent 
          borderRadius="xl" 
          boxShadow="2xl"
          onKeyDown={handleDeleteKeyDown}
        >
          <AlertDialogHeader fontSize="lg" fontWeight="bold" pb={2}>
            Sohbeti Sil
          </AlertDialogHeader>
          <AlertDialogBody>
            <Text mb={2}>
              <Text as="span" fontWeight="bold">{chatTitle}</Text> sohbetini silmek istediğinize emin misiniz?
            </Text>
            <Text fontSize="sm" color="gray.500">
              Bu işlem geri alınamaz. Sohbet ve tüm mesajları kalıcı olarak silinecektir.
            </Text>
          </AlertDialogBody>
          <AlertDialogFooter gap={3}>
            <Button ref={cancelRef} onClick={onDeleteClose} variant="ghost">
              İptal
            </Button>
            <Button
              ref={deleteButtonRef}
              colorScheme="red"
              onClick={handleDeleteConfirm}
              bg="red.500"
              color="white"
              border="2px solid"
              borderColor="red.600"
              _hover={{ 
                bg: "red.600",
                borderColor: "red.700",
                transform: "scale(1.02)",
              }}
              _active={{ 
                bg: "red.700",
                borderColor: "red.800",
                transform: "scale(0.98)",
              }}
              _focus={{ 
                boxShadow: "0 0 0 3px rgba(220, 38, 38, 0.3)",
                outline: "none",
                bg: "red.500",
                borderColor: "red.400",
                borderWidth: "3px",
              }}
              transition="all 0.2s ease"
            >
              Sil
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

