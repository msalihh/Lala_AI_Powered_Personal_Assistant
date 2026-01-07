"use client";

import { ChakraProvider, extendTheme } from "@chakra-ui/react";
import { ReactNode } from "react";

const theme = extendTheme({
  config: {
    initialColorMode: "dark",
    useSystemColorMode: false,
  },
  colors: {
    // Premium Emerald Green palette - modern, technical
    green: {
      50: "#ECFDF5",
      100: "#D1FAE5",
      200: "#A7F3D0",
      300: "#6EE7B7",
      400: "#34D399",
      500: "#10B981",  // Primary accent
      600: "#059669",
      700: "#047857",
      800: "#065F46",
      900: "#064E3B",
    },
    // Purple secondary accent
    purple: {
      50: "#FAF5FF",
      100: "#F3E8FF",
      200: "#E9D5FF",
      300: "#D8B4FE",
      400: "#C084FC",
      500: "#8B5CF6",  // Secondary accent
      600: "#7C3AED",
      700: "#6D28D9",
      800: "#5B21B6",
      900: "#4C1D95",
    },
    // Theme colors
    theme: {
      // Dark Theme
      bg: {
        primary: "#0B0F14",
        secondary: "#111827",
        tertiary: "#1F2937",
        panel: "#111827",
        inner: "#1F2937",
        hover: "#1F2937",
        border: "#1F2937",
      },
      accent: {
        primary: "#10B981",
        hover: "#34D399",
        active: "#059669",
        soft: "rgba(16, 185, 129, 0.15)",
        border: "rgba(16, 185, 129, 0.3)",
      },
      accentSecondary: {
        primary: "#8B5CF6",
        soft: "rgba(139, 92, 246, 0.15)",
      },
      text: {
        primary: "#E5E7EB",
        secondary: "#9CA3AF",
        muted: "#6B7280",
        placeholder: "#6B7280",
        disabled: "#4B5563",
      },
      status: {
        error: "#EF4444",
        warning: "#F59E0B",
        success: "#10B981",
        info: "#10B981",
      },
      code: {
        bg: "#020617",
        border: "#065F46",
      },
    },
    // Light Theme
    themeLight: {
      bg: {
        primary: "#FFFFFF",
        secondary: "#F6F8FA",
        tertiary: "#F0F3F6",
        panel: "#F6F8FA",
        inner: "#F0F3F6",
        hover: "#E7ECF0",
        border: "#D1D9E0",
      },
      accent: {
        primary: "#059669",
        hover: "#10B981",
        active: "#047857",
        soft: "rgba(16, 185, 129, 0.1)",
        border: "rgba(16, 185, 129, 0.25)",
      },
      accentSecondary: {
        primary: "#6D4AFF",
        soft: "rgba(109, 74, 255, 0.1)",
      },
      text: {
        primary: "#1F2328",
        secondary: "#656D76",
        muted: "#8B949E",
        placeholder: "#8B949E",
        disabled: "#B1BAC4",
      },
      status: {
        error: "#DC2626",
        warning: "#D97706",
        success: "#059669",
        info: "#059669",
      },
      code: {
        bg: "#F1F5F9",
        border: "#D1FAE5",
      },
    },
  },
  components: {
    // Button component with emerald green accent
    Button: {
      defaultProps: {
        colorScheme: "green",
      },
      baseStyle: {
        borderRadius: "lg",
        fontWeight: "600",
      },
      variants: {
        solid: (props: { colorScheme: string }) => {
          if (props.colorScheme === "green" || props.colorScheme === "blue") {
            return {
              bg: "green.500",
              color: "white",
              _hover: {
                bg: "green.600",
                transform: "translateY(-1px)",
                boxShadow: "0 4px 12px rgba(16, 185, 129, 0.25)",
              },
              _active: {
                bg: "green.700",
                transform: "translateY(0)",
              },
            };
          }
          return {};
        },
        outline: (props: { colorScheme: string }) => {
          if (props.colorScheme === "green" || props.colorScheme === "blue") {
            return {
              borderColor: "green.500",
              color: "green.500",
              _hover: {
                bg: "rgba(16, 185, 129, 0.05)",
                borderColor: "green.400",
              },
            };
          }
          return {};
        },
        ghost: (props: { colorScheme: string }) => {
          if (props.colorScheme === "green" || props.colorScheme === "blue") {
            return {
              color: "green.500",
              _hover: {
                bg: "rgba(16, 185, 129, 0.1)",
              },
            };
          }
          return {};
        },
      },
    },
    // Avatar component
    Avatar: {
      baseStyle: {
        container: {
          bg: "green.500",
          color: "white",
        },
      },
    },
    // Badge component
    Badge: {
      variants: {
        solid: (props: { colorScheme: string }) => {
          if (props.colorScheme === "green" || props.colorScheme === "blue") {
            return {
              bg: "green.500",
              color: "white",
            };
          }
          return {};
        },
        subtle: (props: { colorScheme: string }) => {
          if (props.colorScheme === "green" || props.colorScheme === "blue") {
            return {
              bg: "green.100",
              color: "green.800",
            };
          }
          return {};
        },
      },
    },
  },
  styles: {
    global: (props: { colorMode: string }) => ({
      body: {
        bg: props.colorMode === "dark" ? "#0B0F14" : "#FFFFFF",
        color: props.colorMode === "dark" ? "#E5E7EB" : "#1F2328",
        transition: "background-color 0.5s cubic-bezier(0.4, 0, 0.2, 1), color 0.5s cubic-bezier(0.4, 0, 0.2, 1)",
      },
      "*": {
        transition: "background-color 0.3s cubic-bezier(0.4, 0, 0.2, 1), color 0.3s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
      },
    }),
  },
});

export default function ChakraProviders({ children }: { children: ReactNode }) {
  return <ChakraProvider theme={theme}>{children}</ChakraProvider>;
}

