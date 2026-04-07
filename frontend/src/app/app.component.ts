import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

interface NavLink {
  path: string;
  label: string;
}

interface NavGroup {
  label: string;
  links: NavLink[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'ML Dashboard';

  navGroups: NavGroup[] = [
    { label: 'Dashboard', links: [{ path: '/dashboard', label: 'Dashboard' }] },
    { label: 'Orders', links: [
      { path: '/orders', label: 'Order Information' },
      { path: '/active-orders', label: 'Active Orders' },
      { path: '/franchise-store-orders', label: 'Franchise Store Orders' },
      { path: '/na-franchise-orders', label: 'NA Franchise Orders' },
      { path: '/online-orders', label: 'Online Orders' },
    ]},
    { label: 'Franchise Data', links: [
      { path: '/franchise-location-orders', label: 'Orders by Location' },
      { path: '/franchise-order-matrix', label: 'Order Matrix' },
      { path: '/latest-franchise-orders', label: 'Latest Orders' },
    ]},
    { label: 'ML / Predictions', links: [
      { path: '/training-predictions', label: 'Model Training' },
      { path: '/demand-forecast', label: 'Demand Forecast' },
      { path: '/franchise-product-matrix', label: 'Product Order Matrix' },
      { path: '/latest-franchise-product-orders', label: 'Latest Product Orders' },
    ]},
    { label: 'Products', links: [
      { path: '/products', label: 'Products' },
      { path: '/roast-inventory', label: 'Roast Inventory' },
    ]},
    { label: 'Configuration', links: [
      { path: '/settings', label: 'Settings' },
    ]},
  ];
}
