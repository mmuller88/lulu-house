import { useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { de } from "date-fns/locale";
import { CalendarIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type DayInfo = {
  absent?: boolean;
  totals: { grid: number; pv: number };
};

export type DatePickerProps = {
  dayKeys: string[];
  daysData: Record<string, DayInfo>;
  currentDay: string;
  onSelectDay: (day: string) => void;
  onPrevDay: () => void;
  onNextDay: () => void;
  canPrev: boolean;
  canNext: boolean;
};

export function EnergyDatePicker({
  dayKeys,
  daysData,
  currentDay,
  onSelectDay,
  onPrevDay,
  onNextDay,
  canPrev,
  canNext,
}: DatePickerProps) {
  const [open, setOpen] = useState(false);
  const selected = useMemo(() => parseISO(currentDay), [currentDay]);
  const available = useMemo(
    () => new Set(dayKeys),
    [dayKeys],
  );
  const fromMonth = useMemo(() => parseISO(dayKeys[0]), [dayKeys]);
  const toMonth = useMemo(
    () => parseISO(dayKeys[dayKeys.length - 1]),
    [dayKeys],
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={onPrevDay}
        disabled={!canPrev}
        aria-label="Vorheriger Tag"
      >
        <span aria-hidden="true">←</span>
      </Button>

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className={cn(
              "min-w-[220px] justify-start text-left font-normal",
              !currentDay && "text-muted-foreground",
            )}
          >
            <CalendarIcon className="h-4 w-4" />
            {format(selected, "PPP", { locale: de })}
            {daysData[currentDay]?.absent ? " ✈" : ""}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={selected}
            defaultMonth={selected}
            startMonth={fromMonth}
            endMonth={toMonth}
            disabled={(date) => {
              const iso = format(date, "yyyy-MM-dd");
              return !available.has(iso);
            }}
            modifiers={{
              absent: dayKeys.filter((day) => daysData[day]?.absent),
            }}
            modifiersClassNames={{
              absent: "border border-dashed border-muted-foreground/60",
            }}
            onSelect={(date) => {
              if (!date) return;
              const iso = format(date, "yyyy-MM-dd");
              if (!available.has(iso)) return;
              onSelectDay(iso);
              setOpen(false);
            }}
          />
        </PopoverContent>
      </Popover>

      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={onNextDay}
        disabled={!canNext}
        aria-label="Nächster Tag"
      >
        <span aria-hidden="true">→</span>
      </Button>
    </div>
  );
}
