import { create } from "zustand";
export const useWorkspace = create<{
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}>((set) => ({
  sidebarOpen: false,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}));
