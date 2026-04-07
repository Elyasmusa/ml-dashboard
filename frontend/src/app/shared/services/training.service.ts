import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  TrainingRequest,
  TrainingResponse,
  PredictionRow,
  ProductVariantResult,
  ProductTrainingResponse,
  ProductPredictionRow,
  CombinedPredictionRow,
} from '../models/training.model';

// Re-export so existing imports from this path keep working.
export type {
  TrainingRequest,
  TrainingResponse,
  VariantResult,
  PredictionRow,
  ProductVariantResult,
  ProductTrainingResponse,
  ProductPredictionRow,
  CombinedPredictionRow,
} from '../models/training.model';

@Injectable({
  providedIn: 'root',
})
export class TrainingService {
  constructor(private api: ApiService) {}

  startTraining(request: TrainingRequest): Observable<TrainingResponse> {
    return this.api.post<TrainingResponse>('/training/', request);
  }

  getStatus(jobId: string): Observable<TrainingResponse> {
    return this.api.get<TrainingResponse>(`/training/${jobId}`);
  }

  getPredictions(): Observable<{ data: PredictionRow[]; totalCount: number }> {
    return this.api.get<{ data: PredictionRow[]; totalCount: number }>('/inflow/predicted-next-order-date');
  }

  getVariantPredictions(variant: string): Observable<{ data: PredictionRow[]; totalCount: number }> {
    return this.api.get<{ data: PredictionRow[]; totalCount: number }>(
      `/inflow/predicted-next-order-date/${variant}`
    );
  }

  startProductTraining(request: TrainingRequest): Observable<ProductTrainingResponse> {
    return this.api.post<ProductTrainingResponse>('/training/products/', request);
  }

  getProductStatus(jobId: string): Observable<ProductTrainingResponse> {
    return this.api.get<ProductTrainingResponse>(`/training/products/${jobId}`);
  }

  getProductVariantPredictions(variant: string): Observable<{ data: ProductPredictionRow[]; totalCount: number }> {
    return this.api.get<{ data: ProductPredictionRow[]; totalCount: number }>(
      `/inflow/predicted-next-products/${variant}`
    );
  }

  getCombinedPredictions(variant: string): Observable<{ data: CombinedPredictionRow[]; totalCount: number }> {
    return this.api.get<{ data: CombinedPredictionRow[]; totalCount: number }>(
      `/inflow/predicted-orderdate-with-products/${variant}`
    );
  }
}
