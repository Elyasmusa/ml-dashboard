export interface PredictionRequest {
  model_name: string;
  input_data: number[][];
}

export interface PredictionResponse {
  model_name: string;
  predictions: number[];
}
