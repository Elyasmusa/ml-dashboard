import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { timer } from 'rxjs';
import { switchMap, takeWhile } from 'rxjs/operators';
import { TrainingService } from '../../../shared/services/training.service';
import {
  TrainingResponse,
  VariantResult,
  ProductTrainingResponse,
  ProductVariantResult,
  CombinedPredictionRow,
} from '../../../shared/models/training.model';
import { formatCity, formatDate, buildProductEntries } from '../../../shared/utils/prediction.utils';

@Component({
  selector: 'app-training-predictions',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './training-predictions.component.html',
  styleUrl: './training-predictions.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TrainingPredictionsComponent implements OnInit {
  // Order training state
  training = false;
  trainingError = '';
  trainingResult: TrainingResponse | null = null;

  // Variant tabs
  readonly variantNames = ['base', 'min_orders', 'year', 'min_orders_year'];
  readonly variantLabels: Record<string, string> = {
    base: 'Base',
    min_orders: 'Min Orders (3+)',
    year: 'Year Feature',
    min_orders_year: 'Min Orders + Year',
  };
  activeVariant = 'base';
  variantResults: Partial<Record<string, VariantResult>> = {};

  // Combined predictions state (order dates + products)
  combinedPredictions: Record<string, CombinedPredictionRow[]> = {};
  combinedLoading = false;

  // Product training state
  productTraining = false;
  productTrainingError = '';
  productTrainingResult: ProductTrainingResponse | null = null;

  // Product variant state
  productVariantResults: Record<string, ProductVariantResult> = {};

  private readonly destroyRef = inject(DestroyRef);
  private readonly cdr = inject(ChangeDetectorRef);

  constructor(private trainingService: TrainingService) {}

  ngOnInit(): void {
    this.loadAllCombinedPredictions();
  }

  // ── Order Training ──────────────────────────────────────────

  trainModel(): void {
    this.training = true;
    this.trainingError = '';
    this.trainingResult = null;

    this.trainingService.startTraining({
      model_name: 'order_predictor',
      epochs: 100,
      batch_size: 32,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.pollTrainingStatus(res.job_id);
      },
      error: (err) => {
        this.trainingError = 'Failed to start training';
        this.training = false;
        this.cdr.markForCheck();
        console.error('Training start error:', err);
      },
    });
  }

  private pollTrainingStatus(jobId: string): void {
    timer(0, 2000).pipe(
      switchMap(() => this.trainingService.getStatus(jobId)),
      takeWhile(res => res.status !== 'completed' && res.status !== 'failed', true),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (res) => {
        if (res.status === 'completed' || res.status === 'failed') {
          this.training = false;
          if (res.status === 'completed') {
            this.trainingResult = res;
            if (res.variant_results) {
              this.variantResults = res.variant_results;
            }
            this.loadAllCombinedPredictions();
          } else {
            this.trainingError = res.error || 'Training failed';
          }
          this.cdr.markForCheck();
        }
      },
      error: () => {
        this.training = false;
        this.trainingError = 'Failed to poll training status';
        this.cdr.markForCheck();
      },
    });
  }

  selectVariant(variant: string): void {
    this.activeVariant = variant;
  }

  get activeResult(): VariantResult | null {
    return this.variantResults[this.activeVariant] || null;
  }

  get activePredictions(): CombinedPredictionRow[] {
    return this.combinedPredictions[this.activeVariant] || [];
  }

  private loadAllCombinedPredictions(): void {
    this.combinedLoading = true;
    let remaining = this.variantNames.length;
    for (const variant of this.variantNames) {
      this.trainingService.getCombinedPredictions(variant).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (res) => {
          this.combinedPredictions[variant] = res.data || [];
          remaining--;
          if (remaining <= 0) this.combinedLoading = false;
          this.cdr.markForCheck();
        },
        error: () => {
          this.combinedPredictions[variant] = [];
          remaining--;
          if (remaining <= 0) this.combinedLoading = false;
          this.cdr.markForCheck();
        },
      });
    }
  }

  // ── Product Training ──────────────────────────────────────────

  trainProductModel(): void {
    this.productTraining = true;
    this.productTrainingError = '';
    this.productTrainingResult = null;

    this.trainingService.startProductTraining({
      model_name: 'product_predictor',
      epochs: 100,
      batch_size: 32,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.pollProductTrainingStatus(res.job_id);
      },
      error: (err) => {
        this.productTrainingError = 'Failed to start product training';
        this.productTraining = false;
        this.cdr.markForCheck();
        console.error('Product training start error:', err);
      },
    });
  }

  private pollProductTrainingStatus(jobId: string): void {
    timer(0, 2000).pipe(
      switchMap(() => this.trainingService.getProductStatus(jobId)),
      takeWhile(res => res.status !== 'completed' && res.status !== 'failed', true),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (res) => {
        if (res.status === 'completed' || res.status === 'failed') {
          this.productTraining = false;
          if (res.status === 'completed') {
            this.productTrainingResult = res;
            if (res.variant_results) {
              this.productVariantResults = res.variant_results;
            }
            this.loadAllCombinedPredictions();
          } else {
            this.productTrainingError = res.error || 'Product training failed';
          }
          this.cdr.markForCheck();
        }
      },
      error: () => {
        this.productTraining = false;
        this.productTrainingError = 'Failed to poll product training status';
        this.cdr.markForCheck();
      },
    });
  }

  get activeProductResult(): ProductVariantResult | null {
    return this.productVariantResults[this.activeVariant] || null;
  }

  // ── Helpers ──────────────────────────────────────────────────

  getProductEntries(row: CombinedPredictionRow): { name: string; qty: number }[] {
    return buildProductEntries(row);
  }

  formatCity(slug: string): string {
    return formatCity(slug);
  }

  formatDate(date?: string): string {
    return formatDate(date);
  }
}
