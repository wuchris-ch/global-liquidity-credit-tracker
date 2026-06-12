import { redirect } from "next/navigation";

/** Risk-by-Regime merged into The Playbook. */
export default function RiskRedirect() {
  redirect("/playbook");
}
