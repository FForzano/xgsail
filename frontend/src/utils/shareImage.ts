import { toBlob } from "html-to-image";
import { Capacitor } from "@capacitor/core";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";

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

/** Base64 body (no data: prefix), which is the only shape Filesystem.writeFile
 * accepts on native — its Blob support is web-only. Chunked because
 * String.fromCharCode(...bytes) blows the argument limit on a ~2 MP PNG. */
async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** Native share sheet (files) when supported, otherwise a plain browser
 * download — same blob+anchor mechanics as any client-side file save,
 * there's no server round-trip to proxy through (unlike the GPX download,
 * which streams from the backend).
 *
 * The native branch goes through the Share plugin rather than the Web Share
 * API: an Android WebView doesn't expose navigator.share for files, so the web
 * path below would always fall through to the download and the image would
 * never reach Instagram et al. The file is written to the cache directory
 * (already exposed by the app's FileProvider, see res/xml/file_paths.xml) —
 * it's a throwaway the share target copies, not app data to keep. */
export async function shareOrDownloadImage(
  blob: Blob,
  filename: string,
  shareTitle?: string,
): Promise<ShareImageResult> {
  if (Capacitor.isNativePlatform()) {
    try {
      await Filesystem.writeFile({
        path: filename,
        directory: Directory.Cache,
        data: await blobToBase64(blob),
      });
      const { uri } = await Filesystem.getUri({ path: filename, directory: Directory.Cache });
      await Share.share({ files: [uri], title: shareTitle });
      return "shared";
    } catch {
      // The plugin rejects with a plain Error both when the user dismisses the
      // sheet and when nothing can handle the file, with no code to tell them
      // apart — treat both as a cancel rather than showing an error over a
      // sheet the user closed on purpose.
      return "cancelled";
    }
  }

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
