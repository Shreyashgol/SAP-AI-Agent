import {
  ResponsiveContainer,
  LineChart,
  AreaChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

interface SeriesPoint {
  label: string;
  value: number;
}

interface DeltaPoint {
  label: string;
  delta_pct: number | null;
  delta_abs: number;
}

interface TrendData {
  type: "trend";
  series: SeriesPoint[];
  deltas: DeltaPoint[];
  direction: "up" | "down" | "flat";
  cagr_pct: number;
  period_column: string;
  metric_column: string;
  periods: number;
}

interface Props {
  data: TrendData;
  chartHint: "line" | "area";
}

function formatValue(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toFixed(2);
}

const DIRECTION_COLOR: Record<string, string> = {
  up: "#16a34a",
  down: "#dc2626",
  flat: "#6b7280",
};

const STROKE = "#3b82f6";
const FILL = "#93c5fd";

export default function TrendChart({ data, chartHint }: Props) {
  if (!data.series || data.series.length === 0) return null;

  const directionColor = DIRECTION_COLOR[data.direction] ?? "#6b7280";
  const directionLabel =
    data.direction === "up" ? "▲" : data.direction === "down" ? "▼" : "→";

  const chartData = data.series.map((pt) => ({
    name: pt.label,
    value: pt.value,
  }));

  const Chart = chartHint === "area" ? AreaChart : LineChart;

  return (
    <div className="space-y-2">
      {/* KPI strip */}
      <div className="flex items-center gap-4 text-xs">
        <span className="font-medium text-gray-700">{data.metric_column}</span>
        <span style={{ color: directionColor }} className="font-semibold">
          {directionLabel} {data.direction}
        </span>
        {data.cagr_pct !== 0 && (
          <span className="text-gray-500">
            CAGR {data.cagr_pct > 0 ? "+" : ""}
            {data.cagr_pct.toFixed(1)}%
          </span>
        )}
        <span className="text-gray-400">{data.periods} periods</span>
      </div>

      {/* Chart */}
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <Chart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={formatValue}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={false}
              width={52}
            />
            <Tooltip
              formatter={(val: number) => [formatValue(val), data.metric_column]}
              labelStyle={{ fontSize: 11 }}
              contentStyle={{ fontSize: 11, borderRadius: 8 }}
            />
            {chartHint === "area" ? (
              <Area
                type="monotone"
                dataKey="value"
                stroke={STROKE}
                fill={FILL}
                strokeWidth={2}
                dot={data.series.length <= 12}
                activeDot={{ r: 4 }}
              />
            ) : (
              <Line
                type="monotone"
                dataKey="value"
                stroke={STROKE}
                strokeWidth={2}
                dot={data.series.length <= 12}
                activeDot={{ r: 4 }}
              />
            )}
          </Chart>
        </ResponsiveContainer>
      </div>

      {/* Delta chips — last 5 periods */}
      {data.deltas.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.deltas.slice(-5).map((d) => (
            <span
              key={d.label}
              className={`text-xs px-2 py-0.5 rounded-full border font-mono ${
                d.delta_pct == null
                  ? "bg-gray-50 text-gray-400 border-gray-200"
                  : d.delta_pct >= 0
                  ? "bg-green-50 text-green-700 border-green-200"
                  : "bg-red-50 text-red-600 border-red-200"
              }`}
            >
              {d.label}{" "}
              {d.delta_pct != null
                ? `${d.delta_pct >= 0 ? "+" : ""}${d.delta_pct.toFixed(1)}%`
                : "n/a"}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
