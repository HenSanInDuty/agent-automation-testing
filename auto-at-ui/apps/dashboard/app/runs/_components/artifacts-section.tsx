import { Download, Eye, File as FileIcon, FileArchive, FileText, Film, Image as ImageIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { artifactArchiveDownloadUrl, artifactDownloadUrl } from "../../api-client";
import { Section } from "../../components/section";
import type { Artifact } from "../../run-api";
import { CodeBlock } from "./code-block";

export type ArchiveEntry = { path: string; size: number; is_directory: boolean };
export type PreviewKind = "image" | "video" | "text" | "binary";

export function previewType(file: Artifact): PreviewKind {
  const path = file.uri.toLowerCase();
  if (file.content_type?.startsWith("image/") || path.endsWith(".png") || path.endsWith(".jpg") || path.endsWith(".jpeg")) return "image";
  if (file.content_type?.startsWith("video/") || path.endsWith(".webm") || path.endsWith(".mp4")) return "video";
  if (file.content_type?.startsWith("text/") || path.endsWith(".txt") || path.endsWith(".json")) return "text";
  return "binary";
}

function ArtifactIcon({ file }: { file: Artifact }) {
  const isZip = file.uri.toLowerCase().endsWith(".zip") || file.content_type === "application/zip";
  const Icon = isZip ? FileArchive : { image: ImageIcon, video: Film, text: FileText, binary: FileIcon }[previewType(file)];
  return (
    <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
      <Icon className="size-4" aria-hidden="true" />
    </span>
  );
}

export function ArtifactsSection({ apiUrl, runId, evidence, preview, previewContent, previewUrl, archiveEntries, onPreview, onClose }: {
  apiUrl: string;
  runId: string;
  evidence: Artifact[];
  preview: Artifact | null;
  previewContent: string | null;
  previewUrl: string | null;
  archiveEntries: ArchiveEntry[] | null;
  onPreview: (file: Artifact) => void;
  onClose: () => void;
}) {
  return (
    <Section
      title="Artifacts"
      description="For new runs, Preview the video or screenshot to see the browser run directly. Download the ZIP for the full trace."
      actions={evidence.length > 0 && (
        <Button asChild variant="outline" size="sm">
          <a href={artifactArchiveDownloadUrl(apiUrl, runId)}><Download /> Download all (.zip)</a>
        </Button>
      )}
    >
      {evidence.length ? (
        <ul className="divide-y rounded-lg border">
          {evidence.map((file) => (
            <li key={file.id} className="flex flex-wrap items-center gap-3 p-3">
              <ArtifactIcon file={file} />
              <div className="min-w-40 flex-1">
                <p className="truncate text-sm font-medium">{file.kind}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {file.size.toLocaleString()} bytes · {file.content_type ?? "binary artifact"}
                </p>
              </div>
              <div className="flex w-full gap-2 sm:w-auto">
                <Button type="button" variant="outline" size="sm" onClick={() => onPreview(file)}><Eye /> Preview</Button>
                <Button asChild variant="outline" size="sm">
                  <a href={artifactDownloadUrl(apiUrl, runId, file.id)}><Download /> Download</a>
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No artifacts were retained for this run.</p>
      )}
      {preview && (
        <div className="mt-5 space-y-3 rounded-lg border bg-muted/30 p-4" aria-live="polite">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Preview: {preview.kind}</h3>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Close</Button>
          </div>
          {archiveEntries && (
            <>
              <p className="text-sm text-muted-foreground">
                This ZIP contains {archiveEntries.length.toLocaleString()} entries. Files are listed without extracting the archive.
              </p>
              <ul className="max-h-80 divide-y overflow-auto rounded-lg border bg-card">
                {archiveEntries.map((entry) => (
                  <li key={entry.path} className="flex items-center justify-between gap-3 px-3 py-1.5">
                    <code className="min-w-0 break-all font-mono text-xs">{entry.is_directory ? `${entry.path}/` : entry.path}</code>
                    {!entry.is_directory && <span className="shrink-0 text-xs text-muted-foreground">{entry.size.toLocaleString()} bytes</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {previewType(preview) === "image" && previewUrl && (
            <img className="max-h-[32rem] max-w-full rounded-md border" src={previewUrl} alt={`Artifact preview: ${preview.kind}`} />
          )}
          {previewType(preview) === "video" && previewUrl && (
            <video className="max-h-[32rem] max-w-full rounded-md border" controls src={previewUrl}>Your browser cannot preview this video.</video>
          )}
          {previewType(preview) === "text" && <CodeBlock>{previewContent ?? "Loading preview..."}</CodeBlock>}
          {previewType(preview) === "binary" && !archiveEntries && (
            <p className="text-sm text-muted-foreground">
              This {preview.content_type ?? "binary"} artifact cannot be previewed in the browser. Download it to inspect it with the appropriate tool.
            </p>
          )}
        </div>
      )}
    </Section>
  );
}
