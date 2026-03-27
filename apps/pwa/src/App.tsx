import { useState, useEffect, useCallback } from 'react';
import { useDroneLink } from './hooks/useDroneLink';
import { Joystick } from './components/Joystick';
import { TelemetryPanel } from './components/TelemetryPanel';
import { Shield, ShieldAlert, Cpu, Activity, Bug, Keyboard } from 'lucide-react';

// Detect if running on a touch-primary device (phones/tablets)
function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof navigator === 'undefined') return false;
    return (
      /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ||
      (navigator.maxTouchPoints > 0 && window.innerWidth < 1024)
    );
  });

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(
        /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ||
        (navigator.maxTouchPoints > 0 && window.innerWidth < 1024)
      );
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return isMobile;
}

function App() {
  const {
    isConnected,
    error,
    telemetry,
    setArmed,
    updateAxes,
    currentCommand,
    txRate,
    bridgeHost,
    setBridgeHost,
    bridgeToken,
    setBridgeToken,
  } = useDroneLink();
  const [isArmed, setIsArmedUI] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const isMobile = useIsMobile();

  // Mode 2 Left Joystick: Throttle (Z) and Yaw (cw/ccw)
  const handleLeftJoystick = (data: { x: number; y: number }) => {
    updateAxes({
      yaw: data.x,  // Right -> CW (+), Left -> CCW (-)
      vz: data.y    // Up -> Ascend (+), Down -> Descend (-)
    });
  };

  // Mode 2 Right Joystick: Pitch (X) and Roll (Y)
  const handleRightJoystick = (data: { x: number; y: number }) => {
    updateAxes({
      vy: data.x,   // Right -> Roll Right (+), Left -> Roll Left (-)
      vx: data.y    // Up -> Pitch Forward (+), Down -> Pitch Backward (-)
    });
  };

  const handleZeroAxes = () => {
    updateAxes({ vx: 0, vy: 0, vz: 0, yaw: 0 });
  };

  const handleArmToggle = useCallback(() => {
    const nextState = !isArmed;
    setIsArmedUI(nextState);
    setArmed(nextState);
  }, [isArmed, setArmed]);

  // Desktop keyboard controls (WASD + Arrow Keys)
  const keysDown = useState<Set<string>>(() => new Set())[0];

  const computeKeyboardAxes = useCallback(() => {
    // Left hand: WASD → Throttle (vz) + Yaw
    const vz = (keysDown.has('w') ? 1 : 0) + (keysDown.has('s') ? -1 : 0);
    const yaw = (keysDown.has('d') ? 1 : 0) + (keysDown.has('a') ? -1 : 0);
    // Right hand: Arrow keys → Pitch (vx) + Roll (vy)
    const vx = (keysDown.has('arrowup') ? 1 : 0) + (keysDown.has('arrowdown') ? -1 : 0);
    const vy = (keysDown.has('arrowright') ? 1 : 0) + (keysDown.has('arrowleft') ? -1 : 0);
    updateAxes({ vx, vy, vz, yaw });
  }, [keysDown, updateAxes]);

  useEffect(() => {
    if (isMobile) return; // Skip keyboard on mobile

    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      // Space toggles arm
      if (key === ' ') {
        e.preventDefault();
        handleArmToggle();
        return;
      }
      if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
        e.preventDefault();
        keysDown.add(key);
        computeKeyboardAxes();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
        keysDown.delete(key);
        computeKeyboardAxes();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [isMobile, keysDown, computeKeyboardAxes, handleArmToggle]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex flex-col font-sans overflow-hidden select-none">

      {/* HEADER SECTION */}
      <header className="flex items-center justify-between p-4 bg-slate-900/80 border-b border-slate-800 backdrop-blur-md safe-top">
        <div className="flex items-center gap-3">
          <div className="relative">
            <Cpu className="w-8 h-8 text-cyan-400" />
            <span className={`absolute -bottom-1 -right-1 w-3 h-3 rounded-full border-2 border-slate-900 ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">SASE AQI Drone</h1>
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 mt-1">
              <p className="text-xs text-slate-400 font-medium tracking-wide">
                {isConnected ? 'LINK ESTABLISHED' : 'LINK OFFLINE'}
                <span className="ml-2 text-slate-600 hidden sm:inline">{isMobile ? '📱 TOUCH' : '⌨️ KEYBOARD'}</span>
              </p>
              <div className="flex items-center gap-2 bg-slate-800/80 rounded-md px-2 py-1 border border-slate-700">
                <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Bridge Host:</span>
                <input
                  type="text"
                  value={bridgeHost}
                  onChange={(e) => setBridgeHost(e.target.value)}
                  className="bg-transparent text-xs font-mono text-cyan-400 focus:outline-none w-24 sm:w-32 placeholder-slate-600"
                  placeholder="e.g. 192.168.1.5"
                />
              </div>
              <div className="flex items-center gap-2 bg-slate-800/80 rounded-md px-2 py-1 border border-slate-700">
                <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Token:</span>
                <input
                  type="password"
                  value={bridgeToken}
                  onChange={(e) => setBridgeToken(e.target.value)}
                  className="bg-transparent text-xs font-mono text-orange-300 focus:outline-none w-24 sm:w-32 placeholder-slate-600"
                  placeholder="optional"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowDebug(!showDebug)}
            className={`p-2 rounded-lg border transition-all ${showDebug ? 'bg-slate-700 border-slate-600 text-cyan-400' : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:text-slate-300 hover:bg-slate-700/50'}`}
            title="Toggle Debug View"
          >
            <Bug className="w-5 h-5" />
          </button>

          <button
            onClick={handleArmToggle}
            className={`
              relative overflow-hidden group px-8 py-3 rounded-xl font-bold text-lg tracking-widest transition-all duration-300
              ${isArmed
                ? 'bg-rose-500 hover:bg-rose-600 text-white shadow-[0_0_20px_rgba(244,63,94,0.4)]'
                : 'bg-emerald-500 hover:bg-emerald-600 text-slate-950 shadow-[0_0_20px_rgba(16,185,129,0.3)]'
              }
            `}
          >
            <div className="flex items-center gap-2">
              {isArmed ? <ShieldAlert className="w-6 h-6 animate-pulse" /> : <Shield className="w-6 h-6" />}
              {isArmed ? 'DISARM' : 'ARM'}
            </div>
          </button>
        </div>
      </header>

      {/* MAIN CONTENT DASHBOARD */}
      <main className="flex-1 p-4 lg:p-6 flex flex-col gap-6 relative">
        {error ? (
          <section className="w-full rounded-xl border border-rose-500/30 bg-rose-950/40 px-4 py-3 text-sm text-rose-100">
            {error}
          </section>
        ) : null}

        {/* TELEMETRY LAYER */}
        <section className="w-full">
          <TelemetryPanel data={telemetry} />
        </section>

        {/* CONTROLS LAYER — switches between touch joysticks and keyboard hints */}
        {isMobile ? (
          /* MOBILE: Dual touch joysticks */
          <section className="flex-1 flex items-center justify-between px-8 pb-8 mt-4 w-full max-w-5xl mx-auto opacity-80 hover:opacity-100 transition-opacity">
            <div className="flex flex-col items-center gap-4">
              <div className="text-cyan-400/80 font-bold tracking-widest text-sm uppercase">Throttle / Yaw</div>
              <Joystick
                id="left-stick"
                type="left"
                onMove={handleLeftJoystick}
                onEnd={handleZeroAxes}
              />
            </div>

            <div className="hidden md:flex flex-col items-center justify-center pointer-events-none opacity-20">
              <Activity className="w-32 h-32 text-cyan-500" />
            </div>

            <div className="flex flex-col items-center gap-4">
              <div className="text-orange-400/80 font-bold tracking-widest text-sm uppercase">Pitch / Roll</div>
              <Joystick
                id="right-stick"
                type="right"
                onMove={handleRightJoystick}
                onEnd={handleZeroAxes}
              />
            </div>
          </section>
        ) : (
          /* DESKTOP: Keyboard control reference */
          <section className="flex-1 flex items-center justify-center">
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-8 backdrop-blur-md max-w-lg w-full">
              <div className="flex items-center gap-3 mb-6">
                <Keyboard className="w-6 h-6 text-cyan-400" />
                <h2 className="text-lg font-bold text-slate-200">Keyboard Controls (Mode 2)</h2>
              </div>

              <div className="grid grid-cols-2 gap-8">
                {/* Left hand */}
                <div>
                  <p className="text-xs font-bold text-cyan-400/80 tracking-widest uppercase mb-4">Left Hand — Throttle / Yaw</p>
                  <div className="space-y-2 text-sm text-slate-300">
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">W</span><span>Ascend</span></div>
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">S</span><span>Descend</span></div>
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">A</span><span>Yaw CCW</span></div>
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">D</span><span>Yaw CW</span></div>
                  </div>
                </div>

                {/* Right hand */}
                <div>
                  <p className="text-xs font-bold text-orange-400/80 tracking-widest uppercase mb-4">Right Hand — Pitch / Roll</p>
                  <div className="space-y-2 text-sm text-slate-300">
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">↑</span><span>Pitch Fwd</span></div>
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">↓</span><span>Pitch Back</span></div>
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">←</span><span>Roll Left</span></div>
                    <div className="flex justify-between"><span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">→</span><span>Roll Right</span></div>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800">
                <div className="flex justify-between text-sm text-slate-400">
                  <span className="font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">SPACE</span>
                  <span>Toggle Arm / Disarm</span>
                </div>
              </div>
            </div>
          </section>
        )}

      </main>

      {/* DEV DEBUG OVERLAY */}
      {showDebug && (
        <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 bg-slate-900/95 border border-slate-700 rounded-xl p-4 text-xs font-mono text-slate-300 shadow-2xl backdrop-blur-md z-50 min-w-[300px]">
          <div className="flex justify-between items-center mb-3 border-b border-slate-700 pb-2">
            <span className="font-bold text-cyan-400">PWA DEV CONSOLE</span>
            <span className={`px-2 py-0.5 rounded ${txRate >= 28 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
              TX RATE: {txRate} Hz
            </span>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
            <div className="flex justify-between"><span>Pitch (vx):</span> <span className={currentCommand.vx !== 0 ? 'text-white font-bold' : ''}>{currentCommand.vx.toFixed(4)}</span></div>
            <div className="flex justify-between"><span>Yaw (yaw):</span> <span className={currentCommand.yaw !== 0 ? 'text-white font-bold' : ''}>{currentCommand.yaw.toFixed(4)}</span></div>
            <div className="flex justify-between"><span>Roll (vy):</span> <span className={currentCommand.vy !== 0 ? 'text-white font-bold' : ''}>{currentCommand.vy.toFixed(4)}</span></div>
            <div className="flex justify-between"><span>Arm:</span> <span className={currentCommand.arm ? 'text-rose-400 font-bold' : 'text-slate-500'}>{currentCommand.arm.toString().toUpperCase()}</span></div>
            <div className="flex justify-between"><span>Ascend (vz):</span> <span className={currentCommand.vz !== 0 ? 'text-white font-bold' : ''}>{currentCommand.vz.toFixed(4)}</span></div>
            <div className="flex justify-between"><span>Input:</span> <span className="text-slate-400">{isMobile ? 'Touch' : 'Keyboard'}</span></div>
          </div>
          <div className="mt-3 text-slate-500 pt-2 border-t border-slate-800 text-[10px] leading-tight text-center">
            Mode 2 | Auto-Center | Strict 30Hz | {isMobile ? 'Joystick' : 'WASD + Arrows'}
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
