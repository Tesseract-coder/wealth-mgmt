import { MapPinOff } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonClass, EmptyState } from "../components/ui";

export function NotFound() {
  return (
    <EmptyState
      icon={MapPinOff}
      title="Page not found"
      action={
        <Link to="/" className={buttonClass("primary")}>
          Go to the Overview
        </Link>
      }
    >
      There's no page at this address. It may be an old link. Go to the Overview, or pick a page from the menu.
    </EmptyState>
  );
}
