import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Sidebar } from "@/components/Sidebar";
import PaperReviewPage from "@/pages/PaperReviewPage";
import ReviewQueuePage from "@/pages/ReviewQueuePage";
import PipelineStatusPage from "@/pages/PipelineStatusPage";
import EvidenceGapsPage from "@/pages/EvidenceGapsPage";
import LintReportPage from "@/pages/LintReportPage";
import DuplicateCandidatesPage from "@/pages/DuplicateCandidatesPage";
import InsightsPage from "@/pages/InsightsPage";
import PeopleGridPage from "@/pages/PeopleGridPage";
import MultiGraphPage from "@/pages/MultiGraphPage";
import MultiGraphEmbed from "@/pages/MultiGraphEmbed";
import GeographicPage from "@/pages/GeographicPage";
import NetworkPage from "@/pages/NetworkPage";
import CoauthorNetworkPage from "@/pages/CoauthorNetworkPage";
import SankeyPage from "@/pages/SankeyPage";
import TimelinePage from "@/pages/TimelinePage";
import EvalPage from "@/pages/EvalPage";
import DiscoveryPage from "@/pages/DiscoveryPage";
import ImpactPage from "@/pages/ImpactPage";
import DriftPage from "@/pages/DriftPage";
import ReportPage from "@/pages/ReportPage";
import NetworkGrowthPage from "@/pages/NetworkGrowthPage";
import "@/styles.css";

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">{children}</main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {/* Embed routes — no sidebar, full viewport */}
        <Route path="/multi-graph/embed" element={<MultiGraphEmbed />} />

        {/* Main app shell */}
        <Route path="*" element={
          <Layout>
            <Routes>
              <Route path="/" element={<PaperReviewPage />} />
          <Route path="/queue" element={<ReviewQueuePage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/pipeline" element={<PipelineStatusPage />} />
          <Route path="/evidence-gaps" element={<EvidenceGapsPage />} />
          <Route path="/lint" element={<LintReportPage />} />
          <Route path="/duplicates" element={<DuplicateCandidatesPage />} />
          <Route path="/discovery" element={<DiscoveryPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="/eval" element={<EvalPage />} />
          <Route path="/sankey" element={<SankeyPage />} />
          <Route path="/timeline" element={<TimelinePage />} />
          <Route path="/network" element={<CoauthorNetworkPage />} />
          <Route path="/network-v1" element={<NetworkPage />} />
          <Route path="/impact" element={<ImpactPage />} />
          <Route path="/drift" element={<DriftPage />} />
          <Route path="/people" element={<PeopleGridPage />} />
          <Route path="/multi-graph" element={<MultiGraphPage />} />
          <Route path="/geographic" element={<GeographicPage />} />
          <Route path="/growth" element={<NetworkGrowthPage />} />
            </Routes>
          </Layout>
        } />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
