import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmationDialog } from "./ConfirmationDialog";

describe("ConfirmationDialog", () => {
  it("blocks confirm until phrase matches", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmationDialog
        open
        title="Confirmar"
        description="Teste"
        phrase="CONFIRMO TESTE"
        onCancel={() => undefined}
        onConfirm={onConfirm}
      />,
    );
    const btn = screen.getByRole("button", { name: "Confirmar" });
    expect(btn).toBeDisabled();
    await user.type(screen.getByLabelText(/Digite exatamente/i), "CONFIRMO TESTE");
    expect(btn).toBeEnabled();
    await user.click(btn);
    expect(onConfirm).toHaveBeenCalledWith("CONFIRMO TESTE");
  });
});
