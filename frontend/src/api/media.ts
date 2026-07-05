// Raw byte PUT to a signed upload URL (media presign / import flows).
//
// The URL is self-authorising (HMAC `?expires=&token=` for the MinIO proxy,
// or an AWS presigned URL) — deliberately NO cookies and NO CSRF header, same
// contract as a device upload (docs/device-protocol.md §3.3).
export async function putToUploadUrl(
  url: string,
  data: Blob | File,
  contentType?: string,
): Promise<void> {
  const res = await fetch(url, {
    method: "PUT",
    body: data,
    headers: contentType ? { "Content-Type": contentType } : undefined,
  });
  if (!res.ok) {
    throw new Error(`Upload failed (${res.status})`);
  }
}
