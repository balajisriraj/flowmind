import { describe, expect, it } from "vitest";
import { parseSSE, pretty } from "./api";

describe("helpers", () => {
  it("prettifies templates for condition labels", () => {
    expect(pretty("{{steps.extract.amount}}")).toBe("extract.amount");
    expect(pretty("Invoice {{trigger.file}}")).toBe("Invoice trigger.file");
  });
  it("parses SSE frames and keeps the remainder", () => {
    const got: unknown[] = [];
    expect(parseSSE('data: {"type":"done"}\n\ndata: {', (e) => got.push(e))).toBe("data: {");
    expect(got).toEqual([{ type: "done" }]);
  });
});
