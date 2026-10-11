import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; Radix uses it to position tooltips and popovers.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
