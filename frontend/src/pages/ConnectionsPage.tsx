import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Database, Plus, Trash2, Zap, CheckCircle, XCircle, Loader2, Shield } from "lucide-react";
import {
  useConnections,
  useCreateConnection,
  useTestConnection,
  useDeleteConnection,
  type Connection,
  type TestResult,
} from "@/hooks/useConnections";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  db_type: z.enum(["hana", "mssql"]),
  host: z.string().min(1, "Host is required"),
  port: z.coerce.number().int().min(1).max(65535),
  database_name: z.string().min(1, "Database name is required"),
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
  is_tls: z.boolean(),
});
type FormData = z.infer<typeof schema>;

const DB_DEFAULTS: Record<"hana" | "mssql", { port: number; placeholder: string }> = {
  hana: { port: 30015, placeholder: "HDB (SAP Business One HANA)" },
  mssql: { port: 1433, placeholder: "SQL Server / Azure SQL" },
};

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-gray-400">Never checked</span>;
  return status === "ok" ? (
    <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
      <CheckCircle className="h-3 w-3" /> Healthy
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs text-red-700 bg-red-50 px-2 py-0.5 rounded-full">
      <XCircle className="h-3 w-3" /> Error
    </span>
  );
}

function TestResultPanel({ result }: { result: TestResult }) {
  return result.success ? (
    <div className="mt-2 p-3 bg-green-50 border border-green-200 rounded-lg text-sm">
      <p className="font-medium text-green-800 flex items-center gap-1">
        <CheckCircle className="h-4 w-4" /> Connection successful
      </p>
      <ul className="mt-1 text-green-700 space-y-0.5 text-xs">
        {result.latency_ms != null && <li>Latency: {result.latency_ms}ms</li>}
        {result.db_version && <li>Version: {result.db_version}</li>}
        <li>
          Read-only: {result.is_read_only ? (
            <span className="text-green-800 font-medium">✓ Confirmed</span>
          ) : (
            <span className="text-amber-700 font-medium">⚠ Write access detected</span>
          )}
        </li>
      </ul>
    </div>
  ) : (
    <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
      <p className="font-medium flex items-center gap-1"><XCircle className="h-4 w-4" /> Failed</p>
      <p className="text-xs mt-0.5">{result.error}</p>
    </div>
  );
}

export default function ConnectionsPage() {
  const { data: connections = [], isLoading } = useConnections();
  const createMutation = useCreateConnection();
  const testMutation = useTestConnection();
  const deleteMutation = useDeleteConnection();

  const [showForm, setShowForm] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  const { register, handleSubmit, watch, reset, formState: { errors, isSubmitting } } =
    useForm<FormData>({
      resolver: zodResolver(schema),
      defaultValues: { db_type: "hana", port: 30015, is_tls: true },
    });

  const dbType = watch("db_type");

  const onSubmit = async (data: FormData) => {
    await createMutation.mutateAsync(data);
    reset();
    setShowForm(false);
  };

  const handleTest = async (id: string) => {
    const result = await testMutation.mutateAsync(id);
    setTestResults((prev) => ({ ...prev, [id]: result }));
  };

  return (
    <div className="p-8 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Connections</h1>
          <p className="text-sm text-gray-500 mt-1">
            Connect to SAP Business One HANA or Microsoft SQL Server
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add connection
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 mb-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-4">New connection</h2>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              {/* Name */}
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input {...register("name")}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="SAP B1 Production" />
                {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
              </div>

              {/* DB type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Database type</label>
                <select {...register("db_type")}
                  onChange={(e) => {
                    const t = e.target.value as "hana" | "mssql";
                    reset({ ...watch(), db_type: t, port: DB_DEFAULTS[t].port });
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500">
                  <option value="hana">SAP B1 HANA</option>
                  <option value="mssql">Microsoft SQL Server</option>
                </select>
              </div>

              {/* Host */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Host</label>
                <input {...register("host")}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="192.168.1.100" />
                {errors.host && <p className="text-xs text-red-600 mt-1">{errors.host.message}</p>}
              </div>

              {/* Port */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Port</label>
                <input {...register("port")} type="number"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                {errors.port && <p className="text-xs text-red-600 mt-1">{errors.port.message}</p>}
              </div>

              {/* Database name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Database name</label>
                <input {...register("database_name")}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder={dbType === "hana" ? "SBODemoUS" : "SBODB"} />
                {errors.database_name && <p className="text-xs text-red-600 mt-1">{errors.database_name.message}</p>}
              </div>

              {/* Username */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input {...register("username")}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="readonly_user" autoComplete="off" />
                {errors.username && <p className="text-xs text-red-600 mt-1">{errors.username.message}</p>}
              </div>

              {/* Password */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input {...register("password")} type="password"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  autoComplete="new-password" />
                {errors.password && <p className="text-xs text-red-600 mt-1">{errors.password.message}</p>}
              </div>

              {/* TLS */}
              <div className="col-span-2 flex items-center gap-2">
                <input {...register("is_tls")} type="checkbox" id="is_tls"
                  className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                <label htmlFor="is_tls" className="text-sm text-gray-700 flex items-center gap-1">
                  <Shield className="h-3.5 w-3.5 text-gray-400" />
                  Require TLS/SSL encryption
                </label>
              </div>
            </div>

            {createMutation.isError && (
              <div role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {(createMutation.error as { response?: { data?: { error?: { message?: string } } } })
                  ?.response?.data?.error?.message ?? "Failed to create connection."}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button type="submit" disabled={isSubmitting}
                className="bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors">
                {isSubmitting ? "Saving…" : "Save connection"}
              </button>
              <button type="button" onClick={() => setShowForm(false)}
                className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors">
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Connection list */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-gray-500 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading connections…
        </div>
      ) : connections.length === 0 ? (
        <div className="text-center py-16 bg-white border border-dashed border-gray-300 rounded-xl">
          <Database className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">No connections yet</p>
          <p className="text-sm text-gray-400 mt-1">Add your first SAP B1 HANA or MSSQL connection above.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {connections.map((conn: Connection) => (
            <div key={conn.id} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 bg-brand-50 rounded-lg flex items-center justify-center shrink-0">
                    <Database className="h-5 w-5 text-brand-600" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{conn.name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {conn.db_type === "hana" ? "SAP B1 HANA" : "Microsoft SQL Server"}
                      {" · "}{conn.host}:{conn.port}{" · "}{conn.database_name}
                      {conn.is_tls && <span className="ml-1 text-green-600">🔒 TLS</span>}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <StatusBadge status={conn.last_health_status} />
                  <button
                    onClick={() => handleTest(conn.id)}
                    disabled={testMutation.isPending}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-800 bg-brand-50 hover:bg-brand-100 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {testMutation.isPending && testMutation.variables === conn.id
                      ? <Loader2 className="h-3 w-3 animate-spin" />
                      : <Zap className="h-3 w-3" />}
                    Test
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(conn.id)}
                    className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    aria-label="Delete connection"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {testResults[conn.id] && (
                <TestResultPanel result={testResults[conn.id]} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
