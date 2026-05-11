import "@/styles/globals.css";
import "katex/dist/katex.min.css";

import { type Metadata } from "next";
import { NuqsAdapter } from "nuqs/adapters/next/app";

import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/core/auth";
import { DEFAULT_BRAND } from "@/core/brand";
import { I18nProvider } from "@/core/i18n/context";
import { detectLocaleServer } from "@/core/i18n/server";

export const metadata: Metadata = {
  title: DEFAULT_BRAND.fullName,
  description: DEFAULT_BRAND.description,
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await detectLocaleServer();
  return (
    <html lang={locale} suppressContentEditableWarning suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" enableSystem disableTransitionOnChange>
          <I18nProvider initialLocale={locale}>
            <NuqsAdapter>
              <AuthProvider>{children}</AuthProvider>
            </NuqsAdapter>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
