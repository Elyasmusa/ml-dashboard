export interface TrainingRequest {
  model_name: string;
  epochs?: number;
  batch_size?: number;
  dataset_name?: string;
}

export interface VariantResult {
  variant: string;
  train_mae?: number;
  val_mae?: number;
  val_rmse?: number;
  val_r2?: number;
  accuracy?: number;
  epoch?: number;
  samples_total?: number;
  samples_train?: number;
  samples_val?: number;
  num_features?: number;
  num_locations?: number;
  num_products?: number;
  predictions_count?: number;
  predictions_file?: string;
  error?: string;
}

export interface TrainingResponse {
  job_id: string;
  status: string;
  epoch?: number;
  loss?: number;
  accuracy?: number;
  train_mae?: number;
  train_rmse?: number;
  val_mae?: number;
  val_rmse?: number;
  val_r2?: number;
  val_mape?: number;
  samples_total?: number;
  samples_train?: number;
  samples_val?: number;
  num_features?: number;
  num_locations?: number;
  num_products?: number;
  predictions_count?: number;
  predictions_file?: string;
  variant_results?: Record<string, VariantResult>;
  error?: string;
}

export interface PredictionRow {
  orderNumber: string;
  contactName: string;
  city: string;
  orderDate: string;
  predictedDaysToNext: number;
  predictedNextOrderDate: string;
  predictedEarliestDate?: string;
  predictedLatestDate?: string;
}

export interface ProductVariantResult {
  variant: string;
  train_mae?: number;
  val_mae?: number;
  val_rmse?: number;
  val_r2?: number;
  epoch?: number;
  samples_total?: number;
  samples_train?: number;
  samples_val?: number;
  num_features?: number;
  num_products?: number;
  predictions_count?: number;
  predictions_file?: string;
  error?: string;
}

export interface ProductTrainingResponse {
  job_id: string;
  status: string;
  variant_results?: Record<string, ProductVariantResult>;
  error?: string;
}

export interface ProductPredictionRow {
  orderNumber: string;
  contactName: string;
  city: string;
  orderDate: string;
  predictedProducts: Record<string, number>;
}

export interface CombinedPredictionRow {
  orderNumber: string;
  contactName: string;
  customerName: string;
  city: string;
  orderDate: string;
  predictedDaysToNext: number;
  predictedNextOrderDate: string;
  predictedEarliestDate?: string;
  predictedLatestDate?: string;
  predictedProducts: Record<string, number>;
}
