import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface TrainingRequest {
  model_name: string;
  epochs?: number;
  batch_size?: number;
  dataset_name?: string;
}

export interface TrainingResponse {
  job_id: string;
  status: string;
  epoch?: number;
  loss?: number;
  accuracy?: number;
}

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
}
