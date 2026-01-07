"use client";

import { Box, BoxProps } from "@chakra-ui/react";

interface LalaAILogoProps extends BoxProps {
  size?: number | string;
}

export default function LalaAILogo({ size = 24, ...props }: LalaAILogoProps) {
  return (
    <Box
      as="img"
      src="/lala-icon.png"
      alt="Lala Logo"
      width={size}
      height={size}
      objectFit="contain"
      {...props}
    />
  );
}
