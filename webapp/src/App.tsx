import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/layout/Layout';
import PipelineListPage from './pages/PipelineListPage';
import PipelineDesignerPage from './pages/PipelineDesignerPage';
import MonitorDashboardPage from './pages/MonitorDashboardPage';
import JobListPage from './pages/WorkItemListPage';
import JobDetailPage from './pages/WorkItemDetailPage';
import DefinitionListPage from './pages/DefinitionListPage';
import PluginMarketplacePage from './pages/PluginMarketplacePage';
import SystemLogsPage from './pages/SystemLogsPage';
import ProvenancePage from './pages/ProvenancePage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/pipelines" replace />} />
        <Route path="pipelines" element={<PipelineListPage />} />
        <Route path="pipelines/:id/designer" element={<PipelineDesignerPage />} />
        <Route path="monitor" element={<MonitorDashboardPage />} />
        <Route path="jobs" element={<JobListPage />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="definitions" element={<DefinitionListPage />} />
        <Route path="plugins" element={<PluginMarketplacePage />} />
        <Route path="logs" element={<SystemLogsPage />} />
        <Route path="provenance" element={<ProvenancePage />} />
      </Route>
    </Routes>
  );
}

export default App;
