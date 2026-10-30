import { Navigate, Route, Routes } from "react-router-dom";
import { AlertProvider } from "./alerts";
import { useAuth } from "./auth";
import { Spinner } from "./components/Feedback";
import Icon from "./components/Icons";
import Layout from "./components/Layout";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Search from "./pages/Search";
import Settings from "./pages/Settings";
import Watchlist from "./pages/Watchlist";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="boot-screen">
        <span className="brand-mark large">
          <Icon name="shield" size={30} />
        </span>
        <Spinner label="Starting THEA" />
      </div>
    );
  }

  if (!user) return <Login />;

  return (
    <AlertProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="watchlist" element={<Watchlist />} />
          <Route path="search" element={<Search />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AlertProvider>
  );
}
