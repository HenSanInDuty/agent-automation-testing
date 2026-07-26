import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/next-env.d.ts",
      "**/test-results/**",
    ],
  },
  ...tseslint.configs.recommended,
);
