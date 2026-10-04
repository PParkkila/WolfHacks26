import type { Metadata } from "next"
import type { ReactNode } from "react"

import { Providers } from "@/components/providers"

import "./globals.css"

export const metadata: Metadata = {
  title: "Gluco",
  description:
    "Gluco turns your wearable's daily readings into a simple score, with easy-to-read dashboards and an assistant for people at risk of diabetes and their care team.",
}

type RootLayoutProps = Readonly<{ children: ReactNode }>

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" suppressHydrationWarning className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
