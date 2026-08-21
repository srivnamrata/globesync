import { create } from 'zustand';

export interface Action {
  type: 'edit_transcript' | 'edit_translation' | 'split_segment' | 'merge_segments' | 'adjust_timing';
  targetId: string;
  before: any;
  after: any;
  description: string;
}

interface HistoryState {
  undoStack: Action[];
  redoStack: Action[];
  pushAction: (action: Action) => void;
  undo: () => Action | null;
  redo: () => Action | null;
  clearHistory: () => void;
}

export const useHistoryStore = create<HistoryState>((set, get) => ({
  undoStack: [],
  redoStack: [],

  pushAction: (action) => set((state) => {
    const nextUndo = [...state.undoStack, action];
    // Cap undo stack to 100 actions
    if (nextUndo.length > 100) {
      nextUndo.shift();
    }
    return {
      undoStack: nextUndo,
      redoStack: [], // Clear redo on new action
    };
  }),

  undo: () => {
    const { undoStack, redoStack } = get();
    if (undoStack.length === 0) return null;

    const action = undoStack[undoStack.length - 1];
    set({
      undoStack: undoStack.slice(0, -1),
      redoStack: [...redoStack, action],
    });
    return action;
  },

  redo: () => {
    const { undoStack, redoStack } = get();
    if (redoStack.length === 0) return null;

    const action = redoStack[redoStack.length - 1];
    set({
      undoStack: [...undoStack, action],
      redoStack: redoStack.slice(0, -1),
    });
    return action;
  },

  clearHistory: () => set({ undoStack: [], redoStack: [] }),
}));
