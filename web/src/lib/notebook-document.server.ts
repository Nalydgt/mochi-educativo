export class NotebookDocumentError extends Error {}

export type NotebookChunk = {
  content: string;
  page_number: number | null;
};

export async function extractNotebookDocument(file: Blob, extension: "pdf" | "txt") {
  if (file.size === 0 || file.size > 10485760) {
    throw new NotebookDocumentError("El archivo debe tener entre 1 byte y 10 MB.");
  }
  let pages: string[];
  if (extension === "txt") {
    pages = [await file.text()];
  } else {
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (new TextDecoder().decode(bytes.subarray(0, 5)) !== "%PDF-") {
      throw new NotebookDocumentError("El archivo no contiene un PDF válido.");
    }
    const { extractText, getDocumentProxy } = await import("unpdf");
    const pdf = await getDocumentProxy(bytes);
    try {
      if (pdf.numPages > 100) throw new NotebookDocumentError("El PDF supera 100 páginas.");
      pages = (await extractText(pdf, { mergePages: false })).text;
    } finally {
      await (pdf as unknown as { destroy?: () => Promise<void> }).destroy?.();
    }
  }
  if (!pages.join("").trim()) {
    throw new NotebookDocumentError(
      "No hay texto extraíble. Puedes subir un PDF digital o un TXT.",
    );
  }
  if (pages.reduce((length, page) => length + page.length, 0) > 300000) {
    throw new NotebookDocumentError("El documento supera 300.000 caracteres.");
  }
  const chunks: NotebookChunk[] = [];
  pages.forEach((page, index) => {
    for (let offset = 0; offset < page.length; offset += 1200) {
      const content = page.slice(offset, offset + 1400).trim();
      if (content) chunks.push({ content, page_number: extension === "pdf" ? index + 1 : null });
    }
  });
  return chunks;
}
