/** @type {import('next').NextConfig} */

// The browser only ever talks to this origin; /api/* is proxied server-side to
// the backend. That destination is baked in at build time, so a missing value
// ships a deployment that looks fine and fails on every call: Vercel refuses to
// proxy to a private host and returns an opaque plain-text 404
// (DNS_HOSTNAME_RESOLVED_PRIVATE). Fail the build instead of shipping that.
function apiBase() {
  const api = process.env.NEXT_PUBLIC_API_BASE;
  if (api) return api.replace(/\/+$/, ""); // a trailing slash would yield //api/*
  if (process.env.VERCEL) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE is not set. Point it at the backend " +
        "(e.g. http://<ec2-ip>:8000) in the Vercel project's Environment " +
        "Variables, then redeploy — the /api/* rewrite is baked at build time."
    );
  }
  return "http://localhost:8000";
}

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiBase()}/api/:path*` }];
  },
};
export default nextConfig;
