import { Outlet, NavLink } from "react-router-dom";
import {
  MessageSquare,
  LayoutDashboard,
  Database,
  FileText,
  Settings,
  Bell,
  Search,
  Layers,
  Network,
  Wrench,
} from "lucide-react";

const navItems = [
  { to: "/", icon: MessageSquare, label: "Chat" },
  { to: "/dashboards", icon: LayoutDashboard, label: "Dashboards" },
  { to: "/connections", icon: Database, label: "Connections" },
  { to: "/discovery", icon: Search,  label: "Catalog" },
  { to: "/semantic",          icon: Layers,  label: "Semantic" },
  { to: "/knowledge-graph",  icon: Network, label: "KG" },
  { to: "/tools",            icon: Wrench,  label: "Tools" },
  { to: "/documents",        icon: FileText, label: "Documents" },
  { to: "/alerts", icon: Bell, label: "Alerts" },
  { to: "/admin", icon: Settings, label: "Admin" },
];

export default function AppShell() {
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-16 lg:w-56 bg-white border-r border-gray-200 flex flex-col shrink-0">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-gray-200">
          <span className="hidden lg:block font-bold text-brand-700 text-sm truncate">
            AI Platform
          </span>
          <span className="lg:hidden text-brand-700 font-bold text-lg">A</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 space-y-1 px-2" aria-label="Main navigation">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`
              }
            >
              <Icon className="h-5 w-5 shrink-0" />
              <span className="hidden lg:block">{label}</span>
            </NavLink>
          ))}
        </nav>

      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
