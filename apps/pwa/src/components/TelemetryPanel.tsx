import type { ReactNode } from 'react';
import type { TelemetryMessage } from '../hooks/useDroneLink';
import { Activity, Wind, Thermometer, Droplets, Battery } from 'lucide-react';

export function TelemetryPanel({ data }: { data: TelemetryMessage | null }) {
    if (!data) {
        return (
            <div className="flex flex-col items-center justify-center p-6 bg-slate-800/50 rounded-xl border border-slate-700 h-full">
                <Activity className="w-8 h-8 text-slate-500 mb-2 animate-pulse" />
                <p className="text-slate-400 font-medium">Waiting for Telemetry...</p>
            </div>
        );
    }

    const { status, aqi, tvoc, eco2, temperature_c, humidity_pct, batt_v } = data;

    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 w-full">
            <MetricCard
                icon={<Activity className="w-5 h-5 text-emerald-400" />}
                label="System Status"
                value={status.toUpperCase()}
            />

            <MetricCard
                icon={<Wind className="w-5 h-5 text-blue-400" />}
                label="AQI"
                value={aqi !== null ? aqi : '--'}
                unit=""
                alert={aqi !== null && aqi > 100}
            />

            <MetricCard
                icon={<Wind className="w-5 h-5 text-purple-400" />}
                label="eCO2"
                value={eco2 !== null ? eco2 : '--'}
                unit="ppm"
            />

            <MetricCard
                icon={<Wind className="w-5 h-5 text-indigo-400" />}
                label="TVOC"
                value={tvoc !== null ? tvoc : '--'}
                unit="ppb"
            />

            <MetricCard
                icon={<Thermometer className="w-5 h-5 text-orange-400" />}
                label="Temp"
                value={temperature_c !== null ? temperature_c.toFixed(1) : '--'}
                unit="°C"
            />

            <MetricCard
                icon={<Droplets className="w-5 h-5 text-cyan-400" />}
                label="Humidity"
                value={humidity_pct !== null ? humidity_pct.toFixed(1) : '--'}
                unit="%"
            />

            <MetricCard
                icon={<Battery className={`w-5 h-5 ${batt_v && batt_v < 10.5 ? 'text-red-500 animate-pulse' : 'text-green-400'}`} />}
                label="Battery"
                value={batt_v !== null && batt_v !== undefined ? batt_v.toFixed(1) : '--'}
                unit="V"
            />
        </div>
    );
}

function MetricCard({ icon, label, value, unit = '', alert = false }: { icon: ReactNode, label: string, value: string | number, unit?: string, alert?: boolean }) {
    return (
        <div className={`p-4 bg-slate-800/80 rounded-xl border ${alert ? 'border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.2)]' : 'border-slate-700/50'} backdrop-blur-sm flex flex-col justify-between`}>
            <div className="flex items-center gap-2 mb-2">
                {icon}
                <span className="text-slate-400 text-sm font-medium tracking-wide">{label}</span>
            </div>
            <div className="flex items-baseline gap-1">
                <span className={`text-2xl font-bold ${alert ? 'text-red-400' : 'text-slate-100'}`}>{value}</span>
                {unit && <span className="text-slate-500 text-sm font-semibold">{unit}</span>}
            </div>
        </div>
    );
}
