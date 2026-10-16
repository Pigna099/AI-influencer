import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nProvider } from "../i18n";
import AppHeader from "../components/ui/AppHeader";
import Banner from "../components/ui/Banner";

function renderWithProviders(ui: React.ReactNode) {
  return render(<I18nProvider><MemoryRouter>{ui}</MemoryRouter></I18nProvider>);
}

describe("AppHeader", () => {
  it("marks the current page in the navigation", () => {
    const { container } = renderWithProviders(<AppHeader current="/images" onLogout={() => {}} />);
    const wideNav = container.querySelector(".top-nav-wide");
    expect(wideNav).toBeTruthy();
    const images = wideNav!.querySelector('a[aria-current="page"]');
    expect(images?.textContent).toBe("Images");
    expect(wideNav!.querySelectorAll('a[aria-current="page"]').length).toBe(1);
  });

  it("shows the logout button and optional label", () => {
    renderWithProviders(<AppHeader current="/chat" onLogout={() => {}} label="Sandbox" />);
    expect(screen.getByText("Sandbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByLabelText("Menu and account")).toBeInTheDocument();
  });
});

describe("Banner", () => {
  it("renders as alert with close button", () => {
    renderWithProviders(<Banner onClose={() => {}} closeAria="Close">Something failed</Banner>);
    expect(screen.getByRole("alert")).toHaveTextContent("Something failed");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("renders as status for info tone", () => {
    renderWithProviders(<Banner tone="info" closeAria="Close">Saved</Banner>);
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });
});
