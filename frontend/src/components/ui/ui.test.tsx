import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { Upload } from "lucide-react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { initialTheme } from "../../hooks/useTheme";
import { DevComponents } from "../../pages/DevComponents";
import { Alert, Badge, Button, Delta, EmptyState, ErrorState, InfoTip, Segmented, SkeletonCard, Stat, StatusIcon, Tabs } from ".";

describe("Button", () => {
  it("keeps the text as the accessible name when it has an icon", () => {
    render(<Button icon={Upload}>Import holdings</Button>);
    expect(screen.getByRole("button", { name: "Import holdings" })).toHaveAttribute("type", "button");
  });
});

describe("Delta", () => {
  it.each([
    [1.48, "pct", "Up", "+1.5%"],
    [-1328.67, "inr-compact", "Down", "−₹1,329"],
    [0, "pct", "Unchanged", "0.0%"],
  ] as const)("%s as %s says %s in words, not just colour", (value, format, word, text) => {
    const { container } = render(<Delta value={value} format={format} />);
    expect(container).toHaveTextContent(`${word} ${text}`);
  });

  it("shows a dash for missing values", () => {
    const { container } = render(<Delta value={null} />);
    expect(container).toHaveTextContent("—");
  });
});

describe("StatusIcon", () => {
  it.each([
    ["pass", "Pass"],
    ["fail", "Fail"],
    ["no_data", "No data"],
  ] as const)("%s has a text label", (status, label) => {
    render(<StatusIcon status={status} />);
    expect(screen.getByText(label)).toHaveClass("sr-only");
  });
});

describe("Alert / Badge / Stat", () => {
  it("announces errors immediately and other messages politely", () => {
    render(
      <>
        <Alert tone="error">Broken</Alert>
        <Alert tone="info">FYI</Alert>
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Broken");
    expect(screen.getByRole("status")).toHaveTextContent("FYI");
  });

  it("badges always carry text", () => {
    render(<Badge tone="bad">Sell</Badge>);
    expect(screen.getByText("Sell")).toBeInTheDocument();
  });

  it("stat explains its metric through a labelled info button", () => {
    render(
      <dl>
        <Stat label="ROE" value="9.3%" help="Profit earned for every ₹100 of shareholder money." />
      </dl>,
    );
    expect(screen.getByRole("button", { name: "About ROE" })).toBeInTheDocument();
    expect(screen.getByText("9.3%")).toBeInTheDocument();
  });
});

describe("InfoTip", () => {
  it("shows the explanation on keyboard focus", async () => {
    vi.useFakeTimers();
    render(<InfoTip label="PEG">P/E divided by profit growth.</InfoTip>);
    await act(async () => {
      fireEvent.focus(screen.getByRole("button", { name: "About PEG" }));
      vi.advanceTimersByTime(300);
    });
    expect(screen.getByRole("tooltip")).toHaveTextContent("P/E divided by profit growth.");
    vi.useRealTimers();
  });
});

describe("Segmented", () => {
  function Harness({ onChange }: { onChange: (v: string) => void }) {
    const [v, setV] = useState<"cards" | "table">("cards");
    return (
      <Segmented
        label="View"
        value={v}
        onChange={(n) => {
          setV(n);
          onChange(n);
        }}
        options={[
          { value: "cards", label: "Cards" },
          { value: "table", label: "Table" },
        ]}
      />
    );
  }

  it("switches option and never ends up with nothing selected", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const group = screen.getByRole("radiogroup", { name: "View" });
    fireEvent.click(within(group).getByRole("radio", { name: "Table" }));
    expect(onChange).toHaveBeenLastCalledWith("table");
    // Clicking the selected option again would deselect it in a plain toggle group.
    fireEvent.click(within(group).getByRole("radio", { name: "Table" }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(within(group).getByRole("radio", { name: "Table" })).toHaveAttribute("aria-checked", "true");
  });
});

describe("Tabs", () => {
  it("shows the chosen panel", () => {
    render(
      <Tabs
        label="Sections"
        tabs={[
          { value: "a", label: "Valuation", content: <p>Valuation panel</p> },
          { value: "b", label: "Health", content: <p>Health panel</p> },
        ]}
      />,
    );
    expect(screen.getByRole("tablist", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getByText("Valuation panel")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Health" }), { button: 0, ctrlKey: false });
    expect(screen.getByText("Health panel")).toBeInTheDocument();
  });
});

describe("Empty, error and loading states", () => {
  it("empty state says what to do next", () => {
    render(<EmptyState title="No holdings yet" action={<Button>Import holdings</Button>}>Import your Groww holdings.</EmptyState>);
    expect(screen.getByText("No holdings yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import holdings" })).toBeInTheDocument();
  });

  it("error state says what failed and retries", () => {
    const retry = vi.fn();
    render(<ErrorState title="Price data is 2 days old" hint="Retry now." onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Price data is 2 days old");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalled();
  });

  it("skeletons are announced as loading", () => {
    render(<SkeletonCard label="holdings" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading holdings…")).toBeInTheDocument();
  });
});

describe("theme", () => {
  afterEach(() => {
    localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("defaults to dark", () => {
    expect(initialTheme()).toBe("dark");
  });

  it("uses the saved choice", () => {
    localStorage.setItem("theme", "light");
    expect(initialTheme()).toBe("light");
  });

  it("lets ?theme= preview a theme over the saved one", () => {
    localStorage.setItem("theme", "dark");
    window.history.replaceState(null, "", "/?theme=light");
    expect(initialTheme()).toBe("light");
  });
});

describe("/dev/components", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("shows the primitives in both themes", () => {
    // The sample screener and watchlist cards include Watch buttons, which ask the API what's watched.
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DevComponents />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Light theme")).toBeInTheDocument();
    expect(screen.getByText("Dark theme (default)")).toBeInTheDocument();
    expect(container.querySelector(".light")).not.toBeNull();
    expect(container.querySelector(".dark")).not.toBeNull();
    expect(screen.getAllByRole("button", { name: "Import holdings" })).toHaveLength(4);
  });
});
