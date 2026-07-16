import "@testing-library/jest-dom/vitest";

Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", { configurable: true, value: () => false });
Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: () => undefined });
Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", { configurable: true, value: () => undefined });
Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => undefined });
Object.defineProperty(HTMLElement.prototype, "getAnimations", { configurable: true, value: () => [] });
Object.defineProperty(document, "getAnimations", { configurable: true, value: () => [] });

// xyflow 只渲染「已量过尺寸」的节点，没量到就挂 visibility:hidden——
// jsdom 里所有元素都是 0×0 且 ResizeObserver 从不回调，画布节点会整片进不了
// 无障碍树，测不到。下面这套是 xyflow 官方的 jsdom 配方（测试文档同款）：
// ResizeObserver 在 observe 时立刻回调一次，元素报出非零尺寸，节点就量得到了。
/** 画布视口尺寸：1440×960 减顶栏，正好是 v7 验收基准的桌面视口 */
const VIEWPORT = { width: 1440, height: 895 };

function entryFor(target: Element): ResizeObserverEntry {
  const box = { width: VIEWPORT.width, height: VIEWPORT.height };
  return { target, contentRect: { ...box, x: 0, y: 0, top: 0, left: 0, right: box.width, bottom: box.height } } as ResizeObserverEntry;
}

class ResizeObserverStub {
  private live = true;
  constructor(private readonly callback: ResizeObserverCallback) {}
  // 必须异步回调：真实 ResizeObserver 也是下一帧才回调，而 xyflow 要等外层
  // ReactFlow 的 effect 把 domNode 存进 store 才量得到节点。子组件 effect 先跑，
  // 同步回调会赶在 domNode 之前，量测被直接丢弃（节点就永远 hidden）。
  observe(target: Element) {
    queueMicrotask(() => { if (this.live) this.callback([entryFor(target)], this as unknown as ResizeObserver); });
  }
  unobserve() {}
  disconnect() { this.live = false; }
}

class DOMMatrixReadOnlyStub {
  m22: number;
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([1-9.]+)\)/)?.[1];
    this.m22 = scale === undefined ? 1 : Number(scale);
  }
}

class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}

// 画布节点是可拖的（react-flow 给每个节点挂 d3-drag）。jsdom 里 user-event 派发的
// mousedown 事件 view 为 null，而 d3-drag 的 mousedown 回调会读 event.view.document——
// 直接崩在 nodrag.js。jsdom 把这个监听器异常当作未捕获异常上报（测试照过，但整轮 exit code=1）。
//
// 光在 UIEvent.prototype 上补 view 回退没用：user-event 的 createEvent 会用 assignProps 给
// 每个合成事件挂一个「自有」view getter（未显式传 view 时返回 null），自有属性优先级高于
// 原型、且被定义成不可配置，直接盖过原型上的回退。所以收窄地包一层 Object.defineProperty：
// 只在给某个 UIEvent 实例定义 view getter 时，补一个「空值回退到 window」，其余原样透传。
// 这样 d3-drag 拿到的是 window.document，不再崩。
const nativeDefineProperty = Object.defineProperty.bind(Object);
Object.defineProperty = ((target: object, key: PropertyKey, descriptor: PropertyDescriptor) => {
  if (key === "view" && typeof descriptor.get === "function" && target instanceof UIEvent) {
    const original = descriptor.get;
    return nativeDefineProperty(target, key, { ...descriptor, get(this: unknown) { return original.call(this) ?? window; } });
  }
  return nativeDefineProperty(target, key, descriptor);
}) as typeof Object.defineProperty;

Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: ResizeObserverStub });
Object.defineProperty(globalThis, "DOMMatrixReadOnly", { configurable: true, value: DOMMatrixReadOnlyStub });
Object.defineProperties(HTMLElement.prototype, {
  offsetHeight: { configurable: true, get() { return Number.parseFloat(this.style.height) || 1; } },
  offsetWidth: { configurable: true, get() { return Number.parseFloat(this.style.width) || 1; } },
});
Object.defineProperty(SVGElement.prototype, "getBBox", { configurable: true, value: () => ({ x: 0, y: 0, width: 0, height: 0 }) });
Object.defineProperty(globalThis, "IntersectionObserver", { configurable: true, value: IntersectionObserverStub });
Object.defineProperty(window, "matchMedia", {
  configurable: true,
  value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
});

const storage = new Map<string, string>();
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: {
    clear: () => storage.clear(),
    getItem: (key: string) => storage.get(key) ?? null,
    key: (index: number) => [...storage.keys()][index] ?? null,
    get length() { return storage.size; },
    removeItem: (key: string) => storage.delete(key),
    setItem: (key: string, value: string) => storage.set(key, String(value)),
  },
});
