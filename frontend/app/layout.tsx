import React from 'react';
import './globals.css';

export const metadata = {
  title: {
    default: 'GlobeSync | Video Translation Studio',
    template: '%s | GlobeSync',
  },
  description: 'Translate, review, dub, and export video for global audiences.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="bg-slate-950 text-slate-100 font-sans antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
