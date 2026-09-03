'use client';

import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
};

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-brand-500 text-white hover:bg-brand-400',
  secondary: 'border border-white/15 bg-white/5 text-slate-200 hover:border-white/25 hover:bg-white/10 hover:text-white',
  quiet: 'text-slate-300 hover:bg-white/10 hover:text-white',
  danger: 'bg-rose-500 text-white hover:bg-rose-400',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'min-h-8 rounded-lg px-3 py-1.5 text-xs',
  md: 'min-h-10 rounded-control px-4 py-2 text-sm',
  lg: 'min-h-12 rounded-control px-5 py-3 text-base',
};

export function Button({
  children,
  className = '',
  disabled,
  loading = false,
  size = 'md',
  type = 'button',
  variant = 'primary',
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 font-semibold transition duration-interface ease-interface focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {loading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
      ) : null}
      <span>{children}</span>
    </button>
  );
}
