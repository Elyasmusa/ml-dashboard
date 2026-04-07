import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { ApiService } from './api.service';
import { AppSettings, DEFAULT_SETTINGS } from '../models/settings.model';

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private _settings$ = new BehaviorSubject<AppSettings>(DEFAULT_SETTINGS);

  /** Stream of the current settings. */
  readonly settings$ = this._settings$.asObservable();

  /** Synchronous snapshot of the current settings. */
  get current(): AppSettings {
    return this._settings$.value;
  }

  constructor(private api: ApiService) {}

  /** Load settings from the backend. Call once on app init. */
  load(): Observable<AppSettings> {
    return this.api.get<AppSettings>('/settings').pipe(
      tap(s => this._settings$.next(s))
    );
  }

  /** Save settings to the backend and update the local cache. */
  save(settings: AppSettings): Observable<AppSettings> {
    return this.api.put<AppSettings>('/settings', settings).pipe(
      tap(s => this._settings$.next(s))
    );
  }
}
