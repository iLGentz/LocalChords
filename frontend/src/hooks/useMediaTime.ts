import { useEffect, useState } from "react";

/** Tempo corrente di un elemento audio, aggiornato a ogni frame durante la riproduzione. */
export function useMediaTime(media: HTMLMediaElement | null): number {
  const [time, setTime] = useState(0);

  useEffect(() => {
    if (!media) return;
    let frame = 0;
    const tick = (): void => {
      setTime(media.currentTime);
      if (!media.paused) frame = requestAnimationFrame(tick);
    };
    const start = (): void => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(tick);
    };
    const sync = (): void => setTime(media.currentTime);
    media.addEventListener("play", start);
    media.addEventListener("seeked", sync);
    media.addEventListener("pause", sync);
    sync();
    return () => {
      cancelAnimationFrame(frame);
      media.removeEventListener("play", start);
      media.removeEventListener("seeked", sync);
      media.removeEventListener("pause", sync);
    };
  }, [media]);

  return time;
}
