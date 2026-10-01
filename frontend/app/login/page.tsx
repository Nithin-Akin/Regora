import { redirect } from "next/navigation";
import { GitBranch, ShieldCheck } from "lucide-react";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import { auth, signIn } from "@/auth";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string }>;
}) {
  if (process.env.AUTH_MODE !== "github") redirect("/");
  const session = await auth();
  if (session?.user) redirect("/");
  const requested = (await searchParams).returnTo || "/";
  const returnTo = requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";

  return (
    <div className="login-page">
      <header className="topbar">
        <Brand />
        <ThemeToggle />
      </header>
      <main className="login-card">
        <div className="icon-well"><GitBranch size={25} /></div>
        <div className="eyebrow">SECURE WORKSPACE</div>
        <h1>Sign in to Regora</h1>
        <p>Connect GitHub to analyze repositories in your private workspace.</p>
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: returnTo });
          }}
        >
          <button className="button primary full" type="submit">
            <GitBranch size={18} /> Continue with GitHub
          </button>
        </form>
        <span className="secure-note">
          <ShieldCheck size={14} /> Regora reads source for static analysis and never executes it.
        </span>
      </main>
    </div>
  );
}
