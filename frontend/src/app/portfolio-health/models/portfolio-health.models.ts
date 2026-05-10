export interface Escalation {
  id: number;
  account_id: string;
  client_name: string;
  risk_score: number;
  explanation: string;
  status: string;
  created_at?: string;
}

export interface ScanStatus {
  id?: number;
  status: string;
  started_at?: string;
  completed_at?: string;
}

export interface Decision {
  id: number;
  timestamp: string;
  scan_id: string;
  loan_id: number;
  client_id: number;
  client_name: string;
  risk_score: number;
  risk_level: string;
  action_taken: string;
  agent_reasoning: string;
  factor_breakdown?: string;
}

export interface PortfolioStats {
  total_decisions: number;
  by_risk_level: { [key: string]: number };
  by_action: { [key: string]: number };
  average_risk_score: number;
  escalation_approval_rate: string;
}
