import { useEffect, useRef } from 'react';

type UseDialogAccessibilityOptions = {
    isOpen: boolean;
    onRequestClose: () => void;
    dialogSelector?: string;
};

export function useDialogAccessibility({
    isOpen,
    onRequestClose,
    dialogSelector = '[role="dialog"]',
}: UseDialogAccessibilityOptions) {
    const focusOriginRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
        if (isOpen && !focusOriginRef.current && document.activeElement instanceof HTMLElement) {
            focusOriginRef.current = document.activeElement;
            return;
        }

        if (!isOpen && focusOriginRef.current) {
            focusOriginRef.current.focus();
            focusOriginRef.current = null;
        }
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen) return;

        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                onRequestClose();
            }
        };

        window.addEventListener('keydown', handleEscape);
        return () => window.removeEventListener('keydown', handleEscape);
    }, [isOpen, onRequestClose]);

    useEffect(() => {
        if (!isOpen) return;

        const dialog = document.querySelector<HTMLElement>(dialogSelector);
        if (!dialog) return;

        const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
        const handleTab = (event: KeyboardEvent) => {
            if (event.key !== 'Tab') return;

            const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
            if (focusable.length === 0) return;

            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };

        dialog.addEventListener('keydown', handleTab);
        return () => dialog.removeEventListener('keydown', handleTab);
    }, [dialogSelector, isOpen]);
}
