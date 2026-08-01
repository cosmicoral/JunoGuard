import { Dashboard } from "./Dashboard";
import { Landing } from "./Landing";

export default function App() {
  return window.location.pathname.startsWith("/dashboard") ? <Dashboard /> : <Landing />;
}
