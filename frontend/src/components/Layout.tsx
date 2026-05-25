import { NavLink, Outlet } from "react-router-dom";

const TABS: { to: string; label: string; icon: string }[] = [
  { to: "/feed", label: "Лента", icon: "📋" },
  { to: "/tracker", label: "Трекер", icon: "🎯" },
  { to: "/profile", label: "Профиль", icon: "👤" },
];

export function Layout() {
  return (
    <div className="flex flex-col h-full">
      <main className="flex-1 overflow-y-auto pb-16">
        <Outlet />
      </main>
      <nav className="fixed bottom-0 left-0 right-0 bg-tg-bg border-t border-tg-secondary-bg flex">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              `flex-1 py-2.5 flex flex-col items-center text-xs ${
                isActive ? "text-tg-link" : "text-tg-hint"
              }`
            }
          >
            <span className="text-lg leading-none">{t.icon}</span>
            <span className="mt-0.5">{t.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
