import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import UploadPage from './pages/UploadPage';
import IdeasPage from './pages/IdeasPage';
import IdeasDetailPage from './pages/IdeasDetailPage';
import OutlinesPage from './pages/OutlinesPage';
import OutlinesDetailPage from './pages/OutlinesDetailPage';
import ProjectsPage from './pages/ProjectsPage';
import ProjectWorkspace from './pages/ProjectWorkspace';
import RewritePage from './pages/RewritePage';
import StoryboardPage from './pages/StoryboardPage';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/ideas" element={<IdeasPage />} />
        <Route path="/ideas/:id" element={<IdeasDetailPage />} />
        <Route path="/outlines" element={<OutlinesPage />} />
        <Route path="/outlines/:id" element={<OutlinesDetailPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:id" element={<ProjectWorkspace />} />
        {/* 旧的 /writing/* 链接重定向到作品列表 */}
        <Route path="/writing" element={<Navigate to="/projects" replace />} />
        <Route path="/writing/*" element={<Navigate to="/projects" replace />} />
        <Route path="/rewrite" element={<RewritePage />} />
        <Route path="/storyboard" element={<StoryboardPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
