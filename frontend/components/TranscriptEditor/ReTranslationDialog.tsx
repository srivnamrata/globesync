'use client';

import React from 'react';

interface ReTranslationDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  isTranslating: boolean;
}

export const ReTranslationDialog: React.FC<ReTranslationDialogProps> = ({
  isOpen,
  onConfirm,
  onCancel,
  isTranslating,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
        <div className="space-y-2">
          <h3 className="text-lg font-bold text-white">Manual Override Confirmed</h3>
          <p className="text-sm text-slate-400 leading-relaxed">
            You modified the segment transcription. Do you want to submit this override directly to the database or trigger auto-retranslation?
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm font-semibold transition"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold transition"
            disabled={isTranslating}
          >
            {isTranslating ? 'Translating...' : 'Apply Override'}
          </button>
        </div>
      </div>
    </div>
  );
};
export default ReTranslationDialog;
