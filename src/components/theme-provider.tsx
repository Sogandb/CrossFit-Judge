"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

type Props = ComponentProps<typeof NextThemesProvider>;

/** next-themes wrapper — class strategy, dark by default (the v1 template look). */
export function ThemeProvider(props: Props) {
  return <NextThemesProvider {...props} />;
}
