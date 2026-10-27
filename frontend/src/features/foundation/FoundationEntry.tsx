import LoginScreen from "../../LoginScreen";
import { supabase } from "../../lib/supabase";
import { foundationApi } from "./runtime";
import FoundationPage from "./FoundationPage";
import "./foundation.css";

export default function FoundationEntry() {
  return <FoundationPage auth={supabase.auth} api={foundationApi} login={<LoginScreen />} pathname={window.location.pathname} />;
}
