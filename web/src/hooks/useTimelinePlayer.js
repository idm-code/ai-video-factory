import { useState, useEffect, useRef, useCallback } from 'react';

export function useTimelinePlayer(enabledClips, onSelectClip) {
  const [playing, setPlaying] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);
  const timerRef = useRef(null);

  const stop = useCallback(() => {
    clearTimeout(timerRef.current);
    setPlaying(false);
    setCurrentIdx(0);
  }, []);

  const start = useCallback(() => {
    if (enabledClips.length === 0) return;
    setCurrentIdx(0);
    setPlaying(true);
  }, [enabledClips.length]);

  const advance = useCallback(() => {
    clearTimeout(timerRef.current);
    setCurrentIdx((idx) => {
      const next = idx + 1;
      if (next >= enabledClips.length) { setPlaying(false); return 0; }
      return next;
    });
  }, [enabledClips.length]);

  useEffect(() => {
    if (!playing) return;
    const clip = enabledClips[currentIdx];
    if (!clip) { stop(); return; }
    onSelectClip(clip.id);
    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(clip.path || '');
    // Imágenes: avanzar tras duration; vídeos: onEnded + timeout de seguridad
    const safetyMs = (isImage
      ? Math.max(1, Number(clip.duration || 4))
      : Math.max(Number(clip.duration || 4) + 5, 60)
    ) * 1000;
    timerRef.current = setTimeout(advance, safetyMs);
    return () => clearTimeout(timerRef.current);
  }, [playing, currentIdx, enabledClips]);

  return { playing, currentIdx, start, stop, advance };
}
