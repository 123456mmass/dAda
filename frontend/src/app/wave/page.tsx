"use client";

import React from "react";
import { useApp } from "@/context/AppContext";
import WaveChart from "@/components/WaveChart";

export default function WaveformsPage() {
  const { data } = useApp();

  return (
    <div className="p-4">
      <WaveChart waveforms={data?.waveforms} />
    </div>
  );
}
