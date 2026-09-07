import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZB Hub",
  description: "A central hub for all of my projects.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
