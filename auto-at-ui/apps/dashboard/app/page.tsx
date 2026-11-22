import { Bot, FolderKanban, PlayCircle, ShieldCheck, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { Section } from "./components/section";
import { PageHeader } from "./components/page-header";

export const dynamic = "force-dynamic";

const quickLinks: { href: string; title: string; description: string; icon: LucideIcon }[] = [
  { href: "/runs", title: "Runs", description: "Create and investigate deterministic test runs.", icon: PlayCircle },
  { href: "/projects", title: "Projects & Tests", description: "Organise projects and manage their test catalog.", icon: FolderKanban },
  { href: "/agent", title: "Agent workspace", description: "Generate and refine tests with the vision agent.", icon: Bot },
  { href: "/reviews", title: "Reviews", description: "Approve generated changes before they are promoted.", icon: ShieldCheck },
  { href: "/admin", title: "Admin", description: "Provision tenant accounts and assign least-privilege roles.", icon: Users },
];

const steps = [
  { title: "Create a project", description: "Add the application under test in Projects & Tests.", href: "/projects" },
  { title: "Run a test", description: "Start a deterministic run and follow it live.", href: "/runs" },
  { title: "Review the results", description: "Inspect evidence and approve what should be kept.", href: "/reviews" },
];

export default function DashboardPage() {
  return <>
    <PageHeader
      eyebrow="Demo tenant"
      title="Overview"
      description="A clear starting point for test operations. Live portfolio summaries arrive with the catalog and run APIs in M3."
    />
    <div className="grid gap-6 xl:grid-cols-3">
      <section aria-labelledby="quick-links-title" className="xl:col-span-2">
        <h2 id="quick-links-title" className="mb-3 text-sm font-medium text-muted-foreground">Jump to a section</h2>
        <ul className="grid gap-4 sm:grid-cols-2">
          {quickLinks.map(({ href, title, description, icon: Icon }) => <li key={href}>
            <Link
              href={href}
              className="group flex h-full gap-4 rounded-xl border bg-card p-5 text-card-foreground shadow-xs outline-none transition-all hover:border-primary/40 hover:shadow-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Icon className="size-5" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block font-medium tracking-tight">{title}</span>
                <span className="mt-1 block text-sm text-muted-foreground">{description}</span>
              </span>
            </Link>
          </li>)}
        </ul>
      </section>
      <Section title="Getting started" description="Create and investigate deterministic runs from the dashboard once Projects & Tests is connected.">
        <ol className="flex flex-col gap-4">
          {steps.map((step, index) => <li key={step.title} className="flex gap-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full border bg-muted text-xs font-semibold text-muted-foreground" aria-hidden="true">{index + 1}</span>
            <div className="min-w-0">
              <Link href={step.href} className="rounded-sm text-sm font-medium outline-none hover:text-primary hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50">{step.title}</Link>
              <p className="text-sm text-muted-foreground">{step.description}</p>
            </div>
          </li>)}
        </ol>
      </Section>
    </div>
  </>;
}
