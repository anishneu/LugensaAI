import "leaflet/dist/leaflet.css";
import { Route, Routes } from "react-router-dom";
import "./App.css";
import { LandingPage } from "./pages/LandingPage";
import { ResearchWorkspace } from "./pages/ResearchWorkspace";

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/app" element={<ResearchWorkspace />} />
    </Routes>
  );
}

export default App;
