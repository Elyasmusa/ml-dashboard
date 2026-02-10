import { Component, Input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-metrics-card',
  standalone: true,
  imports: [MatCardModule, MatIconModule],
  templateUrl: './metrics-card.component.html',
  styleUrl: './metrics-card.component.scss',
})
export class MetricsCardComponent {
  @Input() title = '';
  @Input() value: string | number = '';
  @Input() icon = 'info';
  @Input() color = '#3f51b5';
}
