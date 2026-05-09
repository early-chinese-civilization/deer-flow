import assert from "node:assert/strict";
import test from "node:test";

const {
  humanMessagePlugins,
  remarkLinkifyOssUris,
  streamdownPlugins,
  streamdownPluginsWithWordAnimation,
} = await import(new URL("./plugins.ts", import.meta.url).href);

type TestMarkdownNode = {
  type: string;
  value?: string;
  url?: string;
  children?: TestMarkdownNode[];
};

type TestMarkdownParent = TestMarkdownNode & {
  children: TestMarkdownNode[];
};

function getFirstParagraph(tree: TestMarkdownNode): TestMarkdownParent {
  const paragraph = tree.children?.[0];
  assert.ok(paragraph?.children);
  return paragraph as TestMarkdownParent;
}

function getChild(parent: TestMarkdownParent, index: number): TestMarkdownNode {
  const child = parent.children[index];
  assert.ok(child);
  return child;
}

void test("linkifies oss uris inside text nodes", () => {
  const transformer = remarkLinkifyOssUris();
  const tree: TestMarkdownNode = {
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

  const paragraph = getFirstParagraph(tree);
  assert.equal(paragraph.children.length, 3);
  assert.deepEqual(getChild(paragraph, 1), {
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
  const tree: TestMarkdownNode = {
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

  const paragraph = getFirstParagraph(tree);
  const link = getChild(paragraph, 1);
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
