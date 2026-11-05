import { useEffect, useRef, useState } from "react";

type Cue =
  "select" | "move" | "connect" | "reveal" | "pair" | "reset" | "experiment" | "success" | "retry";
const notes: Record<Cue, number[]> = {
  select: [440],
  move: [330],
  connect: [440, 660],
  reveal: [392, 523],
  pair: [440, 587],
  reset: [294],
  experiment: [330, 440, 660],
  success: [523, 659, 784],
  retry: [349, 330],
};

export function useStudySound() {
  const [enabled, setEnabled] = useState(false);
  const [available, setAvailable] = useState(false);
  const context = useRef<AudioContext | null>(null);
  const lastSound = useRef(0);

  useEffect(() => {
    setAvailable(typeof AudioContext !== "undefined");
    return () => {
      void context.current?.close();
    };
  }, []);

  function play(cue: Cue) {
    if (!enabled || !context.current || performance.now() - lastSound.current < 55) return;
    const audio = context.current;
    if (audio.state !== "running") return;
    lastSound.current = performance.now();
    notes[cue].forEach((frequency, index) => {
      const oscillator = audio.createOscillator();
      const volume = audio.createGain();
      const start = audio.currentTime + index * 0.07;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(frequency, start);
      volume.gain.setValueAtTime(0, start);
      volume.gain.linearRampToValueAtTime(0.045, start + 0.012);
      volume.gain.exponentialRampToValueAtTime(0.001, start + 0.12);
      oscillator.connect(volume);
      volume.connect(audio.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.14);
      oscillator.onended = () => {
        oscillator.disconnect();
        volume.disconnect();
      };
    });
  }

  async function toggle() {
    if (!available) return;
    if (enabled) {
      setEnabled(false);
      await context.current?.suspend().catch(() => undefined);
      return;
    }
    try {
      context.current ??= new AudioContext();
      await context.current.resume();
      setEnabled(true);
    } catch {
      setEnabled(false);
      setAvailable(false);
    }
  }

  return { enabled, available, toggle, play };
}
