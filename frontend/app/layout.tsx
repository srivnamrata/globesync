import React from 'react';
import { Space_Grotesk } from 'next/font/google';
import './globals.css';

const brandFont = Space_Grotesk({
  subsets: ['latin'],
  weight: ['500', '700'],
  variable: '--font-brand',
});

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
    <html lang="en" dir="ltr" className="h-full">
      <body className={`${brandFont.variable} bg-slate-950 text-slate-100 font-sans antialiased`} suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
