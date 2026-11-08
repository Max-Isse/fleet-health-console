import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import AlertsTable from "../components/AlertsTable";
import BandBadge from "../components/BandBadge";
import { rolesFromToken } from "../auth";
import type { Alert } from "../types";

const open: Alert = {
  id: 1, engine_id: 7, band: "critical", cycle: 180, rul_pred: 12.4,
  raised_at: "2026-01-01T10:00:00Z", acknowledged_by: null, acknowledged_at: null,
};
const done: Alert = { ...open, id: 2, engine_id: 9, band: "warning", acknowledged_by: "sam", acknowledged_at: "2026-01-01T10:05:00Z" };

function renderTable(canAcknowledge: boolean, onAcknowledge = vi.fn()) {
  render(
    <MemoryRouter>
      <AlertsTable alerts={[open, done]} canAcknowledge={canAcknowledge} onAcknowledge={onAcknowledge} />
    </MemoryRouter>,
  );
  return onAcknowledge;
}

describe("BandBadge", () => {
  it("labels each band", () => {
    render(<BandBadge band="critical" />);
    expect(screen.getByText("Critical")).toHaveClass("badge-critical");
  });
});

describe("AlertsTable", () => {
  it("lets an engineer acknowledge an open alert", async () => {
    const onAck = renderTable(true);
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(onAck).toHaveBeenCalledWith(1);
  });

  it("disables acknowledging for a viewer and explains why", () => {
    renderTable(false);
    const button = screen.getByRole("button", { name: "Acknowledge" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Needs the engineer role");
  });

  it("shows who acknowledged a closed alert instead of a button", () => {
    renderTable(true);
    expect(screen.getByText(/Acknowledged by sam/)).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("links each alert to its engine", () => {
    renderTable(true);
    expect(screen.getByRole("link", { name: "Engine 7" })).toHaveAttribute("href", "/engines/7");
  });
});

describe("rolesFromToken", () => {
  const b64url = (o: object) => btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  it("reads realm roles from an access token", () => {
    const token = `${b64url({ alg: "RS256" })}.${b64url({ realm_access: { roles: ["viewer", "engineer"] } })}.sig`;
    expect(rolesFromToken(token)).toEqual(["viewer", "engineer"]);
  });
  it("returns no roles for a missing or malformed token", () => {
    expect(rolesFromToken(undefined)).toEqual([]);
    expect(rolesFromToken("not-a-jwt")).toEqual([]);
  });
});
