"use client";

import React from "react";
import { useApp } from "@/context/AppContext";
import MeterCard from "@/components/MeterCard";
import TripChart from "@/components/TripChart";
import BiasChart from "@/components/BiasChart";

export default function Home() {
  const { data } = useApp();

  if (!data) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-white">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
          <p className="text-sm font-medium text-slate-400">Loading metrics...</p>
        </div>
      </div>
    );
  }

  const { meters, relay } = data;

  return (
    <div className="p-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <MeterCard
          title="High Voltage Side (HV)"
          side="HV"
          address={1}
          data={meters.hv}
          relay={relay}
        />
        <MeterCard
          title="Low Voltage Side (LV)"
          side="LV"
          address={2}
          data={meters.lv}
          relay={relay}
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {relay && <BiasChart relay={relay} />}
        {relay && <TripChart relay={relay} />}
      </div>
    </div>
  );
}
