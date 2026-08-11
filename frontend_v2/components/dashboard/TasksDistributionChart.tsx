
import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { Task } from '../../types';

interface TasksDistributionChartProps {
    tasks: Task[];
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];
const STATUS_NAMES: Record<string, string> = {
    'NEW': 'جديدة',
    'ACCEPTED': 'تم القبول',
    'IN_PROGRESS': 'قيد العمل',
    'WAITING_FOR_REVIEW': 'مراجعة',
    'COMPLETED': 'مكتملة',
    'REJECTED': 'مرفوضة'
};

export const TasksDistributionChart: React.FC<TasksDistributionChartProps> = ({ tasks }) => {
    const data = React.useMemo(() => {
        const counts: Record<string, number> = {};
        tasks.forEach(t => {
            counts[t.status] = (counts[t.status] || 0) + 1;
        });
        return Object.keys(counts).map(key => ({
            name: STATUS_NAMES[key] || key,
            value: counts[key]
        }));
    }, [tasks]);

    return (
        <div className="bg-[var(--color-surface)] rounded-2xl shadow-sm border border-[var(--color-border)] p-6 h-[400px]">
            <h3 className="text-lg font-bold text-[var(--color-text)] mb-4">توزيع المهام</h3>
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                        data={data}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        fill="#8884d8"
                        paddingAngle={5}
                        dataKey="value"
                    >
                        {data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                    </Pie>
                    <Tooltip
                        contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.9)', borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                    />
                    <Legend />
                </PieChart>
            </ResponsiveContainer>
        </div>
    );
};
