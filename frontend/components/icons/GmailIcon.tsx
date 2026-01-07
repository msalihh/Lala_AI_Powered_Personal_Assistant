import { Box, BoxProps } from "@chakra-ui/react";

interface GmailIconProps extends BoxProps {
  size?: number | string;
}

export default function GmailIcon({ size = 24, ...props }: GmailIconProps) {
  return (
    <Box
      as="svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      {/* Gmail M Logo - Multi-color segments with proper proportions */}
      {/* Top-left segment - Red */}
      <path
        d="M 5 4 L 5 10 L 11 4 Z"
        fill="#EA4335"
        stroke="#0D1117"
        strokeWidth="0.3"
      />
      {/* Bottom-left segment - Blue */}
      <path
        d="M 5 10 L 5 20 L 11 16 L 11 10 Z"
        fill="#4285F4"
        stroke="#0D1117"
        strokeWidth="0.3"
      />
      {/* Center V shape - Pink/Red with fold lines */}
      <path
        d="M 11 4 L 17 10 L 11 16 Z"
        fill="#C5221F"
        stroke="#0D1117"
        strokeWidth="0.3"
      />
      <path
        d="M 11 7 L 14 10 L 11 13"
        stroke="#8B1A17"
        strokeWidth="0.25"
        fill="none"
        strokeDasharray="0.8,0.8"
        opacity="0.6"
      />
      {/* Top-right segment - Yellow */}
      <path
        d="M 17 4 L 17 10 L 11 4 Z"
        fill="#FBBC04"
        stroke="#0D1117"
        strokeWidth="0.3"
      />
      {/* Bottom-right segment - Green */}
      <path
        d="M 17 10 L 17 20 L 11 16 L 11 10 Z"
        fill="#34A853"
        stroke="#0D1117"
        strokeWidth="0.3"
      />
    </Box>
  );
}

