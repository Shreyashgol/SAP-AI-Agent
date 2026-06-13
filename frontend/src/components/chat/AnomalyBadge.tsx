interface Anomaly {
  severity: "low" | "medium" | "high" | "none";
  description: string;
  z_score?: number;
}

interface Props {
  anomaly: Anomaly;
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-700 border-red-300",
  medium: "bg-amber-100 text-amber-700 border-amber-300",
  low: "bg-yellow-50 text-yellow-700 border-yellow-200",
  none: "hidden",
};

const SEVERITY_LABEL: Record<string, string> = {
  high: "Anomaly",
  medium: "Unusual",
  low: "Outlier",
};

export default function AnomalyBadge({ anomaly }: Props) {
  if (!anomaly || anomaly.severity === "none") return null;

  const style = SEVERITY_STYLES[anomaly.severity] ?? "";
  const label = SEVERITY_LABEL[anomaly.severity] ?? "Flagged";

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border font-medium ${style}`}
      title={anomaly.description}
    >
      ⚠ {label}
    </span>
  );
}
