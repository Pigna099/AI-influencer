import { useState, useEffect } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import Login from "./components/Login";
import Playground from "./components/Playground";

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
      <Route path="/" element={<Playground onLogout={handleLogout} />} />
    </Routes>
  );
}

export default App;
