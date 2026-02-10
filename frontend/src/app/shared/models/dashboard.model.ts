export interface MetricCard {
  title: string;
  value: number | string;
  icon: string;
  color: string;
  trend?: number;
}

export interface ChartData {
  labels: string[];
  datasets: { label: string; data: number[] }[];
}
