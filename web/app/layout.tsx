// The frame around every page: fonts, the top bar and its three links.
// Fonts are bundled with the app (Mukta covers both Latin and Devanagari, for Hinglish transcripts).
import "@fontsource/mukta/400.css";
import "@fontsource/mukta/500.css";
import "@fontsource/mukta/600.css";
import "@fontsource/mukta/devanagari-400.css";
import "@fontsource/mukta/devanagari-600.css";
import "@fontsource-variable/anek-latin";
import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = {
  title: "Virtual KAM",
  description: "A voice account manager for marketplace sellers. Prototype built for the Snapdeal AI First Intern assignment.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="top">
          <Link href="/" className="brand"><i aria-hidden />Virtual KAM</Link>
          <span className="note">Prototype for the Snapdeal assignment, mock data only</span>
          <nav>
            <Link href="/">Sellers</Link>
            <Link href="/dashboard">Team dashboard</Link>
            <Link href="/how-it-works">How it works</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
