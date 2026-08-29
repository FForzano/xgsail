import { useQuery } from "@tanstack/react-query";
import { progressService, progressKeys } from "@/services/progress";

export function useProgress(year?: number) {
  return useQuery({
    queryKey: progressKeys.me(year),
    queryFn: () =>
      progressService.me({
        year,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      }),
  });
}
