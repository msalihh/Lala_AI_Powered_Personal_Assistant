"use client";

import React from "react";
import { VStack } from "@chakra-ui/react";
import AttachmentCard from "./AttachmentCard";

interface Attachment {
  id: string;
  filename: string;
  type: string;
  size: number;
  documentId?: string;
}

interface AttachmentListProps {
  attachments: Attachment[] | undefined;
  onAttachmentClick?: (attachment: Attachment) => void;
}

/**
 * AttachmentList component - Displays a list of file attachments.
 * Used in chat message flow to show multiple attached files.
 */
export default function AttachmentList({ attachments, onAttachmentClick }: AttachmentListProps) {
  if (!attachments || attachments.length === 0) {
    return null;
  }

  return (
    <VStack align="flex-end" spacing={1.5} w="auto" maxW="100%">
      {attachments.map((attachment) => (
        <AttachmentCard
          key={attachment.id}
          attachment={attachment}
          onClick={onAttachmentClick ? () => onAttachmentClick(attachment) : undefined}
        />
      ))}
    </VStack>
  );
}

