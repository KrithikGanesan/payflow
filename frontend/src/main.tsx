import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import { Layout } from "@/components/Layout";
import { LiveRun } from "@/pages/LiveRun";
import { DecisionFlow } from "@/pages/DecisionFlow";
import { Dashboard } from "@/pages/Dashboard";
import { History } from "@/pages/History";
import { ExceptionQueue } from "@/pages/ExceptionQueue";
import { AuditTrail } from "@/pages/AuditTrail";
import { RunDetail } from "@/pages/RunDetail";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <LiveRun /> },
      { path: "flow", element: <DecisionFlow /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "history", element: <History /> },
      { path: "exceptions", element: <ExceptionQueue /> },
      { path: "audit", element: <AuditTrail /> },
      { path: "runs/:id", element: <RunDetail /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
