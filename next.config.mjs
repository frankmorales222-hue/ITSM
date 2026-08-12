/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output — the Dockerfile copies just .next/standalone
  // instead of the whole node_modules tree, which is most of why the
  // Next.js Docker image guide uses it.
  output: "standalone",

  // Playwright runs its own `next dev` (see playwright.config.ts) that
  // needs to coexist with whatever dev server you already have running
  // on the default .next — without this override they'd fight over the
  // same build directory and corrupt each other's state.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
