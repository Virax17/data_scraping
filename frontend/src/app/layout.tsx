import type { ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

export const metadata = { title: "Tritorc Enrichment" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <div className="flex h-screen w-full overflow-hidden bg-background">
          <Sidebar />
          {children}
        </div>
      </body>
    </html>
  );
}
