import { NgModule } from '@angular/core';
import { Routes, RouterModule } from '@angular/router';

const routes: Routes = [
  { path: '', redirectTo: 'portfolio-health', pathMatch: 'full' },
  {
    path: 'portfolio-health',
    loadChildren: () =>
      import('./portfolio-health/portfolio-health.module').then(m => m.PortfolioHealthModule)
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes, { useHash: true })],
  exports: [RouterModule]
})
export class AppRoutingModule {}
