/** Simple SVG-based line chart component. */

import React from "react";

interface DataPoint {
  date: string;
  value: number;
}

interface SimpleLineChartProps {
  data: DataPoint[];
  width?: number;
  height?: number;
  color?: string;
}

export const SimpleLineChart: React.FC<SimpleLineChartProps> = ({
  data,
  width = 800,
  height = 200,
  color = "#251D1C",
}) => {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 bg-gray-50 rounded-sm border border-gray-200">
        <p className="text-gray-500">No data available</p>
      </div>
    );
  }

  const padding = 40;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const minValue = Math.min(...data.map((d) => d.value), 0);

  const valueRange = maxValue - minValue || 1;

  const getX = (index: number) => {
    const divisor = data.length > 1 ? data.length - 1 : 1;
    return padding + (index / divisor) * chartWidth;
  };

  const getY = (value: number) => {
    return padding + chartHeight - ((value - minValue) / valueRange) * chartHeight;
  };

  const points = data.map((point, index) => `${getX(index)},${getY(point.value)}`).join(" ");

  return (
    <div className="bg-white rounded-sm border border-[#251D1C]/20 p-4">
      <svg width={width} height={height} className="overflow-visible">
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding + chartHeight - ratio * chartHeight;
          return (
            <line
              key={ratio}
              x1={padding}
              y1={y}
              x2={width - padding}
              y2={y}
              stroke="#E5E7EB"
              strokeWidth="1"
            />
          );
        })}

        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Points */}
        {data.map((point, index) => (
          <circle
            key={index}
            cx={getX(index)}
            cy={getY(point.value)}
            r="4"
            fill={color}
            className="hover:r-6 transition-all"
          />
        ))}

        {/* Labels */}
        {data.map((point, index) => {
          if (index % Math.ceil(data.length / 7) === 0 || index === data.length - 1) {
            return (
              <text
                key={index}
                x={getX(index)}
                y={height - 10}
                textAnchor="middle"
                className="text-xs fill-gray-600"
              >
                {new Date(point.date).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </text>
            );
          }
          return null;
        })}
      </svg>
    </div>
  );
};
