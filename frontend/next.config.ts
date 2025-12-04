import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  reactCompiler: true,
  devIndicators: false,
  
  // Allow images from external domains if needed
  images: {
    unoptimized: true,
  },
  
  // Environment variables validation (build will warn if missing)
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },

  webpack: (config) => {
    config.resolve.alias["@"] = path.join(process.cwd(), "src");
    return config;
  },
};

export default nextConfig;
