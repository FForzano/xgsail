import { api } from "@/api/client";
import type { ImageUploadTicket, Post, PostOwnerType, UUID } from "@/types";

export const postKeys = {
  list: (ownerType: PostOwnerType, ownerId: UUID) => ["posts", ownerType, ownerId] as const,
};

export const postsService = {
  list: (ownerType: PostOwnerType, ownerId: UUID) =>
    api.get<Post[]>(`/posts?owner_type=${ownerType}&owner_id=${ownerId}`),
  create: (body: { owner_type: PostOwnerType; owner_id: UUID; body: string; image_id?: UUID | null }) =>
    api.post<Post>("/posts", body),
  remove: (id: UUID) => api.del(`/posts/${id}`),

  uploadImage: () => api.post<ImageUploadTicket>("/posts/image"),
  confirmImage: (imageId: UUID) => api.post(`/posts/image/${imageId}/confirm`),
};
