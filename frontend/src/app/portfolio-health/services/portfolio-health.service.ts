import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Escalation, ScanStatus, Decision, PortfolioStats } from '../models/portfolio-health.models';

@Injectable({
  providedIn: 'root'
})
export class PortfolioHealthService {

  private baseUrl = environment.portfolioHealthApiUrl;

  constructor(private http: HttpClient) {}

  triggerScan(): Observable<any> {
    return this.http.post(`${this.baseUrl}/scan`, {});
  }

  getScanStatus(): Observable<ScanStatus> {
    return this.http.get<ScanStatus>(`${this.baseUrl}/scan/status`);
  }

  getEscalations(): Observable<{ escalations: Escalation[] }> {
    return this.http.get<{ escalations: Escalation[] }>(`${this.baseUrl}/escalations`);
  }

  getAllEscalations(): Observable<{ escalations: Escalation[] }> {
    return this.http.get<{ escalations: Escalation[] }>(`${this.baseUrl}/escalations/all`);
  }

  resolveEscalation(id: number, action: 'APPROVE' | 'DISMISS'): Observable<any> {
    return this.http.patch(`${this.baseUrl}/escalations/${id}`, { action });
  }

  getDecisions(limit: number = 100): Observable<{ decisions: Decision[], count: number }> {
    return this.http.get<{ decisions: Decision[], count: number }>(`${this.baseUrl}/decisions`, {
      params: { limit: limit.toString() }
    });
  }

  getStats(): Observable<PortfolioStats> {
    return this.http.get<PortfolioStats>(`${this.baseUrl}/stats`);
  }

  assessRisk(profile: any): Observable<any> {
    return this.http.post(`${this.baseUrl}/assess`, profile);
  }

  getHealth(): Observable<any> {
    return this.http.get(`${this.baseUrl}/health`);
  }
}
