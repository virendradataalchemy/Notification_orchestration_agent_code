import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orchestration Ledger",
  description: "B2B Notification Orchestration Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-white text-slate-900 scroll-smooth antialiased">
        {children}
      </body>
    </html>
  );
}
