import { Children, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import styles from "./Carousel.module.css";

/** One slide centered at a time, swipeable (native scroll-snap) or via the
 * arrow buttons. `index` tracks the scroll position via onScroll rather than
 * driving it, so a manual swipe and an arrow click end up in the same
 * state. */
export function Carousel({ children }: { children: ReactNode }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const slides = Children.toArray(children);
  const count = slides.length;

  const goTo = (i: number) => {
    const track = trackRef.current;
    if (!track) return;
    const clamped = Math.max(0, Math.min(count - 1, i));
    const slide = track.children[clamped] as HTMLElement | undefined;
    slide?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  };

  const handleScroll = () => {
    const track = trackRef.current;
    if (!track) return;
    const center = track.scrollLeft + track.clientWidth / 2;
    let closest = 0;
    let closestDist = Infinity;
    Array.from(track.children).forEach((child, i) => {
      const el = child as HTMLElement;
      const dist = Math.abs(el.offsetLeft + el.offsetWidth / 2 - center);
      if (dist < closestDist) {
        closestDist = dist;
        closest = i;
      }
    });
    setIndex(closest);
  };

  if (count === 0) return null;

  return (
    <div className={styles.carousel}>
      <Button
        variant="ghost"
        className={`sf-btn--icon-sm ${styles.arrow}`}
        onClick={() => goTo(index - 1)}
        disabled={index === 0}
        aria-label="Previous"
      >
        <ChevronLeft size={20} />
      </Button>
      <div className={styles.track} ref={trackRef} onScroll={handleScroll}>
        {slides.map((slide, i) => (
          <div className={styles.slide} key={i}>
            {slide}
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        className={`sf-btn--icon-sm ${styles.arrow}`}
        onClick={() => goTo(index + 1)}
        disabled={index === count - 1}
        aria-label="Next"
      >
        <ChevronRight size={20} />
      </Button>
      {count > 1 && (
        <div className={styles.dots}>
          {slides.map((_, i) => (
            <span key={i} className={`${styles.dot} ${i === index ? styles.dotActive : ""}`} />
          ))}
        </div>
      )}
    </div>
  );
}
