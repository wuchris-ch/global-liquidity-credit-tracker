import path from "path";
import fs from "fs";

// Resolve the frontend src directory regardless of where the build is run
const cwd = process.cwd();
const aliasCandidates = [
  path.join(cwd, "frontend", "src"), // when build runs from repo root
  path.join(cwd, "src"), // when build runs from frontend root
];
const aliasPath = aliasCandidates.find(fs.existsSync) ?? aliasCandidates[0];
console.log("[next.config] cwd:", cwd, "alias:", aliasPath);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactCompiler: true,
  devIndicators: false,

  images: {
    unoptimized: true,
  },

  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },

  webpack: (config) => {
    config.resolve.alias = config.resolve.alias || {};
    config.resolve.alias["@"] = aliasPath;
    return config;
  },
};

export default nextConfig;

