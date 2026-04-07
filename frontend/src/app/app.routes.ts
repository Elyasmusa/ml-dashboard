import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full',
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./dashboard/pages/dashboard-home/dashboard-home.component').then(
        (m) => m.DashboardHomeComponent
      ),
  },
  {
    path: 'products',
    loadComponent: () =>
      import('./dashboard/pages/product-inventory/product-inventory.component').then(
        (m) => m.ProductInventoryComponent
      ),
  },
  {
    path: 'orders',
    loadComponent: () =>
      import('./dashboard/pages/order-information/order-information.component').then(
        (m) => m.OrderInformationComponent
      ),
  },
  {
    path: 'active-orders',
    loadComponent: () =>
      import('./dashboard/pages/active-orders/active-orders.component').then(
        (m) => m.ActiveOrdersComponent
      ),
  },
  {
    path: 'franchise-store-orders',
    loadComponent: () =>
      import('./dashboard/pages/franchise-store-orders/franchise-store-orders.component').then(
        (m) => m.FranchiseStoreOrdersComponent
      ),
  },
  {
    path: 'na-franchise-orders',
    loadComponent: () =>
      import('./dashboard/pages/na-franchise-orders/na-franchise-orders.component').then(
        (m) => m.NaFranchiseOrdersComponent
      ),
  },
  {
    path: 'online-orders',
    loadComponent: () =>
      import('./dashboard/pages/online-orders/online-orders.component').then(
        (m) => m.OnlineOrdersComponent
      ),
  },
  {
    path: 'franchise-location-orders',
    loadComponent: () =>
      import('./dashboard/pages/franchise-location-orders/franchise-location-orders.component').then(
        (m) => m.FranchiseLocationOrdersComponent
      ),
  },
  {
    path: 'franchise-order-matrix',
    loadComponent: () =>
      import('./dashboard/pages/franchise-order-matrix/franchise-order-matrix.component').then(
        (m) => m.FranchiseOrderMatrixComponent
      ),
  },
  {
    path: 'latest-franchise-orders',
    loadComponent: () =>
      import('./dashboard/pages/latest-franchise-orders/latest-franchise-orders.component').then(
        (m) => m.LatestFranchiseOrdersComponent
      ),
  },
  {
    path: 'franchise-product-matrix',
    loadComponent: () =>
      import('./dashboard/pages/franchise-product-matrix/franchise-product-matrix.component').then(
        (m) => m.FranchiseProductMatrixComponent
      ),
  },
  {
    path: 'latest-franchise-product-orders',
    loadComponent: () =>
      import('./dashboard/pages/latest-franchise-product-orders/latest-franchise-product-orders.component').then(
        (m) => m.LatestFranchiseProductOrdersComponent
      ),
  },
  {
    path: 'training-predictions',
    loadComponent: () =>
      import('./dashboard/pages/training-predictions/training-predictions.component').then(
        (m) => m.TrainingPredictionsComponent
      ),
  },
  {
    path: 'demand-forecast',
    loadComponent: () =>
      import('./dashboard/pages/demand-forecast/demand-forecast.component').then(
        (m) => m.DemandForecastComponent
      ),
  },
  {
    path: 'roast-inventory',
    loadComponent: () =>
      import('./dashboard/pages/roast-inventory/roast-inventory.component').then(
        (m) => m.RoastInventoryComponent
      ),
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./dashboard/pages/settings/settings.component').then(
        (m) => m.SettingsComponent
      ),
  },
];
