/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for the order API. Empty string means same-origin (nginx proxies /orders). */
  readonly VITE_API_BASE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
