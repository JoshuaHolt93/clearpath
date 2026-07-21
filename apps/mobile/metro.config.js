// Monorepo-aware Metro config. ClearPath is a pnpm monorepo, so Metro must watch
// the workspace root and resolve modules from both the app's and the root's
// node_modules. This lets apps/mobile consume the shared @clearpath/* packages
// (api-client, validation, design-tokens) the same way apps/web does — once
// apps/mobile is activated into the pnpm workspace (see MOBILE.md).
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];
// pnpm uses a symlinked store; Metro must follow symlinks and not walk up out of
// the project for hierarchical lookups.
config.resolver.disableHierarchicalLookup = true;
config.resolver.unstable_enableSymlinks = true;

module.exports = config;
