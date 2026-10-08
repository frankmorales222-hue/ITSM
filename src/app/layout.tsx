import "./globals.css";
import { ToastProvider } from "@/components/Toast";

export const metadata = {
  title: 'IT Support',
  description: 'Internal IT support ticketing',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  )
}
