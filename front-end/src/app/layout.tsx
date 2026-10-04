import type { Metadata } from "next"
import { Geist_Mono, Manrope } from "next/font/google"

import { Providers } from "@/components/providers"

import "./globals.css"

// Manrope: friendly, open shapes for patients, with tabular figures for tables.
const manrope = Manrope({
  variable: "--font-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "Gluco",
  description:
    "Gluco turns your wearable's daily readings into a simple score, with easy-to-read dashboards and an assistant for people at risk of diabetes and their care team.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${manrope.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
