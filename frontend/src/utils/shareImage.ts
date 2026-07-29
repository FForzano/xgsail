import { toBlob } from "html-to-image";

/** Rasterizes a ShareCard DOM node (see components/session/ShareCard.tsx) to
 * a PNG blob at its own CSS pixel size — the node is already built at the
 * exact 1080x1920 export resolution, so pixelRatio stays at 1 rather than
 * multiplying by devicePixelRatio (which would just make the file bigger
 * without adding real detail).
 *
 * `cacheBust` stays off: it appends a bare `?<timestamp>` to every image URL,
 * which invalidates the signature of a presigned S3 URL (the shape
 * storage/object_store.py returns when a public endpoint is configured) and
 * silently drops that image from the export. */
export async function renderShareCardToBlob(node: HTMLElement): Promise<Blob> {
  const blob = await toBlob(node, { pixelRatio: 1, cacheBust: false });
  if (!blob) throw new Error("Image generation failed");
  return blob;
}

export type ShareImageResult = "shared" | "cancelled" | "downloaded";

/** Native share sheet (files) when supported, otherwise a plain browser
 * download — same blob+anchor mechanics as any client-side file save,
 * there's no server round-trip to proxy through (unlike the GPX download,
 * which streams from the backend). */
export async function shareOrDownloadImage(
  blob: Blob,
  filename: string,
  shareTitle?: string,
): Promise<ShareImageResult> {
  const file = new File([blob], filename, { type: blob.type || "image/png" });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: shareTitle });
      return "shared";
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return "cancelled";
      // Other failures (e.g. no share target picked up the file type) fall
      // through to the download below instead of leaving the user stuck.
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return "downloaded";
}
