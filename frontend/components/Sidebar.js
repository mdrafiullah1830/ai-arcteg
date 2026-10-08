"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, getUser } from "../lib/api";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/devices", label: "Devices" },
  { href: "/simulation", label: "Simulation" },
  { href: "/ai", label: "AI / ML" },
  { href: "/anomalies", label: "Anomalies" },
  { href: "/experiments", label: "Experiments" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUser(getUser());
    setReady(true);
  }, [pathname]);

  if (pathname === "/login") return null;

  function logout() {
    clearSession();
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      <div className="brand">AI-ARCTEG</div>
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`nav-link${pathname === l.href ? " active" : ""}`}
        >
          {l.label}
        </Link>
      ))}
      <div className="spacer" />
      {ready && user ? (
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            {user.name} · {user.role}
          </div>
          <button className="secondary" style={{ width: "100%" }} onClick={logout}>
            Log out
          </button>
        </div>
      ) : (
        <Link href="/login" className="btn secondary" style={{ textAlign: "center" }}>
          Log in
        </Link>
      )}
    </aside>
  );
}
