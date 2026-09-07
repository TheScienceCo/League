/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle for the Docker runtime stage.
  output: "standalone",
  // The browser talks to the API through this rewrite in development so there is
  // no CORS story to get wrong; in Docker Compose it points at the api service.
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
