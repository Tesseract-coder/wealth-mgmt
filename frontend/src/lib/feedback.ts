/** Where feedback goes: a new GitHub issue on the project. */
export const ISSUES_URL = "https://github.com/Tesseract-coder/wealth-mgmt/issues";

/**
 * The page as a pattern, never what's on it: stock tickers, fund codes and query strings
 * (Compare's tickers, a search) are left out, so a report can't reveal what you hold.
 */
export function pagePattern(pathname: string): string {
  return (
    pathname
      .replace(/^\/analysis\/[^/]+/, "/analysis/:stock")
      .replace(/^\/technical\/[^/]+/, "/technical/:stock")
      .replace(/^\/mutual-funds\/[^/]+/, "/mutual-funds/:fund")
      .replace(/\/+$/, "") || "/"
  );
}

/** A link that opens a new issue with the app version, page and screen size filled in. */
export function feedbackUrl(pathname: string): string {
  const width = typeof window === "undefined" ? null : window.innerWidth;
  const theme = typeof document === "undefined" ? null : document.documentElement.classList.contains("dark") ? "dark" : "light";
  const body = [
    "**What happened, or what would you like?**",
    "",
    "",
    "**What did you expect?**",
    "",
    "",
    "---",
    `App version: ${__APP_VERSION__}`,
    `Page: ${pagePattern(pathname)}`,
    width ? `Screen width: ${width}px` : null,
    theme ? `Theme: ${theme}` : null,
    "",
    "Please don't paste your holdings, values or file contents: describe the problem instead.",
  ]
    .filter((l) => l !== null)
    .join("\n");
  return `${ISSUES_URL}/new?${new URLSearchParams({ title: "Feedback: ", body }).toString()}`;
}
