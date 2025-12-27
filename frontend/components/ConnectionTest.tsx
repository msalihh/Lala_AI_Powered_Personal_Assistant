"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function ConnectionTest() {
  const [status, setStatus] = useState<"checking" | "ok" | "down">("checking");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function checkBackend() {
      try {
        await apiFetch<{ ok: boolean }>("/api/health");
        setStatus("ok");
        setError(null);
      } catch (err: any) {
        setStatus("down");
        setError(err.detail || "Connection failed");
      }
    }

    checkBackend();
  }, []);

  return (
    <div style={{
      padding: "12px 16px",
      marginBottom: "24px",
      borderRadius: "10px",
      fontSize: "13px",
      backgroundColor: status === "ok" 
        ? "rgba(16, 185, 129, 0.1)" 
        : status === "down" 
        ? "rgba(239, 68, 68, 0.1)" 
        : "rgba(251, 191, 36, 0.1)",
      color: status === "ok" 
        ? "#10b981" 
        : status === "down" 
        ? "#ef4444" 
        : "#fbbf24",
      border: `1px solid ${status === "ok" 
        ? "rgba(16, 185, 129, 0.3)" 
        : status === "down" 
        ? "rgba(239, 68, 68, 0.3)" 
        : "rgba(251, 191, 36, 0.3)"}`,
      display: "flex",
      alignItems: "center",
      gap: "8px",
      fontWeight: "500"
    }}>
      <span style={{
        width: "6px",
        height: "6px",
        borderRadius: "50%",
        backgroundColor: status === "ok" 
          ? "#10b981" 
          : status === "down" 
          ? "#ef4444" 
          : "#fbbf24",
        animation: status === "checking" ? "neuralPulse 2s ease-in-out infinite" : "none"
      }}></span>
      <span>
        <strong>Bağlantı Durumu:</strong>{" "}
        {status === "checking" && "Bağlantı kuruluyor..."}
        {status === "ok" && "✓ Bağlandı"}
        {status === "down" && "✗ Bağlantı başarısız"}
      </span>
      {error && (
        <span style={{ 
          display: "block", 
          marginTop: "4px", 
          fontSize: "11px",
          opacity: 0.8,
          width: "100%"
        }}>
          {error}
        </span>
      )}
    </div>
  );
}

