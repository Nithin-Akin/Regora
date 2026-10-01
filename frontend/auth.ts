import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

const githubMode = process.env.AUTH_MODE === "github";

export const { handlers, auth, signIn, signOut } = NextAuth({
  secret:
    process.env.AUTH_SECRET ||
    (githubMode ? undefined : "regora-local-development-session-secret"),
  providers: githubMode
    ? [
        GitHub({
          authorization: {
            params: { scope: "read:user user:email repo" },
          },
        }),
      ]
    : [],
  pages: { signIn: "/login" },
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 7 },
  trustHost: true,
  callbacks: {
    jwt({ token, account, profile }) {
      if (account?.provider === "github") {
        token.userId = `github:${String(profile?.id ?? account.providerAccountId)}`;
        token.githubAccessToken = account.access_token;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) session.user.id = String(token.userId || "");
      session.githubAccessToken = String(token.githubAccessToken || "");
      return session;
    },
  },
});
