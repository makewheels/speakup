import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { UserProvider, useUser } from "./context/UserContext.jsx";
import { LanguageProvider } from "./i18n/index.jsx";
import Layout from "./components/layout/Layout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import PracticePage from "./pages/PracticePage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import SessionDetailPage from "./pages/SessionDetailPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import PracticePreferencePage from "./pages/PracticePreferencePage.jsx";
import ManageSharesPage from "./pages/ManageSharesPage.jsx";
import SharePage from "./pages/SharePage.jsx";
import "./App.css";
import "./styles/practice-preferences.css";

function ProtectedRoutes() {
  const { user } = useUser();
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/s/:token" element={<SharePage />} />
      <Route element={<ProtectedRoutes />}>
        <Route path="/" element={<Navigate to="/practice" replace />} />
        <Route path="/practice" element={<PracticePage />} />
        <Route path="/practice/:practiceId" element={<PracticePage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/history/:practiceId" element={<SessionDetailPage />} />
        <Route path="/shares" element={<ManageSharesPage />} />
        <Route path="/me" element={<ProfilePage />} />
        <Route path="/me/practice-preferences" element={<PracticePreferencePage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <UserProvider>
          <AppRoutes />
        </UserProvider>
      </LanguageProvider>
    </BrowserRouter>
  );
}
