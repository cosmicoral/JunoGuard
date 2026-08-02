import { count } from "../lib/format";

const WIDTH = 760;
const HEIGHT = 280;
const PAD_X = 42;
const PAD_TOP = 34;
const PAD_BOTTOM = 42;

function smooth(series: number[]): number[] {
  let prev = series[0] ?? 0;
  return series.map((value) => {
    prev = prev * 0.68 + value * 0.32;
    return prev;
  });
}

function pointsFor(series: number[], peak: number): string {
  const plotWidth = WIDTH - PAD_X * 2;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const last = Math.max(series.length - 1, 1);

  return series
    .map((value, index) => {
      const x = PAD_X + (index / last) * plotWidth;
      const y = PAD_TOP + (1 - value / peak) * plotHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function ActivityChart({
  rate,
  limit,
  reqPerMin,
}: {
  rate: number[];
  limit: number;
  reqPerMin: number;
}) {
  const series = rate.length > 1 ? rate : Array.from({ length: 26 }, () => 0);
  const peak = Math.max(...series, limit, 1) * 1.12;
  const primaryPoints = pointsFor(series, peak);
  const secondaryPoints = pointsFor(smooth(series), peak);
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const limitY = PAD_TOP + (1 - Math.min(limit / peak, 1)) * plotHeight;
  const latest = series[series.length - 1] ?? 0;

  return (
    <section className="panel activity-card" aria-labelledby="activity-title">
      <div className="activity-head">
        <div>
          <p className="section-kicker">Rate policy</p>
          <h2 id="activity-title">Requests per minute</h2>
        </div>
        <div className="activity-reading">
          <strong>{count(reqPerMin)}</strong>
          <span>current / min</span>
        </div>
      </div>

      <div className="activity-chart-wrap">
        <svg
          className="activity-chart"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Request rate chart. Current rate ${count(reqPerMin)} per minute. Limit ${count(limit)} per minute.`}
        >
          <line className="chart-grid" x1={PAD_X} y1={PAD_TOP} x2={PAD_X} y2={HEIGHT - PAD_BOTTOM} />
          <line
            className="chart-grid"
            x1={PAD_X}
            y1={HEIGHT - PAD_BOTTOM}
            x2={WIDTH - PAD_X}
            y2={HEIGHT - PAD_BOTTOM}
          />
          <line className="chart-grid chart-grid-muted" x1={PAD_X} y1={PAD_TOP + plotHeight / 2} x2={WIDTH - PAD_X} y2={PAD_TOP + plotHeight / 2} />
          <line className="chart-limit" x1={PAD_X} y1={limitY} x2={WIDTH - PAD_X} y2={limitY} />
          <text className="chart-limit-label" x={WIDTH - PAD_X} y={Math.max(limitY - 8, 14)}>
            LIMIT {count(limit)}
          </text>
          <polyline className="chart-line chart-line-secondary" points={secondaryPoints} />
          <polyline className="chart-line chart-line-primary" points={primaryPoints} />
          <circle
            className="chart-terminal"
            cx={WIDTH - PAD_X}
            cy={PAD_TOP + (1 - latest / peak) * plotHeight}
            r="3.5"
          />
        </svg>
      </div>

      <div className="activity-legend" aria-hidden="true">
        <span><i data-tone="primary" />Live</span>
        <span><i data-tone="secondary" />Smoothed</span>
        <span><i data-tone="limit" />Policy limit</span>
      </div>
    </section>
  );
}
