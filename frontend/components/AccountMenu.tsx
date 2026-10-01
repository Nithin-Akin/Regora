"use client";

import { useEffect, useState } from "react";
import { LogIn, LogOut, UserRound } from "lucide-react";
import { signIn, signOut, useSession } from "next-auth/react";

export default function AccountMenu() {
  const { data: session, status } = useSession();
  const [mode, setMode] = useState<"local" | "github" | "loading">("loading");

  useEffect(() => {
    fetch("/api/mode")
      .then((response) => response.json())
      .then((value) => setMode(value.authMode === "github" ? "github" : "local"))
      .catch(() => setMode("local"));
  }, []);

  if (mode === "loading") return <span className="account-skeleton" aria-hidden />;
  if (mode === "local") {
    return (
      <span className="account-local" title="Authentication is disabled in local mode">
        <UserRound size={14} /> Local workspace
      </span>
    );
  }
  if (status === "loading") return <span className="account-skeleton" aria-hidden />;
  if (!session?.user) {
    return (
      <button className="button subtle small" onClick={() => void signIn("github", { redirectTo: "/" })}>
        <LogIn size={14} /> Sign in
      </button>
    );
  }
  return (
    <div className="account-menu">
      {session.user.image ? (
        // GitHub controls the authenticated avatar URL.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={session.user.image} alt="" />
      ) : (
        <UserRound size={15} />
      )}
      <span>{session.user.name || session.user.email || "GitHub user"}</span>
      <button
        className="icon-button"
        aria-label="Sign out"
        title="Sign out"
        onClick={() => void signOut({ redirectTo: "/" })}
      >
        <LogOut size={14} />
      </button>
    </div>
  );
}
