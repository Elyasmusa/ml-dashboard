import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface ModelInfo {
  name: string;
  description: string;
  input_shape?: number[];
  output_shape?: number[];
  created_at?: string;
  file_path?: string;
}

@Injectable({
  providedIn: 'root',
})
export class ModelService {
  constructor(private api: ApiService) {}

  listModels(): Observable<ModelInfo[]> {
    return this.api.get<ModelInfo[]>('/models/');
  }

  getModel(name: string): Observable<ModelInfo> {
    return this.api.get<ModelInfo>(`/models/${name}`);
  }
}
