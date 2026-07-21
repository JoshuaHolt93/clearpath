import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
  // Every workspace package ships raw TypeScript (main: src/index.ts, build is
  // `tsc --noEmit`), so each one web imports must be transpiled by Next.
  transpilePackages: [
    "@clearpath/api-client",
    "@clearpath/validation",
    "@clearpath/design-tokens",
    "@clearpath/domain",
  ],
};

export default nextConfig;
