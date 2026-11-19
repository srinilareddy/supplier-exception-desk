import { expect, type Page, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

async function signIn(page: Page, account: "buyer" | "viewer" = "buyer") {
  await page.goto("/");
  await page.getByLabel("Email").fill(`${account}@example.test`);
  await page.getByLabel("Password").fill(process.env.DESK_TEST_DEMO_PASSWORD ?? "local-demo-only");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Shipment exceptions" })).toBeVisible();
}

async function capture(page: Page, name: string) {
  const directory = process.env.DESK_SCREENSHOT_DIR;
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.mouse.move(0, 0);
  await page.screenshot({ path: path.join(directory, name), animations: "disabled", fullPage: true });
}

test("buyer filters, reviews evidence, assigns, acknowledges, and resolves an exception", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await signIn(page);
  await expect(page.getByRole("row")).toHaveCount(8);
  await expect(page.getByText("Showing 1–7 of 7")).toBeVisible();
  await capture(page, "queue.png");
  await page.getByRole("searchbox", { name: "Search exceptions" }).fill("PO-48109");
  await expect(page.getByRole("row")).toHaveCount(2);
  await page.getByRole("button", { name: "Open PO-48109 line 1" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "PO-48109 · Line 1" })).toBeVisible();
  await expect(dialog.getByText("SH-88710")).toBeVisible();
  await expect(dialog.getByText("In transit", { exact: true })).toBeVisible();
  await capture(page, "detail.png");
  await dialog.getByLabel("Owner").selectOption({ label: "Jordan Avery" });
  await expect(dialog.getByText("Assigned to Jordan Avery.")).toBeVisible();
  await dialog.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(dialog.getByText("Acknowledged the exception.")).toBeVisible();
  await dialog.getByRole("button", { name: "Resolve", exact: true }).click();
  await dialog.getByLabel("Resolution reason").fill("Supplier confirmed a replacement shipment.");
  await dialog.getByRole("button", { name: "Confirm resolution" }).click();
  await expect(dialog.getByText("Supplier confirmed a replacement shipment.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText("No exceptions match these filters.")).toBeVisible();
  await page.getByRole("combobox", { name: "Status", exact: true }).selectOption("resolved");
  await expect(page.getByRole("button", { name: "Open PO-48109 line 1" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("buyer uploads a mixed CSV and sees conflict and validation details", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Import CSV" }).click();
  await expect(page.getByRole("heading", { name: "Data intake" })).toBeVisible();
  const fixture = path.resolve(import.meta.dirname, "../../fixtures/orders-mixed.csv");
  await page.getByLabel("Purchase order CSV").setInputFiles(fixture);
  await page.getByRole("button", { name: "Upload order file" }).click();
  await expect(page.getByRole("status").filter({ hasText: "3 rejected rows" })).toBeVisible();
  await expect(page.getByText("Order line exists with different values.")).toBeVisible();
  await expect(page.getByText("promise_date: use YYYY-MM-DD.")).toBeVisible();
  await page.getByRole("link", { name: "Exception queue" }).click();
  await expect(page.getByRole("button", { name: "Open PO-48145 line 1" })).toBeVisible();
});

test("viewer can inspect a shipment on a small screen without write controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "viewer");
  await expect(page.getByRole("button", { name: "Sync carrier" })).toHaveCount(0);
  const target = page.getByRole("button", { name: "Open PO-48112 line 1" });
  await expect(target).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await capture(page, "mobile.png");
  await target.click();
  const details = page.getByRole("dialog");
  await expect(details.getByText("SH-88714")).toBeVisible();
  await expect(details.getByRole("button", { name: "Resolve", exact: true })).toHaveCount(0);
  await details.getByRole("button", { name: "Close details" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
