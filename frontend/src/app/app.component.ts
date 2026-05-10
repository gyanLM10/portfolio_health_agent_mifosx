import { Component } from '@angular/core';

@Component({
  selector: 'mifosx-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent {
  title = 'Portfolio Health Agent';

  navItems = [
    { label: 'Dashboard', icon: 'dashboard', route: '/portfolio-health/dashboard' },
  ];
}
