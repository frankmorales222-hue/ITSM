import "./globals.css";

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
      <body>{children}</body>
    </html>
  )
}
