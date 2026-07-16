import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { ApiError } from "@/api/client";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/contexts/ToastContext";
import { NativeVersionGate } from "@/components/native/NativeVersionGate";
import App from "./App";
import "./i18n";
import "./styles/global.css";

// Dynamic import: keeps @capacitor/status-bar's native calls out of the web
// bundle's execution path (see contexts/AuthContext.tsx's nativeAuth).
if (Capacitor.isNativePlatform()) {
  void import("@/services/nativeStatusBar").then((m) => m.initNativeStatusBar());
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // 401s are handled by the client's refresh replay; 4xx are final.
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status < 500) && failureCount < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <NativeVersionGate>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ToastProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ToastProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </NativeVersionGate>
  </StrictMode>,
);

// Confirms to CapacitorUpdater that the freshly-applied OTA bundle (if any)
// rendered successfully — without this, the plugin assumes it crashed and
// silently reverts to the previous bundle once its readiness timeout
// elapses, mid-session. Fired after the initial render call returns (so a
// synchronous mount failure never sends a false "ready").
if (Capacitor.isNativePlatform()) {
  void import("@/services/nativeUpdater").then((m) => m.notifyNativeAppReady());
}
