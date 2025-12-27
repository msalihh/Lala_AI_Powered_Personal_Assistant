import type { Metadata } from "next";
import { ColorModeScript } from "@chakra-ui/react";
import ChakraProviders from "@/providers/ChakraProvider";
import { SidebarProvider } from "@/contexts/SidebarContext";
import "./globals.css";
import "katex/dist/katex.min.css"; // KaTeX CSS - Global import for all pages

export const metadata: Metadata = {
  title: "HACE",
  description: "HACE - AI-powered chat application",
  icons: {
    icon: "/hace-logo.svg",
    apple: "/hace-logo.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr">
      <head>
        <ColorModeScript initialColorMode="dark" />
      </head>
      <body suppressHydrationWarning>
        <ChakraProviders>
          <SidebarProvider>{children}</SidebarProvider>
        </ChakraProviders>
      </body>
    </html>
  );
}
