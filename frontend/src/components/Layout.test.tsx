import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Layout } from "./Layout";

describe("Layout", () => {
  it("always renders the disclaimer footer", () => {
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    );
    expect(screen.getByRole("contentinfo")).toHaveTextContent(
      "This is not investment advice. Consult a SEBI-registered investment adviser before acting.",
    );
  });
});
