import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService } from '../../../shared/services/inflow.service';
import { FranchiseLocationCity, FranchiseLocationOrderRow } from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-franchise-location-orders',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './franchise-location-orders.component.html',
  styleUrl: './franchise-location-orders.component.scss',
})
export class FranchiseLocationOrdersComponent implements OnInit {
  cities: FranchiseLocationCity[] = [];
  selectedCitySlug: string | null = null;
  orders: FranchiseLocationOrderRow[] = [];

  loadingCities = true;
  loadingOrders = false;
  citiesError: string | null = null;
  ordersError: string | null = null;

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadCities();
  }

  loadCities(): void {
    this.loadingCities = true;
    this.citiesError = null;

    this.inflowService.listFranchiseLocationCities().subscribe({
      next: (response) => {
        this.cities = response.data || [];
        this.loadingCities = false;
        if (this.cities.length > 0 && !this.selectedCitySlug) {
          this.onCitySelect(this.cities[0].citySlug);
        }
      },
      error: (err) => {
        this.citiesError =
          err.status === 404
            ? 'Location data not yet available. Please visit the Order Information page first to load detailed order data.'
            : `Failed to load cities: ${err.message || 'Unknown error'}`;
        this.loadingCities = false;
      },
    });
  }

  onCitySelect(citySlug: string): void {
    if (!citySlug) return;
    this.selectedCitySlug = citySlug;
    this.loadOrders(citySlug);
  }

  loadOrders(citySlug: string): void {
    this.loadingOrders = true;
    this.ordersError = null;
    this.orders = [];

    this.inflowService.getFranchiseLocationOrders(citySlug).subscribe({
      next: (response) => {
        this.orders = this.sortByOrderDate(response.data || []);
        this.loadingOrders = false;
      },
      error: (err) => {
        this.ordersError = `Failed to load orders: ${err.message || 'Unknown error'}`;
        this.loadingOrders = false;
      },
    });
  }

  getSelectedCityName(): string {
    const city = this.cities.find((c) => c.citySlug === this.selectedCitySlug);
    return city?.displayName ?? this.selectedCitySlug ?? '';
  }

  sortByOrderDate(rows: FranchiseLocationOrderRow[]): FranchiseLocationOrderRow[] {
    return [...rows].sort((a, b) => {
      const dateA = a.orderDate ? new Date(a.orderDate).getTime() : 0;
      const dateB = b.orderDate ? new Date(b.orderDate).getTime() : 0;
      return dateB - dateA;
    });
  }

  formatDate(dateString: string | undefined | null): string {
    if (!dateString) return '-';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  }

  formatCurrency(value: number | string | undefined | null): string {
    if (value == null) return '-';
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '-' : '$' + num.toFixed(2);
  }

}
