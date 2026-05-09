import assert from "node:assert/strict";
import test from "node:test";

const { getArtifactDisplayMode } = await import(
  new URL("./display.ts", import.meta.url).href
);

void test("uses image preview for image files", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/photo.png"),
    "image-preview",
  );
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/diagram.svg"),
    "image-preview",
  );
});

void test("keeps html files in rich preview", () => {
  assert.equal(
    getArtifactDisplayMode("/mnt/user-data/uploads/page.html"),
    "rich-preview",
  );
});
