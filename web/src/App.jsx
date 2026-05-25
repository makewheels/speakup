import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { UserProvider, useUser } from "./context/UserContext.jsx";
import Layout from "./components/layout/Layout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import PracticePage from "./pages/PracticePage.jsx";
import VocabularyPage from "./pages/VocabularyPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import "./App.css";

function ProtectedRoutes() {
  const { user } = useUser();
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoutes />}>
        <Route path="/" element={<Navigate to="/practice" replace />} />
        <Route path="/practice" element={<PracticePage />} />
        <Route path="/practice/:sessionId" element={<PracticePage />} />
        <Route path="/vocabulary" element={<VocabularyPage />} />
        <Route path="/me" element={<ProfilePage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <UserProvider>
        <AppRoutes />
      </UserProvider>
    </BrowserRouter>
  );
}
