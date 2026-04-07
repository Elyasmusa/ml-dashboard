export interface ManufacturingTiming {
  prepBatchSize: number;
  prepPerBatch: number;
  bagBatchSize: number;
  bagPerBatch: number;
}

export interface RoastRequirement {
  roast: string;       // 'Light Roast' | 'Medium Roast' | 'Dark Roast'
  lbsPerUnit: number;  // lbs of raw roast consumed per finished unit
}

export interface ManufacturingCapacity {
  dailyHours: number;
  bufferMinutes: number;
}

export interface ManufacturingCoverage {
  phase1Threshold: number;
  exclusionThreshold: number;
}

export interface ManufacturingSettings {
  capacity: ManufacturingCapacity;
  coverage: ManufacturingCoverage;
  maxBatchMultiplier: number;
  dailyCaps: Record<string, number | null>;
  excluded: string[];
  roastRequirements: Record<string, RoastRequirement>;
  timings: Record<string, ManufacturingTiming>;
}

export interface StockSettings {
  thresholds: Record<string, number>;
}

export interface TrainingSettings {
  defaultEpochs: number;
  defaultBatchSize: number;
  learningRate: number;
  weightDecay: number;
  lrSchedulerPatience: number;
  lrSchedulerFactor: number;
  earlyStoppingPatience: number;
  trainValSplit: number;
  predictionTolerance: number;
  recencyWeightMin: number;
  recencyWeightMax: number;
  minR2ForRetraining: number;
  minAccuracyForRetraining: number;
  maxValTrainMaeRatio: number;
  finalLearningRate: number;
}

export interface DataPipelineSettings {
  minOrdersThreshold: number;
  smallOrderQtyThreshold: number;
  smallOrderCascadeThreshold: number;
  mergeWindowDays: number;
  dormantThresholdDays: number;
}

export interface SystemSettings {
  backendPollInterval: number;
  fullRefreshEveryCycles: number;
  apiPageSize: number;
  maxPagesPerFetch: number;
  productRefreshHour: number;
  frontendPollIntervalMs: number;
}

export interface AppSettings {
  stock: StockSettings;
  manufacturing: ManufacturingSettings;
  training: TrainingSettings;
  dataPipeline: DataPipelineSettings;
  system: SystemSettings;
}

export const DEFAULT_SETTINGS: AppSettings = {
  stock: {
    thresholds: {
      'Dark Roast Coffee (Whole)': 10,
      'Qishr': 10,
      'Juban Mix': 10,
      'Radaa Mix': 10,
      'Marib Mix': 10,
      'Sanaa Mix': 10,
      'Sunrise Socotra': 64,
      "Old City Sana'a": 64,
      'Queen Sheeba': 32,
      'Ancient Marib': 80,
      'Gate of Yemen': 80,
      'Mount Haraz': 128,
      'Cinnamon (Ground)': 5,
      'Cloves (Whole)': 5,
      'Ginger (Ground)': 5,
      'Cardamom (Ground)': 10,
      'Valley Juban': 64,
    },
  },
  manufacturing: {
    capacity: { dailyHours: 6, bufferMinutes: 15 },
    coverage: { phase1Threshold: 1.5, exclusionThreshold: 2.0 },
    maxBatchMultiplier: 2,
    dailyCaps: { 'Cardamom (Ground)': 30 },
    excluded: ['Medium Roast Coffee (Whole)'],
    roastRequirements: {
      'Gate of Yemen':             { roast: 'Dark Roast',   lbsPerUnit: 0.75 },
      'Sunrise Socotra':           { roast: 'Light Roast',  lbsPerUnit: 0.75 },
      'Mount Haraz':               { roast: 'Medium Roast', lbsPerUnit: 0.75 },
      'Dark Roast Coffee (Whole)': { roast: 'Dark Roast',   lbsPerUnit: 2.5  },
    },
    timings: {
      'Dark Roast Coffee (Whole)': { prepBatchSize: 10, prepPerBatch: 0,   bagBatchSize: 10, bagPerBatch: 15 },
      'Qishr':                     { prepBatchSize: 10, prepPerBatch: 0,   bagBatchSize: 10, bagPerBatch: 15 },
      'Juban Mix':                  { prepBatchSize: 10, prepPerBatch: 40,  bagBatchSize: 10, bagPerBatch: 15 },
      'Radaa Mix':                  { prepBatchSize: 10, prepPerBatch: 30,  bagBatchSize: 10, bagPerBatch: 15 },
      'Marib Mix':                  { prepBatchSize: 10, prepPerBatch: 30,  bagBatchSize: 10, bagPerBatch: 15 },
      'Sanaa Mix':                  { prepBatchSize: 10, prepPerBatch: 40,  bagBatchSize: 10, bagPerBatch: 15 },
      'Valley Juban':               { prepBatchSize: 32, prepPerBatch: 40,  bagBatchSize: 32, bagPerBatch: 60 },
      'Gate of Yemen':              { prepBatchSize: 32, prepPerBatch: 0,   bagBatchSize: 32, bagPerBatch: 60 },
      'Queen Sheeba':               { prepBatchSize: 32, prepPerBatch: 0,   bagBatchSize: 32, bagPerBatch: 60 },
      'Sunrise Socotra':            { prepBatchSize: 32, prepPerBatch: 0,   bagBatchSize: 32, bagPerBatch: 60 },
      'Mount Haraz':                { prepBatchSize: 32, prepPerBatch: 0,   bagBatchSize: 32, bagPerBatch: 60 },
      'Ancient Marib':              { prepBatchSize: 32, prepPerBatch: 30,  bagBatchSize: 32, bagPerBatch: 60 },
      "Old City Sana'a":            { prepBatchSize: 32, prepPerBatch: 40,  bagBatchSize: 32, bagPerBatch: 60 },
      'Cardamom (Ground)':          { prepBatchSize: 33, prepPerBatch: 180, bagBatchSize: 10, bagPerBatch: 15 },
      'Cinnamon (Ground)':          { prepBatchSize: 10, prepPerBatch: 0,   bagBatchSize: 10, bagPerBatch: 15 },
      'Cloves (Whole)':             { prepBatchSize: 10, prepPerBatch: 0,   bagBatchSize: 10, bagPerBatch: 15 },
      'Ginger (Ground)':            { prepBatchSize: 10, prepPerBatch: 0,   bagBatchSize: 10, bagPerBatch: 15 },
    },
  },
  training: {
    defaultEpochs: 10,
    defaultBatchSize: 32,
    learningRate: 0.001,
    weightDecay: 0.0001,
    lrSchedulerPatience: 5,
    lrSchedulerFactor: 0.5,
    earlyStoppingPatience: 10,
    trainValSplit: 0.8,
    predictionTolerance: 7,
    recencyWeightMin: 0.5,
    recencyWeightMax: 1.0,
    minR2ForRetraining: 0.0,
    minAccuracyForRetraining: 50,
    maxValTrainMaeRatio: 2.0,
    finalLearningRate: 0.0001,
  },
  dataPipeline: {
    minOrdersThreshold: 3,
    smallOrderQtyThreshold: 5,
    smallOrderCascadeThreshold: 0.25,
    mergeWindowDays: 3,
    dormantThresholdDays: 180,
  },
  system: {
    backendPollInterval: 60,
    fullRefreshEveryCycles: 60,
    apiPageSize: 100,
    maxPagesPerFetch: 100,
    productRefreshHour: 16,
    frontendPollIntervalMs: 60000,
  },
};
