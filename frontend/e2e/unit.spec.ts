import { expect, test } from "@playwright/test";
import { parseSseBlock } from "../src/sse";
import { cleanDisplayText } from "../src/textUtils";

// Plain functions, no browser: these run in Node.

test.describe("parseSseBlock", () => {
  test("reads an event and its data", () => {
    expect(parseSseBlock('event: step\ndata: {"a":1}')).toEqual({ event: "step", data: '{"a":1}' });
  });

  test("ignores the server's keep-alive comments", () => {
    expect(parseSseBlock(": keep-alive")).toBeNull();
    expect(parseSseBlock(": connected\nevent: result\ndata: {}")).toEqual({ event: "result", data: "{}" });
  });

  test("joins a data value split over several lines, and accepts CRLF", () => {
    expect(parseSseBlock("event: x\r\ndata: one\r\ndata: two")).toEqual({ event: "x", data: "one\ntwo" });
  });

  test("a block with no data is not an event", () => {
    expect(parseSseBlock("event: step")).toBeNull();
  });
});

test.describe("cleanDisplayText", () => {
  test("removes tags, and markdown links keep their text", () => {
    expect(cleanDisplayText("<p>Hello <b>there</b></p>")).toBe("Hello there");
    expect(cleanDisplayText("see [the guide](https://example.org) now")).toBe("see the guide now");
  });

  test("leaves no tag behind when tags are nested inside each other", () => {
    const out = cleanDisplayText("a<scr<b>ipt>alert(1)</scr</b>ipt>b");
    expect(out).not.toMatch(/<\s*\/?script/i);
  });

  test("keeps a plain less-than or greater-than sign", () => {
    expect(cleanDisplayText("x < 5 and y > 2")).toBe("x < 5 and y > 2");
  });
});
