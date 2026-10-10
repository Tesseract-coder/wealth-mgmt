import { Link } from "react-router-dom";
import { Card } from "../components/ui";

export function NotFound() {
  return (
    <Card title="Page not found">
      <p className="text-sm text-slate-600 dark:text-slate-400">
        There's no page at this address. It may be an old link.{" "}
        <Link to="/" className="underline">
          Go to the Overview
        </Link>{" "}
        or pick a page from the menu.
      </p>
    </Card>
  );
}
