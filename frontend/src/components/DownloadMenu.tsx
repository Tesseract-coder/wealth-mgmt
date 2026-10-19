import * as RPopover from "@radix-ui/react-popover";
import { ChevronDown, Download, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { buttonClass } from "./ui";

/**
 * One Download button that asks for the format. `href` is the export URL without its extension
 * (e.g. `/export/stocks`); query strings after `?` are kept. PDF reads better on a phone,
 * CSV opens in a spreadsheet.
 */
export function DownloadMenu({ href, label = "Download", size = "md" }: { href: string; label?: string; size?: "sm" | "md" }) {
  const [open, setOpen] = useState(false);
  const [path, query = ""] = href.split("?");
  const url = (ext: string) => `${path}.${ext}${query ? `?${query}` : ""}`;
  const item =
    "flex w-full items-start gap-2 rounded-control px-2.5 py-2 text-left text-sm text-fg hover:bg-surface-2 focus-visible:bg-surface-2";
  return (
    <RPopover.Root open={open} onOpenChange={setOpen}>
      <RPopover.Trigger className={buttonClass("secondary", size)}>
        <Download aria-hidden className="size-4" />
        {label}
        <ChevronDown aria-hidden className="size-3.5" />
      </RPopover.Trigger>
      <RPopover.Portal>
        <RPopover.Content
          align="start"
          sideOffset={6}
          collisionPadding={8}
          aria-label="Choose a file format"
          className="z-50 w-56 rounded-control border border-border bg-surface p-1 shadow-pop"
        >
          <a href={url("pdf")} download className={item} onClick={() => setOpen(false)}>
            <FileText aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span>
              PDF<span className="block text-xs text-fg-subtle">Easy to read on a phone</span>
            </span>
          </a>
          <a href={url("csv")} download className={item} onClick={() => setOpen(false)}>
            <FileSpreadsheet aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span>
              CSV<span className="block text-xs text-fg-subtle">Opens in Excel or Sheets</span>
            </span>
          </a>
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  );
}
