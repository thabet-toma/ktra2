import React from 'react';

interface ChartData {
    labels: string[];
    datasets: {
        label: string;
        data: number[];
        backgroundColor: string;
    }[];
}

interface BarChartProps {
    data: ChartData;
}

export const BarChart: React.FC<BarChartProps> = ({ data }) => {
    const maxValue = Math.max(...data.datasets[0].data, 1);
    const chartHeight = 300;
    const barWidth = 35;
    const barMargin = 15;
    const svgWidth = data.labels.length * (barWidth + barMargin);

    return (
        <div className="w-full overflow-x-auto">
            <svg width={svgWidth} height={chartHeight} className="font-sans">
                {data.datasets[0].data.map((value, index) => {
                    const barHeight = (value / maxValue) * (chartHeight - 40);
                    const x = index * (barWidth + barMargin);
                    const y = chartHeight - barHeight - 20;

                    return (
                        <g key={index}>
                            <rect
                                x={x}
                                y={y}
                                width={barWidth}
                                height={barHeight}
                                fill={data.datasets[0].backgroundColor}
                                rx="4"
                                ry="4"
                            />
                            <text
                                x={x + barWidth / 2}
                                y={y - 5}
                                textAnchor="middle"
                                className="text-xs font-semibold fill-current text-[var(--color-text)]"
                            >
                                {value}
                            </text>
                            <text
                                x={x + barWidth / 2}
                                y={chartHeight}
                                textAnchor="middle"
                                className="text-sm fill-current text-[var(--color-text-muted)]"
                            >
                                {data.labels[index]}
                            </text>
                        </g>
                    );
                })}
            </svg>
        </div>
    );
};
