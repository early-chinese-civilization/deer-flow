"use client";

import { useEffect, useMemo } from "react";

import { withBasePath } from "@/core/config";

type LoginRedirectProps = {
  returnTo: string;
};

export function LoginRedirect({ returnTo }: LoginRedirectProps) {
  const loginUrl = useMemo(() => {
    const params = new URLSearchParams({ return_to: returnTo });
    return withBasePath(`/api/auth/login?${params.toString()}`);
  }, [returnTo]);

  useEffect(() => {
    window.location.replace(loginUrl);
  }, [loginUrl]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 px-6 py-16">
      <section className="w-full max-w-md rounded-3xl border border-neutral-200 bg-white p-10 shadow-sm">
        <p className="text-xs font-medium tracking-[0.28em] text-neutral-500 uppercase">
          DeerFlow
        </p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-neutral-950">
          Redirecting to sign in
        </h1>
        <p className="mt-3 text-sm leading-6 text-neutral-600">
          The login flow is opening in this browser tab.
        </p>
        <a
          className="mt-8 inline-flex h-10 items-center justify-center rounded-md bg-neutral-950 px-4 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
          href={loginUrl}
        >
          Continue
        </a>
      </section>
    </main>
  );
}
