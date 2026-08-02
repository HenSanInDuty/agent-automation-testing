export function CodeBlock({ children, label = "Code" }: { children: string; label?: string }) {
  return <pre className="code-block" aria-label={label}><code>{children}</code></pre>;
}
