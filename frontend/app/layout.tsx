import type { Metadata, ReactNode } from "next";

export const metadata: Metadata = {
  title: "Knowledge Search",
  description: "Document Q&A with citations",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
