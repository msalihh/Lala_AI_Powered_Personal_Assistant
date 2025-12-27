"use client";

import { ChakraProvider, extendTheme } from "@chakra-ui/react";
import { ReactNode } from "react";

const theme = extendTheme({
  config: {
    initialColorMode: "dark",
    useSystemColorMode: false,
  },
  colors: {
    // Profesyonel tema renk paleti - GitHub tarzı
    theme: {
      // Dark Theme
      bg: {
        primary: "#0D1117",
        panel: "#161B22",
        inner: "#1C2128",
        hover: "#22272E",
        border: "#30363D",
      },
      accent: {
        primary: "#3FB950",
        hover: "#2EA043",
        active: "#238636",
        soft: "rgba(63, 185, 80, 0.15)",
        border: "rgba(63, 185, 80, 0.3)",
      },
      text: {
        primary: "#E6EDF3",
        secondary: "#8B949E",
        placeholder: "#6E7681",
        disabled: "#484F58",
      },
      status: {
        error: "#F85149",
        warning: "#D29922",
        success: "#3FB950",
        info: "#58A6FF",
      },
    },
    // Light Theme (useColorModeValue ile kullanılacak)
    themeLight: {
      bg: {
        primary: "#FFFFFF",
        panel: "#F6F8FA",
        inner: "#F0F3F6",
        hover: "#E7ECF0",
        border: "#D1D9E0",
      },
      accent: {
        primary: "#1A7F37",
        hover: "#2EA043",
        active: "#238636",
        soft: "rgba(26, 127, 55, 0.1)",
        border: "rgba(26, 127, 55, 0.25)",
      },
      text: {
        primary: "#1F2328",
        secondary: "#656D76",
        placeholder: "#8B949E",
        disabled: "#B1BAC4",
      },
      status: {
        error: "#CF222E",
        warning: "#9A6700",
        success: "#1A7F37",
        info: "#0969DA",
      },
    },
  },
  styles: {
    global: (props: { colorMode: string }) => ({
      body: {
        bg: props.colorMode === "dark" ? "#0D1117" : "#FFFFFF",
        color: props.colorMode === "dark" ? "#E6EDF3" : "#1F2328",
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

