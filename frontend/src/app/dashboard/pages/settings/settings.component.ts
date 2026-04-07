import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SettingsService } from '../../../shared/services/settings.service';
import {
  AppSettings,
  DEFAULT_SETTINGS,
  ManufacturingTiming,
  RoastRequirement,
} from '../../../shared/models/settings.model';

type Tab = 'stock' | 'manufacturing' | 'training' | 'pipeline' | 'system';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent implements OnInit {
  activeTab: Tab = 'stock';
  saving = false;
  saveSuccess = false;
  saveError = '';
  loading = true;

  /** Deep-cloned working copy — mutated by the form, never the live settings. */
  draft!: AppSettings;

  /** Products that appear in stock thresholds (ordered for display). */
  readonly stockProducts = [
    'Dark Roast Coffee (Whole)',
    'Qishr',
    'Juban Mix',
    'Radaa Mix',
    'Marib Mix',
    'Sanaa Mix',
    'Sunrise Socotra',
    "Old City Sana'a",
    'Queen Sheeba',
    'Ancient Marib',
    'Gate of Yemen',
    'Mount Haraz',
    'Cinnamon (Ground)',
    'Cloves (Whole)',
    'Ginger (Ground)',
    'Cardamom (Ground)',
    'Valley Juban',
  ];

  /** Products that have manufacturing timings. */
  readonly mfgProducts = [
    'Dark Roast Coffee (Whole)',
    'Qishr',
    'Juban Mix',
    'Radaa Mix',
    'Marib Mix',
    'Sanaa Mix',
    'Valley Juban',
    'Gate of Yemen',
    'Queen Sheeba',
    'Sunrise Socotra',
    'Mount Haraz',
    'Ancient Marib',
    "Old City Sana'a",
    'Cardamom (Ground)',
    'Cinnamon (Ground)',
    'Cloves (Whole)',
    'Ginger (Ground)',
  ];

  /** Products that have a daily qty cap (others have none). */
  readonly cappedProducts = ['Cardamom (Ground)'];

  /** Products that can have a roast raw-material requirement. */
  readonly roastProducts = [
    'Gate of Yemen',
    'Sunrise Socotra',
    'Mount Haraz',
    'Dark Roast Coffee (Whole)',
    'Queen Sheeba',
    'Ancient Marib',
    "Old City Sana'a",
    'Valley Juban',
    'Qishr',
  ];

  /** Available roast types. */
  readonly roastTypes = ['Light Roast', 'Medium Roast', 'Dark Roast'];

  constructor(private settingsService: SettingsService) {}

  ngOnInit(): void {
    this.settingsService.load().subscribe({
      next: (s) => {
        this.draft = this.deepClone(s);
        this.loading = false;
      },
      error: () => {
        this.draft = this.deepClone(DEFAULT_SETTINGS);
        this.loading = false;
      },
    });
  }

  selectTab(tab: Tab): void {
    this.activeTab = tab;
  }

  getThreshold(name: string): number {
    return this.draft.stock.thresholds[name] ?? 0;
  }

  setThreshold(name: string, value: number): void {
    this.draft.stock.thresholds[name] = value;
  }

  getTiming(name: string): ManufacturingTiming {
    return (
      this.draft.manufacturing.timings[name] ?? {
        prepBatchSize: 0,
        prepPerBatch: 0,
        bagBatchSize: 0,
        bagPerBatch: 0,
      }
    );
  }

  setTiming(name: string, field: keyof ManufacturingTiming, value: number): void {
    if (!this.draft.manufacturing.timings[name]) {
      this.draft.manufacturing.timings[name] = {
        prepBatchSize: 0,
        prepPerBatch: 0,
        bagBatchSize: 0,
        bagPerBatch: 0,
      };
    }
    this.draft.manufacturing.timings[name][field] = value;
  }

  getDailyCap(name: string): number | null {
    const v = this.draft.manufacturing.dailyCaps[name];
    return v !== undefined ? v : null;
  }

  setDailyCap(name: string, value: string): void {
    const n = Number(value);
    this.draft.manufacturing.dailyCaps[name] = isNaN(n) ? null : n;
  }

  getRoastReq(name: string): RoastRequirement | null {
    return this.draft.manufacturing.roastRequirements?.[name] ?? null;
  }

  getRoastType(name: string): string {
    return this.draft.manufacturing.roastRequirements?.[name]?.roast ?? '';
  }

  setRoastType(name: string, roast: string): void {
    if (!this.draft.manufacturing.roastRequirements) {
      this.draft.manufacturing.roastRequirements = {};
    }
    if (!roast) {
      delete this.draft.manufacturing.roastRequirements[name];
      return;
    }
    if (!this.draft.manufacturing.roastRequirements[name]) {
      this.draft.manufacturing.roastRequirements[name] = { roast, lbsPerUnit: 0 };
    } else {
      this.draft.manufacturing.roastRequirements[name].roast = roast;
    }
  }

  getRoastLbs(name: string): number {
    return this.draft.manufacturing.roastRequirements?.[name]?.lbsPerUnit ?? 0;
  }

  setRoastLbs(name: string, value: number): void {
    if (!this.draft.manufacturing.roastRequirements?.[name]) return;
    this.draft.manufacturing.roastRequirements[name].lbsPerUnit = value;
  }

  isExcluded(name: string): boolean {
    return this.draft.manufacturing.excluded.includes(name);
  }

  toggleExcluded(name: string, checked: boolean): void {
    if (checked) {
      if (!this.draft.manufacturing.excluded.includes(name)) {
        this.draft.manufacturing.excluded.push(name);
      }
    } else {
      this.draft.manufacturing.excluded = this.draft.manufacturing.excluded.filter(
        (n) => n !== name
      );
    }
  }

  save(): void {
    if (this.saving) return;
    this.saving = true;
    this.saveSuccess = false;
    this.saveError = '';
    this.settingsService.save(this.draft).subscribe({
      next: (saved) => {
        this.draft = this.deepClone(saved);
        this.saving = false;
        this.saveSuccess = true;
        setTimeout(() => (this.saveSuccess = false), 3000);
      },
      error: () => {
        this.saving = false;
        this.saveError = 'Failed to save settings. Please try again.';
      },
    });
  }

  resetToDefaults(): void {
    this.draft = this.deepClone(DEFAULT_SETTINGS);
  }

  private deepClone<T>(obj: T): T {
    return JSON.parse(JSON.stringify(obj));
  }
}
