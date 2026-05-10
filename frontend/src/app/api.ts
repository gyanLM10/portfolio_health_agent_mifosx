import { Injectable } from '@angular/core';

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

@Injectable({
  providedIn: 'root'
})
export class Api {
  private baseUrl = 'http://localhost:8000';

  async triggerScan(): Promise<any> {
    const res = await fetch(`${this.baseUrl}/scan`, { method: 'POST' });
    return res.json();
  }

  async getScanStatus(): Promise<ScanStatus> {
    const res = await fetch(`${this.baseUrl}/scan/status`);
    return res.json();
  }

  async getEscalations(): Promise<{ escalations: Escalation[] }> {
    const res = await fetch(`${this.baseUrl}/escalations`);
    return res.json();
  }

  async resolveEscalation(id: number, action: 'APPROVE' | 'DISMISS'): Promise<any> {
    const res = await fetch(`${this.baseUrl}/escalations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
    return res.json();
  }
}
