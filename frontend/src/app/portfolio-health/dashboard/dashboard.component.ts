import { Component, OnInit, OnDestroy } from '@angular/core';
import { PortfolioHealthService } from '../services/portfolio-health.service';
import { Escalation, ScanStatus, Decision, PortfolioStats } from '../models/portfolio-health.models';
import { interval, Subscription } from 'rxjs';
import { switchMap, takeWhile } from 'rxjs/operators';

@Component({
  selector: 'mifosx-portfolio-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit, OnDestroy {

  escalations: Escalation[] = [];
  decisions: Decision[] = [];
  stats: PortfolioStats | null = null;
  scanStatus: ScanStatus | null = null;
  scanMessage = '';
  loading = false;
  backendOnline = false;

  displayedColumns: string[] = ['timestamp', 'loan_id', 'client_name', 'risk_level', 'risk_score', 'action_taken'];

  private pollSub: Subscription | null = null;

  constructor(private portfolioHealthService: PortfolioHealthService) {}

  ngOnInit(): void {
    this.checkBackendHealth();
    this.fetchEscalations();
    this.fetchStats();
    this.fetchDecisions();
    this.checkScanStatus();
  }

  ngOnDestroy(): void {
    if (this.pollSub) {
      this.pollSub.unsubscribe();
    }
  }

  checkBackendHealth(): void {
    this.portfolioHealthService.getHealth().subscribe({
      next: () => { this.backendOnline = true; },
      error: () => { this.backendOnline = false; }
    });
  }

  fetchEscalations(): void {
    this.loading = true;
    this.portfolioHealthService.getEscalations().subscribe({
      next: (data) => {
        this.escalations = data.escalations;
        this.loading = false;
      },
      error: () => { this.loading = false; }
    });
  }

  fetchStats(): void {
    this.portfolioHealthService.getStats().subscribe({
      next: (data) => { this.stats = data; },
      error: () => {}
    });
  }

  fetchDecisions(): void {
    this.portfolioHealthService.getDecisions(20).subscribe({
      next: (data) => { this.decisions = data.decisions; },
      error: () => {}
    });
  }

  checkScanStatus(): void {
    this.portfolioHealthService.getScanStatus().subscribe({
      next: (status) => { this.scanStatus = status; },
      error: () => {}
    });
  }

  runScan(): void {
    this.scanMessage = 'Connecting to Rust MCP Server and dispatching agent...';
    this.portfolioHealthService.triggerScan().subscribe({
      next: () => {
        this.scanMessage = 'Agent is scanning the portfolio via the Rust MCP Server...';
        this.startPolling();
      },
      error: () => {
        this.scanMessage = 'Error connecting to the agent backend.';
      }
    });
  }

  private startPolling(): void {
    this.pollSub = interval(3000).pipe(
      switchMap(() => this.portfolioHealthService.getScanStatus()),
      takeWhile((status) => status.status === 'RUNNING', true)
    ).subscribe({
      next: (status) => {
        this.scanStatus = status;
        if (status.status !== 'RUNNING') {
          this.scanMessage = `Scan ${status.status}. Refreshing results...`;
          this.fetchEscalations();
          this.fetchStats();
          this.fetchDecisions();
          setTimeout(() => { this.scanMessage = ''; }, 3000);
        }
      }
    });
  }

  approveEscalation(id: number): void {
    this.portfolioHealthService.resolveEscalation(id, 'APPROVE').subscribe({
      next: () => {
        this.escalations = this.escalations.filter(e => e.id !== id);
        this.fetchStats();
      }
    });
  }

  dismissEscalation(id: number): void {
    this.portfolioHealthService.resolveEscalation(id, 'DISMISS').subscribe({
      next: () => {
        this.escalations = this.escalations.filter(e => e.id !== id);
        this.fetchStats();
      }
    });
  }

  getRiskClass(score: number): string {
    if (score >= 75) { return 'critical'; }
    if (score >= 50) { return 'high'; }
    if (score >= 25) { return 'medium'; }
    return 'low';
  }

  getRiskLabel(score: number): string {
    if (score >= 75) { return 'CRITICAL'; }
    if (score >= 50) { return 'HIGH'; }
    if (score >= 25) { return 'MEDIUM'; }
    return 'LOW';
  }
}
