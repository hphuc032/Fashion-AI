import type { Metadata } from "next";
import { Providers } from "./providers";
import { Workspace } from "@/components/layout/workspace";
import "./globals.css";
export const metadata: Metadata = {
  title: "Fashion AI · Local Studio",
  description: "Không gian xử lý video thời trang cục bộ.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body>
        <Providers>
          <Workspace>{children}</Workspace>
        </Providers>
      </body>
    </html>
  );
}
