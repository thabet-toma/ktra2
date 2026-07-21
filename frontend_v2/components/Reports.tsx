import React, { useMemo } from 'react';
import { Task, User } from '../types';
import { BarChart } from './charts/BarChart';

interface ReportsProps {
  tasks: Task[];
  users: User[];
}

const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.round(seconds % 60);
    let timeString = '';
    if (h > 0) timeString += `${h}س `;
    if (m > 0) timeString += `${m}د `;
    if (s > 0 || (h === 0 && m === 0)) timeString += `${s}ث`;
    return timeString.trim();
};

export const Reports: React.FC<ReportsProps> = ({ tasks, users }) => {

  const employeeTimeData = useMemo(() => {
    const employees = users.filter(u => u.role === 'employee');
    return employees.map(employee => {
      const employeeTasks = tasks.filter(t => t.assignedTo === employee.id);
      const totalTime = employeeTasks.reduce((acc, task) => acc + task.totalWorkTime, 0);
      return {
        name: employee.name,
        totalTime, // in milliseconds
        taskCount: employeeTasks.length
      };
    });
  }, [tasks, users]);

  const chartData = {
      labels: employeeTimeData.map(e => e.name),
      datasets: [
          {
              label: 'الوقت المستغرق (بالدقائق)',
              data: employeeTimeData.map(e => Math.round(e.totalTime / 60000)),
              backgroundColor: 'rgba(59, 130, 246, 0.7)',
          }
      ]
  }

  return (
    <div className="animate-fade-in">
        <h1 className="text-3xl font-bold mb-6 text-[var(--color-text)]">التقارير والتحليلات</h1>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[var(--color-surface)] rounded-2xl shadow-md border border-[var(--color-border)] p-6">
                 <h2 className="text-xl font-bold mb-4 text-[var(--color-text)]">الوقت المستغرق لكل موظف</h2>
                 <div className="overflow-x-auto">
                    <table className="w-full text-right">
                        <thead className="border-b border-[var(--color-border)]">
                            <tr>
                                <th className="p-3 font-semibold text-[var(--color-text-muted)]">الموظف</th>
                                <th className="p-3 font-semibold text-[var(--color-text-muted)]">عدد المهام</th>
                                <th className="p-3 font-semibold text-[var(--color-text-muted)]">إجمالي الوقت</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--color-border)]">
                            {employeeTimeData.map(data => (
                                <tr key={data.name}>
                                    <td className="p-3 font-medium text-[var(--color-text)]">{data.name}</td>
                                    <td className="p-3 text-[var(--color-text-muted)]">{data.taskCount}</td>
                                    <td className="p-3 text-[var(--color-text-muted)] font-mono">{formatTime(data.totalTime / 1000)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                 </div>
            </div>

            <div className="bg-[var(--color-surface)] rounded-2xl shadow-md border border-[var(--color-border)] p-6">
                <h2 className="text-xl font-bold mb-4 text-[var(--color-text)]">رسم بياني للوقت المستغرق (بالدقائق)</h2>
                <BarChart data={chartData} />
            </div>
        </div>
    </div>
  );
};