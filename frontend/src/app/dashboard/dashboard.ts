import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Api, Escalation, ScanStatus } from '../api';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.html',
  styleUrls: ['./dashboard.css']
})
export class Dashboard implements OnInit, OnDestroy {
  escalations: Escalation[] = [];
  loading = false;
  scanStatus: ScanStatus | null = null;
  scanMessage = '';
  pollInterval: any = null;

  constructor(private api: Api) {}

  ngOnInit() {
    this.fetchEscalations();
    this.checkScanStatus();
  }

  ngOnDestroy() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }
  }

  async fetchEscalations() {
    this.loading = true;
    try {
      const data = await this.api.getEscalations();
      this.escalations = data.escalations;
    } catch (err) {
      console.error('Failed to fetch escalations:', err);
    } finally {
      this.loading = false;
    }
  }

  async checkScanStatus() {
    try {
      this.scanStatus = await this.api.getScanStatus();
    } catch (err) {
      console.error('Failed to check scan status:', err);
    }
  }

  async runScan() {
    this.scanMessage = 'Connecting to Rust MCP Server and dispatching agent...';
    try {
      await this.api.triggerScan();
      this.scanMessage = 'Agent is scanning the portfolio via the Rust MCP Server. This may take a moment...';

      // Poll for completion
      this.pollInterval = setInterval(async () => {
        await this.checkScanStatus();
        if (this.scanStatus && this.scanStatus.status !== 'RUNNING') {
          clearInterval(this.pollInterval);
          this.pollInterval = null;
          this.scanMessage = `Scan ${this.scanStatus.status}. Refreshing results...`;
          await this.fetchEscalations();
          setTimeout(() => { this.scanMessage = ''; }, 3000);
        }
      }, 2000);
    } catch (err) {
      this.scanMessage = 'Error connecting to the agent backend.';
    }
  }

  async approveEscalation(id: number) {
    try {
      await this.api.resolveEscalation(id, 'APPROVE');
      this.escalations = this.escalations.filter(e => e.id !== id);
    } catch (err) {
      console.error('Failed to approve escalation:', err);
    }
  }

  async dismissEscalation(id: number) {
    try {
      await this.api.resolveEscalation(id, 'DISMISS');
      this.escalations = this.escalations.filter(e => e.id !== id);
    } catch (err) {
      console.error('Failed to dismiss escalation:', err);
    }
  }

  getRiskClass(score: number): string {
    if (score >= 86) return 'critical';
    if (score >= 61) return 'high-risk';
    if (score >= 31) return 'medium-risk';
    return 'low-risk';
  }

  getRiskLabel(score: number): string {
    if (score >= 86) return 'CRITICAL';
    if (score >= 61) return 'HIGH';
    if (score >= 31) return 'MEDIUM';
    return 'LOW';
  }
}
