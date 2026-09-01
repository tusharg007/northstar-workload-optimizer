import { Routes, Route } from 'react-router-dom';
import { Toaster } from 'sonner';
import { ThemeProvider } from '@/components/theme-provider';
import DashboardLayout from './layouts/DashboardLayout';
import Dashboard from './pages/Dashboard';
import SubmitExpense from './pages/SubmitExpense';
import Approvals from './pages/Approvals';
import ExpenseDetail from './pages/ExpenseDetail';
import ContextExplorer from './pages/ContextExplorer';
import Analytics from './pages/Analytics';
import SystemHealth from './pages/SystemHealth';

export default function App() {
  return (
    <ThemeProvider defaultTheme="system">
      <Routes>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/submit" element={<SubmitExpense />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/expenses/:id" element={<ExpenseDetail />} />
          <Route path="/context" element={<ContextExplorer />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/health" element={<SystemHealth />} />
        </Route>
      </Routes>
      <Toaster richColors position="top-right" />
    </ThemeProvider>
  );
}
