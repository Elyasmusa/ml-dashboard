import { Component, Input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';

@Component({
  selector: 'app-chart-placeholder',
  standalone: true,
  imports: [MatCardModule],
  templateUrl: './chart-placeholder.component.html',
  styleUrl: './chart-placeholder.component.scss',
})
export class ChartPlaceholderComponent {
  @Input() title = 'Chart';
}
