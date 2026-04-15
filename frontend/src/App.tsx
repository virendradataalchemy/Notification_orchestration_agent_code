import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import HomePage from './pages/home/HomePage';
import LoginPage from './pages/login/LoginPage';
import SignupPage from './pages/signup/SignupPage';
import AdminPage from './pages/admin/AdminPage';
import AuthCallbackPage from './pages/auth/AuthCallbackPage';
import ClientLayout from './pages/client/ClientLayout';
import ClientPortalResolver from './pages/client/ClientPortalResolver';
import ClientDashboardPage from './pages/client/ClientDashboardPage';
import AnalyticsPage from './pages/client/AnalyticsPage';
import TemplatesPage from './pages/client/TemplatesPage';
import DepartmentsPage from './pages/client/DepartmentsPage';
import DepartmentDetailPage from './pages/client/DepartmentDetailPage';
import SendDemoPage from './pages/client/SendDemoPage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        
        {/* ID-based internal dashboard */}
        <Route path="/client/:id" element={<ClientLayout />}>
          <Route index element={<ClientDashboardPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="templates" element={<TemplatesPage />} />
          <Route path="departments" element={<DepartmentsPage />} />
          <Route path="departments/:department" element={<DepartmentDetailPage />} />
          <Route path="send-demo" element={<SendDemoPage />} />
        </Route>

        {/* Slug-based portal alias */}
        <Route path="/clients/:slug" element={<ClientPortalResolver />}>
          <Route path="portal" element={<ClientDashboardPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="templates" element={<TemplatesPage />} />
          <Route path="departments" element={<DepartmentsPage />} />
          <Route path="departments/:department" element={<DepartmentDetailPage />} />
          <Route path="notifications/demo" element={<SendDemoPage />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
