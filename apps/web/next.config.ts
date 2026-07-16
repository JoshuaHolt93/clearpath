import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
  transpilePackages: ["@clearpath/api-client", "@clearpath/validation", "@clearpath/design-tokens"],
};

export default nextConfig;
