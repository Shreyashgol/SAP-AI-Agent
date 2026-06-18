import { useState } from "react";
import { Plus, Trash2, LayoutDashboard, Share2, Lock, X, GripHorizontal } from "lucide-react";
import GridLayout, { type Layout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import {
  useDashboards,
  useCreateDashboard,
  useDeleteDashboard,
  usePatchDashboard,
  useWidgets,
  useDeleteWidget,
  usePatchWidget,
  type Dashboard,
  type DashboardWidget,
} from "@/hooks/useDashboards";

// ── Widget card ───────────────────────────────────────────────────────────────

function WidgetCard({
  widget,
  dashboardId,
}: {
  widget: DashboardWidget;
  dashboardId: string;
}) {
  const deleteWidget = useDeleteWidget(dashboardId);
  const patchWidget = usePatchWidget(dashboardId);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleValue, setTitleValue] = useState(widget.title ?? "Untitled");

  function saveTitle() {
    if (titleValue.trim() && titleValue !== widget.title) {
      patchWidget.mutate({ widgetId: widget.id, body: { title: titleValue.trim() } });
    }
    setEditingTitle(false);
  }

  const typeLabel: Record<string, string> = {
    kpi_card: "KPI",
    bar: "Bar chart",
    line: "Line chart",
    area: "Area chart",
    donut: "Donut chart",
    waterfall: "Waterfall",
    table: "Table",
  };

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      {/* Widget header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/60">
        <GripHorizontal className="w-3.5 h-3.5 text-gray-300 dark:text-gray-600 cursor-grab" />
        {editingTitle ? (
          <input
            className="flex-1 text-xs font-medium border border-blue-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
            value={titleValue}
            autoFocus
            onChange={(e) => setTitleValue(e.target.value)}
            onBlur={saveTitle}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveTitle();
              if (e.key === "Escape") setEditingTitle(false);
            }}
          />
        ) : (
          <span
            className="flex-1 text-xs font-medium text-gray-700 dark:text-gray-300 truncate cursor-pointer hover:text-blue-600"
            onDoubleClick={() => setEditingTitle(true)}
            title="Double-click to rename"
          >
            {widget.title ?? "Untitled"}
          </span>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
          {typeLabel[widget.widget_type] ?? widget.widget_type}
        </span>
        <button
          onClick={() => deleteWidget.mutate(widget.id)}
          className="text-gray-300 dark:text-gray-600 hover:text-red-500 transition-colors"
          title="Remove widget"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Widget body — placeholder for chart rendering */}
      <div className="flex-1 flex items-center justify-center p-4 text-center">
        <div className="space-y-1">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            Turn {widget.conversation_turn_id.slice(0, 8)}…
          </p>
          <p className="text-xs text-gray-300 dark:text-gray-600">{typeLabel[widget.widget_type]}</p>
        </div>
      </div>
    </div>
  );
}

// ── Dashboard panel ───────────────────────────────────────────────────────────

function DashboardPanel({ dashboard }: { dashboard: Dashboard }) {
  const { data: widgets } = useWidgets(dashboard.id);
  const patchDashboard = usePatchDashboard();
  const deleteDashboard = useDeleteDashboard();

  const layout: Layout[] = (widgets ?? []).map((w) => ({
    i: w.id,
    x: w.position_x,
    y: w.position_y,
    w: w.width,
    h: w.height,
    minW: 2,
    minH: 2,
  }));

  function onLayoutChange(newLayout: Layout[]) {
    const layoutMap: Record<string, unknown> = {};
    newLayout.forEach((item) => {
      layoutMap[item.i] = { x: item.x, y: item.y, w: item.w, h: item.h };
    });
    patchDashboard.mutate({ id: dashboard.id, body: { layout: layoutMap } });
  }

  function toggleShare() {
    patchDashboard.mutate({
      id: dashboard.id,
      body: { is_shared: !dashboard.is_shared },
    });
  }

  return (
    <div className="space-y-3">
      {/* Dashboard toolbar */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleShare}
          className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
            dashboard.is_shared
              ? "bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-300 border-green-200 dark:border-green-900 hover:bg-green-100"
              : "bg-gray-50 dark:bg-gray-800/60 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
          }`}
          title={dashboard.is_shared ? "Shared — click to make private" : "Private — click to share"}
        >
          {dashboard.is_shared ? (
            <Share2 className="w-3.5 h-3.5" />
          ) : (
            <Lock className="w-3.5 h-3.5" />
          )}
          {dashboard.is_shared ? "Shared" : "Private"}
        </button>
        {dashboard.is_shared && dashboard.share_token && (
          <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
            Token: {dashboard.share_token.slice(0, 12)}…
          </span>
        )}
        <div className="flex-1" />
        <button
          onClick={() => {
            if (confirm(`Delete dashboard "${dashboard.name}"?`)) {
              deleteDashboard.mutate(dashboard.id);
            }
          }}
          className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 hover:text-red-500 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </div>

      {/* Grid */}
      {(widgets ?? []).length === 0 ? (
        <div className="border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl py-16 text-center">
          <LayoutDashboard className="w-10 h-10 text-gray-200 mx-auto mb-3" />
          <p className="text-sm text-gray-400 dark:text-gray-500">No widgets yet.</p>
          <p className="text-xs text-gray-300 dark:text-gray-600 mt-1">
            Pin an answer from the Chat page using the Pin button.
          </p>
        </div>
      ) : (
        <GridLayout
          className="layout"
          layout={layout}
          cols={12}
          rowHeight={80}
          width={1100}
          draggableHandle=".cursor-grab"
          onLayoutChange={onLayoutChange}
        >
          {(widgets ?? []).map((widget) => (
            <div key={widget.id}>
              <WidgetCard widget={widget} dashboardId={dashboard.id} />
            </div>
          ))}
        </GridLayout>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardsPage() {
  const { data: dashboards, isLoading } = useDashboards();
  const createDashboard = useCreateDashboard();
  const [activeDashId, setActiveDashId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const activeDash =
    dashboards?.find((d) => d.id === activeDashId) ?? dashboards?.[0] ?? null;

  async function handleCreate() {
    const name = newName.trim() || "My Dashboard";
    const dash = await createDashboard.mutateAsync({ name });
    setActiveDashId(dash.id);
    setNewName("");
    setShowCreate(false);
  }

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-100 dark:bg-gray-800 rounded w-48" />
          <div className="h-48 bg-gray-100 dark:bg-gray-800 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 flex flex-col">
        <div className="p-3 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="w-full flex items-center gap-2 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" />
            New dashboard
          </button>
          {showCreate && (
            <div className="mt-2 flex gap-2">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleCreate();
                  if (e.key === "Escape") setShowCreate(false);
                }}
                placeholder="Dashboard name"
                className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleCreate}
                className="px-2.5 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
              >
                Create
              </button>
            </div>
          )}
        </div>
        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {(dashboards ?? []).map((dash) => (
            <button
              key={dash.id}
              onClick={() => setActiveDashId(dash.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                (activeDash?.id === dash.id)
                  ? "bg-blue-100 text-blue-700 dark:text-blue-300"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
            >
              <LayoutDashboard className="w-4 h-4 shrink-0" />
              <span className="flex-1 truncate">{dash.name}</span>
              {dash.is_shared && <Share2 className="w-3 h-3 text-green-500 shrink-0" />}
            </button>
          ))}
          {!dashboards?.length && (
            <p className="text-xs text-gray-400 dark:text-gray-500 px-3 py-4 text-center">
              No dashboards yet.
            </p>
          )}
        </nav>
      </aside>

      {/* Dashboard content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeDash ? (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{activeDash.name}</h1>
            <DashboardPanel dashboard={activeDash} />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <LayoutDashboard className="w-16 h-16 text-gray-200 mb-4" />
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">No dashboards yet</h2>
            <p className="text-gray-400 dark:text-gray-500 mt-2 max-w-sm">
              Create a dashboard, then pin answers from the Chat page to populate it.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="mt-6 px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm font-medium"
            >
              Create first dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
