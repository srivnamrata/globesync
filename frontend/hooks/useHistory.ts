import { useHistoryStore, Action } from '../store/historyStore';
import { useMediaStore } from '../store/mediaStore';
import { useTranslationStore } from '../store/translationStore';

export function useHistory() {
  const history = useHistoryStore();
  const updateTranscriptText = useMediaStore((s) => s.updateSegmentText);
  const updateTranslationText = useTranslationStore((s) => s.updateTranslationText);

  const triggerUndo = () => {
    const action = history.undo();
    if (!action) return;

    switch (action.type) {
      case 'edit_transcript':
        updateTranscriptText(action.targetId, action.before);
        break;
      case 'edit_translation':
        updateTranslationText(action.targetId, action.before);
        break;
      default:
        console.warn(`Undo for action type ${action.type} is not implemented.`);
    }
  };

  const triggerRedo = () => {
    const action = history.redo();
    if (!action) return;

    switch (action.type) {
      case 'edit_transcript':
        updateTranscriptText(action.targetId, action.after);
        break;
      case 'edit_translation':
        updateTranslationText(action.targetId, action.after);
        break;
      default:
        console.warn(`Redo for action type ${action.type} is not implemented.`);
    }
  };

  return {
    canUndo: history.undoStack.length > 0,
    canRedo: history.redoStack.length > 0,
    undo: triggerUndo,
    redo: triggerRedo,
    pushHistory: history.pushAction,
  };
}
