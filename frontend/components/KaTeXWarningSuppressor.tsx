"use client";

import { useEffect } from "react";

/**
 * Suppresses KaTeX LaTeX compatibility warnings in the console.
 * This is a client-side component that runs only in the browser.
 */
export default function KaTeXWarningSuppressor() {
  useEffect(() => {
    // Suppress KaTeX LaTeX compatibility warnings
    const originalWarn = console.warn;
    console.warn = (...args: any[]) => {
      const message = args[0]?.toString() || '';
      // Filter out KaTeX LaTeX compatibility warnings
      if (message.includes('LaTeX-incompatible') || 
          message.includes('newLineInDisplayMode') ||
          message.includes('strict mode is set to')) {
        return; // Suppress this warning
      }
      originalWarn.apply(console, args);
    };
    
    return () => {
      // Restore original console.warn on unmount
      console.warn = originalWarn;
    };
  }, []);

  return null; // This component doesn't render anything
}

