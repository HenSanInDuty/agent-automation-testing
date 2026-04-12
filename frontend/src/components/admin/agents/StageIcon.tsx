"use client";

import * as React from "react";
import {
  Inbox,
  Database,
  FileText,
  Layers,
  FlaskConical,
  Play,
  Cpu,
  BarChart2,
  Settings,
  Wrench,
  Star,
  Zap,
  Bot,
  Shield,
  CheckCircle2,
  Terminal,
  Layout,
  GitBranch,
  Target,
  Eye,
  Search,
  type LucideProps,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type IconComponent = React.FC<LucideProps>;

export interface StageIconProps {
  /** Icon name string, e.g. "flask-conical" or "shield" */
  name?: string | null;
  /** CSS color string, e.g. "#7c3aed" */
  color?: string | null;
  className?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Icon lookup map
// ─────────────────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, IconComponent> = {
  // Storage / data
  inbox: Inbox,
  database: Database,
  "file-text": FileText,
  // Layers / structure
  layers: Layers,
  // Science / lab
  "flask-conical": FlaskConical,
  flask: FlaskConical,
  // Execution
  play: Play,
  cpu: Cpu,
  terminal: Terminal,
  // Charts
  "bar-chart": BarChart2,
  "bar-chart-2": BarChart2,
  "chart-bar": BarChart2,
  barchart: BarChart2,
  // Config / tools
  settings: Settings,
  wrench: Wrench,
  tool: Wrench,
  // Ratings
  star: Star,
  // Speed / power
  zap: Zap,
  // AI / agents
  bot: Bot,
  // Security
  shield: Shield,
  // Status
  "check-circle": CheckCircle2,
  "check-circle-2": CheckCircle2,
  // Layout / branches
  layout: Layout,
  "git-branch": GitBranch,
  "git-branch-plus": GitBranch,
  // Targeting / search
  target: Target,
  eye: Eye,
  search: Search,
};

// ─────────────────────────────────────────────────────────────────────────────
// StageIcon
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Renders a Lucide icon by string name.
 * Falls back to the `Layers` icon if the name is not found in the map.
 */
export function StageIcon({
  name,
  color,
  className = "w-4 h-4",
}: StageIconProps) {
  const key = name?.toLowerCase().trim() ?? "";
  const IconComponent: IconComponent = ICON_MAP[key] ?? Layers;

  return (
    <IconComponent
      className={className}
      style={color ? { color } : undefined}
      aria-hidden="true"
    />
  );
}

export default StageIcon;
