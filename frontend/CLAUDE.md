# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DeerFlow Frontend is a Next.js 16 web interface for an AI agent system. It communicates with a LangGraph-based backend to provide thread-based AI conversations with streaming responses, artifacts, and a skills/tools system.

**Stack**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, pnpm 10.26.2

## Commands

| Command          | Purpose                                           |
| ---------------- | ------------------------------------------------- |
| `pnpm dev`       | Dev server with Turbopack (http://localhost:3000) |
| `pnpm build`     | Production build                                  |
| `pnpm check`     | Lint + type check (run before committing)         |
| `pnpm lint`      | ESLint only                                       |
| `pnpm lint:fix`  | ESLint with auto-fix                              |
| `pnpm typecheck` | TypeScript type check (`tsc --noEmit`)            |
| `pnpm start`     | Start production server                           |

No test framework is configured.

## Architecture

```
Frontend (Next.js) 鈹€鈹€鈻?LangGraph SDK 鈹€鈹€鈻?LangGraph Backend (lead_agent)
                                              鈹溾攢鈹€ Sub-Agents
                                              鈹斺攢鈹€ Tools & Skills
```

The frontend is a stateful chat application. Users create **threads** (conversations), send messages, and receive streamed AI responses. The backend orchestrates agents that can produce **artifacts** (files/code) and **todos**.

### Source Layout (`src/`)

- **`app/`** 鈥?Next.js App Router. Routes: `/` (landing), `/workspace/chats/[thread_id]` (chat).
- **`components/`** 鈥?React components split into:
  - `ui/` 鈥?Shadcn UI primitives (auto-generated, ESLint-ignored)
  - `ai-elements/` 鈥?Vercel AI SDK elements (auto-generated, ESLint-ignored)
  - `workspace/` 鈥?Chat page components (messages, artifacts, settings)
  - `landing/` 鈥?Landing page sections
- **`core/`** 鈥?Business logic, the heart of the app:
  - `threads/` 鈥?Thread creation, streaming, state management (hooks + types)
  - `api/` 鈥?LangGraph client singleton
  - `artifacts/` 鈥?Artifact loading and caching
  - `i18n/` 鈥?Internationalization (en-US, zh-CN)
  - `settings/` 鈥?User preferences in localStorage
  - `memory/` 鈥?Persistent user memory system
  - `skills/` 鈥?Skills installation and management
  - `messages/` 鈥?Message processing and transformation
  - `mcp/` 鈥?Model Context Protocol integration
  - `models/` 鈥?TypeScript types and data models
- **`hooks/`** 鈥?Shared React hooks
- **`lib/`** 鈥?Utilities (`cn()` from clsx + tailwind-merge)
- **`server/`** 鈥?Server-side code (better-auth, not yet active)
- **`styles/`** 鈥?Global CSS with Tailwind v4 `@import` syntax and CSS variables for theming

### Data Flow

1. User input 鈫?thread hooks (`core/threads/hooks.ts`) 鈫?LangGraph SDK streaming
2. Stream events update thread state (messages, artifacts, todos)
3. TanStack Query manages server state; localStorage stores user settings
4. Components subscribe to thread state and render updates

### Key Patterns

- **Server Components by default**, `"use client"` only for interactive components
- **Thread hooks** (`useThreadStream`, `useSubmitThread`, `useThreads`) are the primary API interface
- **LangGraph client** is a singleton obtained via `getAPIClient()` in `core/api/`
- **Environment validation** uses `@t3-oss/env-nextjs` with Zod schemas (`src/env.js`). Skip with `SKIP_ENV_VALIDATION=1`

## Code Style

- **Imports**: Enforced ordering (builtin 鈫?external 鈫?internal 鈫?parent 鈫?sibling), alphabetized, newlines between groups. Use inline type imports: `import { type Foo }`.
- **Unused variables**: Prefix with `_`.
- **Class names**: Use `cn()` from `@/lib/utils` for conditional Tailwind classes.
- **Path alias**: `@/*` maps to `src/*`.
- **Components**: `ui/` and `ai-elements/` are generated from registries (Shadcn, MagicUI, React Bits, Vercel AI SDK) 鈥?don't manually edit these.

## Environment

Backend API URLs are optional; an nginx proxy is used by default:

```
NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8001
NEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:8001/api
```

Requires Node.js 22+ and pnpm 10.26.2+.
