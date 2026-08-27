import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { UserProvider } from "./context/UserContext.jsx";
import { useUser } from "./context/useUser.js";
import { LanguageProvider } from "./i18n/index.jsx";
import Layout from "./components/layout/Layout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import PracticePage from "./pages/PracticePage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import SessionDetailPage from "./pages/SessionDetailPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import EditProfilePage from "./pages/EditProfilePage.jsx";
import PracticePreferencePage from "./pages/PracticePreferencePage.jsx";
import ManageSharesPage from "./pages/ManageSharesPage.jsx";
import SharePage from "./pages/SharePage.jsx";
import FeedbackPage from "./pages/FeedbackPage.jsx";
import "./App.css";
import "./styles/practice-preferences.css";

function ProtectedRoutes() {
  const { user } = useUser();
  const location = useLocation();
  if (!user) {
    // 带原始路径（含 ?scenario= 等查询参数）进登录页，登录成功后回原处
    const from = location.pathname + location.search;
    return <Navigate to={`/login?redirect=${encodeURIComponent(from)}`} replace />;
  }
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
        <Route path="/me/profile" element={<EditProfilePage />} />
        <Route path="/me/practice-preferences" element={<PracticePreferencePage />} />
        <Route path="/me/feedback" element={<FeedbackPage />} />
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
