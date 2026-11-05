import { Blob as NodeBlob } from "node:buffer";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { extractText, getDocumentProxy } from "unpdf";
import { extractNotebookDocument } from "@/lib/notebook-document.server";

vi.mock("unpdf", () => ({ getDocumentProxy: vi.fn(), extractText: vi.fn() }));

const file = (content: string) => new NodeBlob([content]) as unknown as Blob;

describe("Private notebook document extraction", () => {
  beforeEach(() => vi.resetAllMocks());

  it("keeps overlapping text chunks and no invented TXT page reference", async () => {
    const content = "a".repeat(1500);
    const chunks = await extractNotebookDocument(file(content), "txt");
    expect(chunks).toEqual([
      { content: content.slice(0, 1400), page_number: null },
      { content: content.slice(1200), page_number: null },
    ]);
  });

  it("preserves PDF page references and releases the PDF parser", async () => {
    const destroy = vi.fn();
    vi.mocked(getDocumentProxy).mockResolvedValue({ numPages: 2, destroy } as never);
    vi.mocked(extractText).mockResolvedValue({
      text: ["Primera página", "Segunda página"],
      totalPages: 2,
    } as never);
    const chunks = await extractNotebookDocument(file("%PDF-1.7\n"), "pdf");
    expect(chunks).toEqual([
      { content: "Primera página", page_number: 1 },
      { content: "Segunda página", page_number: 2 },
    ]);
    expect(destroy).toHaveBeenCalledOnce();
  });

  it("rejects excess PDF pages and releases the parser", async () => {
    const destroy = vi.fn();
    vi.mocked(getDocumentProxy).mockResolvedValue({ numPages: 101, destroy } as never);
    await expect(extractNotebookDocument(file("%PDF-1.7\n"), "pdf")).rejects.toThrow("100 páginas");
    expect(extractText).not.toHaveBeenCalled();
    expect(destroy).toHaveBeenCalledOnce();
  });

  it("rejects a renamed file before invoking the PDF parser", async () => {
    await expect(
      extractNotebookDocument(file("Texto con extensión cambiada"), "pdf"),
    ).rejects.toThrow("PDF válido");
    expect(getDocumentProxy).not.toHaveBeenCalled();
  });

  it("rejects blank and excessive text", async () => {
    await expect(extractNotebookDocument(file(" \n "), "txt")).rejects.toThrow("texto extraíble");
    await expect(extractNotebookDocument(file("a".repeat(300001)), "txt")).rejects.toThrow(
      "300.000",
    );
  });

  it("enforces the byte limit before reading the file", async () => {
    const text = vi.fn();
    const tooLarge = { size: 10485761, text } as unknown as Blob;
    await expect(extractNotebookDocument(tooLarge, "txt")).rejects.toThrow("10 MB");
    expect(text).not.toHaveBeenCalled();
  });
});
