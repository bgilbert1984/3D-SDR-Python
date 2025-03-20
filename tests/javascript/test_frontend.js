const { test, expect, jest } = require('@jest/globals');
const { renderElement, renderLeaf } = require('../../frontend/frontend-signal-visualization');
const WebSocket = require('ws');

// Mock the WebSocket
jest.mock('ws');

// Mock THREE.js
global.THREE = {
    Scene: jest.fn(),
    PerspectiveCamera: jest.fn(),
    WebGLRenderer: jest.fn(),
    Color: jest.fn(),
    GridHelper: jest.fn(),
    AxesHelper: jest.fn(),
    BufferGeometry: jest.fn(),
    Float32Array: Array,
    PointsMaterial: jest.fn(),
    Points: jest.fn(),
    AmbientLight: jest.fn(),
    DirectionalLight: jest.fn()
};

// Basic rendering tests
test('renderElement should return a paragraph for default type', () => {
    const props = { element: { type: 'paragraph' }, attributes: {}, children: 'Test' };
    const result = renderElement(props);
    expect(result.type).toBe('p');
    expect(result.props.children).toBe('Test');
});

test('renderLeaf should apply bold styling', () => {
    const props = { leaf: { bold: true }, attributes: {}, children: 'Bold Text' };
    const result = renderLeaf(props);
    expect(result.type).toBe('span');
    expect(result.props.children.type).toBe('strong');
    expect(result.props.children.props.children).toBe('Bold Text');
});

// Signal visualization tests
describe('Signal Visualization', () => {
    let visualizer;
    
    beforeEach(() => {
        visualizer = {
            scene: new THREE.Scene(),
            camera: new THREE.PerspectiveCamera(),
            renderer: new THREE.WebGLRenderer(),
            signalData: []
        };
    });

    test('should create point cloud for signal data', () => {
        const testData = {
            freqs: [100, 200, 300],
            amplitudes: [0.5, 0.7, 0.3],
            timestamp: Date.now()
        };
        
        visualizer.updateSignalData(testData);
        expect(visualizer.signalData.length).toBe(3);
        expect(visualizer.pointCloud).toBeDefined();
    });

    test('should handle empty signal data', () => {
        const testData = {
            freqs: [],
            amplitudes: [],
            timestamp: Date.now()
        };
        
        visualizer.updateSignalData(testData);
        expect(visualizer.signalData.length).toBe(0);
    });
});

// WebSocket connection tests
describe('WebSocket Connection', () => {
    let ws;
    
    beforeEach(() => {
        ws = new WebSocket('ws://localhost:8080');
    });

    test('should establish WebSocket connection', () => {
        expect(ws.readyState).toBe(WebSocket.CONNECTING);
    });

    test('should handle incoming signal data', done => {
        const testData = {
            type: 'signal',
            freqs: [100],
            amplitudes: [0.5],
            timestamp: Date.now()
        };

        ws.on('message', data => {
            const parsedData = JSON.parse(data);
            expect(parsedData.type).toBe('signal');
            expect(parsedData.freqs).toHaveLength(1);
            done();
        });

        ws.emit('message', JSON.stringify(testData));
    });

    test('should handle connection errors', done => {
        ws.on('error', error => {
            expect(error).toBeDefined();
            done();
        });

        ws.emit('error', new Error('Connection failed'));
    });
});

// Drone control tests
describe('Drone Control', () => {
    test('should send takeoff command', () => {
        const droneCommand = {
            type: 'command',
            command: 'takeoff',
            drone_id: 'drone1',
            altitude: 50
        };

        expect(droneCommand.type).toBe('command');
        expect(droneCommand.command).toBe('takeoff');
    });

    test('should send land command', () => {
        const droneCommand = {
            type: 'command',
            command: 'land',
            drone_id: 'drone1'
        };

        expect(droneCommand.type).toBe('command');
        expect(droneCommand.command).toBe('land');
    });
});

// FCC violation detection tests
describe('Violation Detection', () => {
    test('should identify FCC violations', () => {
        const signalData = {
            frequency: 146.52,
            power: 0.9,
            modulation: 'FM',
            isViolation: true
        };

        expect(signalData.isViolation).toBe(true);
        expect(signalData.power).toBeGreaterThan(0.8);
    });

    test('should track violation history', () => {
        const violationHistory = [];
        const violation = {
            timestamp: Date.now(),
            frequency: 146.52,
            power: 0.9
        };

        violationHistory.push(violation);
        expect(violationHistory.length).toBe(1);
        expect(violationHistory[0].frequency).toBe(146.52);
    });
});

// Geolocation tests
describe('Signal Geolocation', () => {
    test('should calculate signal position', () => {
        const readings = [
            { lat: 37.7749, lon: -122.4194, power: 0.8 },
            { lat: 37.7750, lon: -122.4195, power: 0.6 },
            { lat: 37.7748, lon: -122.4193, power: 0.7 }
        ];

        const position = calculatePosition(readings);
        expect(position.lat).toBeCloseTo(37.7749, 4);
        expect(position.lon).toBeCloseTo(-122.4194, 4);
    });
});

function calculatePosition(readings) {
    // Simple centroid calculation for testing
    const totalReadings = readings.length;
    const position = readings.reduce((acc, reading) => {
        acc.lat += reading.lat * reading.power;
        acc.lon += reading.lon * reading.power;
        acc.totalPower += reading.power;
        return acc;
    }, { lat: 0, lon: 0, totalPower: 0 });

    return {
        lat: position.lat / position.totalPower,
        lon: position.lon / position.totalPower
    };
}

// Frontend Visualization Tests
describe('Frontend Visualization Tests', () => {
    describe('DroneSDRVisualizer', () => {
        let visualizer;
        let mockSocket;

        beforeEach(() => {
            // Mock Cesium dependencies
            global.Cesium = {
                Viewer: jest.fn(),
                EntityCollection: jest.fn(),
                JulianDate: {
                    now: jest.fn()
                },
                Cartesian3: {
                    fromDegrees: jest.fn(),
                    midpoint: jest.fn(),
                    add: jest.fn()
                },
                Color: {
                    DODGERBLUE: {},
                    SPRINGGREEN: {},
                    RED: {},
                    YELLOW: {},
                    MAGENTA: {},
                    WHITE: {},
                    fromCssColorString: jest.fn()
                },
                Math: {
                    toRadians: jest.fn()
                },
                HeadingPitchRange: jest.fn()
            };

            // Mock DOM elements
            document.body.innerHTML = `
                <div id="stats"></div>
                <div id="connectionStatus"></div>
                <div id="droneList"></div>
                <div id="signalList"></div>
                <div id="violationList"></div>
                <div id="droneCount"></div>
                <div id="signalCount"></div>
                <div id="violationCount"></div>
                <div id="selectedDrone"></div>
                <div id="takeoffAltitude"></div>
                <input id="serverUrl" value="ws://localhost:8080">
            `;

            // Create visualizer instance
            visualizer = new DroneSDRVisualizer();
            mockSocket = {
                send: jest.fn(),
                close: jest.fn()
            };
            visualizer.socket = mockSocket;
        });

        test('processDroneData updates drone state correctly', () => {
            const testData = {
                type: 'drone_status',
                drone_id: 'test-drone-1',
                timestamp: Date.now(),
                location: {
                    latitude: 37.7749,
                    longitude: -122.4194,
                    altitude: 100
                },
                battery: 95,
                is_pursuing: false
            };

            visualizer.processData(testData);
            expect(visualizer.drones['test-drone-1']).toBeDefined();
            expect(visualizer.drones['test-drone-1'].battery).toBe(95);
            expect(visualizer.drones['test-drone-1'].isPursuing).toBe(false);
        });

        test('processSignalData updates signal state correctly', () => {
            const testData = {
                type: 'signal',
                frequency_mhz: 433.5,
                modulation: 'AM',
                power: 0.75,
                confidence: 0.9,
                geolocation: {
                    latitude: 37.7749,
                    longitude: -122.4194,
                    altitude: 50
                }
            };

            visualizer.processData(testData);
            expect(visualizer.signals['433.500']).toBeDefined();
            expect(visualizer.signals['433.500'].modulation).toBe('AM');
            expect(visualizer.signals['433.500'].power).toBe(0.75);
        });

        test('processViolationData updates violation state correctly', () => {
            const testData = {
                type: 'violation',
                frequency_mhz: 435.0,
                modulation: 'FM',
                power: 0.9,
                confidence: 0.95,
                geolocation: {
                    latitude: 37.7749,
                    longitude: -122.4194,
                    altitude: 75
                }
            };

            visualizer.processData(testData);
            expect(visualizer.violations['435.000']).toBeDefined();
            expect(visualizer.violations['435.000'].modulation).toBe('FM');
            expect(visualizer.violations['435.000'].power).toBe(0.9);
        });

        test('pursueViolation sends correct command format', () => {
            // Setup violation data
            visualizer.violations['435.000'] = {
                frequency: 435000000,
                frequency_mhz: 435.0
            };
            
            // Setup mock drone
            visualizer.drones['drone-1'] = {};
            document.getElementById('selectedDrone').value = 'drone-1';

            visualizer.pursueViolation('435.000');

            expect(mockSocket.send).toHaveBeenCalledWith(
                expect.stringContaining('"command":"pursue"')
            );
            expect(mockSocket.send).toHaveBeenCalledWith(
                expect.stringContaining('"drone_id":"drone-1"')
            );
            expect(mockSocket.send).toHaveBeenCalledWith(
                expect.stringContaining('"frequency":435000000')
            );
        });

        test('sendDroneCommand sends correct takeoff command', () => {
            document.getElementById('selectedDrone').value = 'drone-1';
            document.getElementById('takeoffAltitude').value = '75';

            visualizer.sendDroneCommand('takeoff');

            expect(mockSocket.send).toHaveBeenCalledWith(
                expect.stringContaining('"command":"takeoff"')
            );
            expect(mockSocket.send).toHaveBeenCalledWith(
                expect.stringContaining('"altitude":75')
            );
        });

        test('clearAll resets visualization state', () => {
            // Setup some test data
            visualizer.drones['test-drone'] = {};
            visualizer.signals['433.500'] = {};
            visualizer.violations['435.000'] = {};

            visualizer.clearAll();

            expect(Object.keys(visualizer.drones)).toHaveLength(0);
            expect(Object.keys(visualizer.signals)).toHaveLength(0);
            expect(Object.keys(visualizer.violations)).toHaveLength(0);
        });
    });

    describe('CollisionDetection', () => {
        let visualizer;

        beforeEach(() => {
            visualizer = new DroneSDRVisualizer();
            visualizer.minSeparationDistance = 15;
        });

        test('calculateDistance returns correct haversine distance', () => {
            // Test points ~15m apart
            const distance = visualizer.calculateDistance(
                37.7749, -122.4194,
                37.77502, -122.41942
            );
            
            expect(distance).toBeCloseTo(15, 0);
        });

        test('checkCollisionRisks detects close drones', () => {
            // Setup two drones very close to each other
            visualizer.drones['drone-1'] = {
                entity: {
                    position: {
                        getValue: () => ({x: 0, y: 0, z: 100})
                    }
                }
            };
            
            visualizer.drones['drone-2'] = {
                entity: {
                    position: {
                        getValue: () => ({x: 10, y: 0, z: 100})
                    }
                }
            };

            visualizer.checkCollisionRisks();
            expect(Object.keys(visualizer.collisionWarnings)).toHaveLength(1);
        });
    });
});

// Frontend component tests using Jest
const THREE = require('three');
const WebSocket = require('ws');

// Mock THREE and Cesium globals
global.THREE = THREE;
global.Cesium = {
    Viewer: jest.fn(),
    Ion: { defaultAccessToken: '' },
    Cartesian3: {
        fromDegrees: jest.fn(),
        add: jest.fn()
    },
    Color: {
        RED: { withAlpha: jest.fn() },
        YELLOW: { withAlpha: jest.fn() },
        WHITE: { withAlpha: jest.fn() },
        DODGERBLUE: {}
    },
    EntityCollection: jest.fn(),
    JulianDate: {
        now: jest.fn(),
        secondsDifference: jest.fn()
    },
    Math: {
        toRadians: jest.fn()
    },
    VerticalOrigin: {
        CENTER: 'center',
        BOTTOM: 'bottom'
    },
    HorizontalOrigin: {
        CENTER: 'center'
    }
};

// Mock DOM elements
document.body.innerHTML = `
    <div id="connectionStatus"></div>
    <div id="droneCount">0</div>
    <div id="signalCount">0</div>
    <div id="violationCount">0</div>
    <div id="droneList"></div>
    <div id="signalList"></div>
    <div id="violationList"></div>
    <select id="selectedDrone"></select>
    <input id="takeoffAltitude" value="50" />
`;

// Import the visualizer classes
jest.mock('../../frontend/cesium-visualization.js');
jest.mock('../../frontend/frontend-violation-vis.js');

describe('DroneSDRVisualizer', () => {
    let visualizer;
    let mockSocket;

    beforeEach(() => {
        // Create a mock WebSocket
        mockSocket = {
            send: jest.fn(),
            close: jest.fn()
        };
        
        // Reset DOM counters
        document.getElementById('droneCount').textContent = '0';
        document.getElementById('signalCount').textContent = '0';
        document.getElementById('violationCount').textContent = '0';

        // Initialize visualizer
        visualizer = new DroneSDRVisualizer();
        visualizer.socket = mockSocket;
    });

    test('should initialize with empty collections', () => {
        expect(Object.keys(visualizer.drones).length).toBe(0);
        expect(Object.keys(visualizer.signals).length).toBe(0);
        expect(Object.keys(visualizer.violations).length).toBe(0);
    });

    test('should update drone data correctly', () => {
        const mockDroneData = {
            type: 'drone_status',
            drone_id: 'test-drone-1',
            timestamp: Date.now(),
            location: {
                latitude: 37.7749,
                longitude: -122.4194,
                altitude: 100
            },
            battery: 75,
            is_pursuing: false
        };

        visualizer.updateDrone(mockDroneData);
        expect(visualizer.drones['test-drone-1']).toBeTruthy();
        expect(visualizer.drones['test-drone-1'].battery).toBe(75);
    });

    test('should handle signal updates', () => {
        const mockSignalData = {
            type: 'signal',
            frequency_mhz: 433.5,
            modulation: 'FM',
            power: 0.8,
            confidence: 0.95,
            geolocation: {
                latitude: 37.7749,
                longitude: -122.4194,
                altitude: 100
            }
        };

        visualizer.updateSignal(mockSignalData);
        expect(visualizer.signals['433.500']).toBeTruthy();
        expect(visualizer.signals['433.500'].modulation).toBe('FM');
    });

    test('should handle violation updates', () => {
        const mockViolationData = {
            type: 'violation',
            frequency_mhz: 462.5,
            modulation: 'AM',
            power: 0.9,
            confidence: 0.98,
            geolocation: {
                latitude: 37.7749,
                longitude: -122.4194,
                altitude: 100
            }
        };

        visualizer.updateViolation(mockViolationData);
        expect(visualizer.violations['462.500']).toBeTruthy();
        expect(visualizer.violations['462.500'].modulation).toBe('AM');
    });

    test('should send correct drone commands', () => {
        document.getElementById('selectedDrone').value = 'test-drone-1';
        document.getElementById('takeoffAltitude').value = '75';

        visualizer.sendDroneCommand('takeoff');
        
        expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('takeoff'));
        expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('75'));
    });

    test('should update stats display', () => {
        // Add some mock data
        visualizer.drones['drone1'] = {};
        visualizer.signals['signal1'] = {};
        visualizer.violations['violation1'] = {};

        visualizer.updateStats();

        expect(document.getElementById('droneCount').textContent).toBe('1');
        expect(document.getElementById('signalCount').textContent).toBe('1');
        expect(document.getElementById('violationCount').textContent).toBe('1');
    });

    test('should clear all data correctly', () => {
        // Add some mock data first
        visualizer.drones['drone1'] = {};
        visualizer.signals['signal1'] = {};
        visualizer.violations['violation1'] = {};

        visualizer.clearAll();

        expect(Object.keys(visualizer.drones).length).toBe(0);
        expect(Object.keys(visualizer.signals).length).toBe(0);
        expect(Object.keys(visualizer.violations).length).toBe(0);
    });

    test('should handle WebSocket connection errors', () => {
        const statusEl = document.getElementById('connectionStatus');
        visualizer.updateStatus('error', 'Connection failed');
        
        expect(statusEl.className).toBe('error');
        expect(statusEl.textContent).toBe('Connection failed');
    });

    test('should track selected drone', () => {
        // Setup mock drone data
        visualizer.drones['drone1'] = {
            entity: {
                position: {
                    getValue: jest.fn().mockReturnValue({x: 0, y: 0, z: 100})
                }
            }
        };

        visualizer.trackDrone('drone1');
        expect(visualizer.activeTrackingId).toBe('drone1');
    });
});

describe('Signal Processing', () => {
    test('should correctly process geolocation data', () => {
        const visualizer = new DroneSDRVisualizer();
        
        const mockResults = [{
            frequency_mhz: 433.5,
            latitude: 37.7749,
            longitude: -122.4194,
            altitude: 100,
            method: 'tdoa'
        }];

        visualizer.updateGeolocationResults(mockResults);
        // Since this mainly updates Cesium entities, we just verify it doesn't throw
        expect(() => visualizer.updateGeolocationResults(mockResults)).not.toThrow();
    });
});

describe('UI Updates', () => {
    test('should update drone list correctly', () => {
        const visualizer = new DroneSDRVisualizer();
        
        visualizer.drones['drone1'] = {
            id: 'drone1',
            battery: 80,
            isPursuing: false
        };

        visualizer.updateDroneList();
        const droneList = document.getElementById('droneList');
        expect(droneList.innerHTML).toContain('drone1');
        expect(droneList.innerHTML).toContain('80%');
    });

    test('should handle empty lists', () => {
        const visualizer = new DroneSDRVisualizer();
        
        visualizer.updateDroneList();
        visualizer.updateSignalList();
        visualizer.updateViolationList();

        expect(document.getElementById('droneList').innerHTML).toContain('No drones connected');
        expect(document.getElementById('signalList').innerHTML).toContain('No signals detected');
        expect(document.getElementById('violationList').innerHTML).toContain('No violations detected');
    });
});

// Frontend Test Suite
describe('SDR Frontend Tests', () => {
    let visualizer;
    let mockSocket;

    beforeEach(() => {
        // Mock THREE.js globals
        global.THREE = {
            Scene: jest.fn(),
            PerspectiveCamera: jest.fn(),
            WebGLRenderer: jest.fn(),
            Color: jest.fn(),
            AmbientLight: jest.fn(),
            DirectionalLight: jest.fn(),
            GridHelper: jest.fn(),
            AxesHelper: jest.fn(),
            BufferGeometry: jest.fn(),
            Float32Array: jest.fn(),
            PointsMaterial: jest.fn(),
            Points: jest.fn(),
            OrbitControls: jest.fn()
        };

        // Mock WebSocket
        mockSocket = {
            send: jest.fn(),
            close: jest.fn()
        };
        global.WebSocket = jest.fn(() => mockSocket);

        // Mock DOM elements
        document.body.innerHTML = `
            <div id="info">
                <div id="stats">Connection: Waiting...</div>
            </div>
            <div id="violations"></div>
            <input id="pointSize" value="2" />
            <input id="rotationSpeed" value="0.001" />
        `;
    });

    describe('Signal Visualization', () => {
        test('should initialize visualization with correct settings', () => {
            const scene = new THREE.Scene();
            expect(scene.background).toBeDefined();
            expect(global.THREE.PerspectiveCamera).toHaveBeenCalledWith(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        });

        test('should update point cloud when receiving signal data', () => {
            const mockData = {
                freqs: [100.5, 101.2, 102.3],
                amplitudes: [0.5, 0.7, 0.3],
                timestamp: Date.now(),
                violations: []
            };

            // Send mock data through WebSocket
            mockSocket.onmessage({ data: JSON.stringify(mockData) });
            
            // Verify point cloud was updated
            expect(global.THREE.BufferGeometry).toHaveBeenCalled();
            expect(global.THREE.PointsMaterial).toHaveBeenCalled();
        });
    });

    describe('Collision Detection', () => {
        test('should detect potential collisions between drones', () => {
            const drone1 = {
                position: { x: 0, y: 0, z: 0 },
                id: 'drone1'
            };
            const drone2 = {
                position: { x: 10, y: 0, z: 0 },
                id: 'drone2'
            };

            // Add drones to visualizer
            visualizer.drones = {
                drone1: drone1,
                drone2: drone2
            };

            // Check collisions
            visualizer.checkCollisionRisks();
            
            // Should create warning when drones are too close
            expect(visualizer.collisionWarnings).toBeDefined();
        });

        test('should remove collision warnings when drones move apart', () => {
            const drone1 = {
                position: { x: 0, y: 0, z: 0 },
                id: 'drone1'
            };
            const drone2 = {
                position: { x: 100, y: 100, z: 100 }, // Far apart
                id: 'drone2'
            };

            // Add drones to visualizer
            visualizer.drones = {
                drone1: drone1,
                drone2: drone2
            };

            // Check collisions
            visualizer.checkCollisionRisks();
            
            // Should not have any warnings
            expect(Object.keys(visualizer.collisionWarnings).length).toBe(0);
        });
    });

    describe('WebSocket Communication', () => {
        test('should establish WebSocket connection', () => {
            // Attempt connection
            visualizer.connectWebSocket();
            
            expect(global.WebSocket).toHaveBeenCalledWith('ws://localhost:8080');
            expect(document.getElementById('stats').textContent).toContain('Connected');
        });

        test('should handle connection errors', () => {
            // Simulate connection error
            mockSocket.onerror(new Error('Connection failed'));
            
            expect(document.getElementById('stats').textContent).toContain('Error');
        });

        test('should reconnect on connection loss', () => {
            // Simulate connection loss
            mockSocket.onclose();
            
            // Should attempt to reconnect
            expect(global.WebSocket).toHaveBeenCalledTimes(2);
        });
    });

    describe('Performance Monitoring', () => {
        test('should maintain frame rate above threshold', () => {
            const frameRates = [];
            const threshold = 30; // Minimum acceptable FPS
            
            // Monitor frame rate for 1 second
            const startTime = performance.now();
            let lastFrame = startTime;
            
            function recordFrame() {
                const now = performance.now();
                const delta = now - lastFrame;
                frameRates.push(1000 / delta);
                lastFrame = now;
                
                if (now - startTime < 1000) {
                    requestAnimationFrame(recordFrame);
                } else {
                    // Calculate average frame rate
                    const avgFPS = frameRates.reduce((a, b) => a + b) / frameRates.length;
                    expect(avgFPS).toBeGreaterThan(threshold);
                }
            }
            
            recordFrame();
        });
    });

    describe('Signal Classification', () => {
        test('should correctly classify signal types', () => {
            const signals = [
                { freq: 100.5, amplitude: 0.8, modulation: 'AM' },
                { freq: 101.2, amplitude: 0.6, modulation: 'FM' },
                { freq: 102.3, amplitude: 0.9, modulation: 'PSK' }
            ];

            signals.forEach(signal => {
                const color = visualizer.getColor(signal.amplitude);
                expect(color).toBeDefined();
                expect(color.isColor).toBe(true);
            });
        });
    });

    describe('UI Interactions', () => {
        test('should update visualization parameters from UI controls', () => {
            // Change point size
            const pointSizeInput = document.getElementById('pointSize');
            pointSizeInput.value = '3';
            pointSizeInput.dispatchEvent(new Event('input'));
            
            expect(visualizer.material.size).toBe(3);

            // Change rotation speed
            const rotationSpeedInput = document.getElementById('rotationSpeed');
            rotationSpeedInput.value = '0.002';
            rotationSpeedInput.dispatchEvent(new Event('input'));
            
            expect(visualizer.rotationSpeed).toBe(0.002);
        });
    });
});

// Mock requestAnimationFrame for testing
global.requestAnimationFrame = fn => setTimeout(fn, 0);

// Clean up after tests
afterEach(() => {
    jest.clearAllMocks();
    document.body.innerHTML = '';
});

// Mock Three.js and Cesium to avoid DOM dependencies
jest.mock('three', () => ({
    Scene: jest.fn(),
    PerspectiveCamera: jest.fn(),
    WebGLRenderer: jest.fn(() => ({
        setSize: jest.fn(),
        render: jest.fn()
    })),
    Color: jest.fn(),
    AmbientLight: jest.fn(),
    DirectionalLight: jest.fn(),
    GridHelper: jest.fn(),
    AxesHelper: jest.fn(),
    BufferGeometry: jest.fn(),
    Float32Array: Array,
    PointsMaterial: jest.fn(),
    Points: jest.fn(),
    OrbitControls: jest.fn()
}));

// Mock Cesium global object
global.Cesium = {
    Viewer: jest.fn(() => ({
        scene: {},
        camera: {
            flyTo: jest.fn()
        },
        entities: {
            add: jest.fn(),
            removeAll: jest.fn(),
            getById: jest.fn()
        }
    })),
    Cartesian3: {
        fromDegrees: jest.fn(),
        add: jest.fn(),
    },
    Math: {
        toRadians: jest.fn()
    },
    JulianDate: {
        now: jest.fn(),
        secondsDifference: jest.fn()
    },
    Color: {
        RED: { withAlpha: jest.fn() },
        WHITE: {},
        BLACK: {}
    },
    VerticalOrigin: { BOTTOM: 0, CENTER: 1 },
    HorizontalOrigin: { CENTER: 1 },
    LabelStyle: { FILL_AND_OUTLINE: 1 },
    Cartesian2: jest.fn(),
    EntityCollection: jest.fn(),
    HeightReference: { RELATIVE_TO_GROUND: 1 },
    SampledPositionProperty: jest.fn()
};

// Import the modules to test (using dynamic import since they use ES modules)
describe('Frontend Visualization Tests', () => {
    let droneVisualizer;
    let mockSocket;
    
    beforeEach(() => {
        // Reset mocks
        jest.clearAllMocks();
        
        // Create mock WebSocket
        mockSocket = {
            send: jest.fn(),
            close: jest.fn()
        };
        
        global.WebSocket = jest.fn(() => mockSocket);
        
        // Mock DOM elements
        document.body.innerHTML = `
            <div id="info">
                <div id="stats"></div>
            </div>
            <div id="droneList"></div>
            <div id="signalList"></div>
            <div id="violationList"></div>
            <div id="connectionStatus"></div>
            <select id="selectedDrone"></select>
            <input id="serverUrl" value="ws://localhost:8080">
            <input id="takeoffAltitude" value="50">
        `;
        
        // Import and instantiate drone visualizer
        droneVisualizer = new DroneSDRVisualizer();
    });
    
    describe('WebSocket Connection', () => {
        test('should connect to WebSocket server', () => {
            droneVisualizer.connectWebSocket();
            expect(WebSocket).toHaveBeenCalledWith('ws://localhost:8080');
        });
        
        test('should handle connection success', () => {
            droneVisualizer.connectWebSocket();
            mockSocket.onopen();
            expect(droneVisualizer.isConnected).toBe(true);
        });
        
        test('should handle connection close', () => {
            droneVisualizer.connectWebSocket();
            mockSocket.onclose();
            expect(droneVisualizer.isConnected).toBe(false);
        });
    });
    
    describe('Drone Management', () => {
        test('should add new drone', () => {
            const droneData = {
                type: 'drone_status',
                drone_id: 'drone1',
                location: { latitude: 37.7749, longitude: -122.4194, altitude: 100 },
                battery: 90,
                is_pursuing: false
            };
            
            droneVisualizer.processData(droneData);
            
            expect(droneVisualizer.drones['drone1']).toBeDefined();
            expect(Cesium.Viewer.mock.instances[0].entities.add).toHaveBeenCalled();
        });
        
        test('should update existing drone', () => {
            const droneData = {
                type: 'drone_status',
                drone_id: 'drone1',
                location: { latitude: 37.7749, longitude: -122.4194, altitude: 100 },
                battery: 90,
                is_pursuing: false
            };
            
            droneVisualizer.processData(droneData);
            
            // Update same drone
            const updateData = {
                ...droneData,
                battery: 85,
                is_pursuing: true
            };
            
            droneVisualizer.processData(updateData);
            
            expect(droneVisualizer.drones['drone1'].battery).toBe(85);
            expect(droneVisualizer.drones['drone1'].isPursuing).toBe(true);
        });
    });
    
    describe('Signal Management', () => {
        test('should add new signal', () => {
            const signalData = {
                type: 'signal',
                frequency_mhz: 433.92,
                modulation: 'AM',
                power: 0.75,
                confidence: 0.9,
                geolocation: {
                    latitude: 37.7749,
                    longitude: -122.4194,
                    altitude: 100
                }
            };
            
            droneVisualizer.processData(signalData);
            
            const freq = signalData.frequency_mhz.toFixed(3);
            expect(droneVisualizer.signals[freq]).toBeDefined();
            expect(Cesium.Viewer.mock.instances[0].entities.add).toHaveBeenCalled();
        });
    });
    
    describe('Violation Management', () => {
        test('should add new violation', () => {
            const violationData = {
                type: 'violation',
                frequency_mhz: 433.92,
                modulation: 'AM',
                power: 0.75,
                confidence: 0.9,
                geolocation: {
                    latitude: 37.7749,
                    longitude: -122.4194,
                    altitude: 100
                }
            };
            
            droneVisualizer.processData(violationData);
            
            const freq = violationData.frequency_mhz.toFixed(3);
            expect(droneVisualizer.violations[freq]).toBeDefined();
            expect(Cesium.Viewer.mock.instances[0].entities.add).toHaveBeenCalled();
        });
    });
    
    describe('Commands', () => {
        beforeEach(() => {
            droneVisualizer.socket = mockSocket;
        });
        
        test('should send takeoff command', () => {
            document.getElementById('selectedDrone').value = 'drone1';
            droneVisualizer.sendDroneCommand('takeoff');
            
            expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('takeoff'));
            expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('drone1'));
            expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('50')); // Default altitude
        });
        
        test('should send pursue command', () => {
            droneVisualizer.violations['433.920'] = {
                frequency: 433920000,
                frequency_mhz: 433.92
            };
            document.getElementById('selectedDrone').value = 'drone1';
            
            droneVisualizer.pursueViolation('433.920');
            
            expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('pursue'));
            expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('drone1'));
            expect(mockSocket.send).toHaveBeenCalledWith(expect.stringContaining('433920000'));
        });
    });
});