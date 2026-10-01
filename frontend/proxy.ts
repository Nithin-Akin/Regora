import { NextResponse } from "next/server";
import { auth } from "@/auth";

export default auth((request) => {
  if (process.env.AUTH_MODE !== "github" || request.auth?.user?.id) {
    return NextResponse.next();
  }
  const login = new URL("/login", request.url);
  login.searchParams.set("returnTo", request.nextUrl.pathname);
  return NextResponse.redirect(login);
});

export const config = {
  matcher: ["/repositories/:path*", "/repository/:path*"],
};
