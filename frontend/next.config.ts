import type { NextConfig } from "next";
import fs from "fs";
import path from "path";

const cwd = process.cwd();
const aliasCandidates = [
  path.join(cwd, "src"),            // when build runs from frontend root
  path.join(cwd, "frontend", "src"), // when build runs from repo root
  path.resolve(__dirname, "src"),    // fallback to config file dir
];
const resolvedAlias = aliasCandidates.find(fs.existsSync) ?? aliasCandidates[0];

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

  // Ensure @/ resolves to the frontend src directory regardless of build cwd
  webpack: (config) => {
    config.resolve.alias["@"] = resolvedAlias;
    return config;
  },
};

export default nextConfig;
