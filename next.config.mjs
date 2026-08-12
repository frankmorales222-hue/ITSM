/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output — the Dockerfile copies just .next/standalone
  // instead of the whole node_modules tree, which is most of why the
  // Next.js Docker image guide uses it.
  output: "standalone",
};

export default nextConfig;
