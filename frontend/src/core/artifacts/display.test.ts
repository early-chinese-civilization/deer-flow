import assert from "node:assert/strict";
import test from "node:test";

const { getArtifactDisplayMode, getSvgPreviewDataUrl } = await import(
  new URL("./display.ts", import.meta.url).href
);

void test("uses image preview for image files", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/photo.png"),
    "image-preview",
  );
});

void test("keeps html files in rich preview", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/page.html"),
    "rich-preview",
  );
});

void test("keeps svg files in rich preview so active content can use srcDoc", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/diagram.svg"),
    "rich-preview",
  );
});

void test("shows unsupported preview for unknown binary and extensionless files", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/archive.bin"),
    "unsupported-preview",
  );
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/README"),
    "unsupported-preview",
  );
});

void test("uses iframe preview only for known embeddable files", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/report.pdf"),
    "iframe-preview",
  );
});

void test("builds a safe SVG preview data URL from SVG content", () => {
  const dataUrl = getSvgPreviewDataUrl('<svg viewBox="0 0 1 1"></svg>');

  assert.ok(dataUrl?.startsWith("data:image/svg+xml;charset=utf-8,"));
  assert.match(decodeURIComponent(dataUrl ?? ""), /<svg viewBox=/);
});

void test("builds a safe SVG preview data URL when XML declaration is present", () => {
  const dataUrl = getSvgPreviewDataUrl(
    '<?xml version="1.0"?><svg viewBox="0 0 1 1"></svg>',
  );

  assert.ok(dataUrl?.startsWith("data:image/svg+xml;charset=utf-8,"));
});

void test("does not build an SVG preview URL for empty or non-SVG content", () => {
  assert.equal(getSvgPreviewDataUrl(""), null);
  assert.equal(getSvgPreviewDataUrl("<html></html>"), null);
});

void test("does not show a code and preview toggle for SVG artifacts", async () => {
  const { shouldShowArtifactCodePreviewToggle } = await import(
    new URL("./display.ts", import.meta.url).href
  );

  assert.equal(
    shouldShowArtifactCodePreviewToggle({
      displayMode: "rich-preview",
      isSvgPreview: true,
    }),
    false,
  );
  assert.equal(
    shouldShowArtifactCodePreviewToggle({
      displayMode: "rich-preview",
      isSvgPreview: false,
    }),
    true,
  );
});
