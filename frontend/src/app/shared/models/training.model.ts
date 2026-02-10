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
