'use client';

import React, { useState } from 'react';
import OriginalPane from './OriginalPane';
import TranslatedPane from './TranslatedPane';
import WordTimingControl from './WordTimingControl';
import SegmentMenu from './SegmentMenu';
import ReTranslationDialog from './ReTranslationDialog';
import { useTranscriptEditor } from '../../hooks/useTranscriptEditor';
import { useReTranslation } from '../../hooks/useReTranslation';

export const TranscriptEditor: React.FC = () => {
  const editor = useTranscriptEditor();
  const reTrans = useReTranslation();
  const [fontSize, setFontSize] = useState<number>(14);

  const selectedSegment = editor.segments.find((s) => s.id === editor.selectedSegmentId) || null;

  const handleOriginalTextChange = (id: string, text: string) => {
    editor.updateSegmentText(id, 'original', text);
    // Request GPT-4o retranslation of the modified source segment text
    reTrans.requestReTranslation(id, text, 'es');
  };

  const handleTranslatedTextChange = (id: string, text: string) => {
    // Stage manual translation text changes
    reTrans.queueManualOverride(id, text);
  };

  return (
    <div className="h-full flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
      {/* Editor Control Header */}
      <div className="h-12 border-b border-slate-800 bg-slate-900/40 px-4 flex items-center justify-between text-xs select-none">
        <div className="flex items-center gap-3">
          <span className="text-slate-400 font-bold uppercase tracking-wider">Dual Pane Editor</span>
          <div className="flex items-center gap-1.5 border-l border-slate-800 pl-3">
            <button
              onClick={() => setFontSize(Math.max(12, fontSize - 1))}
              className="w-6 h-6 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded flex items-center justify-center font-bold"
            >
              A-
            </button>
            <span className="text-slate-400 font-mono">{fontSize}px</span>
            <button
              onClick={() => setFontSize(Math.min(20, fontSize + 1))}
              className="w-6 h-6 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded flex items-center justify-center font-bold"
            >
              A+
            </button>
          </div>
        </div>

        {/* Action controls for selected segment */}
        <SegmentMenu
          segment={selectedSegment}
          onSplit={editor.splitSegment}
          onMerge={editor.mergeSegments}
          onDelete={editor.deleteSegment}
          onDuplicate={editor.duplicateSegment}
          onToggleLock={editor.setSegmentLock}
        />
      </div>

      {/* Split Pane Dialogue Grid */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 overflow-hidden">
        {/* Left Side: Source Transcript */}
        <div className="border-r border-slate-800 flex flex-col overflow-hidden">
          <div className="h-9 border-b border-slate-850 bg-slate-950/20 px-4 flex items-center justify-between text-[10px] text-slate-500 font-bold uppercase select-none">
            <span>Original Transcript</span>
          </div>
          <OriginalPane
            segments={editor.segments}
            selectedId={editor.selectedSegmentId}
            onSelect={editor.setSelectedSegmentId}
            fontSize={fontSize}
          />
        </div>

        {/* Right Side: Translation Pane */}
        <div className="flex flex-col overflow-hidden">
          <div className="h-9 border-b border-slate-850 bg-slate-950/20 px-4 flex items-center justify-between text-[10px] text-indigo-400 font-bold uppercase select-none">
            <span>Target Translation</span>
          </div>
          <TranslatedPane
            segments={editor.segments}
            selectedId={editor.selectedSegmentId}
            onSelect={editor.setSelectedSegmentId}
            onTextChange={handleTranslatedTextChange}
            fontSize={fontSize}
          />
        </div>
      </div>

      {/* Bottom Area: Word Timing Control Widget */}
      <div className="border-t border-slate-800 p-4 bg-slate-950/60">
        <WordTimingControl segment={selectedSegment} />
      </div>

      {/* Confirmation Modals */}
      <ReTranslationDialog
        isOpen={reTrans.showOverrideConfirm}
        onConfirm={reTrans.confirmOverride}
        onCancel={() => reTrans.setShowOverrideConfirm(false)}
        isTranslating={reTrans.isTranslating}
      />
    </div>
  );
};
export default TranscriptEditor;
