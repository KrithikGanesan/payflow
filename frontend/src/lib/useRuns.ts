import { useEffect, useState } from "react";
import type { RunRecord } from "@/contracts";
import { listRuns, onModeChange, getMode } from "@/api";

export function useRuns() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    function load() {
      setLoading(true);
      listRuns().then((r) => {
        if (alive) {
          setRuns(r);
          setLoading(false);
        }
      });
    }
    load();
    // reload when the data-source mode changes
    const off = onModeChange(load);
    return () => {
      alive = false;
      off();
    };
  }, []);

  return { runs, loading, mode: getMode() };
}
