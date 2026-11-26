// The Núcleo globe: hundreds of thousands of lights on a sphere, one coloured region per agent.
// Plain WebGL 1, no libraries. The number of lights adapts to what the PC can draw smoothly.

export interface GlobeAgent {
  id: string;
  name: string;
}

export interface GlobeStats {
  fps: number;
  lights: number;
  renderer: string;
}

type Vec3 = [number, number, number];

const PALETTE: Vec3[] = [
  [0.21, 0.89, 1.0], [0.36, 1.0, 0.62], [0.62, 0.48, 1.0], [1.0, 0.78, 0.28],
  [1.0, 0.38, 0.74], [0.4, 0.62, 1.0], [0.8, 1.0, 0.36], [1.0, 0.33, 0.3],
  [0.3, 1.0, 0.95], [1.0, 0.6, 0.35], [0.7, 0.7, 1.0], [0.55, 1.0, 0.8],
];
export const MAX_AGENTS = 16;
const START_LIGHTS = 40_000;
const MIN_LIGHTS = 5_000;
const FRAME_MS = 1000 / 30 - 2; // small margin: rAF ticks are not exact

export function agentColor(i: number): string {
  const c = PALETTE[i % PALETTE.length];
  return `rgb(${c.map((v) => Math.round(v * 255)).join(",")})`;
}

function fib(n: number, i: number): Vec3 {
  const y = 1 - (2 * (i + 0.5)) / n;
  const r = Math.sqrt(1 - y * y);
  const t = i * Math.PI * (3 - Math.sqrt(5));
  return [Math.cos(t) * r, y, Math.sin(t) * r];
}

function buildLights(n: number, centers: Vec3[]): Float32Array {
  // 6 floats per light: x y z agent near seed. Random order, so every prefix is evenly spread.
  let s = 1234567;
  const rnd = () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
  const data = new Float32Array(n * 6);
  for (let i = 0; i < n; i++) {
    const u = rnd() * 2 - 1;
    const t = rnd() * Math.PI * 2;
    const r = Math.sqrt(1 - u * u);
    const x = r * Math.cos(t), y = u, z = r * Math.sin(t);
    let best = 0, bd = -2, second = -2;
    for (let a = 0; a < centers.length; a++) {
      const c = centers[a];
      const d = x * c[0] + y * c[1] + z * c[2];
      if (d > bd) { second = bd; bd = d; best = a; } else if (d > second) second = d;
    }
    const near = centers.length > 1 ? Math.min(1, Math.max(0, (bd - second) * 3.2)) : 1;
    const lift = 1 + (rnd() - 0.5) * 0.04 + near * near * 0.03;
    const o = i * 6;
    data[o] = x * lift; data[o + 1] = y * lift; data[o + 2] = z * lift;
    data[o + 3] = best; data[o + 4] = near; data[o + 5] = rnd();
  }
  return data;
}

function buildArcs(centers: Vec3[]): Float32Array {
  // The Director (first agent) to every other agent, plus a ring between neighbours.
  const n = centers.length;
  const pairs: [number, number][] = [];
  for (let a = 1; a < n; a++) pairs.push([0, a]);
  if (n > 2) for (let a = 1; a < n; a++) pairs.push([a, (a % (n - 1)) + 1]);
  const steps = 90;
  const out: number[] = [];
  pairs.forEach(([p, q], k) => {
    const A = centers[p], B = centers[q];
    const om = Math.acos(Math.max(-1, Math.min(1, A[0] * B[0] + A[1] * B[1] + A[2] * B[2])));
    if (om < 1e-3) return;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const w1 = Math.sin((1 - t) * om) / Math.sin(om), w2 = Math.sin(t * om) / Math.sin(om);
      const h = 1.04 + Math.sin(Math.PI * t) * 0.22 * om;
      out.push((A[0] * w1 + B[0] * w2) * h, (A[1] * w1 + B[1] * w2) * h, (A[2] * w1 + B[2] * w2) * h, t, k, q);
    }
  });
  return new Float32Array(out);
}

const COMMON = `
uniform mat3 uRot; uniform float uAspect, uZoom;
vec4 project(vec3 p, out float depth) {
  vec3 q = uRot * p; float d = 3.2 - q.z; depth = q.z;
  vec2 xy = q.xy / d * 2.3 * uZoom;
  return vec4(xy.x / uAspect, xy.y, 0.0, 1.0);
}`;

const LIGHTS_VS = `
attribute vec3 aPos; attribute float aAgent, aNear, aSeed;
uniform float uTime, uScale; uniform float uAct[${MAX_AGENTS}]; uniform vec3 uCol[${MAX_AGENTS}];
varying vec3 vCol; varying float vA;
${COMMON}
void main() {
  float depth; gl_Position = project(aPos, depth);
  int i = int(aAgent + 0.5);
  float act = uAct[i];
  float tw = 0.55 + 0.45 * sin(uTime * (0.7 + aSeed * 2.6) + aSeed * 60.0);
  float wave = pow(max(0.0, 1.0 - abs(fract(uTime * 0.35 + aSeed * 0.05) - (1.0 - aNear)) * 6.0), 3.0) * act;
  float face = 0.22 + 0.78 * smoothstep(-0.55, 0.9, depth);
  vA = ((0.10 + 0.9 * aNear * aNear) * tw * (0.35 + 1.0 * act) + wave * 0.9) * face;
  vCol = mix(vec3(0.55, 0.75, 0.9), uCol[i], 0.35 + 0.65 * aNear);
  gl_PointSize = uScale * (0.8 + 1.6 * aNear * aNear + wave * 2.0) * (3.2 / (3.2 - depth)) * uZoom;
}`;

const ARCS_VS = `
attribute vec3 aPos; attribute float aT, aArc, aTo;
uniform float uTime, uScale; uniform float uAct[${MAX_AGENTS}]; uniform vec3 uCol[${MAX_AGENTS}];
varying vec3 vCol; varying float vA;
${COMMON}
void main() {
  float depth; gl_Position = project(aPos, depth);
  int i = int(aTo + 0.5);
  float act = uAct[i];
  float head = fract(uTime * (0.18 + 0.04 * mod(aArc, 5.0)) + aArc * 0.137);
  float pulse = pow(max(0.0, 1.0 - abs(head - aT) * 10.0), 2.0);
  float face = 0.25 + 0.75 * smoothstep(-0.5, 0.9, depth);
  vA = (0.05 + pulse * 1.3) * (0.15 + act) * face;
  vCol = uCol[i];
  gl_PointSize = uScale * (1.0 + pulse * 2.5) * uZoom;
}`;

const POINT_FS = `
precision mediump float; varying vec3 vCol; varying float vA;
void main() {
  vec2 c = gl_PointCoord - 0.5; float r = dot(c, c) * 4.0;
  if (r > 1.0) discard;
  gl_FragColor = vec4(vCol * vA * (1.0 - r) * (1.0 - r), 1.0);
}`;

interface Program {
  prog: WebGLProgram;
  attribs: [number, number][]; // [location, size]
  u: Record<string, WebGLUniformLocation | null>;
}

export class GlobeRenderer {
  private gl: WebGLRenderingContext;
  private lights: Program;
  private arcs: Program;
  private lightsBuf: WebGLBuffer;
  private arcsBuf: WebGLBuffer;
  private arcCount: number;
  private centers: Vec3[];
  private colors = new Float32Array(MAX_AGENTS * 3);
  private labels: HTMLElement[] = [];
  private count: number;
  private readonly maxLights: number;
  private frame = 0;
  private lastDraw = 0;
  private running = false;
  private t0 = performance.now();
  private frames = 0;
  private lastStats = performance.now();
  private yaw = 0.6;
  private pitch = 0.25;
  private spin = 0.0009;
  private zoom = 1;
  private drag: [number, number] | null = null;
  private pixelScale = 1;
  private readonly rendererName: string;
  readonly activity = new Float32Array(MAX_AGENTS);

  constructor(
    private canvas: HTMLCanvasElement,
    overlay: HTMLElement,
    agents: GlobeAgent[],
    private onStats: (s: GlobeStats) => void,
    private onPick: (agentId: string) => void,
    maxLights = 400_000,
  ) {
    const gl = canvas.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" });
    if (!gl) throw new Error("WebGL non disponibile in questo browser");
    this.gl = gl;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    this.rendererName = String(info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : "WebGL").replace(/\(.*?\)/g, "").trim();
    this.maxLights = maxLights;
    this.count = Math.min(START_LIGHTS, maxLights);
    const shown = agents.slice(0, MAX_AGENTS);
    this.centers = shown.map((_, i) => fib(Math.max(1, shown.length), i));
    shown.forEach((_, i) => this.colors.set(PALETTE[i % PALETTE.length], i * 3));
    this.activity.fill(0.2);

    this.lights = this.program(LIGHTS_VS, POINT_FS, ["aPos", "aAgent", "aNear", "aSeed"]);
    this.arcs = this.program(ARCS_VS, POINT_FS, ["aPos", "aT", "aArc", "aTo"]);
    this.lightsBuf = this.buffer(buildLights(this.maxLights, this.centers));
    const arcData = buildArcs(this.centers);
    this.arcsBuf = this.buffer(arcData);
    this.arcCount = arcData.length / 6;

    this.labels = shown.map((a, i) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "globe-label";
      el.style.color = agentColor(i);
      el.textContent = a.name;
      el.title = `Apri ${a.name}`;
      el.addEventListener("click", () => this.onPick(a.id));
      overlay.append(el);
      return el;
    });

    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    canvas.addEventListener("pointerdown", this.onDown);
    canvas.addEventListener("pointermove", this.onMove);
    canvas.addEventListener("pointerup", this.onUp);
    canvas.addEventListener("pointercancel", this.onUp);
    canvas.addEventListener("wheel", this.onWheel, { passive: false });
    document.addEventListener("visibilitychange", this.onVisibility);
    this.resize();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.lastStats = performance.now();
    this.frames = 0;
    this.frame = requestAnimationFrame(this.draw);
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this.frame);
  }

  destroy() {
    this.stop();
    const c = this.canvas;
    c.removeEventListener("pointerdown", this.onDown);
    c.removeEventListener("pointermove", this.onMove);
    c.removeEventListener("pointerup", this.onUp);
    c.removeEventListener("pointercancel", this.onUp);
    c.removeEventListener("wheel", this.onWheel);
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.labels.forEach((l) => l.remove());
    this.gl.getExtension("WEBGL_lose_context")?.loseContext(); // give the GPU memory back at once
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    this.pixelScale = Math.min(1, window.devicePixelRatio || 1); // fill rate is the limit on small GPUs
    this.canvas.width = Math.max(1, Math.round(rect.width * this.pixelScale));
    this.canvas.height = Math.max(1, Math.round(rect.height * this.pixelScale));
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  private program(vs: string, fs: string, names: string[]): Program {
    const gl = this.gl;
    const prog = gl.createProgram()!;
    for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]] as const) {
      const sh = gl.createShader(type)!;
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) ?? "shader");
      gl.attachShader(prog, sh);
    }
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? "link");
    const sizes = [3, 1, 1, 1];
    const u: Record<string, WebGLUniformLocation | null> = {};
    for (const name of ["uRot", "uAspect", "uZoom", "uTime", "uScale", "uAct[0]", "uCol[0]"]) {
      u[name] = gl.getUniformLocation(prog, name);
    }
    return { prog, attribs: names.map((n, i) => [gl.getAttribLocation(prog, n), sizes[i]]), u };
  }

  private buffer(data: Float32Array): WebGLBuffer {
    const gl = this.gl;
    const buf = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    return buf;
  }

  private use(p: Program, buf: WebGLBuffer, R: Float32Array, aspect: number, fit: number, t: number, scale: number) {
    const gl = this.gl;
    gl.useProgram(p.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    let offset = 0;
    for (const [loc, size] of p.attribs) {
      if (loc >= 0) {
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 24, offset);
      }
      offset += size * 4;
    }
    gl.uniformMatrix3fv(p.u.uRot, false, R);
    gl.uniform1f(p.u.uAspect, aspect);
    gl.uniform1f(p.u.uZoom, this.zoom * fit);
    gl.uniform1f(p.u.uTime, t);
    gl.uniform1f(p.u.uScale, scale);
    gl.uniform1fv(p.u["uAct[0]"], this.activity);
    gl.uniform3fv(p.u["uCol[0]"], this.colors);
  }

  private rotation(): Float32Array {
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    // R = Rx(pitch) * Ry(yaw), column-major
    return new Float32Array([cy, sp * sy, -cp * sy, 0, cp, sp, sy, -sp * cy, cp * cy]);
  }

  private draw = (now: number) => {
    if (!this.running) return;
    // At most ~30 frames per second: on a 2-core PC the globe must leave CPU to GÉNESIS itself.
    if (now - this.lastDraw < FRAME_MS) {
      this.frame = requestAnimationFrame(this.draw);
      return;
    }
    this.lastDraw = now;
    const gl = this.gl;
    const t = (now - this.t0) / 1000;
    if (!this.drag) {
      this.yaw += this.spin;
      this.spin = Math.abs(this.spin) < 0.0009 ? 0.0009 : this.spin * 0.995;
    }
    const R = this.rotation();
    const aspect = this.canvas.width / this.canvas.height;
    const fit = Math.min(1, aspect);
    gl.clearColor(0.008, 0.016, 0.04, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const size = Math.max(1.2, Math.min(3.2, 2.6 * Math.sqrt(START_LIGHTS / this.count))) * (this.canvas.height / 900 + 0.4);
    this.use(this.lights, this.lightsBuf, R, aspect, fit, t, size);
    gl.drawArrays(gl.POINTS, 0, this.count);
    this.use(this.arcs, this.arcsBuf, R, aspect, fit, t, 2.2 * this.pixelScale);
    gl.drawArrays(gl.POINTS, 0, this.arcCount);
    this.placeLabels(R, aspect, fit);

    this.frames++;
    if (now - this.lastStats > 2000) {
      const fps = (this.frames * 1000) / (now - this.lastStats);
      this.frames = 0;
      this.lastStats = now;
      if (fps < 22 && this.count > MIN_LIGHTS) this.count = Math.max(MIN_LIGHTS, Math.round(this.count * 0.7));
      else if (fps > 28 && this.count < this.maxLights) this.count = Math.min(this.maxLights, Math.round(this.count * 1.2));
      this.onStats({ fps: Math.round(fps), lights: this.count, renderer: this.rendererName });
    }
    this.frame = requestAnimationFrame(this.draw);
  };

  private placeLabels(R: Float32Array, aspect: number, fit: number) {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight, k = 2.3 * this.zoom * fit;
    this.centers.forEach((c, i) => {
      const p = [c[0] * 1.06, c[1] * 1.06, c[2] * 1.06];
      const x = R[0] * p[0] + R[3] * p[1] + R[6] * p[2];
      const y = R[1] * p[0] + R[4] * p[1] + R[7] * p[2];
      const z = R[2] * p[0] + R[5] * p[1] + R[8] * p[2];
      const d = 3.2 - z;
      const el = this.labels[i];
      el.style.left = `${((x / d) * k / aspect * 0.5 + 0.5) * w}px`;
      el.style.top = `${(0.5 - (y / d) * k * 0.5) * h}px`;
      const visible = z > -0.15;
      el.style.opacity = visible ? String(Math.min(1, 0.35 + z)) : "0";
      el.tabIndex = visible ? 0 : -1;
      el.style.pointerEvents = visible ? "auto" : "none";
    });
  }

  private onDown = (e: PointerEvent) => {
    this.drag = [e.clientX, e.clientY];
    this.canvas.setPointerCapture(e.pointerId);
  };

  private onMove = (e: PointerEvent) => {
    if (!this.drag) return;
    const dx = e.clientX - this.drag[0], dy = e.clientY - this.drag[1];
    this.drag = [e.clientX, e.clientY];
    this.yaw += dx * 0.005;
    this.pitch = Math.max(-1.3, Math.min(1.3, this.pitch + dy * 0.005));
    this.spin = dx * 0.0002;
  };

  private onUp = () => {
    this.drag = null;
  };

  private onWheel = (e: WheelEvent) => {
    e.preventDefault();
    this.zoom = Math.max(0.6, Math.min(2.2, this.zoom * (e.deltaY < 0 ? 1.08 : 0.93)));
  };

  private onVisibility = () => {
    if (document.hidden) {
      cancelAnimationFrame(this.frame);
    } else if (this.running) {
      this.lastStats = performance.now();
      this.frames = 0;
      this.frame = requestAnimationFrame(this.draw);
    }
  };
}
