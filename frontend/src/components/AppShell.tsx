"use client";

import { useEffect, useMemo, useState } from "react";
import { AppProvider, useApp } from "@/context/AppContext";
import Sidebar from "@/components/Sidebar";
import TripAlert from "@/components/TripAlert";

function AppContent({ children }: { children: React.ReactNode }) {
  const { data } = useApp();
  const [dismissedTripTime, setDismissedTripTime] = useState<number | null>(null);
  const [mutedTripTime, setMutedTripTime] = useState<number | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    if (typeof window === "undefined") {
      return "dark";
    }
    const storedTheme = window.localStorage.getItem("relay-theme");
    return storedTheme === "light" ? "light" : "dark";
  });

  const relay = data?.relay;
  const activeTripTime = relay?.trip_time ?? null;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem("relay-theme", nextTheme);
  };

  const showTripAlert = useMemo(() => {
    return (
      relay?.status === "TRIP" &&
      activeTripTime != null &&
      activeTripTime !== dismissedTripTime
    );
  }, [relay?.status, activeTripTime, dismissedTripTime]);

  const muted = activeTripTime != null && mutedTripTime === activeTripTime;

  return (
    <>
      <div style={{ display: "flex", minHeight: "100vh" }}>
        <Sidebar theme={theme} onToggleTheme={toggleTheme} />
        <main style={{ flex: 1, minWidth: 0, overflow: "auto" }}>{children}</main>
      </div>
      {showTripAlert && relay && (
        <TripAlert
          relay={relay}
          muted={muted}
          onToggleMute={() => setMutedTripTime(muted ? null : activeTripTime)}
          onDismiss={() => setDismissedTripTime(activeTripTime)}
        />
      )}
    </>
  );
}

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppProvider>
      <AppContent>{children}</AppContent>
    </AppProvider>
  );
}
