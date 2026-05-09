import assert from "node:assert/strict";
import test from "node:test";

const {
  humanMessagePlugins,
  remarkLinkifyOssUris,
  streamdownPlugins,
  streamdownPluginsWithWordAnimation,
} = await import(new URL("./plugins.ts", import.meta.url).href);

type TestParagraph = {
  type: string;
  children: Array<{
    type: string;
    url?: string;
    children?: Array<{ type: string; value: string }>;
    value?: string;
  }>;
};

void test("linkifies oss uris inside text nodes", () => {
  const transformer = remarkLinkifyOssUris();
  const tree = {
    type: "root",
    children: [
      {
        type: "paragraph",
        children: [
          {
            type: "text",
            value:
              "See oss://demo-bucket/workspaces/ws-1/uploads/report.md for details.",
          },
        ],
      },
    ],
  };

  transformer(tree);

  const paragraph = tree.children[0] as TestParagraph;
  assert.equal(paragraph.children.length, 3);
  assert.deepEqual(paragraph.children[1], {
    type: "link",
    url: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
    children: [
      {
        type: "text",
        value: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
      },
    ],
  });
});

void test("strips trailing markdown punctuation from oss links", () => {
  const transformer = remarkLinkifyOssUris();
  const tree = {
    type: "root",
    children: [
      {
        type: "paragraph",
        children: [
          {
            type: "text",
            value:
              "See oss://demo-bucket/workspaces/ws-1/uploads/report.md** for details.",
          },
        ],
      },
    ],
  };

  transformer(tree);

  const paragraph = tree.children[0] as TestParagraph;
  const link = paragraph.children[1]!;
  assert.equal(link.type, "link");
  assert.equal(link.url, "oss://demo-bucket/workspaces/ws-1/uploads/report.md");
});

void test("exports oss linkifier in both message plugin sets", () => {
  assert.ok(streamdownPlugins.remarkPlugins?.includes(remarkLinkifyOssUris));
  assert.ok(
    streamdownPluginsWithWordAnimation.remarkPlugins?.includes(
      remarkLinkifyOssUris,
    ),
  );
  assert.ok(humanMessagePlugins.remarkPlugins?.includes(remarkLinkifyOssUris));
});
