import { LayoutGrid, Plus, Table2, Upload } from "lucide-react";
import { useState, type ReactNode } from "react";
import { palette } from "../charts/palette";
import {
  Alert,
  Badge,
  Button,
  Card,
  Delta,
  EmptyState,
  ErrorState,
  InfoTip,
  inputClass,
  PageHeader,
  Segmented,
  SkeletonCard,
  Stat,
  StatusIcon,
  Tabs,
  Tooltip,
} from "../components/ui";
import { formatINR, formatINRCompact, formatPct } from "../lib/format";

const SWATCHES: { group: string; tokens: string[] }[] = [
  { group: "Surfaces", tokens: ["bg", "surface", "surface-2", "surface-3", "border", "border-strong"] },
  { group: "Text", tokens: ["fg", "fg-muted", "fg-subtle", "accent-text"] },
  { group: "Accent", tokens: ["accent", "accent-hover", "accent-soft", "focus"] },
  { group: "Semantic", tokens: ["good", "good-soft", "caution", "caution-soft", "bad", "bad-soft", "neutral", "neutral-soft"] },
  { group: "Score scale (weak → strong)", tokens: ["score-1", "score-2", "score-3", "score-4", "score-5"] },
];

const TYPE: [string, string][] = [
  ["text-2xl", "32 · Hero figure ₹6,12,221"],
  ["text-xl", "24 · Page title"],
  ["text-lg", "20 · Section title / stat value"],
  ["text-base", "16 · Body text"],
  ["text-sm", "14 · Table and secondary text"],
  ["text-xs", "12 · Captions and labels"],
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-fg-subtle">{title}</h2>
      {children}
    </section>
  );
}

function Gallery({ dark }: { dark: boolean }) {
  const [view, setView] = useState<"cards" | "table">("cards");
  const p = palette(dark);
  return (
    <div className="space-y-8">
      <Section title="Colour tokens">
        {SWATCHES.map((g) => (
          <div key={g.group}>
            <p className="mb-1.5 text-xs text-fg-muted">{g.group}</p>
            <div className="flex flex-wrap gap-2">
              {g.tokens.map((t) => (
                <div key={t} className="w-20 text-[11px] text-fg-muted">
                  <div className="h-10 rounded-control border border-border" style={{ background: `var(--${t})` }} />
                  <span className="mt-1 block truncate">{t}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
        <div>
          <p className="mb-1.5 text-xs text-fg-muted">Chart series (charts/palette.ts)</p>
          <div className="flex flex-wrap gap-1.5">
            {p.series.map((c, i) => (
              <span key={c} className="grid h-6 w-8 place-items-center rounded text-[10px] font-semibold text-white" style={{ background: c }}>
                {i + 1}
              </span>
            ))}
          </div>
        </div>
      </Section>

      <Section title="Type scale (Inter, tabular figures)">
        <div className="space-y-1">
          {TYPE.map(([cls, text]) => (
            <p key={cls} className={`${cls} text-fg`}>
              {text}
            </p>
          ))}
        </div>
      </Section>

      <Section title="Numbers">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-fg-muted">formatINR(123456.78)</dt>
          <dd>{formatINR(123456.78)}</dd>
          <dt className="text-fg-muted">formatINRCompact(1240000)</dt>
          <dd>{formatINRCompact(1240000)}</dd>
          <dt className="text-fg-muted">formatINRCompact(32000000)</dt>
          <dd>{formatINRCompact(32000000)}</dd>
          <dt className="text-fg-muted">formatPct(1.234)</dt>
          <dd>{formatPct(1.234)}</dd>
          <dt className="text-fg-muted">Delta (gain / loss / flat)</dt>
          <dd className="flex flex-wrap gap-3">
            <Delta value={1.48} />
            <Delta value={-1328.67} format="inr-compact" />
            <Delta value={0} />
          </dd>
        </dl>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap gap-2">
          <Button icon={Upload}>Import holdings</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Remove</Button>
          <Button disabled>Disabled</Button>
          <Button size="sm" variant="secondary" icon={Plus}>
            Small
          </Button>
        </div>
      </Section>

      <Section title="Badges and status">
        <div className="flex flex-wrap gap-2">
          <Badge tone="good">Buy</Badge>
          <Badge tone="caution">Reduce</Badge>
          <Badge tone="bad">Sell</Badge>
          <Badge tone="neutral">Hold</Badge>
          <Badge tone="accent">Swing style</Badge>
        </div>
        <div className="flex flex-wrap gap-4">
          <StatusIcon status="pass" showLabel />
          <StatusIcon status="fail" showLabel />
          <StatusIcon status="no_data" showLabel />
        </div>
      </Section>

      <Section title="Card, stats and tooltips">
        <Card title="Portfolio" description="Prices as of 09 Oct 2026, 3:30 PM IST" actions={<Button size="sm" variant="secondary">Report</Button>}>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Stat label="Value" value={formatINRCompact(612221)} hint="stocks ₹3.9 L · funds ₹2.2 L" />
            <Stat label="Unrealised P&L" value={<Delta value={-1328.67} format="inr-compact" />} hint={formatPct(-0.22)} />
            <Stat label="XIRR" value="—" help="Your annualised return, counting when each rupee went in." hint="needs purchase dates" />
          </dl>
        </Card>
        <p className="flex items-center gap-1 text-sm text-fg-muted">
          ROE 9.3% <InfoTip label="ROE">Profit earned for every ₹100 of shareholder money.</InfoTip>
          <Tooltip content="Exact value: ₹6,12,221.03">
            <button type="button" className="ml-3 underline decoration-dotted">
              Hover or focus me
            </button>
          </Tooltip>
        </p>
      </Section>

      <Section title="Page header">
        <PageHeader title="Holdings" description="A Buy / Hold / Sell signal for each stock." actions={<Segmented label="View" value={view} onChange={setView} options={[{ value: "cards", label: "Cards", icon: LayoutGrid }, { value: "table", label: "Table", icon: Table2 }]} />} />
      </Section>

      <Section title="Tabs">
        <Tabs
          label="Stock sections"
          tabs={[
            { value: "valuation", label: "Valuation", content: <p className="text-sm text-fg-muted">Valuation checks go here.</p> },
            { value: "health", label: "Financial Health", content: <p className="text-sm text-fg-muted">Health checks go here.</p> },
            { value: "momentum", label: "Momentum", content: <p className="text-sm text-fg-muted">Momentum checks go here.</p> },
          ]}
        />
      </Section>

      <Section title="Form input">
        <input className={inputClass} placeholder="Search a stock, e.g. RELIANCE" aria-label="Search a stock" />
      </Section>

      <Section title="Alerts">
        <div className="space-y-2">
          <Alert tone="info">Fundamentals refresh every Saturday.</Alert>
          <Alert tone="success">Imported 11 stocks.</Alert>
          <Alert tone="warning" title="Price data is 2 days old">Yahoo Finance did not respond to the last refresh.</Alert>
          <Alert tone="error">Couldn't read the file: no header row found.</Alert>
        </div>
      </Section>

      <Section title="Empty, error and loading states">
        <EmptyState title="No holdings yet" action={<Button icon={Upload}>Import holdings</Button>}>
          Import your Groww holdings to see your portfolio score.
        </EmptyState>
        <ErrorState
          title="Price data for TATAMOTORS is 2 days old"
          detail="Yahoo Finance did not respond."
          hint="Retry now, or wait for the 4 PM refresh."
          onRetry={() => undefined}
        />
        <SkeletonCard label="sample" chart />
      </Section>
    </div>
  );
}

/** Every design primitive in both themes, with sample data. Not in the menu: open /dev/components. */
export function DevComponents() {
  return (
    <div className="space-y-6">
      <PageHeader title="Components" description="Design primitives in the light and dark themes, side by side. Later phases add the analysis components here." />
      <div className="grid gap-6 xl:grid-cols-2">
        {[false, true].map((dark) => (
          <div key={String(dark)} className={`${dark ? "dark" : "light"} rounded-card border border-border bg-bg p-4 text-fg sm:p-6`}>
            <p className="mb-6 text-sm font-semibold text-fg">{dark ? "Dark theme (default)" : "Light theme"}</p>
            <Gallery dark={dark} />
          </div>
        ))}
      </div>
    </div>
  );
}
