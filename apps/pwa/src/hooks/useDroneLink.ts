import { useState, useEffect, useRef, useCallback } from 'react';

// The final, locked schema from PROTOCOL.md
export interface ControlCommand {
    vx: number;     // [-1.0, 1.0] Forward Pitch
    vy: number;     // [-1.0, 1.0] Right Roll/Strafe
    vz: number;     // [-1.0, 1.0] Ascend Throttle
    yaw: number;    // [-1.0, 1.0] CW Yaw Rate
    arm: boolean;
}

export interface TelemetryMessage {
    status: string;
    position: { x: number; y: number; z: number };
    gyro: { x: number; y: number; z: number };
    aqi: number | null;
    tvoc: number | null;
    eco2: number | null;
    temperature_c: number | null;
    humidity_pct: number | null;
    batt_v?: number | null;
}

export function useDroneLink() {
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [telemetry, setTelemetry] = useState<TelemetryMessage | null>(null);

    const defaultBridgeHost = (() => {
        if (typeof window === 'undefined') return '127.0.0.1';
        return window.location.hostname || '127.0.0.1';
    })();
    const defaultBridgeToken = import.meta.env.VITE_BRIDGE_WS_TOKEN ?? '';

    const [bridgeHost, setBridgeHostState] = useState(() => {
        if (typeof window === 'undefined') return defaultBridgeHost;
        return localStorage.getItem('sase_bridge_host') || defaultBridgeHost;
    });
    const [bridgeToken, setBridgeTokenState] = useState(() => {
        if (typeof window === 'undefined') return defaultBridgeToken;
        return localStorage.getItem('sase_bridge_token') || defaultBridgeToken;
    });

    const setBridgeHost = useCallback((host: string) => {
        setBridgeHostState(host);
        if (typeof window !== 'undefined') {
            localStorage.setItem('sase_bridge_host', host);
        }
    }, []);

    const setBridgeToken = useCallback((token: string) => {
        setBridgeTokenState(token);
        if (typeof window !== 'undefined') {
            localStorage.setItem('sase_bridge_token', token);
        }
    }, []);

    // Developer metrics
    const [txRate, setTxRate] = useState(0);
    const txCountRef = useRef(0);

    const socketRef = useRef<WebSocket | null>(null);
    const reconnectTimerRef = useRef<number | null>(null);
    const unmountedRef = useRef(false);

    // We use a ref for the joystick state so the 30Hz loop always sees the freshest values
    // without triggering React re-renders on every joystick micro-movement.
    const joystickStateRef = useRef<ControlCommand>({
        vx: 0.0,
        vy: 0.0,
        vz: 0.0,
        yaw: 0.0,
        arm: false
    });

    const loopIntervalRef = useRef<number | null>(null);

    // Rate calculation exact measurement
    useEffect(() => {
        const interval = setInterval(() => {
            setTxRate(txCountRef.current);
            txCountRef.current = 0;
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    // ---------- STRICT CONTROL SEMANTICS ----------

    // Safely clamp values to [-1.0, +1.0]
    const buildCommand = (): ControlCommand => {
        const raw = joystickStateRef.current;
        return {
            vx: Math.max(-1.0, Math.min(1.0, raw.vx)),
            vy: Math.max(-1.0, Math.min(1.0, raw.vy)),
            vz: Math.max(-1.0, Math.min(1.0, raw.vz)),
            yaw: Math.max(-1.0, Math.min(1.0, raw.yaw)),
            arm: raw.arm
        };
    };

    const _sendTick = () => {
        if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
        const cmd = buildCommand();
        socketRef.current.send(JSON.stringify(cmd));
        txCountRef.current++;
    };

    const startControlLoop = () => {
        if (loopIntervalRef.current) return;
        joystickStateRef.current.arm = true;
        console.log("ARMING - Starting 30Hz Control Loop");
        // 33ms interval is ~30.3Hz
        loopIntervalRef.current = window.setInterval(_sendTick, 33);
    };

    const stopControlLoop = () => {
        if (loopIntervalRef.current) {
            window.clearInterval(loopIntervalRef.current);
            loopIntervalRef.current = null;
        }
    };

    // The public method to toggle arm state
    const setArmed = (shouldArm: boolean) => {
        if (shouldArm) {
            startControlLoop();
        } else {
            // STRICT DISARM SEMANTICS:
            // 1) Zero joystick state immediately
            joystickStateRef.current = { vx: 0, vy: 0, vz: 0, yaw: 0, arm: false };

            // 2) Synchronously transmit disarm packet exactly ONCE
            _sendTick();

            // 3) Halt the 30Hz loop
            stopControlLoop();
            console.log("DISARMED - Zeroed axes, sent stop packet, halted loop.");
        }
    };

    // The public method for the UI joysticks to update the target state
    const updateAxes = (axes: { vx?: number; vy?: number; vz?: number; yaw?: number }) => {
        joystickStateRef.current = {
            ...joystickStateRef.current,
            ...axes
        };
    };


    // ---------- CONNECTION MANAGEMENT ----------

    const connect = useCallback(function reconnect() {
        // Don't reconnect if we've been unmounted
        if (unmountedRef.current) return;

        // Guard against duplicate connections
        if (socketRef.current?.readyState === WebSocket.OPEN ||
            socketRef.current?.readyState === WebSocket.CONNECTING) return;

        const protocol = import.meta.env.VITE_BRIDGE_WS_PROTOCOL
            ?? (window.location.protocol === 'https:' ? 'wss' : 'ws');
        const port = import.meta.env.VITE_BRIDGE_WS_PORT ?? '8765';
        const host = bridgeHost.trim() || defaultBridgeHost;
        const params = new URLSearchParams();
        if (bridgeToken.trim()) {
            params.set('token', bridgeToken.trim());
        }

        const suffix = params.toString();
        const wsUrl = `${protocol}://${host}:${port}/ws${suffix ? `?${suffix}` : ''}`;
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            setIsConnected(true);
            setError(null);
            console.log(`Drone WebSocket Connected to ${host}`);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                setTelemetry(data);
            } catch (err) {
                console.error("Telemetry parse error", err);
            }
        };

        ws.onclose = (event) => {
            setIsConnected(false);
            console.log("Drone WebSocket Disconnected");
            if (event?.code === 1008) {
                setError('Bridge rejected the connection. Check WS auth mode and token.');
            }

            // SAFETY: Force disarm on disconnect — no runaway commands
            joystickStateRef.current = { vx: 0, vy: 0, vz: 0, yaw: 0, arm: false };
            stopControlLoop();

            // Fix: Null the ref so the guard in connect() doesn't see a stale CLOSED socket
            socketRef.current = null;

            // Auto-reconnect with cleanup tracking
            if (!unmountedRef.current) {
                reconnectTimerRef.current = window.setTimeout(reconnect, 3000);
            }
        };

        ws.onerror = (e) => {
            setError("WebSocket Error occurred");
            console.error("WS Error", e);
        };

        socketRef.current = ws;
    }, [bridgeHost, bridgeToken, defaultBridgeHost]);

    useEffect(() => {
        unmountedRef.current = false;
        connect();

        return () => {
            // Mark unmounted to prevent zombie reconnect timers
            unmountedRef.current = true;

            // Cancel any pending reconnect timer
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }

            // Stop the control loop
            stopControlLoop();

            // Close the WebSocket (triggering reconnect if IP changed)
            if (socketRef.current) {
                socketRef.current.close();
                socketRef.current = null;
            }
        };
    }, [connect]); // Re-run effect if connect function changes


    return {
        isConnected,
        error,
        telemetry,
        setArmed,
        updateAxes,
        currentCommand: joystickStateRef.current, // For the debug view
        txRate, // Commands sent per second
        bridgeHost,
        setBridgeHost,
        bridgeToken,
        setBridgeToken
    };
}
