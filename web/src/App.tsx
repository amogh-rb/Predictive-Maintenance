import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AtRiskPage from "./pages/AtRiskPage";
import VehicleDetailPage from "./pages/VehicleDetailPage";
import AlertsPage from "./pages/AlertsPage";
import CopilotPage from "./pages/CopilotPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import AuditPage from "./pages/AuditPage";
import MaintenancePage from "./pages/MaintenancePage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/at-risk" replace />} />
        <Route path="/at-risk" element={<AtRiskPage />} />
        <Route path="/maintenance" element={<MaintenancePage />} />
        <Route path="/vehicles/:id" element={<VehicleDetailPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/copilot" element={<CopilotPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/at-risk" replace />} />
      </Route>
    </Routes>
  );
}
