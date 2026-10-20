/** Design primitives. Domain components (score shapes, checks, signals) live in components/analysis. */
export { Button, buttonClass, type ButtonVariant } from "./Button";
export { Card, PageHeader } from "./Card";
export { Alert, EmptyState, ErrorState, type Tone } from "./Feedback";
export { Badge, Delta, Stat, StatusIcon, type CheckStatus, type Semantic } from "./Indicators";
export { InfoTip, Segmented, Tabs, Tooltip } from "./Overlay";
export { Chip, ChipGroup } from "./Chip";
export { Disclosure } from "./Disclosure";
export { Drawer } from "./Drawer";
export { Loading, Skeleton, SkeletonCard, SkeletonText } from "./Skeleton";

export const inputClass =
  "w-full rounded-control border border-border-strong bg-surface px-2.5 py-1.5 text-sm text-fg placeholder:text-fg-subtle";
