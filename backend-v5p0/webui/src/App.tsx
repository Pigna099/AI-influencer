import { useState, useEffect } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import Login from "./components/Login";
import HomePage from "./components/HomePage";
import Playground from "./components/Playground";
import ImagePlayground from "./components/ImagePlayground";
import DatasetPlayground from "./components/DatasetPlayground";
import LoraPlayground from "./components/LoraPlayground";

function App() {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const storedKey = sessionStorage.getItem("api_key");
    if (storedKey) {
      setApiKey(storedKey);
    }
  }, []);

  const handleLogin = async (key: string) => {
    sessionStorage.setItem("api_key", key);
    setApiKey(key);
    navigate("/");
  };

  const handleLogout = () => {
    sessionStorage.removeItem("api_key");
    setApiKey(null);
    navigate("/");
  };

  if (!apiKey) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <Routes>
      <Route path="/" element={<HomePage onLogout={handleLogout} />} />
      <Route path="/chat" element={<Playground onLogout={handleLogout} />} />
      <Route path="/images" element={<ImagePlayground onLogout={handleLogout} />} />
      <Route path="/dataset" element={<DatasetPlayground onLogout={handleLogout} />} />
      <Route path="/loras" element={<LoraPlayground onLogout={handleLogout} />} />
    </Routes>
  );
}

export default App;
