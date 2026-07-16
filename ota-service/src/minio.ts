import { Client } from "minio";
import { config } from "./config.js";

export const minioClient = new Client({
  endPoint: config.minio.host,
  port: config.minio.port,
  useSSL: config.minio.useSSL,
  accessKey: config.accessKey,
  secretKey: config.secretKey,
});

// Separate client for presigning only — SDK signatures are bound to the
// endpoint they were signed against, so a client built from the internal
// endpoint can only ever mint internal (unreachable-from-a-phone) URLs.
// Falls back to `minioClient` (internal) when no public endpoint is
// configured, e.g. local/self-hosted setups where MinIO is reachable as-is.
const minioPublicClient = config.minioPublic
  ? new Client({
      endPoint: config.minioPublic.host,
      port: config.minioPublic.port,
      useSSL: config.minioPublic.useSSL,
      accessKey: config.accessKey,
      secretKey: config.secretKey,
    })
  : minioClient;

function key(...parts: string[]): string {
  return [config.otaPrefix, ...parts].join("/");
}

export const manifestKey = () => key("manifest.json");
export const bundleKey = (version: string) => key("bundles", `${version}.zip`);

export async function getManifestJson(): Promise<string | null> {
  try {
    const chunks: Buffer[] = [];
    const stream = await minioClient.getObject(config.bucket, manifestKey());
    for await (const chunk of stream) chunks.push(chunk as Buffer);
    return Buffer.concat(chunks).toString("utf-8");
  } catch (err) {
    // MinIO SDK throws a generic error with `.code === "NoSuchKey"` when the
    // object doesn't exist yet (no release published).
    if ((err as { code?: string }).code === "NoSuchKey") return null;
    throw err;
  }
}

export async function presignBundleUrl(version: string): Promise<string> {
  return minioPublicClient.presignedGetObject(config.bucket, bundleKey(version), config.presignExpirySeconds);
}

export async function bundleExists(version: string): Promise<boolean> {
  try {
    await minioClient.statObject(config.bucket, bundleKey(version));
    return true;
  } catch (err) {
    if ((err as { code?: string }).code === "NotFound") return false;
    throw err;
  }
}
