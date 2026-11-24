/**
 * Motore audio del player (Web Audio).
 *
 *   sorgente stem ─► gain stem ─► analyser stem ┐
 *   (×6 o mix)                                  ├─► somma ─► SoundTouch ─► master ─► analyser ─► uscita
 *                                               ┘
 *   metronomo (oscillatori schedulati) ─► gain metronomo ─► uscita (non trasposto)
 *
 * - Velocità: `playbackRate` delle sorgenti; SoundTouch ne compensa l'altezza e applica i
 *   semitoni. Velocità e tonalità restano indipendenti.
 * - Loop A/B: `loop/loopStart/loopEnd` nativi delle sorgenti, quindi a campione esatto e
 *   sincronizzati tra gli stem.
 * - Metronomo e count-in: click schedulati in anticipo (lookahead) sui beat dell'analisi.
 * - Clipping: picco del master ≥ 0 dBFS, con tenuta di 1,5 s.
 */
import { SoundTouchNode } from "@soundtouchjs/audio-worklet";
import processorUrl from "@soundtouchjs/audio-worklet/processor?url";

export interface TrackSpec {
  id: string;
  label: string;
  url: string;
}

export interface TrackState {
  id: string;
  label: string;
  volume: number;
  muted: boolean;
  solo: boolean;
  peak: number;
  clipping: boolean;
}

export interface LoopState {
  a: number;
  b: number;
  enabled: boolean;
}

export interface PlayerSnapshot {
  status: "loading" | "ready" | "playing" | "error";
  loadProgress: number;
  error: string | null;
  duration: number;
  rate: number;
  semitones: number;
  masterVolume: number;
  tracks: TrackState[];
  loop: LoopState | null;
  metronome: { enabled: boolean; volume: number };
  countInBars: 0 | 1 | 2 | 4;
  countingIn: boolean;
  clipping: boolean;
  pitchAvailable: boolean;
}

export interface BeatGrid {
  beats: number[];
  downbeats: boolean[];
  bpm: number | null;
  beatsPerBar: number;
}

interface Track {
  spec: TrackSpec;
  buffer: AudioBuffer | null;
  gain: GainNode;
  analyser: AnalyserNode;
  source: AudioBufferSourceNode | null;
  state: TrackState;
  clipUntil: number;
}

const LOOKAHEAD_S = 0.15;
const SCHEDULER_MS = 25;
const CLIP_HOLD_MS = 1500;
const CLIP_LEVEL = 0.999;
export const RATE_MIN = 0.5;
export const RATE_MAX = 1.5;
export const SEMITONES_MAX = 11;

export class PlayerEngine {
  private readonly ctx: AudioContext;
  private readonly sum: GainNode;
  private readonly master: GainNode;
  private readonly masterAnalyser: AnalyserNode;
  private readonly metronomeGain: GainNode;
  private stNode: SoundTouchNode | null = null;
  private tracks: Track[] = [];
  private listeners = new Set<() => void>();
  private snapshot: PlayerSnapshot;
  private anchorCtx = 0;
  private anchorSong = 0;
  private playing = false;
  private grid: BeatGrid = { beats: [], downbeats: [], bpm: null, beatsPerBar: 4 };
  private scheduled = new Set<number>();
  private scheduler: number | undefined;
  private meterFrame = 0;
  private lastMeterEmit = 0;
  private masterClipUntil = 0;
  private abort = new AbortController();
  private disposed = false;

  constructor() {
    this.ctx = new AudioContext({ sampleRate: 44100, latencyHint: "interactive" });
    this.sum = this.ctx.createGain();
    this.master = this.ctx.createGain();
    this.masterAnalyser = this.ctx.createAnalyser();
    this.masterAnalyser.fftSize = 2048;
    this.metronomeGain = this.ctx.createGain();
    this.metronomeGain.gain.value = 0.6;
    this.metronomeGain.connect(this.ctx.destination);
    this.master.connect(this.masterAnalyser);
    this.masterAnalyser.connect(this.ctx.destination);
    this.sum.connect(this.master); // collegamento provvisorio, sostituito da SoundTouch
    this.snapshot = {
      status: "loading",
      loadProgress: 0,
      error: null,
      duration: 0,
      rate: 1,
      semitones: 0,
      masterVolume: 1,
      tracks: [],
      loop: null,
      metronome: { enabled: false, volume: 0.6 },
      countInBars: 0,
      countingIn: false,
      clipping: false,
      pitchAvailable: false,
    };
  }

  // ------------------------------------------------------------ stato esterno

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): PlayerSnapshot => this.snapshot;

  private emit(patch: Partial<PlayerSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const l of this.listeners) l();
  }

  private emitTracks(): void {
    this.emit({ tracks: this.tracks.map((t) => ({ ...t.state })) });
  }

  // ---------------------------------------------------------------- caricamento

  async load(specs: TrackSpec[]): Promise<void> {
    await this.setupSoundTouch();
    this.tracks = specs.map((spec) => {
      const gain = this.ctx.createGain();
      const analyser = this.ctx.createAnalyser();
      analyser.fftSize = 1024;
      gain.connect(analyser);
      analyser.connect(this.sum);
      return {
        spec,
        buffer: null,
        gain,
        analyser,
        source: null,
        clipUntil: 0,
        state: { id: spec.id, label: spec.label, volume: 1, muted: false, solo: false, peak: 0, clipping: false },
      };
    });
    this.emitTracks();
    const progress = new Array<number>(specs.length).fill(0);
    try {
      await Promise.all(
        this.tracks.map(async (track, i) => {
          const data = await this.fetchWithProgress(track.spec.url, (f) => {
            progress[i] = f * 0.8;
            this.emit({ loadProgress: progress.reduce((a, b) => a + b, 0) / specs.length });
          });
          track.buffer = await this.ctx.decodeAudioData(data);
          progress[i] = 1;
          this.emit({ loadProgress: progress.reduce((a, b) => a + b, 0) / specs.length });
        }),
      );
    } catch (err) {
      if (this.disposed) return;
      this.emit({ status: "error", error: `Caricamento dell'audio non riuscito: ${String(err)}` });
      return;
    }
    if (this.disposed) return;
    const duration = Math.max(...this.tracks.map((t) => t.buffer?.duration ?? 0));
    this.emit({ status: "ready", duration, loadProgress: 1 });
  }

  private async setupSoundTouch(): Promise<void> {
    try {
      await SoundTouchNode.register(this.ctx, processorUrl);
      const node = new SoundTouchNode({ context: this.ctx });
      this.sum.disconnect();
      this.sum.connect(node);
      node.connect(this.master);
      this.stNode = node;
      this.emit({ pitchAvailable: true });
    } catch {
      // Senza AudioWorklet: velocità con cambio di altezza, niente trasposizione.
      this.stNode = null;
      this.emit({ pitchAvailable: false });
    }
  }

  private async fetchWithProgress(url: string, onProgress: (f: number) => void): Promise<ArrayBuffer> {
    const res = await fetch(url, { signal: this.abort.signal });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const total = Number(res.headers.get("content-length")) || 0;
    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let loaded = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.byteLength;
      if (total) onProgress(loaded / total);
    }
    const out = new Uint8Array(loaded);
    let offset = 0;
    for (const c of chunks) {
      out.set(c, offset);
      offset += c.byteLength;
    }
    return out.buffer;
  }

  setBeatGrid(grid: BeatGrid): void {
    this.grid = grid;
  }

  // ---------------------------------------------------------------- trasporto

  get isPlaying(): boolean {
    return this.playing;
  }

  getTime(): number {
    if (!this.playing) return this.anchorSong;
    const now = this.ctx.currentTime;
    if (now < this.anchorCtx) return this.anchorSong; // count-in in corso
    let t = this.anchorSong + (now - this.anchorCtx) * this.snapshot.rate;
    const loop = this.activeLoop();
    if (loop && this.anchorSong < loop.b && t >= loop.b) {
      t = loop.a + ((t - loop.a) % (loop.b - loop.a));
    }
    return Math.min(t, this.snapshot.duration);
  }

  async play(): Promise<void> {
    if (this.playing || this.snapshot.status === "loading" || this.snapshot.status === "error") return;
    if (this.ctx.state === "suspended") await this.ctx.resume();
    let offset = this.anchorSong >= this.snapshot.duration - 0.05 ? 0 : this.anchorSong;
    const loop = this.activeLoop();
    if (loop && (offset < loop.a || offset >= loop.b)) offset = loop.a;
    let when = this.ctx.currentTime + 0.05;
    const bars = this.snapshot.countInBars;
    if (bars > 0 && this.grid.bpm) {
      const beatDur = 60 / this.grid.bpm / this.snapshot.rate;
      const count = bars * this.grid.beatsPerBar;
      for (let i = 0; i < count; i++) this.click(when + i * beatDur, i % this.grid.beatsPerBar === 0, 1);
      when += count * beatDur;
      this.emit({ countingIn: true });
      window.setTimeout(() => this.emit({ countingIn: false }), (when - this.ctx.currentTime) * 1000);
    }
    this.startSources(when, offset);
    this.playing = true;
    this.emit({ status: "playing" });
    this.startTimers();
  }

  pause(): void {
    if (!this.playing) return;
    const t = this.getTime();
    this.stopSources();
    this.playing = false;
    this.anchorSong = t;
    this.stopTimers();
    this.emit({ status: "ready", countingIn: false });
  }

  stop(): void {
    this.pause();
    this.anchorSong = this.activeLoop()?.a ?? 0;
    this.emit({});
  }

  toggle(): void {
    if (this.playing) this.pause();
    else void this.play();
  }

  seek(time: number): void {
    const t = Math.min(Math.max(time, 0), this.snapshot.duration);
    if (this.playing) {
      this.stopSources();
      this.scheduled.clear();
      this.startSources(this.ctx.currentTime + 0.03, t);
    } else {
      this.anchorSong = t;
    }
    this.emit({});
  }

  private startSources(when: number, offset: number): void {
    const loop = this.activeLoop();
    for (const track of this.tracks) {
      if (!track.buffer) continue;
      const src = this.ctx.createBufferSource();
      src.buffer = track.buffer;
      src.playbackRate.value = this.snapshot.rate;
      if (loop) {
        src.loop = true;
        src.loopStart = loop.a;
        src.loopEnd = loop.b;
      }
      src.connect(track.gain);
      src.start(when, offset);
      track.source = src;
    }
    const first = this.tracks.find((t) => t.source)?.source;
    if (first) {
      first.onended = () => {
        if (this.playing && first === this.tracks.find((t) => t.source)?.source && !this.activeLoop()) {
          this.playing = false;
          this.anchorSong = 0;
          this.stopTimers();
          this.emit({ status: "ready" });
        }
      };
    }
    this.anchorCtx = when;
    this.anchorSong = offset;
    this.scheduled.clear();
  }

  private stopSources(): void {
    for (const track of this.tracks) {
      if (track.source) {
        track.source.onended = null;
        try {
          track.source.stop();
        } catch {
          /* già fermata */
        }
        track.source.disconnect();
        track.source = null;
      }
    }
  }

  // ------------------------------------------------------- velocità e tonalità

  setRate(rate: number): void {
    const r = Math.min(Math.max(rate, RATE_MIN), RATE_MAX);
    if (this.playing) {
      this.anchorSong = this.getTime();
      this.anchorCtx = Math.max(this.ctx.currentTime, this.anchorCtx);
      for (const t of this.tracks) t.source?.playbackRate.setValueAtTime(r, this.ctx.currentTime);
      this.scheduled.clear();
    }
    if (this.stNode) this.stNode.playbackRate.value = r;
    this.emit({ rate: r });
  }

  setSemitones(semitones: number): void {
    const s = Math.round(Math.min(Math.max(semitones, -SEMITONES_MAX), SEMITONES_MAX));
    if (this.stNode) this.stNode.pitchSemitones.value = s;
    this.emit({ semitones: this.stNode ? s : 0 });
  }

  // ------------------------------------------------------------------- mixer

  setMasterVolume(v: number): void {
    this.master.gain.value = v;
    this.emit({ masterVolume: v });
  }

  setTrack(id: string, patch: Partial<Pick<TrackState, "volume" | "muted" | "solo">>): void {
    const track = this.tracks.find((t) => t.state.id === id);
    if (!track) return;
    track.state = { ...track.state, ...patch };
    this.applyGains();
    this.emitTracks();
  }

  /** Solo la traccia indicata (o nessuna con null): utile per "solo voce". */
  soloOnly(id: string | null): void {
    for (const t of this.tracks) t.state = { ...t.state, solo: t.state.id === id };
    this.applyGains();
    this.emitTracks();
  }

  muteOnly(id: string | null): void {
    for (const t of this.tracks) t.state = { ...t.state, muted: t.state.id === id, solo: false };
    this.applyGains();
    this.emitTracks();
  }

  private applyGains(): void {
    const anySolo = this.tracks.some((t) => t.state.solo);
    for (const t of this.tracks) {
      const audible = !t.state.muted && (!anySolo || t.state.solo);
      t.gain.gain.setTargetAtTime(audible ? t.state.volume : 0, this.ctx.currentTime, 0.01);
    }
  }

  // -------------------------------------------------------------------- loop

  private activeLoop(): LoopState | null {
    const loop = this.snapshot.loop;
    return loop && loop.enabled && loop.b - loop.a > 0.05 ? loop : null;
  }

  setLoop(loop: LoopState | null): void {
    const pos = this.getTime();
    this.emit({ loop });
    if (this.playing) {
      const active = this.activeLoop();
      const start = active && (pos < active.a || pos >= active.b) ? active.a : pos;
      this.stopSources();
      this.startSources(this.ctx.currentTime + 0.03, start);
    }
  }

  // --------------------------------------------------------------- metronomo

  setMetronome(patch: Partial<{ enabled: boolean; volume: number }>): void {
    const metronome = { ...this.snapshot.metronome, ...patch };
    this.metronomeGain.gain.value = metronome.volume;
    this.emit({ metronome });
  }

  setCountIn(bars: 0 | 1 | 2 | 4): void {
    this.emit({ countInBars: bars });
  }

  private click(when: number, accent: boolean, gainScale: number): void {
    const osc = this.ctx.createOscillator();
    const env = this.ctx.createGain();
    osc.frequency.value = accent ? 1600 : 1000;
    env.gain.setValueAtTime(0.0001, when);
    env.gain.exponentialRampToValueAtTime(0.9 * gainScale, when + 0.002);
    env.gain.exponentialRampToValueAtTime(0.0001, when + 0.06);
    osc.connect(env);
    env.connect(this.metronomeGain);
    osc.start(when);
    osc.stop(when + 0.07);
  }

  /** Istanti (nel tempo del contesto) in cui suona il beat `beat`, dentro la finestra. */
  private beatTimes(beat: number, from: number, to: number): number[] {
    const rate = this.snapshot.rate;
    const loop = this.activeLoop();
    const out: number[] = [];
    if (!loop || this.anchorSong >= loop.b) {
      if (beat >= this.anchorSong) {
        const t = this.anchorCtx + (beat - this.anchorSong) / rate;
        if (t >= from && t < to) out.push(t);
      }
      return out;
    }
    if (beat >= this.anchorSong && beat < loop.b) {
      const t = this.anchorCtx + (beat - this.anchorSong) / rate;
      if (t >= from && t < to) out.push(t);
    }
    if (beat >= loop.a && beat < loop.b) {
      const firstWrap = this.anchorCtx + (loop.b - this.anchorSong) / rate;
      const period = (loop.b - loop.a) / rate;
      const k0 = Math.max(0, Math.floor((from - firstWrap) / period) - 1);
      for (let k = k0; k < k0 + 3; k++) {
        const t = firstWrap + k * period + (beat - loop.a) / rate;
        if (t >= from && t < to) out.push(t);
      }
    }
    return out;
  }

  private schedule(): void {
    if (!this.playing || !this.snapshot.metronome.enabled) return;
    const from = this.ctx.currentTime;
    const to = from + LOOKAHEAD_S;
    const { beats, downbeats } = this.grid;
    for (let i = 0; i < beats.length; i++) {
      const beat = beats[i] ?? 0;
      for (const t of this.beatTimes(beat, from, to)) {
        const key = Math.round(t * 1000);
        if (this.scheduled.has(key)) continue;
        this.scheduled.add(key);
        this.click(t, downbeats[i] ?? false, 1);
      }
    }
    if (this.scheduled.size > 500) this.scheduled.clear();
  }

  // ---------------------------------------------------------- misuratori

  private startTimers(): void {
    this.stopTimers();
    this.scheduler = window.setInterval(() => this.schedule(), SCHEDULER_MS);
    this.schedule();
    const buf = new Float32Array(2048);
    const loop = (ts: number): void => {
      this.masterAnalyser.getFloatTimeDomainData(buf);
      let masterPeak = 0;
      for (const v of buf) masterPeak = Math.max(masterPeak, Math.abs(v));
      const now = performance.now();
      if (masterPeak >= CLIP_LEVEL) this.masterClipUntil = now + CLIP_HOLD_MS;
      for (const t of this.tracks) {
        const tb = new Float32Array(t.analyser.fftSize);
        t.analyser.getFloatTimeDomainData(tb);
        let peak = 0;
        for (const v of tb) peak = Math.max(peak, Math.abs(v));
        if (peak >= CLIP_LEVEL) t.clipUntil = now + CLIP_HOLD_MS;
        t.state = { ...t.state, peak: Math.max(peak, t.state.peak * 0.85), clipping: now < t.clipUntil };
      }
      if (ts - this.lastMeterEmit > 66) {
        this.lastMeterEmit = ts;
        this.snapshot = {
          ...this.snapshot,
          clipping: now < this.masterClipUntil,
          tracks: this.tracks.map((t) => ({ ...t.state })),
        };
        for (const l of this.listeners) l();
      }
      this.meterFrame = requestAnimationFrame(loop);
    };
    this.meterFrame = requestAnimationFrame(loop);
  }

  private stopTimers(): void {
    window.clearInterval(this.scheduler);
    cancelAnimationFrame(this.meterFrame);
    for (const t of this.tracks) t.state = { ...t.state, peak: 0 };
  }

  dispose(): void {
    this.disposed = true;
    this.abort.abort();
    this.stopSources();
    this.stopTimers();
    this.listeners.clear();
    void this.ctx.close();
  }
}

/** Beat più vicino a `t` (per agganciare i punti A/B alla griglia). */
export function snapToBeat(t: number, beats: number[]): number {
  let best = t;
  let dist = Infinity;
  for (const b of beats) {
    const d = Math.abs(b - t);
    if (d < dist) {
      dist = d;
      best = b;
    }
  }
  return dist < 2 ? best : t;
}
