from __future__ import annotations

from pydantic import BaseModel, Field


class ManufacturingTiming(BaseModel):
    prepBatchSize: int = 10
    prepPerBatch: int = 0
    bagBatchSize: int = 10
    bagPerBatch: int = 10


class RoastRequirement(BaseModel):
    roast: str           # "Light Roast" | "Medium Roast" | "Dark Roast"
    lbsPerUnit: float    # lbs of raw roast consumed per finished unit


class ManufacturingCapacity(BaseModel):
    dailyHours: float = 6.0
    bufferMinutes: int = 15


class ManufacturingCoverage(BaseModel):
    phase1Threshold: float = 1.5
    exclusionThreshold: float = 2.0


class ManufacturingSettings(BaseModel):
    capacity: ManufacturingCapacity = Field(default_factory=ManufacturingCapacity)
    coverage: ManufacturingCoverage = Field(default_factory=ManufacturingCoverage)
    maxBatchMultiplier: int = 2
    dailyCaps: dict[str, int | None] = Field(
        default_factory=lambda: {"Cardamom (Ground)": 30}
    )
    excluded: list[str] = Field(
        default_factory=lambda: ["Medium Roast Coffee (Whole)"]
    )
    roastRequirements: dict[str, RoastRequirement] = Field(
        default_factory=lambda: {
            "Gate of Yemen":             RoastRequirement(roast="Dark Roast",   lbsPerUnit=0.75),
            "Sunrise Socotra":           RoastRequirement(roast="Light Roast",  lbsPerUnit=0.75),
            "Mount Haraz":               RoastRequirement(roast="Medium Roast", lbsPerUnit=0.75),
            "Dark Roast Coffee (Whole)": RoastRequirement(roast="Dark Roast",   lbsPerUnit=2.5),
        }
    )
    timings: dict[str, ManufacturingTiming] = Field(
        default_factory=lambda: {
            "Dark Roast Coffee (Whole)": ManufacturingTiming(prepBatchSize=10, prepPerBatch=0,   bagBatchSize=10, bagPerBatch=15),
            "Qishr":                     ManufacturingTiming(prepBatchSize=10, prepPerBatch=0,   bagBatchSize=10, bagPerBatch=15),
            "Juban Mix":                 ManufacturingTiming(prepBatchSize=10, prepPerBatch=40,  bagBatchSize=10, bagPerBatch=15),
            "Radaa Mix":                 ManufacturingTiming(prepBatchSize=10, prepPerBatch=30,  bagBatchSize=10, bagPerBatch=15),
            "Marib Mix":                 ManufacturingTiming(prepBatchSize=10, prepPerBatch=30,  bagBatchSize=10, bagPerBatch=15),
            "Sanaa Mix":                 ManufacturingTiming(prepBatchSize=10, prepPerBatch=40,  bagBatchSize=10, bagPerBatch=15),
            "Valley Juban":              ManufacturingTiming(prepBatchSize=32, prepPerBatch=40,  bagBatchSize=32, bagPerBatch=60),
            "Gate of Yemen":             ManufacturingTiming(prepBatchSize=32, prepPerBatch=0,   bagBatchSize=32, bagPerBatch=60),
            "Queen Sheeba":              ManufacturingTiming(prepBatchSize=32, prepPerBatch=0,   bagBatchSize=32, bagPerBatch=60),
            "Sunrise Socotra":           ManufacturingTiming(prepBatchSize=32, prepPerBatch=0,   bagBatchSize=32, bagPerBatch=60),
            "Mount Haraz":               ManufacturingTiming(prepBatchSize=32, prepPerBatch=0,   bagBatchSize=32, bagPerBatch=60),
            "Ancient Marib":             ManufacturingTiming(prepBatchSize=32, prepPerBatch=30,  bagBatchSize=32, bagPerBatch=60),
            "Old City Sana'a":           ManufacturingTiming(prepBatchSize=32, prepPerBatch=40,  bagBatchSize=32, bagPerBatch=60),
            "Cardamom (Ground)":         ManufacturingTiming(prepBatchSize=33, prepPerBatch=180, bagBatchSize=10, bagPerBatch=15),
            "Cinnamon (Ground)":         ManufacturingTiming(prepBatchSize=10, prepPerBatch=0,   bagBatchSize=10, bagPerBatch=15),
            "Cloves (Whole)":            ManufacturingTiming(prepBatchSize=10, prepPerBatch=0,   bagBatchSize=10, bagPerBatch=15),
            "Ginger (Ground)":           ManufacturingTiming(prepBatchSize=10, prepPerBatch=0,   bagBatchSize=10, bagPerBatch=15),
        }
    )


class StockSettings(BaseModel):
    thresholds: dict[str, int] = Field(
        default_factory=lambda: {
            "Dark Roast Coffee (Whole)": 10,
            "Qishr":                     10,
            "Juban Mix":                 10,
            "Radaa Mix":                 10,
            "Marib Mix":                 10,
            "Sanaa Mix":                 10,
            "Sunrise Socotra":           64,
            "Old City Sana'a":           64,
            "Queen Sheeba":              32,
            "Ancient Marib":             80,
            "Gate of Yemen":             80,
            "Mount Haraz":               128,
            "Cinnamon (Ground)":         5,
            "Cloves (Whole)":            5,
            "Ginger (Ground)":           5,
            "Cardamom (Ground)":         10,
            "Valley Juban":              64,
        }
    )


class TrainingSettings(BaseModel):
    defaultEpochs: int = 10
    defaultBatchSize: int = 32
    learningRate: float = 0.001
    weightDecay: float = 1e-4
    lrSchedulerPatience: int = 5
    lrSchedulerFactor: float = 0.5
    earlyStoppingPatience: int = 10
    trainValSplit: float = 0.8
    predictionTolerance: float = 7.0
    recencyWeightMin: float = 0.5
    recencyWeightMax: float = 1.0
    minR2ForRetraining: float = 0.0
    minAccuracyForRetraining: float = 50.0
    maxValTrainMaeRatio: float = 2.0
    finalLearningRate: float = 0.0001


class DataPipelineSettings(BaseModel):
    minOrdersThreshold: int = 3
    smallOrderQtyThreshold: int = 5
    smallOrderCascadeThreshold: float = 0.25
    mergeWindowDays: int = 3
    dormantThresholdDays: int = 180


class SystemSettings(BaseModel):
    backendPollInterval: int = 60
    fullRefreshEveryCycles: int = 60
    apiPageSize: int = 100
    maxPagesPerFetch: int = 100
    productRefreshHour: int = 16
    frontendPollIntervalMs: int = 60000


class AppSettings(BaseModel):
    stock: StockSettings = Field(default_factory=StockSettings)
    manufacturing: ManufacturingSettings = Field(default_factory=ManufacturingSettings)
    training: TrainingSettings = Field(default_factory=TrainingSettings)
    dataPipeline: DataPipelineSettings = Field(default_factory=DataPipelineSettings)
    system: SystemSettings = Field(default_factory=SystemSettings)
