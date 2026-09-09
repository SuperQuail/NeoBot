import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Plugins from './pages/Plugins.jsx';
import ConfigManager from './pages/ConfigManager.jsx';
import System from './pages/System.jsx';
import Bots from './pages/Bots.jsx';
import Logs from './pages/Logs.jsx';
import Login from './pages/Login.jsx';
import { getToken } from './api/client.js';

function RequireAuth({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="plugins" element={<Plugins />} />
        <Route path="config" element={<ConfigManager />} />
        <Route path="system" element={<System />} />
        <Route path="bots" element={<Bots />} />
        <Route path="logs" element={<Logs />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
