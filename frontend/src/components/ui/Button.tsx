import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent-hover",
  secondary: "border border-border-strong bg-surface text-fg hover:bg-surface-2",
  ghost: "text-fg-muted hover:bg-surface-2 hover:text-fg",
  danger: "border border-bad-border bg-surface text-bad hover:bg-bad-soft",
};

const SIZE = {
  sm: "h-8 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
} as const;

/** Shared button look, also for links styled as buttons. */
export function buttonClass(variant: ButtonVariant = "primary", size: keyof typeof SIZE = "md"): string {
  return `inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-control font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${SIZE[size]}`;
}

export function Button({
  variant = "primary",
  size = "md",
  icon: Icon,
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: keyof typeof SIZE; icon?: LucideIcon }) {
  return (
    <button type="button" className={`${buttonClass(variant, size)} ${className}`} {...props}>
      {Icon && <Icon aria-hidden className="size-4 shrink-0" />}
      {children}
    </button>
  );
}
