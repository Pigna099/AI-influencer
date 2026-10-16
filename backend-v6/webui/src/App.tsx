import { useState, useEffect } from "react";
import { Routes, Route, useLocation, useNavigate } from "react-router-dom";
import Login from "./components/Login";
import HomePage from "./components/HomePage";
import Playground from "./components/Playground";
import ImagePlayground from "./components/ImagePlayground";
import DatasetPlayground from "./components/DatasetPlayground";
import LoraPlayground from "./components/LoraPlayground";
import VideoPlayground from "./components/VideoPlayground";
import JobsPage from "./components/JobsPage";

const SESSION_HOURS = 12;

function RouteScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document
      .querySelectorAll(".home-scroll, .library-scroll, .message-scroll, .character-rail, .inspector, .lora-content, .main-panel")
      .forEach(element => element.scrollTo({ top: 0 }));
  }, [pathname]);
  return null;
}

function App() {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const storedKey = sessionStorage.getItem("api_key");
    const storedAt = Number(sessionStorage.getItem("api_key_at") || 0);
    const expired = !storedAt || Date.now() - storedAt > SESSION_HOURS * 3600 * 1000;
    if (storedKey && !expired) {
      setApiKey(storedKey);
    } else {
      sessionStorage.removeItem("api_key");
      sessionStorage.removeItem("api_key_at");
    }
  }, []);

  const handleLogin = async (key: string) => {
    sessionStorage.setItem("api_key", key);
    sessionStorage.setItem("api_key_at", String(Date.now()));
    setApiKey(key);
    navigate("/");
  };

  const handleLogout = () => {
    sessionStorage.removeItem("api_key");
    sessionStorage.removeItem("api_key_at");
    setApiKey(null);
    navigate("/");
  };

  if (!apiKey) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <>
      <RouteScrollReset />
      <Routes>
      <Route path="/" element={<HomePage onLogout={handleLogout} />} />
      <Route path="/chat" element={<Playground onLogout={handleLogout} />} />
      <Route path="/images" element={<ImagePlayground onLogout={handleLogout} />} />
      <Route path="/dataset" element={<DatasetPlayground onLogout={handleLogout} />} />
      <Route path="/loras" element={<LoraPlayground onLogout={handleLogout} />} />
      <Route path="/video" element={<VideoPlayground onLogout={handleLogout} />} />
      <Route path="/jobs" element={<JobsPage onLogout={handleLogout} />} />
      </Routes>
    </>
  );
}

export default App;
