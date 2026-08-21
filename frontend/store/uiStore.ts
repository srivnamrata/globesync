import { create } from 'zustand';

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  message: string;
  autoCloseMs?: number;
}

interface UIState {
  activeTab: 'transcript' | 'translation' | 'voice' | 'settings';
  isExportDialogOpen: boolean;
  notifications: Notification[];
  theme: 'dark' | 'light';
  setActiveTab: (tab: UIState['activeTab']) => void;
  setExportDialogOpen: (isOpen: boolean) => void;
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeTab: 'transcript',
  isExportDialogOpen: false,
  notifications: [],
  theme: 'dark',

  setActiveTab: (activeTab) => set({ activeTab }),
  setExportDialogOpen: (isExportDialogOpen) => set({ isExportDialogOpen }),
  addNotification: (notification) => set((state) => {
    const id = Math.random().toString(36).substring(7);
    const item = { ...notification, id };
    return { notifications: [...state.notifications, item] };
  }),
  removeNotification: (id) => set((state) => ({
    notifications: state.notifications.filter((n) => n.id !== id)
  })),
  toggleTheme: () => set((state) => ({
    theme: state.theme === 'dark' ? 'light' : 'dark'
  })),
}));
