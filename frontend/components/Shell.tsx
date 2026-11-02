"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, createContext, useContext, useEffect, useState } from "react";
import { ROLE_LABEL, api, getToken, setToken } from "@/lib/api";
import type { Me } from "@/lib/types";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

const NAV = [
  { href: "/jobs", label: "Content jobs" },
  { href: "/jobs/new", label: "New request" },
  { href: "/dashboard", label: "Pipeline health" },
  { href: "/library", label: "Style and knowledge" },
];

export default function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const bare = path === "/login";

  useEffect(() => {
    if (bare) return;
    if (!getToken()) { router.replace("/login"); return; }
    api<Me>("/api/me").then(setMe).catch(() => { setToken(null); router.replace("/login"); });
  }, [bare, path, router]);

  if (bare) return <>{children}</>;

  return (
    <MeContext.Provider value={me}>
      <div className="min-h-screen md:grid md:grid-cols-[232px_1fr]">
        <aside className="border-b border-line bg-sheet md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
          <div className="flex items-center justify-between gap-2 px-5 py-4 md:block">
            <Link href="/jobs" className="block">
              <span className="block text-[15px] font-semibold leading-tight">Content Engine</span>
              <span className="block text-xs text-ink-faint">GitLab docs and release content</span>
            </Link>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0" aria-label="Main">
            {NAV.map((n) => {
              const active = n.href === "/jobs" ? path === "/jobs" || (path.startsWith("/jobs/") && path !== "/jobs/new") : path === n.href;
              return (
                <Link key={n.href} href={n.href}
                  className={`whitespace-nowrap rounded-md px-3 py-2 text-sm ${active ? "bg-accent-soft font-medium text-accent" : "text-ink-soft hover:bg-paper hover:text-ink"}`}>
                  {n.label}
                </Link>
              );
            })}
          </nav>
          {me && (
            <div className="hidden border-t border-line px-5 py-4 md:absolute md:bottom-0 md:block md:w-full">
              <p className="text-sm font-medium">{me.name}</p>
              <p className="text-xs text-ink-faint">{ROLE_LABEL[me.role]}</p>
              {me.llm_provider === "mock" && <p className="mt-2 text-xs text-warn">Agents running in offline mock mode</p>}
              <button className="mt-3 text-xs text-ink-soft underline" onClick={() => { setToken(null); router.push("/login"); }}>
                Switch user
              </button>
            </div>
          )}
        </aside>
        <main className="min-w-0 px-4 py-6 md:px-10 md:py-8">{children}</main>
      </div>
    </MeContext.Provider>
  );
}
