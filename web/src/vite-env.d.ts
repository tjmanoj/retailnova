/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MOCK?: string
  readonly VITE_STREAM_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
