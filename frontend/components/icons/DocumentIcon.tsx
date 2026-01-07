import { Box, BoxProps } from "@chakra-ui/react";

interface DocumentIconProps extends BoxProps {
  size?: number | string;
}

export default function DocumentIcon({ size = 24, ...props }: DocumentIconProps) {
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
      {/* Document body - Light green rectangle with rounded corners */}
      <rect
        x="4"
        y="3"
        width="16"
        height="18"
        rx="1.5"
        fill="#A7F3D0"
        stroke="#065F46"
        strokeWidth="0.4"
      />
      {/* Folded corner - Darker blue-green triangle */}
      <path
        d="M 18 3 L 20 5 L 18 7 Z"
        fill="#047857"
        stroke="#065F46"
        strokeWidth="0.4"
      />
      {/* Three horizontal text lines */}
      <line
        x1="7"
        y1="8.5"
        x2="15"
        y2="8.5"
        stroke="#047857"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <line
        x1="7"
        y1="11.5"
        x2="14"
        y2="11.5"
        stroke="#047857"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <line
        x1="7"
        y1="14.5"
        x2="16"
        y2="14.5"
        stroke="#047857"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </Box>
  );
}

