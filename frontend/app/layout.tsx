import type { Metadata } from "next";
import { ColorModeScript } from "@chakra-ui/react";
import ChakraProviders from "@/providers/ChakraProvider";
import { SidebarProvider } from "@/contexts/SidebarContext";
import { ChatStoreProvider } from "@/contexts/ChatStoreContext";
import "./globals.css";
import "katex/dist/katex.min.css"; // KaTeX CSS - Global import for all pages
import KaTeXWarningSuppressor from "@/components/KaTeXWarningSuppressor";

export const metadata: Metadata = {
  title: "Lala",
  description: "Lala - AI-powered chat application",
  icons: {
    icon: "/lala-icon.png",
    apple: "/lala-icon.png",
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
        <KaTeXWarningSuppressor />
        <ChakraProviders>
          <ChatStoreProvider>
            <SidebarProvider>{children}</SidebarProvider>
          </ChatStoreProvider>
        </ChakraProviders>
      </body>
    </html>
  );
}
