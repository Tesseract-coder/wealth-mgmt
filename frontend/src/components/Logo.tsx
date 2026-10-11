/** The app mark: a pentagon "score shape" on an accent tile. Decorative; the name is always beside it. */
export function Logo({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <polygon points="16,6 25.5,12.9 21.9,24.1 10.1,24.1 6.5,12.9" fill="none" stroke="var(--accent-fg)" strokeOpacity="0.45" strokeWidth="1.2" />
      <polygon points="16,9 23,14.2 19.6,22 11.6,21 9.2,13.6" fill="var(--accent-fg)" fillOpacity="0.9" />
    </svg>
  );
}
