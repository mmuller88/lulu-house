import { StrictMode, useEffect, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

import { EnergyDatePicker, type DayInfo } from "./EnergyDatePicker";
import "./index.css";

type MountOptions = {
  dayKeys: string[];
  daysData: Record<string, DayInfo>;
  currentDay: string;
  onSelectDay: (day: string) => void;
};

let root: Root | null = null;

function PickerHost({
  getOptions,
}: {
  getOptions: () => MountOptions;
}) {
  const [options, setOptions] = useState(getOptions);

  useEffect(() => {
    const handler = () => setOptions(getOptions());
    window.addEventListener("lulu-day-change", handler);
    return () => window.removeEventListener("lulu-day-change", handler);
  }, [getOptions]);

  const idx = options.dayKeys.indexOf(options.currentDay);

  return (
    <EnergyDatePicker
      dayKeys={options.dayKeys}
      daysData={options.daysData}
      currentDay={options.currentDay}
      onSelectDay={options.onSelectDay}
      onPrevDay={() => {
        if (idx > 0) options.onSelectDay(options.dayKeys[idx - 1]);
      }}
      onNextDay={() => {
        if (idx < options.dayKeys.length - 1) {
          options.onSelectDay(options.dayKeys[idx + 1]);
        }
      }}
      canPrev={idx > 0}
      canNext={idx >= 0 && idx < options.dayKeys.length - 1}
    />
  );
}

export function mountDatePicker(
  element: HTMLElement,
  getOptions: () => MountOptions,
) {
  if (!root) {
    root = createRoot(element);
  }
  root.render(
    <StrictMode>
      <PickerHost getOptions={getOptions} />
    </StrictMode>,
  );
}

export function notifyDayChange() {
  window.dispatchEvent(new Event("lulu-day-change"));
}

const api = { mountDatePicker, notifyDayChange };
if (typeof globalThis !== "undefined") {
  (globalThis as typeof globalThis & { LuluDatePicker: typeof api }).LuluDatePicker =
    api;
}
