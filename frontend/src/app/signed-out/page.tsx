import Link from "next/link";

import { Button } from "@/components/ui/button";
import { BRAND } from "@/core/brand";
import { withBasePath } from "@/core/config";

export default function SignedOutPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 px-6 py-16">
      <section className="w-full max-w-md rounded-3xl border border-neutral-200 bg-white p-10 shadow-sm">
        <p className="text-xs font-medium tracking-[0.28em] text-neutral-500 uppercase">
          {BRAND.en.shortName}
        </p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-neutral-950">
          You are signed out
        </h1>
        <p className="mt-3 text-sm leading-6 text-neutral-600">
          Your session was ended successfully. You can start a new login flow
          when you are ready.
        </p>
        <div className="mt-8 flex gap-3">
          <Button asChild>
            <Link
              href={withBasePath(
                `/auth/login?return_to=${encodeURIComponent(
                  withBasePath("/workspace"),
                )}`,
              )}
            >
              Sign in again
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={withBasePath("/")}>Refresh status</Link>
          </Button>
        </div>
      </section>
    </main>
  );
}
