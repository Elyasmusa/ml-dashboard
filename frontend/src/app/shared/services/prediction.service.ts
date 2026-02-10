import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface PredictionRequest {
  model_name: string;
  input_data: number[][];
}

export interface PredictionResponse {
  model_name: string;
  predictions: number[];
}

@Injectable({
  providedIn: 'root',
})
export class PredictionService {
  constructor(private api: ApiService) {}

  predict(request: PredictionRequest): Observable<PredictionResponse> {
    return this.api.post<PredictionResponse>('/predictions/', request);
  }
}
